"""Free trial."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select

from app.bot.keyboards import inline as ik
from app.db.models import VPNService
from app.services import settings_service, user_service
from app.services.provision_service import trial_success_text
from app.utils.ids import gen_random_username

logger = logging.getLogger(__name__)

router = Router(name="trial")


@router.message(F.text == "🎁 تست رایگان")
@router.callback_query(F.data == "trial:start")
async def start_trial(event, session):
    message = event.message if hasattr(event, "message") and not hasattr(event, "text") else event
    if not hasattr(message, "answer"):
        message = event.message
    telegram_id = event.from_user.id

    if not await settings_service.get_bool(session, "trial_enabled"):
        await message.answer("⚠️ تست رایگان در حال حاضر غیرفعال است.")
        if hasattr(event, "answer"):
            await event.answer()
        return

    user = await user_service.get_by_telegram_id(session, telegram_id)
    if user is None:
        await message.answer("ابتدا /start را بزنید.")
        if hasattr(event, "answer"):
            await event.answer()
        return

    if user.free_trial_used:
        await message.answer("⚠️ شما قبلاً از تست رایگان استفاده کرده‌اید.")
        if hasattr(event, "answer"):
            await event.answer()
        return

    volume = await settings_service.get_float(session, "trial_volume_gb", 0.01)
    days = await settings_service.get_int(session, "trial_days", 1)

    # نام یکتا
    username = None
    for _ in range(10):
        candidate = gen_random_username("trial")
        exists = await session.scalar(
            select(VPNService.vpn_username).where(VPNService.vpn_username == candidate)
        )
        if exists is None:
            username = candidate
            break
    if username is None:
        await message.answer("خطا در ساخت نام؛ دوباره تلاش کنید.")
        if hasattr(event, "answer"):
            await event.answer()
        return

    from app.vpn import PanelError, get_adapter

    cfg = await settings_service.get_all(session)
    adapter = get_adapter(cfg)
    try:
        await message.answer("⏳ در حال ساخت تست رایگان...")
        panel_user = await adapter.create_user(username, volume, days)
    except PanelError as e:
        logger.error("Trial creation failed: %s", e)
        await message.answer(
            f"⚠️ ساخت تست رایگان با خطا مواجه شد: {e}\nدوباره تلاش کنید."
        )
        if hasattr(event, "answer"):
            await event.answer()
        return
    except Exception:  # noqa: BLE001
        logger.exception("Trial unexpected error")
        await message.answer("⚠️ خطای غیرمنتظره؛ دوباره تلاش کنید.")
        if hasattr(event, "answer"):
            await event.answer()
        return

    expires = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=days)
    service = VPNService(
        user_id=user.id,
        vpn_username=username,
        volume_gb=volume,
        duration_days=days,
        is_trial=True,
        status="ACTIVE",
        subscription_url=panel_user.subscription_url,
        panel_mode=cfg.get("panel_mode", "mock"),
        expires_at=expires,
    )
    session.add(service)
    user.free_trial_used = True
    await session.commit()

    await message.answer(
        trial_success_text(username, volume, panel_user.subscription_url, expires)
    )
    if hasattr(event, "answer"):
        try:
            await event.answer()
        except Exception:  # noqa: BLE001
            pass
