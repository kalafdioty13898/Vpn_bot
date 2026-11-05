"""User service: registration, referral, lookup."""
from __future__ import annotations

import secrets

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Order, Referral, User, UserStatus, VPNService, Wallet
from app.services import settings_service
from app.utils.ids import gen_referral_code


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_wallet(session: AsyncSession, user_id: int) -> Wallet:
    wallet = await session.scalar(
        select(Wallet).where(Wallet.user_id == user_id).with_for_update()
    )
    if wallet is None:
        wallet = Wallet(user_id=user_id, balance=0)
        session.add(wallet)
        await session.flush()
    return wallet


async def get_wallet_balance(session: AsyncSession, user_id: int) -> int:
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id))
    return wallet.balance if wallet else 0


async def register_user(
    session: AsyncSession,
    telegram_id: int,
    first_name: str,
    last_name: str | None,
    telegram_username: str | None,
    ref_code: str | None,
) -> tuple[User, User | None]:
    """ثبت کاربر جدید + ثبت Referral (بدون تکرار، بدون Self-invite)."""
    user = await get_by_telegram_id(session, telegram_id)
    if user is not None:
        # بروزرسانی اطلاعات نمایشی
        user.first_name = first_name or user.first_name
        user.last_name = last_name or user.last_name
        user.telegram_username = telegram_username
        return user, None

    referral_enabled = await settings_service.get_bool(session, "referral_enabled")
    referrer: User | None = None
    if ref_code and referral_enabled:
        referrer = await session.scalar(
            select(User).where(User.referral_code == ref_code.strip())
        )
        if referrer is not None and referrer.telegram_id == telegram_id:
            referrer = None  # self-invite ممنوع
        if referrer is not None:
            existing_ref = await session.scalar(
                select(Referral).where(Referral.referred_id == referrer.id)
            )
            # referred هنوز ثبت نشده؛ فقط چک اینکه referrer خودش زیرمجموعه نباشد مشکل نیست

    # کد یکتا
    while True:
        code = gen_referral_code()
        dup = await session.scalar(select(User.id).where(User.referral_code == code))
        if dup is None:
            break

    user = User(
        telegram_id=telegram_id,
        first_name=first_name or "",
        last_name=last_name or "",
        telegram_username=telegram_username,
        referral_code=code,
        referrer_id=referrer.id if referrer else None,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()

    session.add(Wallet(user_id=user.id, balance=0))

    if referrer is not None:
        # هر کاربر فقط یک referrer؛ فقط کاربران جدید referral می‌گیرند
        exists = await session.scalar(
            select(Referral).where(Referral.referred_id == user.id)
        )
        if not exists:
            session.add(Referral(referrer_id=referrer.id, referred_id=user.id))

    return user, referrer


async def get_referrer_of(session: AsyncSession, user_id: int) -> User | None:
    user = await session.get(User, user_id)
    if user is None or user.referrer_id is None:
        return None
    return await session.get(User, user.referrer_id)


async def referrals_count(session: AsyncSession, user_id: int) -> int:
    return await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.referrer_id == user_id)
    ) or 0


async def services_count(session: AsyncSession, user_id: int) -> int:
    return await session.scalar(
        select(func.count()).select_from(VPNService).where(
            VPNService.user_id == user_id, VPNService.status == "ACTIVE"
        )
    ) or 0


async def paid_invoices_count(session: AsyncSession, user_id: int) -> int:
    from app.db.models import Invoice, InvoiceStatus

    return await session.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.user_id == user_id, Invoice.status == InvoiceStatus.PAID
        )
    ) or 0


async def total_purchases(session: AsyncSession, user_id: int) -> tuple[int, int]:
    """(تعداد خرید, مجموع مبلغ) فقط سفارش‌های پرداخت‌شده."""
    from app.db.models import OrderStatus

    rows = await session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.amount), 0)).where(
            Order.user_id == user_id, Order.status.in_(OrderStatus.SOLD_STATUSES)
        )
    )
    cnt, total = rows.one()
    return int(cnt or 0), int(total or 0)


async def total_purchases_of_referrals(session: AsyncSession, referrer_id: int) -> tuple[int, int]:
    """آمار خریدهای همه زیرمجموعه‌های یک کاربر."""
    from app.db.models import CommissionTransaction, OrderStatus

    row = (
        await session.execute(
            select(
                func.count(func.distinct(CommissionTransaction.order_id)),
                func.coalesce(func.sum(CommissionTransaction.amount), 0),
            ).where(CommissionTransaction.referrer_id == referrer_id)
        )
    ).one()
    return int(row[0] or 0), int(row[1] or 0)


async def total_commissions(session: AsyncSession, referrer_id: int) -> int:
    from app.db.models import CommissionTransaction

    total = await session.scalar(
        select(func.coalesce(func.sum(CommissionTransaction.amount), 0)).where(
            CommissionTransaction.referrer_id == referrer_id,
            CommissionTransaction.status == "PAID",
        )
    )
    return int(total or 0)


async def set_banned(session: AsyncSession, telegram_id: int, banned: bool) -> bool:
    user = await get_by_telegram_id(session, telegram_id)
    if user is None:
        return False
    user.status = UserStatus.BANNED if banned else UserStatus.ACTIVE
    await session.flush()
    return True


def make_referral_link(bot_username: str, user: User) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user.referral_code}"


async def find_free_referral_code(session: AsyncSession) -> str:
    while True:
        code = secrets.token_hex(4).upper()
        dup = await session.scalar(select(User.id).where(User.referral_code == code))
        if dup is None:
            return code
