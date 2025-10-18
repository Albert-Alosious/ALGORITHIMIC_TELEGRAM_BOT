from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from config import APP_CMD, WORKDIR
from handlers.common import guard
from services.ws_client import send_event

_logger = logging.getLogger(__name__)


def _user_metadata(update: Update) -> dict:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "user_id": user.id if user else None,
        "username": user.username if user and user.username else None,
        "chat_id": chat.id if chat else None,
    }


async def _send(update: Update, event_type: str, payload: dict, success_msg: str, error_msg: str) -> None:
    try:
        await send_event(event_type, payload)
        await update.effective_message.reply_text(success_msg)
    except Exception as exc:  # pragma: no cover - network failure path
        _logger.exception("Failed to send event %s: %s", event_type, exc)
        await update.effective_message.reply_text(error_msg)


async def startapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    payload = {"workdir": str(WORKDIR), "cmd": APP_CMD, **_user_metadata(update)}
    await _send(
        update,
        "app.start.command",
        payload,
        "Start command sent to trader engine.",
        "Failed to reach trader engine.",
    )


async def stopapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await _send(
        update,
        "app.stop.command",
        _user_metadata(update),
        "Stop command sent to trader engine.",
        "Failed to reach trader engine.",
    )


async def killapp(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    payload = {"force": True, **_user_metadata(update)}
    await _send(
        update,
        "app.close.command",
        payload,
        "Close command sent to trader engine.",
        "Failed to reach trader engine.",
    )


async def status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await _send(
        update,
        "app.status.command",
        _user_metadata(update),
        "Status request forwarded to trader engine.",
        "Failed to reach trader engine.",
    )


async def tail(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    lines = 50
    if ctx.args:
        try:
            lines = int(ctx.args[0])
        except ValueError:
            pass
    payload = {"lines": lines, **_user_metadata(update)}
    await _send(
        update,
        "app.logs.command",
        payload,
        "Log request forwarded to trader engine.",
        "Failed to reach trader engine.",
    )


async def fetch(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    payload = {"lines": 100, **_user_metadata(update)}
    await _send(
        update,
        "app.logs.command",
        payload,
        "Fetch request forwarded to trader engine.",
        "Failed to reach trader engine.",
    )


async def mon_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await _send(
        update,
        "app.monitor.command",
        _user_metadata(update),
        "Monitor request forwarded to trader engine.",
        "Failed to reach trader engine.",
    )


async def whoami(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.effective_message.reply_text(
        f"Your Telegram user id: `{update.effective_user.id}`",
        parse_mode="Markdown",
    )


def register_system_handlers(app) -> None:
    app.add_handler(CommandHandler("startapp", startapp))
    app.add_handler(CommandHandler("stopapp", stopapp))
    app.add_handler(CommandHandler("killapp", killapp))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("tail", tail))
    app.add_handler(CommandHandler("fetch", fetch))
    app.add_handler(CommandHandler("moninfo", mon_info))
    app.add_handler(CommandHandler("whoami", whoami))


SYSTEM_CALLBACKS = {
    "start": startapp,
    "stop": stopapp,
    "kill": killapp,
    "status": status,
    "tail": tail,
    "fetch": fetch,
    "mon": mon_info,
    "log": tail,
}
