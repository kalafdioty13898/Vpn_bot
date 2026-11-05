"""Notification service — همه پیام‌های مهم از اینجا ارسال می‌شوند."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_admin_ids: list[int] = []


def setup(bot: Bot, admin_ids: list[int]) -> None:
    global _bot, _admin_ids
    _bot = bot
    _admin_ids = admin_ids


def _get_bot() -> Bot | None:
    return _bot


async def send_safe(bot: Bot, chat_id: int, text: str, **kwargs) -> bool:
    """ارسال با مدیریت خطا و rate-limit؛ خروجی: موفق/ناموفق."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        try:
            await bot.send_message(chat_id, text, **kwargs)
            return True
        except TelegramAPIError:
            return False
    except TelegramAPIError as e:
        logger.warning("Send failed to %s: %s", chat_id, type(e).__name__)
        return False


async def notify(target: str, text: str, user_id: int | None = None, **kwargs) -> None:
    """target: 'user' | 'admin' | event names (payment_rejected, provision_failed, ...)"""
    bot = _get_bot()
    if bot is None:
        logger.warning("Notification service not ready: %s", text[:50])
        return

    if target == "user":
        if user_id is None:
            return
        await send_safe(bot, user_id, text, **kwargs)
    elif target == "admin":
        for admin_id in _admin_ids:
            await send_safe(bot, admin_id, text, **kwargs)
    else:
        # رویدادها: هم ادمین هم کاربر مربوطه اگر مشخص باشد
        if user_id is not None:
            await send_safe(bot, user_id, text, **kwargs)


async def notify_admin(text: str, **kwargs) -> None:
    await notify("admin", text, **kwargs)


async def broadcast(bot: Bot, user_ids: list[int], send_fn) -> tuple[int, int]:
    """ارسال همگانی با کنترل نرخ. send_fn(chat_id) -> bool"""
    ok = fail = 0
    for uid in user_ids:
        try:
            success = await send_fn(uid)
        except Exception:  # noqa: BLE001
            success = False
        if success:
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail
