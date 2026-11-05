"""Referral commission — فقط روی خرید موفق، بدون تکرار، با برگشت در Refund."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CommissionTransaction, Order, OrderStatus
from app.services import settings_service, wallet_service
from app.services.notification_service import notify
from app.utils.formatters import money

logger = logging.getLogger(__name__)


async def grant_commission_for_order(session: AsyncSession, order: Order) -> None:
    """پورسانت خرید موفق به معرف. Idempotent (هر سفارش فقط یک‌بار)."""
    if order.status not in OrderStatus.SOLD_STATUSES:
        return

    # تست رایگان پورسانت ندارد
    if order.service_kind == "TRIAL":
        return

    exists = await session.scalar(
        select(CommissionTransaction).where(
            CommissionTransaction.order_id == order.order_id,
            CommissionTransaction.status == "PAID",
        )
    )
    if exists is not None:
        return

    referrer_id = None
    from app.db.models import User

    user = await session.scalar(select(User).where(User.id == order.user_id))
    if user is None or user.referrer_id is None:
        return
    referrer_id = user.referrer_id

    referral_enabled = await settings_service.get_bool(session, "referral_enabled")
    if not referral_enabled:
        return

    percent = await settings_service.get_int(session, "referral_percent", 5)
    if percent <= 0:
        return

    amount = order.amount * percent // 100
    if amount <= 0:
        return

    # Idempotency: سفارش باید PAID باشد نه REFUNDED
    if order.status == OrderStatus.REFUNDED:
        return

    session.add(
        CommissionTransaction(
            referrer_id=referrer_id,
            referred_id=order.user_id,
            order_id=order.order_id,
            amount=amount,
            percent=percent,
            status="PAID",
        )
    )
    balance = await wallet_service.adjust_balance(
        session, referrer_id, amount, tx_type="COMMISSION", reference=order.order_id
    )
    if balance is None:
        logger.warning("Commission wallet adjust failed referrer=%s", referrer_id)
        return

    await session.flush()
    logger.info("Commission %s toman (order=%s) -> referrer=%s", amount, order.order_id, referrer_id)

    try:
        await notify(
            "user",
            f"🎉 پورسانت {percent}٪ از خرید زیرمجموعه به کیف پول شما اضافه شد:\n"
            f"💵 {money(amount)} تومان",
            user_id=int(
                session.scalar(select(User.telegram_id).where(User.id == referrer_id)) or 0
            ),
        )
    except Exception:  # noqa: BLE001
        pass


async def reverse_commission_for_order(session: AsyncSession, order_id: str) -> None:
    """برگشت پورسانت هنگام Refund."""
    rows = (
        await session.execute(
            select(CommissionTransaction).where(
                CommissionTransaction.order_id == order_id,
                CommissionTransaction.status == "PAID",
            )
        )
    ).scalars().all()
    for tx in rows:
        tx.status = "REVERSED"
        await wallet_service.adjust_balance(
            session, tx.referrer_id, -tx.amount, tx_type="REFUND", reference=f"reverse-{order_id}"
        )
    await session.flush()
