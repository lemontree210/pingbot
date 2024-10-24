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


URLS = os.environ.get("URLS")
STATUS = {"timestamp": datetime.now(), "status_codes": {url: None for url in URLS}}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.job_queue.start()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Начинаю опрос сайтов. Запросы будут отправляться каждые 10 минут, "
             "в случае ошибок напишу об этом. Используйте команду /status для проверки статуса всех сайтов. "
             "Для остановки мониторинга используйте команду /stop"
    )
    context.job_queue.run_repeating(ping, chat_id=update.effective_chat.id, interval=600, first=1)


async def ping(context: ContextTypes.DEFAULT_TYPE) -> None:

    async def ping_one(url):
        r = await client.get(url)
        STATUS["status_codes"][url] = r.status_code
        if r.status_code != 200:
            await context.bot.send_message(
                chat_id=context.job.chat_id, text=f"Статус сайта {url}: {r.status_code}"
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


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.job_queue.stop()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Опрос сайтов остановлен")


if __name__ == "__main__":
    application = ApplicationBuilder().token(os.environ.get("BOT_TOKEN")).build()

    job_queue = application.job_queue

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    status_handler = CommandHandler("status", status)
    application.add_handler(status_handler)

    stop_handler = CommandHandler("stop", stop)
    application.add_handler(stop_handler)

    application.run_polling()
