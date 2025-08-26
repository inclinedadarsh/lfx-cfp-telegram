import os
import asyncio
import logging

from dotenv import load_dotenv, find_dotenv

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from cfp_scraper import fetch_cfp_events, fetch_event_details

load_dotenv(find_dotenv())

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome! Use /cfp to list open CFPs. Tap a button to fetch details."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "- /start: Quick intro.\n"
        "- /cfp: Show open Linux Foundation CFPs with buttons.\n"
        "- /help: This help message."
    )


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

    # Store a short-lived map of tokens to event URLs for callbacks
    token_map: dict[str, str] = {}
    keyboard_rows: list[list[InlineKeyboardButton]] = []

    # Build a concise response; Telegram has message limits, keep it compact
    lines = []
    for idx, ev in enumerate(events[:15]):  # cap to avoid overly long messages
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

        token = f"ev:{idx}"
        token_map[token] = ev.link
        keyboard_rows.append(
            [InlineKeyboardButton(text=ev.title[:60], callback_data=token)]
        )

    text = "\n\n".join(lines)
    # Save the map in chat_data scoped to this chat
    context.chat_data["cfp_token_map"] = token_map
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard_rows)
    )


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
    application.add_error_handler(on_error)

    async def on_cfp_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.callback_query:
            return
        await update.callback_query.answer()
        data = update.callback_query.data or ""
        if not data.startswith("ev:"):
            return
        token_map = context.chat_data.get("cfp_token_map", {})
        url = token_map.get(data)
        if not url:
            await update.callback_query.edit_message_text(
                "Sorry, I can't find that event anymore. Please run /cfp again."
            )
            return

        await update.callback_query.edit_message_text("Fetching event details...")
        try:
            details = await asyncio.to_thread(fetch_event_details, url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to fetch event details")
            await update.callback_query.edit_message_text(
                f"Error fetching details: {exc}"
            )
            return

        parts = []
        if details.title:
            parts.append(f"• {details.title}")
        if details.event_starts:
            parts.append(f"Starts: {details.event_starts}")
        if details.event_ends:
            parts.append(f"Ends: {details.event_ends}")
        if details.location:
            parts.append(f"Location: {details.location}")
        if details.cfp_opens:
            parts.append(f"CFP Opens: {details.cfp_opens}")
        if details.cfp_closes:
            parts.append(f"CFP Closes: {details.cfp_closes}")
        if details.cfp_timezone:
            parts.append(f"Timezone: {details.cfp_timezone}")
        if details.cfp_notifications:
            parts.append(f"Notifications: {details.cfp_notifications}")
        if details.schedule_announced:
            parts.append(f"Schedule announced: {details.schedule_announced}")

        parts.append(f"Link: {url}")
        text = "\n".join(parts)
        await update.callback_query.edit_message_text(text)

    application.add_handler(CallbackQueryHandler(on_cfp_button))

    logger.info("Bot starting with polling...")
    application.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
