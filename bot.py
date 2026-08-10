"""Telegram send/receive for Jarvis. One responsibility: talk to Walker's
Telegram account, and no one else's.
"""

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])


def send_message(text):
    """Push a message to Walker outside of any reply flow. This is the path
    the scheduled morning briefing and evening debrief will call — they
    initiate contact on a timer, they don't respond to an update — so it
    must work standalone, without the polling loop running."""

    async def _send():
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(chat_id=ALLOWED_USER_ID, text=text)

    asyncio.run(_send())


def _is_allowed(update: Update) -> bool:
    user = update.effective_user
    return user is not None and user.id == ALLOWED_USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text("Jarvis is online, sir.")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed(update):
        return
    await update.message.reply_text(update.message.text)


def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    print("Jarvis bot polling for messages...")
    application.run_polling()


if __name__ == "__main__":
    main()
