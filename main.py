import os
import asyncio
import logging

from dotenv import load_dotenv, find_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from cfp_scraper import fetch_cfp_events

load_dotenv(find_dotenv())

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I am alive. Send me any message and I'll echo it back."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands: /start, /help. I also echo your text."
    )


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message and update.message.text:
        await update.message.reply_text(update.message.text)


async def cfp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_text("Fetching open CFPs... This may take a moment.")
    try:
        events = await asyncio.to_thread(fetch_cfp_events)
    except Exception as exc:  # noqa: BLE001 broad to surface to user
        logger.exception("Failed to fetch CFP events")
        await update.message.reply_text(f"Error fetching CFPs: {exc}")
        return

    if not events:
        await update.message.reply_text("No open CFPs found.")
        return

    # Build a concise response; Telegram has message limits, keep it compact
    lines = []
    for ev in events[:15]:  # cap to avoid overly long messages
        parts = [f"• {ev.title}"]
        if ev.date:
            parts.append(f"Date: {ev.date}")
        if ev.location:
            parts.append(f"Location: {ev.location}")
        if ev.event_type:
            parts.append(f"Type: {ev.event_type}")
        if ev.status:
            parts.append(f"Status: {ev.status}")
        parts.append(f"Link: {ev.link}")
        lines.append(" | ".join(parts))

    text = "\n\n".join(lines)
    await update.message.reply_text(text)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update: %s", update)


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

    application: Application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cfp", cfp))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    application.add_error_handler(on_error)

    logger.info("Bot starting with polling...")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
