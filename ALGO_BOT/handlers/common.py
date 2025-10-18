from __future__ import annotations

from typing import Iterable

from telegram import Update

from config import ALLOWED_USER_IDS


def auth_check(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USER_IDS)


async def guard(update: Update) -> bool:
    if auth_check(update):
        return True
    message = update.effective_message
    if message:
        await message.reply_text("Not authorized.")
    return False
