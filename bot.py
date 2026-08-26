"""Telegram send/receive for Jarvis. One responsibility: talk to Walker's
Telegram account, and no one else's.
"""

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import telegram_format

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])

# Telegram rejects messages over 4096 characters. Chunk the Markdown well under
# that: HTML tags don't count toward the limit, but the margin costs nothing.
CHUNK_LIMIT = 3500


def send_message(text, parse_mode=None):
    """Push a message to Walker outside of any reply flow. This is the path
    the scheduled morning briefing and evening debrief will call — they
    initiate contact on a timer, they don't respond to an update — so it
    must work standalone, without the polling loop running."""

    async def _send():
        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(chat_id=ALLOWED_USER_ID, text=text, parse_mode=parse_mode)

    asyncio.run(_send())


def _chunks(text):
    """Split Markdown into sendable pieces, preferring paragraph then line
    breaks. Splitting happens on the Markdown, before conversion, so a chunk
    boundary can never land inside an HTML tag or a blockquote."""
    remaining = text.strip()
    while remaining:
        if len(remaining) <= CHUNK_LIMIT:
            yield remaining
            return

        window = remaining[:CHUNK_LIMIT]
        split = max(window.rfind("\n\n"), window.rfind("\n"))
        if split <= 0:
            split = CHUNK_LIMIT
        yield remaining[:split].strip()
        remaining = remaining[split:].strip()


def send_markdown(text):
    """Send Claude's Markdown as formatted Telegram messages.

    Falls back to the unformatted text if Telegram rejects the HTML — a
    formatting bug must never cost Walker the briefing itself."""
    for chunk in _chunks(text):
        try:
            send_message(telegram_format.to_html(chunk), parse_mode=ParseMode.HTML)
        except BadRequest as e:
            print(f"Telegram rejected the formatted message ({e}); sending plain text.")
            send_message(chunk)


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
