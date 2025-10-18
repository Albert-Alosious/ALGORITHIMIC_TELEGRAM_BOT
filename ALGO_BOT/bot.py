from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import suppress

from telegram.ext import Application

from config import TOKEN
from handlers.orders import register_order_handlers
from handlers.system import register_system_handlers
from handlers.ui import register_ui_handlers
from services.ws_client import close_ws_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def _exit_listener(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
        except Exception:
            logging.info("Exit listener encountered an error; shutting down.")
            stop_event.set()
            return
        if not line:
            continue
        if line.strip().lower() == "exit":
            logging.info("Exit command received. Terminating bot.")
            stop_event.set()
            return


async def main() -> None:
    if not TOKEN:
        raise RuntimeError("TG_TOKEN is not set. Export it or place it in .env before starting the bot.")

    app = Application.builder().token(TOKEN).build()

    register_system_handlers(app)
    register_order_handlers(app)
    register_ui_handlers(app)

    stop_event = asyncio.Event()
    listener_task = asyncio.create_task(_exit_listener(stop_event))

    await app.initialize()
    try:
        await app.start()
        if app.updater:
            await app.updater.start_polling()
        logging.info("Bot running. Type 'exit' in this terminal to stop.")
        await stop_event.wait()
        logging.info("Exit signal received. Shutting down bot.")
    finally:
        if app.updater:
            await app.updater.stop()
        await app.stop()
        await app.shutdown()
        stop_event.set()
        listener_task.cancel()
        with suppress(asyncio.CancelledError):
            await listener_task
        await close_ws_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received. Shutting down.")
