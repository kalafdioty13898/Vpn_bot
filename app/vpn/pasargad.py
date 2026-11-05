"""Pasargad Panel adapter.

⚠️ مطابق قانون پروژه: API پنل پاسارگاد «حدس زده نمی‌شود».
اسکلت Adapter کامل آماده است؛ فقط وقتی مستندات واقعی API را بدهید،
بخش‌های مشخص‌شده با PASARGAD_API_TODO تکمیل می‌شوند و بقیه سیستم
دست‌نخورده می‌ماند (فقط این فایل عوض می‌شود).
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from app.vpn.base import PanelError, PanelUser, VpnPanelAdapter

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


class PasargadPanelAdapter(VpnPanelAdapter):
    mode = "pasargad"

    def __init__(self, cfg: dict[str, str]) -> None:
        self.cfg = cfg
        self.base_url = (cfg.get("panel_api_url") or cfg.get("panel_url") or "").rstrip("/")
        self.api_key = cfg.get("panel_api_key") or ""

    def _require_config(self) -> None:
        if not self.base_url or not self.api_key:
            raise PanelError(
                "PASARGAD_API_NOT_CONFIGURED: آدرس API یا کلید پنل تنظیم نشده است. "
                "مستندات API پنل را ارائه دهید تا این Adapter تکمیل شود."
            )

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._require_config()
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        logger.info("Panel request: %s %s", method.upper(), path)
        try:
            async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
                async with session.request(method, url, json=payload, headers=headers) as resp:
                    text = await resp.text()
                    if resp.status >= 400:
                        logger.error("Panel HTTP %s on %s", resp.status, path)
                        raise PanelError(f"HTTP {resp.status} از پنل (پاسخ در لاگ ذخیره شد)")
                    import json

                    try:
                        return json.loads(text)
                    except Exception:
                        return {"raw": text}
        except aiohttp.ClientError as e:
            logger.error("Panel connection error on %s: %s", path, type(e).__name__)
            raise PanelError("اتصال به پنل برقرار نشد") from e

    # ---------------- Interface ----------------

    async def check_connection(self) -> str:
        # PASARGAD_API_TODO: endpoint تست اتصال طبق مستندات واقعی، مثلا GET /api/system/ping
        await self._request("GET", "system/info")
        return "✅ اتصال به پنل پاسارگاد برقرار است."

    async def create_user(self, username: str, volume_gb: float, days: int) -> PanelUser:
        # PASARGAD_API_TODO: endpoint ساخت کاربر طبق مستندات واقعی
        data = await self._request(
            "POST",
            "users",
            {
                "username": username,
                "volume_gb": volume_gb,
                "expire_days": days,
            },
        )
        sub_url = data.get("subscription_url", "")
        if not sub_url:
            sub_url = await self.generate_subscription(username)
        return PanelUser(
            username=username,
            subscription_url=sub_url,
            raw=data,
        )

    async def delete_user(self, username: str) -> bool:
        # PASARGAD_API_TODO: endpoint حذف کاربر
        await self._request("DELETE", f"users/{username}")
        return True

    async def get_user(self, username: str) -> PanelUser | None:
        # PASARGAD_API_TODO: endpoint اطلاعات کاربر
        data = await self._request("GET", f"users/{username}")
        return PanelUser(
            username=username,
            subscription_url=data.get("subscription_url", ""),
            used_gb=float(data.get("used_gb", 0) or 0),
            total_gb=float(data.get("total_gb", 0) or 0),
            status=data.get("status", "ACTIVE"),
            raw=data,
        )

    async def generate_subscription(self, username: str) -> str:
        # PASARGAD_API_TODO: endpoint لینک اشتراک
        data = await self._request("GET", f"users/{username}/subscription")
        return data.get("subscription_url", "")
