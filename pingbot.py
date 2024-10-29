import asyncio
import os

from datetime import datetime

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


URLS = os.environ.get("URLS").split(", ")
STATUS = {"timestamp": datetime.now(), "status_codes": {url: None for url in URLS}}


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
    status_codes = "\n".join(sorted(f"{url}: {STATUS['status_codes'][url]}" for url in STATUS['status_codes']))

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Дата и время последнего запроса: {STATUS['timestamp']}\n\nСтатусы:\n{status_codes}",
        disable_web_page_preview=True,
    )


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["subscribers"].add(update.effective_chat.id)

    text = f"В этот чат будут отправляться уведомления о статусе ссылок:\n"
    for url in URLS:
        text = f"{text}\n{url}"

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text,
        disable_web_page_preview=True,
    )


async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot_data["subscribers"].remove(update.effective_chat.id)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="В этот чат больше не будут отправляться уведомления о статусе ссылок",
        disable_web_page_preview=True,
    )


if __name__ == "__main__":
    application = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()
    application.bot_data["subscribers"] = set()
    application.job_queue.run_repeating(ping, interval=600, first=1)

    status_handler = CommandHandler("status", status)
    application.add_handler(status_handler)

    subscribe_handler = CommandHandler("subscribe", subscribe)
    application.add_handler(subscribe_handler)

    unsubscribe_handler = CommandHandler("unsubscribe", unsubscribe)
    application.add_handler(unsubscribe_handler)

    application.run_polling()
