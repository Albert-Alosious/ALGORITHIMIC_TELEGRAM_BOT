from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Dict

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, MessageHandler, filters

from handlers.common import guard
from res_search import get_nse_company, search_nse_companies
from services.orders import list_order_records, save_order_record
from services.ws_client import send_event

AWAITING_STOCK_KEY = "awaiting_stock_query"


def _user_metadata(update: Update) -> dict:
    user = update.effective_user
    chat = update.effective_chat
    return {
        "user_id": user.id if user else None,
        "username": user.username if user and user.username else None,
        "chat_id": chat.id if chat else None,
    }


async def show_order_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    ctx.user_data.pop(AWAITING_STOCK_KEY, None)
    chat = update.effective_chat
    if not chat:
        return
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("New Order", callback_data="order_new")],
            [InlineKeyboardButton("LIST", callback_data="order_prev")],
            [InlineKeyboardButton("Back", callback_data="back")],
        ]
    )
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text("Order menu", reply_markup=keyboard)
            return
        except Exception:
            pass
    await ctx.bot.send_message(chat_id=chat.id, text="Order menu", reply_markup=keyboard)


async def handle_new_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    ctx.user_data.pop(AWAITING_STOCK_KEY, None)
    chat = update.effective_chat
    if not chat:
        return
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("NSE", callback_data="order_nse")],
            [InlineKeyboardButton("Back", callback_data="order")],
        ]
    )
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text("Select exchange:", reply_markup=keyboard)
            return
        except Exception:
            pass
    await ctx.bot.send_message(chat_id=chat.id, text="Select exchange:", reply_markup=keyboard)


async def handle_order_exchange(update: Update, ctx: ContextTypes.DEFAULT_TYPE, exchange: str):
    if not await guard(update):
        return
    ctx.user_data[AWAITING_STOCK_KEY] = {"exchange": exchange.upper(), "step": "stock", "results": {}, "serial": None}
    prompt = f"New {exchange.upper()} order.\nPlease enter the stock name:"
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(prompt)
            return
        except Exception:
            pass
    await update.effective_message.reply_text(prompt)


async def handle_list_prev(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    chat = update.effective_chat
    if not chat:
        return
    orders = list_order_records()
    if not orders:
        text = "No saved orders yet."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="order")]])
    else:
        buttons = []
        for row in orders[:20]:
            company = (row.get("Company", "") or "").strip()
            symbol = (row.get("Symbol", "") or "").strip()
            if company and symbol:
                label = f"{company} ({symbol})"
            elif company:
                label = company
            elif symbol:
                label = symbol
            else:
                label = f"Order #{row.get('Serial', '')}"
            buttons.append(
                [InlineKeyboardButton(label, callback_data=f"order_edit:{row.get('Serial', '')}")]
            )
        buttons.append([InlineKeyboardButton("Menu", callback_data="order")])
        keyboard = InlineKeyboardMarkup(buttons)
        text = "Select an order to update:"
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(text, reply_markup=keyboard)
            return
        except Exception:
            pass
    await ctx.bot.send_message(chat_id=chat.id, text=text, reply_markup=keyboard)


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    text = (update.effective_message.text or "").strip()
    if text.lower() == "cmd":
        from handlers.ui import show_panel

        await show_panel(update, ctx)
        return
    state = ctx.user_data.get(AWAITING_STOCK_KEY)
    if not state:
        return
    stage = state.get("step")
    exchange = state.get("exchange", "").upper()
    if stage == "stock":
        if exchange == "NSE":
            results = search_nse_companies(text, limit=8)
            entries = []
            for item in results:
                symbol = str(item.get("symbol", "")).strip()
                name = str(item.get("name", "")).strip()
                if not symbol or not name:
                    continue
                entries.append((symbol, name))
            if not entries:
                await update.effective_message.reply_text("No NSE matches found. Try another name.")
                return
            state["results"] = {symbol: {"symbol": symbol, "name": name} for symbol, name in entries}
            buttons = [
                [InlineKeyboardButton(name, callback_data=f"sel_nse:{symbol}")]
                for symbol, name in entries
            ]
            buttons.append([InlineKeyboardButton("Back", callback_data="order_new")])
            buttons.append([InlineKeyboardButton("Menu", callback_data="order")])
            await update.effective_message.reply_text(
                "Select a company from the NSE list:", reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        await update.effective_message.reply_text(f"{exchange} search is not available.")
        ctx.user_data.pop(AWAITING_STOCK_KEY, None)
        return
    if stage == "quantity":
        try:
            qty = int(text)
            if qty <= 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text("Quantity must be a positive integer. Try again.")
            return
        state["quantity"] = qty
        state["step"] = "max_profit"
        await update.effective_message.reply_text(
            f"Quantity recorded: {qty}. What is your target profit (INR)?"
        )
        return
    if stage == "max_profit":
        try:
            max_profit = float(text)
            if max_profit < 0:
                raise ValueError
        except ValueError:
            await update.effective_message.reply_text(
                "Target profit must be a non-negative number in INR. Try again."
            )
            return
        state["max_profit"] = max_profit
        state["step"] = "min_profit"
        await update.effective_message.reply_text(
            "Understood. What is your minimum acceptable profit (INR)?"
        )
        return
    if stage == "min_profit":
        try:
            min_profit = float(text)
        except ValueError:
            await update.effective_message.reply_text("Please enter a numeric minimum profit amount in INR.")
            return
        state["min_profit"] = min_profit
        symbol = state.get("symbol", "")
        name = state.get("company", "")
        qty = state.get("quantity")
        max_profit = state.get("max_profit")
        min_profit_val = state.get("min_profit")
        save_error: str | None = None
        serial_value = state.get("serial")
        try:
            serial_int = int(serial_value) if serial_value is not None else None
        except (TypeError, ValueError):
            serial_int = None
        record_serial = None
        try:
            record_serial = save_order_record(
                symbol=str(symbol),
                company=str(name),
                quantity=int(qty) if qty is not None else 0,
                min_profit=float(min_profit_val),
                max_profit=float(max_profit),
                serial=serial_int,
            )
        except Exception as exc:
            save_error = str(exc)
        ctx.user_data.pop(AWAITING_STOCK_KEY, None)
        max_profit_fmt = f"{float(max_profit):.2f}" if isinstance(max_profit, (int, float)) else str(max_profit)
        min_profit_fmt = (
            f"{float(min_profit_val):.2f}" if isinstance(min_profit_val, (int, float)) else str(min_profit_val)
        )
        message = (
            f"Order captured:\n"
            f"Exchange: {state.get('exchange', 'NSE')}\n"
            f"Company: {name} ({symbol})\n"
            f"Quantity: {qty}\n"
            f"Target profit: {max_profit_fmt} INR\n"
            f"Minimum profit: {min_profit_fmt} INR"
        )
        if record_serial is not None:
            message = f"Order #{record_serial} saved.\n" + message
        if save_error:
            message += f"\nWarning: failed to record order: {save_error}"
        else:
            event_payload = {
                "serial": record_serial,
                "symbol": str(symbol),
                "company": str(name),
                "quantity": int(qty) if qty is not None else 0,
                "min_profit_inr": float(min_profit_val),
                "max_profit_inr": float(max_profit),
                "exchange": state.get("exchange", "NSE"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **_user_metadata(update),
            }
            try:
                await send_event("order.saved", event_payload)
            except Exception as exc:
                logging.exception("Failed to forward order to trader engine: %s", exc)
                message += "\nWarning: failed to notify trader engine."
        await update.effective_message.reply_text(message)


async def handle_nse_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE, symbol: str):
    if not await guard(update):
        return
    state = ctx.user_data.get(AWAITING_STOCK_KEY) or {}
    cache = state.get("results", {}) if isinstance(state, dict) else {}
    company = cache.get(symbol)
    if not company:
        company = get_nse_company(symbol)
    if company:
        ctx.user_data[AWAITING_STOCK_KEY] = {
            "exchange": "NSE",
            "step": "quantity",
            "symbol": company["symbol"],
            "company": company["name"],
            "serial": state.get("serial"),
        }
        text = f"Selected NSE company: {company['name']} ({company['symbol']}).\nPlease enter the quantity:"
    else:
        ctx.user_data.pop(AWAITING_STOCK_KEY, None)
        text = f"No NSE company found for symbol {symbol}."
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(text)
            return
        except Exception:
            pass
        await ctx.bot.send_message(chat_id=query.message.chat_id, text=text)
    else:
        await update.effective_message.reply_text(text)


async def handle_order_edit_selection(update: Update, ctx: ContextTypes.DEFAULT_TYPE, serial: str):
    if not await guard(update):
        return
    orders = list_order_records()
    target = next((row for row in orders if row.get("Serial") == str(serial)), None)
    if not target:
        message = "Selected order was not found."
        query = update.callback_query
        if query and query.message:
            await query.message.reply_text(message)
        else:
            await update.effective_message.reply_text(message)
        return
    company = target.get("Company", "")
    symbol = target.get("Symbol", "")
    quantity = target.get("Quantity", "")
    try:
        serial_int = int(target.get("Serial", "") or 0)
    except ValueError:
        serial_int = None
    ctx.user_data[AWAITING_STOCK_KEY] = {
        "exchange": "NSE",
        "step": "quantity",
        "symbol": symbol,
        "company": company,
        "serial": serial_int,
    }
    prompt = (
        f"Editing order #{target.get('Serial')} for {company} ({symbol}).\n"
        f"Current quantity: {quantity}\nEnter new quantity:"
    )
    query = update.callback_query
    if query and query.message:
        try:
            await query.edit_message_text(prompt)
            return
        except Exception:
            pass
        await ctx.bot.send_message(chat_id=query.message.chat_id, text=prompt)
    else:
        await update.effective_message.reply_text(prompt)


def register_order_handlers(app) -> None:
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


ORDER_CALLBACKS: Dict[str, Callable] = {
    "order": show_order_panel,
    "order_new": handle_new_order,
    "order_prev": handle_list_prev,
    "order_nse": lambda update, ctx: handle_order_exchange(update, ctx, "NSE"),
}


SPECIAL_CALLBACKS: Dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE, str], None]] = {
    "sel_nse:": handle_nse_selection,
    "order_edit:": handle_order_edit_selection,
}
