"""
main.py

Telegram bot entry point.
Registers all handlers and starts polling.

Usage:
    python main.py

Environment:
    Copy .env.example to .env and fill in your values.
"""

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Load environment variables from .env
load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ── Ensure output dirs exist ──────────────────────────────────────────────────
Path(os.getenv("OUTPUT_IMAGES_DIR", "output/images")).mkdir(parents=True, exist_ok=True)
Path(os.getenv("OUTPUT_VIDEOS_DIR", "output/videos")).mkdir(parents=True, exist_ok=True)
Path("auth").mkdir(exist_ok=True)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    # Import handlers here (after env is loaded)
    from handlers.conversation import (
        build_conversation_handler,
        button_callback,
        help_command,
        status_command,
        resume_command,
    )

    # Build the Application
    app = (
        Application.builder()
        .token(token)
        .build()
    )

    # ── Register handlers ─────────────────────────────────────────────────────
    app.add_handler(build_conversation_handler())
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    logger.info("🎬 Storyboard Bot starting...")
    logger.info("LLM provider: %s / model: %s", os.getenv("LLM_PROVIDER", "anthropic"), os.getenv("LLM_MODEL", "claude-sonnet-4-5"))
    logger.info("Image tool: %s", os.getenv("IMAGE_GEN_TOOL", "manual"))
    logger.info("Video tool: %s", os.getenv("VIDEO_GEN_TOOL", "manual"))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()