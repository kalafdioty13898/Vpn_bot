"""Wallet menu + deposit flow."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.filters import is_admin_id
from app.bot.handlers.receipts import send_card_info
from app.bot.keyboards import inline as ik
from app.bot.keyboards.reply import cancel_kb, main_menu_kb, CANCEL
from app.bot.states import WalletStates
from app.db.models import InvoiceStatus, InvoiceType
from app.services import order_service, settings_service, user_service
from app.utils.formatters import money
from app.utils.validators import parse_int

logger = logging.getLogger(__name__)

router = Router(name="wallet")


@router.callback_query(F.data == "wallet:menu")
async def cb_wallet_menu(cb: CallbackQuery, session):
    await _show_wallet(cb.message, cb.from_user.id, session)
    await cb.answer()


@router.message(F.text == "💰 کیف پول")
async def menu_wallet(message: Message, session):
    await _show_wallet(message, message.from_user.id, session)


async def _show_wallet(target, telegram_id: int, session):
    user = await user_service.get_by_telegram_id(session, telegram_id)
    if user is None:
        await target.answer("ابتدا /start را بزنید.")
        return

    balance = await user_service.get_wallet_balance(session, user.id)
    services_count = await user_service.services_count(session, user.id)
    invoices_count = await user_service.paid_invoices_count(session, user.id)
    referrals_count = await user_service.referrals_count(session, user.id)

    from app.utils.formatters import jalali

    phone = user.phone_number if user.phone_number else "🔴 ارسال نشده است 🔴"
    text = (
        "🤖 اطلاعات حساب کاربری شما:\n\n"
        f"🪪 آیدی عددی: <code>{user.telegram_id}</code>\n"
        f"👤 نام: {user.first_name or 'کاربر گرامی'}\n"
        f"📱 شماره تماس: {phone}\n"
        f"⌚️ زمان ثبت‌نام: {jalali(user.created_at)}\n"
        f"💰 موجودی: {money(balance)} تومان\n"
        f"🛒 تعداد سرویس‌های خریداری‌شده: {services_count} عدد\n"
        f"📑 تعداد فاکتورهای پرداخت‌شده: {invoices_count} عدد\n"
        f"🤝 تعداد زیرمجموعه‌های شما: {referrals_count} نفر"
    )
    await target.answer(text, reply_markup=ik.wallet_menu_kb())


@router.callback_query(F.data == "wal:cancel")
async def cb_wallet_cancel(cb: CallbackQuery, state: FSMContext):
    """دکمه «❌ لغو» در کیبورد شارژ کیف پول."""
    await state.clear()
    await cb.answer("✅ لغو شد")
    try:
        await cb.message.answer(
            "✅ عملیات لغو شد.\n\n🏠 منوی اصلی:",
            reply_markup=main_menu_kb(is_admin_id(cb.from_user.id)),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "wallet:dep")
async def cb_deposit(cb: CallbackQuery, state: FSMContext, session):
    min_amount = await settings_service.get_int(session, "wallet_min_deposit", 20000)
    max_amount = await settings_service.get_int(session, "wallet_max_deposit", 100000000)
    await state.set_state(WalletStates.waiting_amount)
    await cb.message.answer(
        "💸 مبلغ را به تومان وارد کنید:\n\n"
        f"✅ حداقل مبلغ {money(min_amount)} تومان\n"
        f"✅ حداکثر مبلغ {money(max_amount)} تومان\n\n"
        "یا از دکمه‌های سریع استفاده کنید:",
        reply_markup=ik.deposit_kb(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("dep:"))
async def cb_quick_deposit(cb: CallbackQuery, state: FSMContext, session):
    amount = int(cb.data.split(":")[1])
    await _create_deposit(cb.message, state, session, cb.from_user.id, amount)
    await cb.answer()


@router.message(WalletStates.waiting_amount, F.text)
async def deposit_amount(message: Message, state: FSMContext, session):
    if (message.text or "").strip() == CANCEL:
        await state.clear()
        await message.answer("✅ لغو شد.")
        return

    min_amount = await settings_service.get_int(session, "wallet_min_deposit", 20000)
    max_amount = await settings_service.get_int(session, "wallet_max_deposit", 100000000)
    amount = parse_int(message.text or "")
    if amount is None or amount < min_amount or amount > max_amount:
        await message.answer(
            f"⚠️ مبلغ باید عدد صحیح بین {money(min_amount)} و {money(max_amount)} تومان باشد.\n"
            "دوباره ارسال کنید:",
            reply_markup=ik.deposit_kb(),
        )
        return

    await _create_deposit(message, state, session, message.from_user.id, amount)


async def _create_deposit(target, state: FSMContext, session, telegram_id: int, amount: int):
    user = await user_service.get_by_telegram_id(session, telegram_id)
    if user is None:
        await state.clear()
        await target.answer("ابتدا /start را بزنید.")
        return

    invoice = await order_service.create_wallet_deposit_invoice(session, user.id, amount)
    await state.clear()
    await target.answer(
        f"✅ فاکتور شارژ کیف پول ساخته شد.\n🧾 شناسه: <code>{invoice.invoice_id}</code>\n"
        f"💰 مبلغ: {money(amount)} تومان"
    )
    await send_card_info(target, session, invoice)
