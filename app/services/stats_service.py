"""Admin statistics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatus,
    Receipt,
    ReceiptStatus,
    User,
    VPNService,
)


def _start_of_day() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _days_ago(days: int) -> datetime:
    return _start_of_day() - timedelta(days=days - 1)


async def user_stats(session: AsyncSession) -> dict:
    total = await session.scalar(select(func.count()).select_from(User)) or 0
    today = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= _start_of_day())
    ) or 0
    week = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= _days_ago(7))
    ) or 0
    month = await session.scalar(
        select(func.count()).select_from(User).where(User.created_at >= _days_ago(30))
    ) or 0
    banned = await session.scalar(
        select(func.count()).select_from(User).where(User.status == "BANNED")
    ) or 0
    trial_used = await session.scalar(
        select(func.count()).select_from(User).where(User.free_trial_used.is_(True))
    ) or 0
    with_services = await session.scalar(
        select(func.count(func.distinct(VPNService.user_id))).where(VPNService.status == "ACTIVE")
    ) or 0
    return {
        "total": total,
        "today": today,
        "week": week,
        "month": month,
        "banned": banned,
        "trial_used": trial_used,
        "with_services": with_services,
    }


async def sales_stats(session: AsyncSession) -> dict:
    total_orders = await session.scalar(select(func.count()).select_from(Order)) or 0
    ok_orders = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status.in_(OrderStatus.SOLD_STATUSES))
    ) or 0
    pending_orders = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.PENDING_PAYMENT)
    ) or 0
    rejected_orders = await session.scalar(
        select(func.count()).select_from(Order).where(Order.status == OrderStatus.PAYMENT_REJECTED)
    ) or 0

    def _sum_filter():
        return Order.status.in_(OrderStatus.SOLD_STATUSES)

    total_amount = await session.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(_sum_filter())
    ) or 0
    today_amount = await session.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            _sum_filter(), Order.created_at >= _start_of_day()
        )
    ) or 0
    week_amount = await session.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            _sum_filter(), Order.created_at >= _days_ago(7)
        )
    ) or 0
    month_amount = await session.scalar(
        select(func.coalesce(func.sum(Order.amount), 0)).where(
            _sum_filter(), Order.created_at >= _days_ago(30)
        )
    ) or 0

    top_row = (
        await session.execute(
            select(Order.plan_id, func.count(Order.id))
            .where(_sum_filter(), Order.plan_id.isnot(None))
            .group_by(Order.plan_id)
            .order_by(func.count(Order.id).desc())
            .limit(1)
        )
    ).first()

    sold_services = await session.scalar(
        select(func.count()).select_from(VPNService).where(VPNService.is_trial.is_(False))
    ) or 0
    sold_volume = await session.scalar(
        select(func.coalesce(func.sum(VPNService.volume_gb), 0)).where(VPNService.is_trial.is_(False))
    ) or 0

    pending_receipts = await session.scalar(
        select(func.count()).select_from(Receipt).where(Receipt.status == ReceiptStatus.PENDING)
    ) or 0

    return {
        "total_orders": total_orders,
        "ok_orders": ok_orders,
        "pending_orders": pending_orders,
        "rejected_orders": rejected_orders,
        "total_amount": int(total_amount),
        "today_amount": int(today_amount),
        "week_amount": int(week_amount),
        "month_amount": int(month_amount),
        "top_plan_id": top_row[0] if top_row else None,
        "top_plan_count": top_row[1] if top_row else 0,
        "sold_services": sold_services,
        "sold_volume": float(sold_volume),
        "pending_receipts": pending_receipts,
    }
