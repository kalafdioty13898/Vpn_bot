"""Order + Invoice creation and payment flows."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Invoice,
    InvoiceStatus,
    InvoiceType,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    ServicePlan,
)
from app.services import wallet_service
from app.utils.ids import gen_order_id, gen_payment_id, gen_service_invoice_id, gen_wallet_invoice_id

logger = logging.getLogger(__name__)

# سفارش‌های تکراری در این بازه دوباره ساخته نمی‌شوند (Anti-duplicate)
DUPLICATE_WINDOW_MINUTES = 30


async def get_invoice(session: AsyncSession, invoice_id: str) -> Invoice | None:
    return await session.scalar(select(Invoice).where(Invoice.invoice_id == invoice_id))


async def get_order(session: AsyncSession, order_id: str) -> Order | None:
    return await session.scalar(select(Order).where(Order.order_id == order_id))


async def find_recent_pending_invoice(
    session: AsyncSession, user_id: int, vpn_username: str, amount: int
) -> Invoice | None:
    """جلوگیری از سفارش تکراری: اگر همین کاربر همان نام و مبلغ را در بازه اخیر ساخته، همان برگردد."""
    since = datetime.utcnow().replace(tzinfo=None) - timedelta(minutes=DUPLICATE_WINDOW_MINUTES)
    rows = await session.execute(
        select(Invoice)
        .join(Order, Order.invoice_id == Invoice.invoice_id)
        .where(
            Invoice.user_id == user_id,
            Invoice.invoice_type == InvoiceType.SERVICE,
            Invoice.status == InvoiceStatus.PENDING,
            Order.vpn_username == vpn_username,
            Order.amount == amount,
            Order.status == OrderStatus.PENDING_PAYMENT,
            Order.created_at >= since,
        )
        .limit(1)
    )
    return rows.scalar_one_or_none()


async def create_service_invoice(
    session: AsyncSession,
    user_id: int,
    *,
    plan: ServicePlan | None,
    vpn_username: str,
    volume_gb: float,
    duration_days: int,
    amount: int,
    service_kind: str = "PLAN",
) -> tuple[Invoice, Order]:
    invoice = Invoice(
        invoice_id=gen_service_invoice_id(),
        user_id=user_id,
        invoice_type=InvoiceType.SERVICE,
        amount=amount,
        status=InvoiceStatus.PENDING,
    )
    order = Order(
        order_id=gen_order_id(),
        user_id=user_id,
        plan_id=plan.id if plan else None,
        invoice_id=invoice.invoice_id,
        service_kind=service_kind,
        vpn_username=vpn_username,
        volume_gb=volume_gb,
        duration_days=duration_days,
        amount=amount,
        status=OrderStatus.PENDING_PAYMENT,
    )
    invoice.order_id = order.order_id
    session.add_all([invoice, order])
    await session.flush()
    logger.info("Order created: %s user=%s amount=%s", order.order_id, user_id, amount)
    return invoice, order


async def create_wallet_deposit_invoice(
    session: AsyncSession, user_id: int, amount: int
) -> Invoice:
    invoice = Invoice(
        invoice_id=gen_wallet_invoice_id(),
        user_id=user_id,
        invoice_type=InvoiceType.WALLET_DEPOSIT,
        amount=amount,
        status=InvoiceStatus.PENDING,
    )
    session.add(invoice)
    await session.flush()
    return invoice


async def pay_with_wallet(
    session: AsyncSession, invoice: Invoice
) -> tuple[bool, str]:
    """پرداخت از کیف پول — کاملاً Transaction-safe با Row Lock.

    اگر پرداخت موفق باشد Payment/Invoice/Order در همان تراکنش آپدیت می‌شوند.
    """
    if invoice.status != InvoiceStatus.PENDING:
        return False, "این فاکتور قبلاً پردازش شده است."

    order: Order | None = None
    if invoice.order_id:
        order = await get_order(session, invoice.order_id)
        if order is None or order.status != OrderStatus.PENDING_PAYMENT:
            return False, "این سفارش قبلاً پردازش شده است."

    balance = await wallet_service.adjust_balance(
        session,
        invoice.user_id,
        -invoice.amount,
        tx_type="PURCHASE",
        reference=invoice.invoice_id,
    )
    if balance is None:
        return False, "موجودی کیف پول کافی نیست."

    session.add(
        Payment(
            payment_id=gen_payment_id(),
            invoice_id=invoice.invoice_id,
            user_id=invoice.user_id,
            amount=invoice.amount,
            method=PaymentMethod.WALLET,
            status=PaymentStatus.PAID,
        )
    )
    invoice.status = InvoiceStatus.PAID
    if order is not None:
        order.status = OrderStatus.PAID
        order.paid_by = PaymentMethod.WALLET
    await session.flush()
    logger.info("Wallet payment ok: invoice=%s amount=%s", invoice.invoice_id, invoice.amount)
    return True, ""


async def mark_payment_rejected(session: AsyncSession, invoice: Invoice) -> None:
    invoice.status = InvoiceStatus.REJECTED
    if invoice.order_id:
        order = await get_order(session, invoice.order_id)
        if order is not None:
            order.status = OrderStatus.PAYMENT_REJECTED
    await session.flush()
