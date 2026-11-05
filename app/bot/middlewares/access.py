"""Access middleware for normal users:
- Maintenance mode (bot off)
- Banned users
- Forced channel join gate
Admins bypass everything.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.bot.filters import is_admin_id
from app.services import settings_service
from app.utils.formatters import user_display_name

logger = logging.getLogger(__name__)

MAINTENANCE_TEXT = (
    "⚠️ ربات موقتاً در حال بروزرسانی است.\nبعداً دوباره تلاش کنید."
)
BANNED_TEXT = "⛔️ دسترسی شما به ربات مسدود شده است."
FORCE_JOIN_TEXT = "کاربر گرامی برای استفاده از ربات لطفاً در کانال زیر عضو شوید."


def _is_start(msg: Message) -> bool:
    return bool(msg.text) and msg.text.startswith("/start")


async def _check_member(bot, channel: str, telegram_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=telegram_id)
        return member.status not in ("left", "kicked")
    except Exception as e:  # noqa: BLE001
        logger.warning("Force-join check failed: %s", type(e).__name__)
        # اگر ربات ادمین کانال نباشد بررسی ممکن نیست؛ بلاک نکنیم ولی هشدار بده
        return True


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        session = data.get("session")
        bot = data.get("bot")
        if session is None or bot is None:
            return await handler(event, data)

        if isinstance(event, Message):
            user = event.from_user
            tg_id = user.id
            chat_type = event.chat.type
            display_name = user.first_name
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            tg_id = user.id
            chat_type = "private"
            display_name = user.first_name
        else:
            return await handler(event, data)

        if chat_type != "private" or is_admin_id(tg_id):
            return await handler(event, data)

        # 1) Maintenance
        if not await settings_service.get_bool(session, "bot_enabled"):
            if isinstance(event, Message):
                await event.answer(MAINTENANCE_TEXT)
            else:
                try:
                    await event.answer("⚠️ ربات در حال بروزرسانی است.", show_alert=True)
                except Exception:  # noqa: BLE001
                    pass
            return None

        # 2) Banned
        from app.services.user_service import get_by_telegram_id

        db_user = await get_by_telegram_id(session, tg_id)
        if db_user is not None and db_user.status == "BANNED":
            if isinstance(event, Message):
                await event.answer(BANNED_TEXT)
            else:
                try:
                    await event.answer("⛔️ دسترسی مسدود شده است.", show_alert=True)
                except Exception:  # noqa: BLE001
                    pass
            return None

        # 3) Forced join (فقط برای شروع/دکمه‌ها؛ خود /start هم گیت را نشان می‌دهد)
        if await settings_service.get_bool(session, "force_join_enabled"):
            channel = await settings_service.get_setting(session, "force_join_channel")
            if channel:
                allowed_callback = isinstance(event, CallbackQuery) and (
                    event.data in ("fj:check", "main:menu", "noop")
                )
                if not allowed_callback and not (isinstance(event, Message) and _is_start(event)):
                    ok = await _check_member(bot, channel, tg_id)
                    if not ok:
                        from app.bot.keyboards.inline import force_join_kb

                        url = await settings_service.get_setting(session, "force_join_url")
                        if not url:
                            url = f"https://t.me/{channel.lstrip('@')}"
                        text = FORCE_JOIN_TEXT + f"\n\n👤 {user_display_name(display_name, tg_id)}"
                        if isinstance(event, Message):
                            await event.answer(text, reply_markup=force_join_kb(url))
                        else:
                            try:
                                await event.message.answer(text, reply_markup=force_join_kb(url))
                                await event.answer()
                            except Exception:  # noqa: BLE001
                                pass
                        return None

        return await handler(event, data)
