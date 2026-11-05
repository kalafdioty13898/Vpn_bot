"""VPN provisioning — ساخت سرویس روی پنل، Idempotent و با Retry."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Invoice, Order, OrderStatus, VPNService
from app.services import settings_service
from app.services.notification_service import notify
from app.utils.formatters import fmt_gb, jalali, money
from app.vpn import PanelError, get_adapter
from app.vpn.mock_panel import build_mock_config_text

logger = logging.getLogger(__name__)

_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_provisioner(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    global _sessionmaker
    _sessionmaker = sessionmaker


def _config_text(username: str, sub_url: str, panel_mode: str) -> str:
    if panel_mode == "mock":
        vless, _ = build_mock_config_text(username, sub_url)
        return vless
    return ""


async def provision_order(order_id: str) -> bool:
    """ساخت سرویس VPN برای سفارش پرداخت‌شده.

    Idempotent: اگر قبلاً PROVISIONED شده دوباره ساخته نمی‌شود.
    """
    assert _sessionmaker is not None, "init_provisioner() must be called at startup"

    async with _sessionmaker() as session:
        order = await get_order(session, order_id)
        if order is None:
            return False
        if order.status == OrderStatus.PROVISIONED:
            logger.info("Order %s already provisioned (skip)", order_id)
            return True
        if order.status not in (OrderStatus.PAID, OrderStatus.PROVISION_FAILED):
            logger.warning("Order %s not payable for provisioning (status=%s)", order_id, order.status)
            return False

        order.status = OrderStatus.PROVISIONING
        await session.commit()

        # تنظیمات پنل از دیتابیس (ادمین قابل تغییر)
        cfg = await settings_service.get_all(session)
        adapter = get_adapter(cfg)
        panel_mode = cfg.get("panel_mode", "mock")

        # جلوگیری از ساخت تکراری سرویس برای همین سفارش
        existing = await session.scalar(
            select(VPNService).where(VPNService.order_id == order.order_id)
        )
        if existing is not None:
            order.status = OrderStatus.PROVISIONED
            await session.commit()
            return True

        try:
            panel_user = await adapter.create_user(order.vpn_username, order.volume_gb, order.duration_days)
        except PanelError as e:
            logger.error("Provision failed for %s: %s", order_id, e)
            order.status = OrderStatus.PROVISION_FAILED
            await session.commit()
            await notify(
                "provision_failed",
                f"⚠️ پرداخت تأیید شد اما ساخت سرویس با خطا مواجه شد.\n"
                f"سفارش: <code>{order.order_id}</code>\n"
                f"کاربر: {order.user_id}\n"
                f"خطا: {e}",
                order_id=order.order_id,
            )
            return False
        except Exception as e:  # noqa: BLE001
            logger.exception("Unexpected provision error for %s", order_id)
            order.status = OrderStatus.PROVISION_FAILED
            await session.commit()
            await notify(
                "provision_failed",
                f"⚠️ خطای غیرمنتظره در ساخت سرویس.\nسفارش: <code>{order.order_id}</code>",
                order_id=order.order_id,
            )
            _ = e
            return False

        expires = datetime.utcnow().replace(tzinfo=timezone.utc) + timedelta(days=order.duration_days)
        vpn_service = VPNService(
            user_id=order.user_id,
            vpn_username=order.vpn_username,
            plan_id=order.plan_id,
            volume_gb=order.volume_gb,
            duration_days=order.duration_days,
            is_trial=(order.service_kind == "TRIAL"),
            status="ACTIVE",
            subscription_url=panel_user.subscription_url,
            panel_mode=panel_mode,
            expires_at=expires,
            order_id=order.order_id,
        )
        session.add(vpn_service)
        order.status = OrderStatus.PROVISIONED
        await session.commit()
        logger.info("Order %s provisioned successfully", order_id)

        # پیام موفقیت برای کاربر
        config_line = _config_text(order.vpn_username, panel_user.subscription_url, panel_mode)
        text = (
            "🎉 خرید شما با موفقیت انجام شد!\n\n"
            f"👤 نام کاربری: <code>{order.vpn_username}</code>\n"
            f"📦 حجم: {fmt_gb(order.volume_gb)}\n"
            f"📆 مدت: {order.duration_days} روز\n"
            f"📅 تاریخ انقضا: {jalali(expires)}\n\n"
            "🔗 لینک اشتراک:\n"
            f"<code>{panel_user.subscription_url}</code>\n"
        )
        if config_line:
            text += f"\n🖥 کانفیگ:\n<code>{config_line}</code>\n"
        text += "\n📚 برای نحوه استفاده از «آموزش» در منو استفاده کنید."
        await notify("user", text, user_id=order.user_id)
        return True


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.order_id == order_id))


async def get_invoice(session: AsyncSession, invoice_id: str) -> Invoice | None:
    return await session.scalar(select(Invoice).where(Invoice.invoice_id == invoice_id))


async def trial_success_text(username: str, volume_gb: float, sub_url: str, expires: datetime) -> str:
    config_line = _config_text(username, sub_url, "mock")
    text = (
        "🎁 تست رایگان شما فعال شد!\n\n"
        f"👤 نام کاربری: <code>{username}</code>\n"
        f"📦 حجم: {fmt_gb(volume_gb)}\n"
        f"📆 مدت: ۱ روز\n"
        f"📅 انقضا: {jalali(expires)}\n\n"
        f"🔗 لینک اشتراک:\n<code>{sub_url}</code>\n"
    )
    if config_line:
        text += f"\n🖥 کانفیگ:\n<code>{config_line}</code>\n"
    return text


__all__ = ["init_provisioner", "provision_order", "trial_success_text", "money"]
