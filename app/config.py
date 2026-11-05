"""Bot configuration from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env", override=True)

# ادمین پیش‌فرض مالک ربات (فقط وقتی Secret های ADMIN_IDS/ADMIN_ID خالی یا نامعتبر
# باشند استفاده می‌شود تا ربات هیچ‌وقت بدون ادمین نماند).
# اگر Secret مقدار معتبر داشته باشد، دقیقاً همان لیست ملاک است.
DEFAULT_ADMIN_IDS: tuple[int, ...] = (1051928416,)

# آیدی‌هایی که صاحب ربات صریحاً لغو کرده — حتی اگر در Secret بمانند ادمین نمی‌شوند
RETIRED_ADMIN_IDS: frozenset[int] = frozenset({8581608010, 8560434777})


def _parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    """پارس ادمین‌ها از ورودی متنی؛ مقاوم به فاصله، کوتیشن، براکت و کامای فارسی."""
    if not raw:
        return ()
    ids: list[int] = []
    for part in raw.replace(";", ",").replace("؛", ",").replace("،", ",").split(","):
        part = part.strip().strip("\"'[]()«» ").strip()
        if part.isdigit():
            ids.append(int(part))
    return tuple(dict.fromkeys(ids))


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: tuple[int, ...]
    timezone: str
    log_level: str
    panel_mode: str
    panel_url: str
    panel_api_url: str
    panel_api_key: str
    panel_username: str
    panel_password: str


def load_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        database_url=os.getenv("DATABASE_URL", "").strip()
        or "sqlite+aiosqlite:///./vpnbot.db",
        # هم ADMIN_IDS (جدا با کاما) و هم ADMIN_ID (تکی) پذیرفته می‌شود
        # + ادمین پیش‌فرض مالک (fallback) و بدون آیدی‌های لغوشده
        admin_ids=tuple(dict.fromkeys(
            aid for aid in (
                _parse_admin_ids(
                    f"{os.getenv('ADMIN_IDS', '')},{os.getenv('ADMIN_ID', '')}"
                ) + DEFAULT_ADMIN_IDS
            )
            if aid not in RETIRED_ADMIN_IDS
        )),
        timezone=os.getenv("TIMEZONE", "Asia/Tehran").strip() or "Asia/Tehran",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        panel_mode=os.getenv("PANEL_MODE", "mock").strip().lower(),
        panel_url=os.getenv("PANEL_URL", "").strip(),
        panel_api_url=os.getenv("PANEL_API_URL", "").strip(),
        panel_api_key=os.getenv("PANEL_API_KEY", "").strip(),
        panel_username=os.getenv("PANEL_USERNAME", "").strip(),
        panel_password=os.getenv("PANEL_PASSWORD", "").strip(),
    )


settings = load_settings()
