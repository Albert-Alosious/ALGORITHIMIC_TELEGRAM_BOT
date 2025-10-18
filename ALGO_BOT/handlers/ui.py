from __future__ import annotations

import asyncio
import logging
import time

from datetime import datetime

import httpx

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.common import guard
from handlers.orders import ORDER_CALLBACKS, SPECIAL_CALLBACKS, AWAITING_STOCK_KEY
from handlers.system import SYSTEM_CALLBACKS
from services.ws_client import send_event

_logger = logging.getLogger(__name__)


def _control_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("APP", callback_data="app"),
                InlineKeyboardButton("CLEAR", callback_data="clear"),
            ],
            [
                InlineKeyboardButton("ORDER", callback_data="order"),
            ],
        ]
    )


async def show_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    chat = update.effective_chat
    if not chat:
        return
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text("Control panel", reply_markup=_control_keyboard())
            return
        except Exception:
            pass
    await ctx.bot.send_message(chat_id=chat.id, text="Control panel", reply_markup=_control_keyboard())

async def show_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    help_text = (
        "Commands available:\n"
        "- APP ▸ OPEN/START/STOP/CLOSE control the managed app.\n"
        "- ORDER lets you create or edit stored orders.\n"
        "- CLEAR removes recent bot messages.\n"
        "Use the buttons or send 'cmd' to reopen this menu."
    )
    await update.effective_message.reply_text(help_text)


async def show_app_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("OPEN", callback_data="open"),
                InlineKeyboardButton("START", callback_data="start"),
                InlineKeyboardButton("STOP", callback_data="stop"),
                InlineKeyboardButton("CLOSE", callback_data="kill"),
            ],
            [InlineKeyboardButton("LIVE", callback_data="live")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
    )
    query = update.callback_query
    chat = update.effective_chat
    if not chat:
        return
    if query and query.message:
        try:
            await query.edit_message_text("App controls:", reply_markup=keyboard)
            return
        except Exception:
            pass
    await ctx.bot.send_message(chat_id=chat.id, text="App controls:", reply_markup=keyboard)


async def handle_open(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    from config import WORKDIR

    await update.effective_message.reply_text(
        f"The managed application lives at:\n{WORKDIR}\n"
        "Use START to launch it or CLOSE to stop it."
    )
    try:
        await send_event("app.open", {"workdir": str(WORKDIR), **_user_metadata(update)})
    except Exception as exc:
        _logger.exception("Failed to notify trader about app.open: %s", exc)


async def handle_live_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    placeholder = await update.effective_message.reply_text("Running live status check…")
    try:
        lines = await _collect_live_status()
        await placeholder.edit_text("\n".join(lines))
    except Exception as exc:  # pragma: no cover - defensive
        _logger.exception("Live status check failed: %s", exc)
        await placeholder.edit_text("Live status check failed. Please try again later.")


def _user_metadata(update: Update) -> dict:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "user_id": user.id if user else None,
        "username": user.username if user and user.username else None,
        "chat_id": chat.id if chat else None,
    }


async def clear_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    ctx.user_data.pop(AWAITING_STOCK_KEY, None)
    chat = update.effective_chat
    if not chat:
        return
    message = update.effective_message
    last_id = message.message_id if message else None
    if last_id:
        lowest = max(last_id - 50, 0)
        for mid in range(last_id, lowest, -1):
            try:
                await ctx.bot.delete_message(chat_id=chat.id, message_id=mid)
            except Exception:
                continue
    await show_panel(update, ctx)


async def _collect_live_status() -> list[str]:
    lines = ["Live status (5 samples, 1s apart):"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        for attempt in range(5):
            timestamp = datetime.now().strftime("%H:%M:%S")
            trader_status = await _ping_endpoint(client, "http://localhost:8000/health")
            groww_status = await _ping_endpoint(client, "https://groww.in")
            lines.append(
                f"{timestamp} | trader: {trader_status} | groww.in: {groww_status}"
            )
            if attempt < 4:
                await asyncio.sleep(1)
    return lines


async def _ping_endpoint(client: httpx.AsyncClient, url: str) -> str:
    start = time.perf_counter()
    try:
        response = await client.get(url)
        duration_ms = (time.perf_counter() - start) * 1000
        return f"OK {response.status_code} ({duration_ms:.0f} ms)"
    except Exception as exc:
        return f"ERR {type(exc).__name__}"


BUTTON_ACTIONS = {
    **SYSTEM_CALLBACKS,
    **ORDER_CALLBACKS,
    "app": show_app_menu,
    "clear": clear_panel,
    "open": handle_open,
    "live": handle_live_status,
    "help": show_help,
    "back": show_panel,
}


async def handle_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    action = query.data if query else None
    if not action:
        return
    for prefix, handler in SPECIAL_CALLBACKS.items():
        if action.startswith(prefix):
            await handler(update, ctx, action[len(prefix) :])
            return
    callback = BUTTON_ACTIONS.get(action)
    if not callback:
        if query and query.message:
            await query.message.reply_text("Unknown action.")
        return
    await callback(update, ctx)


def register_ui_handlers(app) -> None:
    app.add_handler(CommandHandler("start", show_panel))
    app.add_handler(CommandHandler("panel", show_panel))
    app.add_handler(CommandHandler("app", show_app_menu))
    app.add_handler(CommandHandler("open", handle_open))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(CallbackQueryHandler(handle_button))
