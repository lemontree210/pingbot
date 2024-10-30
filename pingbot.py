import asyncio
import os

from datetime import datetime
from functools import partial

import httpx
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)

load_dotenv()


# no conversion to int here, because otherwise membership check won't work
ACCEPTED_CHAT_IDS = {chat_id for chat_id in os.environ.get("ACCEPTED_CHAT_IDS").split(", ")}
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID")
URLS = os.environ.get("URLS").split(", ")
STATUS = {"timestamp": datetime.now(), "status_codes": {url: None for url in URLS}}


async def alert_owner(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    await context.bot.send_message(
        chat_id=OWNER_CHAT_ID,
        text=text
    )


async def ping(context: ContextTypes.DEFAULT_TYPE) -> None:

    async def ping_one(url):
        r = await client.get(url)
        STATUS["status_codes"][url] = r.status_code

        if r.status_code != 200:
            for chat_id in context.bot_data["subscribers"]:
                await context.bot.send_message(
                    chat_id=chat_id, text=f"⚠ Статус сайта {url}: {r.status_code}"
                )

    # verify=False because httpx won't accept self-signed certificate
    # (Let's Encrypt is apparently one)
    async with httpx.AsyncClient(verify=False) as client:
        coroutines = [ping_one(url) for url in URLS]
        await asyncio.gather(*coroutines)

    STATUS["timestamp"] = datetime.now()


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if chat_id not in ACCEPTED_CHAT_IDS:
        text_for_user = (
            f"Вы не можете получать сообщения о статусе. "
            f"Сообщите ID чата {chat_id} администратору."
        )
    else:
        status_codes = "\n".join(
            sorted(f"{url}: {STATUS['status_codes'][url]}" for url in STATUS['status_codes'])
        )
        text_for_user = (
            f"Дата и время последнего запроса: {STATUS['timestamp']}\n\n"
            f"Статусы:\n{status_codes}"
        )

    await context.bot.send_message(chat_id=chat_id, text=text_for_user)


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

    chat_id = update.effective_chat.id
    username = update.effective_user.username

    text_for_owner = (
        f"Пользователь {update.effective_user.name} ({username=}, {chat_id=}) "
        "хочет подписаться на уведомления: "
    )

    if chat_id in ACCEPTED_CHAT_IDS:
        context.bot_data["subscribers"].add(chat_id)

        text_for_owner += "✅"
        text_for_user = "Я буду отправлять сюда уведомления, если сломается любая из ссылок:\n"
        for url in URLS:
            text_for_user = f"{text_for_user}\n{url}"
    else:
        text_for_owner += "❌"
        text_for_user = f"Вы пока не можете подписаться. Сообщите ID чата {chat_id} администратору."

    await alert_owner(context=context, text=text_for_owner)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_for_user)


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "В этот чат больше не будут отправляться уведомления о статусе ссылок"
    try:
        context.bot_data["subscribers"].remove(update.effective_chat.id)
    except KeyError:
        text = "Вы не были подписаны на уведомления"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        disable_web_page_preview=True,
    )


if __name__ == '__main__':
    application = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()
    application.bot_data["subscribers"] = set()

    alert_about_start = partial(alert_owner, text=f"Бот запущен {datetime.now()}")
    application.job_queue.run_once(alert_about_start, when=0, name="alert_owner")

    application.job_queue.run_repeating(ping, interval=600, first=15)

    status_handler = CommandHandler("status", status)
    application.add_handler(status_handler)

    subscribe_handler = CommandHandler("subscribe", subscribe)
    application.add_handler(subscribe_handler)

    unsubscribe_handler = CommandHandler("unsubscribe", unsubscribe)
    application.add_handler(unsubscribe_handler)

    application.run_polling()
