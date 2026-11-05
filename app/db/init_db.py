"""Schema creation + initial seed (idempotent, safe to run on every start)."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import settings
from app.db.models import (
    Admin,
    Base,
    BotSetting,
    ServicePlan,
    Tutorial,
    UserRole,
)

logger = logging.getLogger(__name__)

# ---------------- Settings defaults (all editable from admin panel) ----------------
SETTINGS_DEFAULTS: dict[str, str] = {
    "bot_enabled": "1",
    "sales_enabled": "1",
    "referral_enabled": "1",
    "force_join_enabled": "0",
    "force_join_channel": "",
    "force_join_url": "",
    "card_number": "",
    "card_holder": "",
    "referral_percent": "5",
    "trial_enabled": "1",
    "trial_volume_gb": "0.01",
    "trial_days": "1",
    "custom_min_volume": "1",
    "custom_max_volume": "1000",
    "custom_min_days": "1",
    "custom_max_days": "365",
    "custom_min_price": "50000",
    "custom_base_price_per_gb": "10000",
    "wallet_min_deposit": "20000",
    "wallet_max_deposit": "100000000",
    "username_min_len": "3",
    "username_max_len": "32",
    "panel_mode": settings.panel_mode,
    "panel_url": settings.panel_url,
    "panel_api_url": settings.panel_api_url,
    "panel_api_key": settings.panel_api_key,
    "panel_username": settings.panel_username,
    "panel_password": settings.panel_password,
    "bot_username": "",
}

INITIAL_PLANS = [
    ("gb5", "5 گیگ", 5, 31, 50_000, 1),
    ("gb10", "10 گیگ", 10, 31, 100_000, 2),
    ("gb20", "20 گیگ", 20, 31, 200_000, 3),
    ("gb30", "30 گیگ", 30, 31, 300_000, 4),
    ("gb40", "40 گیگ", 40, 31, 400_000, 5),
    ("gb50", "50 گیگ", 50, 31, 490_000, 6),
    ("gb100", "100 گیگ", 100, 31, 950_000, 7),
]

INITIAL_TUTORIALS = [
    ("V2RAY", "آموزش اضافه کردن اشتراک به V2Ray (اندروید)", 
     "۱- برنامه V2Ray را نصب کنید.\n۲- روی لینک اشتراک که ربات داده کلیک کنید یا آن را کپی کنید.\n۳- در برنامه از منوی «Subscription» گزینه «+» را بزنید.\n۴- لینک را Paste کنید و ذخیره کنید.\n۵- روی اشتراک Swipe بزنید تا آپدیت شود.\n۶- کانفیگ را انتخاب و دکمه اتصال را بزنید."),
    ("V2BOX", "آموزش اضافه کردن اشتراک به V2Box (iOS)", 
     "۱- برنامه V2Box را از App Store نصب کنید.\n۲- لینک اشتراک ربات را کپی کنید.\n۳- در برنامه روی «+» بزنید و «Add subscription» را انتخاب کنید.\n۴- لینک را Paste و ذخیره کنید.\n۵- اشتراک را آپدیت کنید.\n۶- سرور را انتخاب و Connect بزنید."),
]


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema ensured")


async def seed_defaults(session: AsyncSession) -> None:
    # settings
    for key, value in SETTINGS_DEFAULTS.items():
        exists = await session.scalar(select(BotSetting).where(BotSetting.key == key))
        if exists is None:
            session.add(BotSetting(key=key, value=value))

    # plans
    count = await session.scalar(select(func.count()).select_from(ServicePlan))
    if not count:
        for code, name, volume, days, price, sort in INITIAL_PLANS:
            session.add(
                ServicePlan(
                    code=code, name=name, volume_gb=float(volume),
                    duration_days=days, price=price, sort_order=sort,
                )
            )

    # tutorials
    count = await session.scalar(select(func.count()).select_from(Tutorial))
    if not count:
        for cat, title, content in INITIAL_TUTORIALS:
            session.add(Tutorial(category=cat, title=title, content=content, sort_order=0))

    # super admin from env
    if settings.admin_ids:
        super_id = settings.admin_ids[0]
        exists = await session.scalar(select(Admin).where(Admin.telegram_id == super_id))
        if exists is None:
            session.add(Admin(telegram_id=super_id, role=UserRole.SUPER_ADMIN))

    await session.commit()
    logger.info("Seed defaults done")
