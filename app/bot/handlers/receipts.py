"""Receipts: card info display, user sends receipt, admin approve/reject/wait + provision retry + refund."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards import inline as ik
from app.bot.keyboards.reply import cancel_kb, CANCEL
from app.bot.states import ReceiptStates


class RejectStates(StatesGroup):
    waiting_reason = State()


from app.db.models import (
    Invoice,
    InvoiceStatus,
    InvoiceType,
    Order,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Receipt,
    ReceiptStatus,
)
from app.services import order_service, settings_service, user_service, wallet_service
from app.services.notification_service import notify, send_safe
from app.utils.formatters import fmt_gb, jalali, money
from app.utils.ids import gen_payment_id

logger = logging.getLogger(__name__)

router = Router(name="receipts")


async def get_card_info(session) -> tuple[str, str]:
    card = await settings_service.get_setting(session, "card_number")
    holder = await settings_service.get_setting(session, "card_holder")
    return card, holder


async def send_card_info(target, session, invoice: Invoice):
    card, holder = await get_card_info(session)
    if not card or not holder:
        await target.answer(
            "⚠️ اطلاعات کارت هنوز توسط ادمین تنظیم نشده است.\n"
            "لطفاً با پشتیبانی در تماس باشید.",
            reply_markup=ik.noop_kb(),
        )
        return

    # شناسه یکتا برای مبلغ (خرده مبلغ برای تشخیص رسید) — آخرین ۳ رقم ثابت نگه داشته می‌شود
    amount = invoice.amount
    deposit_id = invoice.invoice_id
    kind = "خدمات" if invoice.invoice_type == InvoiceType.SERVICE else "شارژ کیف پول"

    await target.answer(
        "💳 پرداخت کارت به کارت\n\n"
        f"🧾 شناسه فاکتور:\n<code>{deposit_id}</code>\n\n"
        f"📦 نوع: {kind}\n"
        f"💰 مبلغ قابل پرداخت:\n<b>{money(amount)} تومان</b>\n\n"
        "⭕️ مبلغ را دقیق بزنید و رند نکنید. ⭕️\n"
        "⭕️ خرده مبلغ را حذف نکنید. ⭕️\n\n"
        f"💳 شماره کارت:\n<code>{card}</code>\n\n"
        f"👤 نام صاحب کارت:\n<b>{holder}</b>\n\n"
        "پس از واریز، رسید را ارسال کنید.",
        reply_markup=ik.card_pay_kb(invoice.invoice_id),
    )


# ---------------- User: send receipt ----------------
@router.callback_query(F.data.startswith("rc:send:"))
async def cb_receipt_start(cb: CallbackQuery, state: FSMContext, session):
    invoice_id = cb.data.split(":")[2]
    invoice = await order_service.get_invoice(session, invoice_id)
    if invoice is None or invoice.status != InvoiceStatus.PENDING:
        await cb.answer("این فاکتور معتبر نیست.", show_alert=True)
        return
    await state.set_state(ReceiptStates.waiting_file)
    await state.update_data(invoice_id=invoice_id)
    await cb.message.answer(
        "📸 عکس رسید واریزی را ارسال کنید.\n"
        "(می‌توانید فایل یا متن رسید را هم بفرستید)",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(ReceiptStates.waiting_file, F.photo)
@router.message(ReceiptStates.waiting_file, F.document)
@router.message(ReceiptStates.waiting_file, F.text)
async def receipt_received(message: Message, state: FSMContext, session):
    if message.text and message.text == CANCEL:
        await state.clear()
        await message.answer("✅ لغو شد.")
        return

    data = await state.get_data()
    invoice_id = data.get("invoice_id")
    invoice = await order_service.get_invoice(session, invoice_id) if invoice_id else None
    if invoice is None or invoice.status != InvoiceStatus.PENDING:
        await state.clear()
        await message.answer("⚠️ این فاکتور معتبر نیست.")
        return

    file_id = None
    file_type = None
    text_content = None
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "PHOTO"
    elif message.document:
        file_id = message.document.file_id
        file_type = "DOCUMENT"
    else:
        text_content = message.text
        file_type = "TEXT"

    await state.update_data(
        pend_file_id=file_id,
        pend_file_type=file_type,
        pend_text=text_content,
    )
    await message.answer(
        "آیا مطمئن هستید این رسید صحیح است؟",
        reply_markup=ik.receipt_confirm_kb(invoice_id),
    )


@router.callback_query(F.data.startswith("rc:no:"))
async def cb_receipt_no(cb: CallbackQuery, state: FSMContext):
    await cb.answer("رسید لغو شد؛ دوباره ارسال کنید.")
    await cb.message.answer("📸 لطفاً رسید صحیح را دوباره ارسال کنید:", reply_markup=cancel_kb())


@router.callback_query(F.data.startswith("rc:ok:"))
async def cb_receipt_ok(cb: CallbackQuery, state: FSMContext, session, bot):
    data = await state.get_data()
    invoice_id = cb.data.split(":")[2] or data.get("invoice_id")
    invoice = await order_service.get_invoice(session, invoice_id)
    if invoice is None:
        await cb.answer("فاکتور یافت نشد.", show_alert=True)
        return

    user = await user_service.get_by_telegram_id(session, cb.from_user.id)
    if invoice.user_id != (user.id if user else -1):
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    file_id = data.get("pend_file_id")
    file_type = data.get("pend_file_type")
    text_content = data.get("pend_text")
    if not file_type:
        await cb.answer("ابتدا رسید را ارسال کنید.", show_alert=True)
        return

    # ایجاد Payment و Receipt
    payment = Payment(
        payment_id=gen_payment_id(),
        invoice_id=invoice.invoice_id,
        user_id=invoice.user_id,
        amount=invoice.amount,
        method=PaymentMethod.CARD_TO_CARD,
        status=PaymentStatus.PENDING,
    )
    session.add(payment)
    await session.flush()

    receipt = Receipt(
        payment_id=payment.payment_id,
        invoice_id=invoice.invoice_id,
        user_id=invoice.user_id,
        file_id=file_id,
        file_type=file_type,
        text_content=text_content,
        amount=invoice.amount,
        status=ReceiptStatus.PENDING,
    )
    session.add(receipt)

    # وضعیت سفارش → بررسی پرداخت
    if invoice.order_id:
        order = await order_service.get_order(session, invoice.order_id)
        if order and order.status == OrderStatus.PENDING_PAYMENT:
            order.status = OrderStatus.PAYMENT_REVIEW

    await state.clear()
    await session.commit()

    await cb.message.answer("✅ رسید شما ثبت شد و در انتظار بررسی ادمین است.")
    await cb.answer("ارسال شد ✅")

    # ارسال برای ادمین‌ها
    order = await order_service.get_order(session, invoice.order_id) if invoice.order_id else None
    caption = (
        "🧾 رسید پرداخت جدید\n\n"
        f"👤 کاربر: {cb.from_user.first_name or ''} @{cb.from_user.username or '-'}\n"
        f"🆔 Telegram ID: <code>{cb.from_user.id}</code>\n"
        f"🧾 شناسه فاکتور: <code>{invoice.invoice_id}</code>\n"
        f"📦 سرویس: {order.service_kind if order else 'شارژ کیف پول'}\n"
        f"👤 نام کانفیگ: {order.vpn_username if order else '-'}\n"
        f"📊 حجم: {fmt_gb(order.volume_gb) if order else '-'}\n"
        f"📆 مدت: {order.duration_days if order else '-'} روز\n"
        f"💰 مبلغ: {money(invoice.amount)} تومان\n"
        f"🕐 زمان: {jalali(datetime.now(timezone.utc))}\n"
    )
    markup = ik.receipt_action_kb(receipt.id)

    for admin_id in _admin_ids(bot):
        try:
            if file_type == "PHOTO" and file_id:
                await bot.send_photo(admin_id, file_id)
            elif file_type == "DOCUMENT" and file_id:
                await bot.send_document(admin_id, file_id)
        except Exception:  # noqa: BLE001
            pass
        await send_safe(bot, admin_id, caption, reply_markup=markup)


def _admin_ids(bot) -> list[int]:
    from app.bot.filters import is_admin_id
    from app.config import settings

    ids = list(settings.admin_ids)
    return ids


# ---------------- Admin actions ----------------
@router.callback_query(F.data.startswith("adm:rcap:"))
async def cb_admin_approve(cb: CallbackQuery, session, bot):
    """تأیید رسید → پرداخت موفق → provisioning (یا شارژ کیف پول)."""
    try:
        receipt_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return

    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        await cb.answer("رسید یافت نشد.", show_alert=True)
        return
    if receipt.status != ReceiptStatus.PENDING:
        await cb.answer("این عملیات قبلاً انجام شده است.", show_alert=True)
        return

    invoice = await order_service.get_invoice(session, receipt.invoice_id)
    if invoice is None:
        await cb.answer("فاکتور یافت نشد.", show_alert=True)
        return

    receipt.status = ReceiptStatus.APPROVED
    receipt.reviewed_by = cb.from_user.id
    receipt.reviewed_at = datetime.now(timezone.utc)

    payment = await session.scalar(
        select(Payment).where(Payment.payment_id == receipt.payment_id)
    )
    if payment:
        payment.status = PaymentStatus.PAID

    invoice.status = InvoiceStatus.PAID
    order = None
    if invoice.order_id:
        order = await order_service.get_order(session, invoice.order_id)
        if order:
            order.status = OrderStatus.PAID
            order.paid_by = PaymentMethod.CARD_TO_CARD

    if invoice.invoice_type == InvoiceType.WALLET_DEPOSIT:
        balance = await wallet_service.adjust_balance(
            session, invoice.user_id, invoice.amount, tx_type="DEPOSIT", reference=invoice.invoice_id
        )
        await session.commit()
        text = (
            "✅ شارژ کیف پول شما تأیید شد.\n"
            f"💵 مبلغ: {money(invoice.amount)} تومان\n"
            f"💰 موجودی جدید: {money(balance or 0)} تومان"
        )
        await notify("user", text, user_id=invoice.user_id)
        try:
            await cb.message.edit_reply_markup(reply_markup=ik.kb(
                [[ik.btn("✅ تأیید شد", "noop")]]
            ))
        except Exception:  # noqa: BLE001
            pass
        await cb.answer("شارژ کیف پول تأیید شد ✅")
        return

    # خرید سرویس
    await session.commit()
    from app.services import provision_service

    await cb.answer("پرداخت تأیید شد؛ در حال ساخت سرویس...")
    try:
        await cb.message.edit_reply_markup(reply_markup=ik.kb(
            [[ik.btn("⏳ در حال ساخت سرویس...", "noop")]]
        ))
    except Exception:  # noqa: BLE001
        pass
    if order is not None:
        await provision_service.provision_order(order.order_id)


@router.callback_query(F.data.startswith("adm:rcwa:"))
async def cb_admin_wait(cb: CallbackQuery, session, bot):
    try:
        receipt_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None or receipt.status != ReceiptStatus.PENDING:
        await cb.answer("این عملیات قبلاً انجام شده است.", show_alert=True)
        return
    invoice = await order_service.get_invoice(session, receipt.invoice_id)
    await cb.answer("در حالت انتظار قرار گرفت ⏳")
    if invoice is not None:
        await notify(
            "user",
            "⏳ رسید شما در حال بررسی است؛ نتیجه به‌زودی اعلام می‌شود.",
            user_id=invoice.user_id,
        )


@router.callback_query(F.data.startswith("adm:rcrj:"))
async def cb_admin_reject(cb: CallbackQuery, state: FSMContext, session):
    try:
        receipt_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None or receipt.status != ReceiptStatus.PENDING:
        await cb.answer("این عملیات قبلاً انجام شده است.", show_alert=True)
        return

    await state.set_state(RejectStates.waiting_reason)
    await state.update_data(receipt_id=receipt_id)
    await cb.message.answer(
        "❌ دلیل رد رسید را بنویسید (برای ارسال به کاربر). یا /skip:",
    )
    await cb.answer()


@router.message(RejectStates.waiting_reason, F.text)
async def admin_reject_reason(message: Message, state: FSMContext, session, bot):
    data = await state.get_data()
    receipt_id = data.get("receipt_id")
    reason = "" if (message.text or "").strip() == "/skip" else (message.text or "").strip()
    await state.clear()

    receipt = await session.get(Receipt, receipt_id)
    if receipt is None or receipt.status != ReceiptStatus.PENDING:
        await message.answer("این عملیات قبلاً انجام شده است.")
        return

    receipt.status = ReceiptStatus.REJECTED
    receipt.reject_reason = reason or None
    receipt.reviewed_by = message.from_user.id
    receipt.reviewed_at = datetime.now(timezone.utc)

    payment = await session.scalar(
        select(Payment).where(Payment.payment_id == receipt.payment_id)
    )
    if payment:
        payment.status = PaymentStatus.REJECTED

    invoice = await order_service.get_invoice(session, receipt.invoice_id)
    if invoice:
        invoice.status = InvoiceStatus.REJECTED
        await order_service.mark_payment_rejected(session, invoice)

    await session.commit()
    await message.answer("❌ رسید رد شد.")

    if invoice is not None:
        text = (
            "❌ رسید پرداخت شما تأیید نشد.\n"
            "لطفاً در صورت اشتباه بودن رسید، مجدداً پرداخت و رسید صحیح را ارسال کنید."
        )
        if reason:
            text += f"\n\n📝 دلیل: {reason}"
        await notify("user", text, user_id=invoice.user_id)


@router.callback_query(F.data.startswith("adm:prov:"))
async def cb_admin_provision_retry(cb: CallbackQuery, session, bot):
    order_id = cb.data.split(":")[2]
    from app.services import provision_service

    await cb.answer("⏳ در حال تلاش مجدد...")
    ok = await provision_service.provision_order(order_id)
    if ok:
        try:
            await cb.message.edit_text(f"✅ سرویس سفارش <code>{order_id}</code> با موفقیت ساخته شد.")
        except Exception:  # noqa: BLE001
            pass


@router.callback_query(F.data.startswith("adm:refund:"))
async def cb_admin_refund(cb: CallbackQuery, session, bot):
    """عودت مبلغ سفارش به کیف پول کاربر (Idempotent)."""
    order_id = cb.data.split(":")[2]
    order = await order_service.get_order(session, order_id)
    if order is None:
        await cb.answer("سفارش یافت نشد.", show_alert=True)
        return
    if order.status == OrderStatus.REFUNDED:
        await cb.answer("این سفارش قبلاً عودت داده شده است.", show_alert=True)
        return
    if order.status not in (OrderStatus.PAID, OrderStatus.PROVISION_FAILED):
        await cb.answer("این سفارش قابل عودت نیست.", show_alert=True)
        return

    from app.services.referral_service import reverse_commission_for_order

    await reverse_commission_for_order(session, order.order_id)

    if order.paid_by == PaymentMethod.WALLET:
        await wallet_service.adjust_balance(
            session, order.user_id, order.amount, tx_type="REFUND", reference=order.order_id
        )
        note = "مبلغ به کیف پول کاربر برگشت داده شد."
    else:
        note = "پرداخت کارت‌به‌کارت بوده؛ لطفاً مبلغ را دستی به کاربر برگردانید."

    order.status = OrderStatus.REFUNDED
    await session.commit()

    await notify(
        "user",
        f"💵 سفارش <code>{order.order_id}</code> عودت داده شد و مبلغ به کیف پول شما برگشت.",
        user_id=order.user_id,
    )
    try:
        await cb.message.edit_text(f"✅ سفارش <code>{order_id}</code> عودت داده شد.\n{note}")
    except Exception:  # noqa: BLE001
        pass
    await cb.answer("انجام شد ✅")
