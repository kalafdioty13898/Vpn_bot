"""Anti-spam / throttle middleware."""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.filters import is_admin_id


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, interval: float = 0.6) -> None:
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user is None or user.is_bot or is_admin_id(user.id):
            return await handler(event, data)

        now = time.monotonic()
        last = self._last.get(user.id, 0.0)
        if now - last < self.interval:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("⏳ آهسته‌تر!", show_alert=False)
                except Exception:  # noqa: BLE001
                    pass
            return None  # drop
        self._last[user.id] = now
        return await handler(event, data)
