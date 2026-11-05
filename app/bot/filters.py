"""Filters: IsAdmin (env ADMIN_IDS + DB admins cache)."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery, TelegramObject

from app.config import settings

# ادمین‌های دیتابیسی (به‌جز env) در حافظه کش می‌شوند
db_admins: set[int] = set()


def register_admin(telegram_id: int) -> None:
    db_admins.add(telegram_id)


def unregister_admin(telegram_id: int) -> None:
    db_admins.discard(telegram_id)


def is_admin_id(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids or telegram_id in db_admins


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        if user is None:
            event_obj = getattr(event, "message", None) or getattr(event, "callback_query", None)
            user = getattr(event_obj, "from_user", None) if event_obj else None
        if user is None:
            return False
        return is_admin_id(user.id)
