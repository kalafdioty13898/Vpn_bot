"""Mock panel adapter — کاملاً کار می‌کند برای تست؛ کانفیگ نمونه تولید می‌کند.

وقتی PANEL_MODE=mock باشد (پیش‌فرض)، بات بدون پنل واقعی هم کامل بالا می‌آید
و همه فلوها (خرید/تأیید/ساخت کانفیگ) قابل تست هستند.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from app.vpn.base import PanelUser, VpnPanelAdapter


class MockPanelAdapter(VpnPanelAdapter):
    mode = "mock"

    def __init__(self, cfg: dict[str, str]) -> None:
        self.cfg = cfg

    async def check_connection(self) -> str:
        return "✅ حالت Mock فعال است (پنل واقعی وصل نیست، کانفیگ آزمایشی ساخته می‌شود)."

    async def create_user(self, username: str, volume_gb: float, days: int) -> PanelUser:
        token = secrets.token_hex(12)
        expires = datetime.utcnow() + timedelta(days=days)
        sub_url = f"https://mock-panel.local/sub/{username}-{token}"
        return PanelUser(
            username=username,
            subscription_url=sub_url,
            expires_at=expires.strftime("%Y-%m-%d"),
            total_gb=volume_gb,
            status="ACTIVE",
            raw={"mode": "mock"},
        )

    async def delete_user(self, username: str) -> bool:
        return True

    async def get_user(self, username: str) -> PanelUser | None:
        return PanelUser(username=username, subscription_url="https://mock-panel.local/sub/" + username)

    async def generate_subscription(self, username: str) -> str:
        token = secrets.token_hex(8)
        return f"https://mock-panel.local/sub/{username}-{token}"

    async def reset_usage(self, username: str) -> bool:
        return True

    async def enable_user(self, username: str) -> bool:
        return True

    async def disable_user(self, username: str) -> bool:
        return True


def build_mock_config_text(username: str, sub_url: str) -> str:
    uuid = secrets.token_hex(16)
    vless = (
        f"vless://{uuid}@mock-panel.local:443?encryption=none&security=tls"
        f"&sni=mock-panel.local&type=ws&path=%2F{username}#VPN-{username}"
    )
    return vless, sub_url
