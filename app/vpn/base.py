"""Abstract VPN panel adapter + factory.

تمام ارتباط با پنل VPN فقط از طریق این Interface انجام می‌شود.
اگر بعداً پنل دیگری اضافه شد، فقط Adapter جدید بسازید و در get_adapter ثبت کنید.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class PanelError(Exception):
    """خطای ارتباط با پنل VPN."""


@dataclass
class PanelUser:
    username: str
    subscription_url: str
    expires_at: str | None = None
    used_gb: float = 0.0
    total_gb: float = 0.0
    status: str = "ACTIVE"
    raw: dict = field(default_factory=dict)


class VpnPanelAdapter(ABC):
    mode: str = "base"

    @abstractmethod
    async def check_connection(self) -> str:
        """تست اتصال؛ در صورت خطا PanelError برمی‌گرداند. در موفقیت پیام برمی‌گرداند."""

    @abstractmethod
    async def create_user(self, username: str, volume_gb: float, days: int) -> PanelUser:
        """ساخت کاربر/کانفیگ جدید روی پنل."""

    @abstractmethod
    async def delete_user(self, username: str) -> bool: ...

    @abstractmethod
    async def get_user(self, username: str) -> PanelUser | None: ...

    @abstractmethod
    async def generate_subscription(self, username: str) -> str:
        """لینک اشتراک کاربر."""

    async def enable_user(self, username: str) -> bool:
        raise PanelError("این پنل از این عملیات پشتیبانی نمی‌کند")

    async def disable_user(self, username: str) -> bool:
        raise PanelError("این پنل از این عملیات پشتیبانی نمی‌کند")

    async def reset_usage(self, username: str) -> bool:
        raise PanelError("این پنل از این عملیات پشتیبانی نمی‌کند")


def get_adapter(session_settings: dict[str, str]) -> VpnPanelAdapter:
    """ساخت Adapter بر اساس تنظیمات دیتابیس (که ادمین از پنل تغییر می‌دهد)."""
    from app.vpn.mock_panel import MockPanelAdapter
    from app.vpn.pasargad import PasargadPanelAdapter

    mode = (session_settings.get("panel_mode") or "mock").lower()
    if mode == "pasargad":
        return PasargadPanelAdapter(session_settings)
    return MockPanelAdapter(session_settings)
