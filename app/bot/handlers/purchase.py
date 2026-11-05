"""Purchase flow: plan list → username → invoice → payment."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards import inline as ik
from app.bot.keyboards.inline import kb, btn, btn_url
from app.bot.states import PurchaseStates
from app.db.models import Invoice, InvoiceStatus, ServicePlan, VPNService
from app.services import (
    order_service,
    settings_service,
    user_service,
    wallet_service,
)
from app.utils.formatters import fmt_gb, money
from app.utils.ids import gen_random_username
from app.utils.validators import validate_vpn_username

logger = logging.getLogger(__name__)

router = Router(name="purchase")

SERVICE_LINE = "🌍 مولتی لوکیشن (اقتصادی)"
ASK_SERVICE = "🛍 لطفاً سرویسی که می‌خواهید خریداری کنید را انتخاب کنید:"
SALES_OFF = "⚠️ فروش سرویس در حال حاضر موقتاً متوقف است."


async def _sales_enabled(session) -> bool:
    return await settings_service.get_bool(session, "sales_enabled")


async def show_buy_menu(target_message, session, edit: bool = False):
    plans = (
        await session.execute(
            select(ServicePlan)
            .where(ServicePlan.is_active.is_(True))
            .order_by(ServicePlan.sort_order)
        )
    ).scalars().all()
    sales_on = await _sales_enabled(session)
    text = "سرویس مورد نظر خود را انتخاب کنید:\n\n" + SERVICE_LINE
    markup = ik.plans_kb(plans, sales_on)
    if edit:
        try:
            await target_message.edit_text(text, reply_markup=markup)
            return
        except Exception:  # noqa: BLE001
            pass
    await target_message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "svc:buy")
async def cb_buy(cb: CallbackQuery, session):
    if not await _sales_enabled(session):
        await cb.answer(SALES_OFF, show_alert=True)
        return
    await show_buy_menu(cb.message, session, edit=True)
    await cb.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.startswith("pl:"))
async def cb_plan(cb: CallbackQuery, state: FSMContext, session):
    parts = cb.data.split(":")
    try:
        plan_id = int(parts[1])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر است", show_alert=True)
        return

    plan = await session.get(ServicePlan, plan_id)
    if plan is None or not plan.is_active:
        await cb.answer("این سرویس در دسترس نیست.", show_alert=True)
        return
    if not await _sales_enabled(session):
        await cb.answer(SALES_OFF, show_alert=True)
        return

    await state.set_state(PurchaseStates.waiting_username)
    await state.update_data(plan_id=plan.id, custom=None)
    await cb.message.answer(
        "یک نام کاربری دلخواه ارسال کنید.\n\n"
        "⚠️ نام کاربری باید بدون کاراکترهای اضافه مانند @، فاصله، خط تیره باشد.\n"
        "⚠️ نام کاربری باید انگلیسی باشد.\n\n"
        "✅ مثال: ali12 ، mahdi ، ws1_ksdf",
        reply_markup=ik.username_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "cust:start")
async def cb_custom(cb: CallbackQuery, state: FSMContext, session):
    if not await _sales_enabled(session):
        await cb.answer(SALES_OFF, show_alert=True)
        return
    min_v = await settings_service.get_int(session, "custom_min_volume", 1)
    max_v = await settings_service.get_int(session, "custom_max_volume", 1000)
    await state.set_state(PurchaseStates.waiting_custom_volume)
    await state.update_data(plan_id=None, custom={"volume": None, "days": None})
    await cb.message.answer(
        "📌 حجم دلخواه خود را به گیگابایت وارد کنید:\n\n"
        f"🔹 حداقل: {min_v} گیگابایت\n"
        f"🔹 حداکثر: {max_v} گیگابایت\n\n"
        "فقط عدد ارسال کنید. مثال:\n5",
        reply_markup=ik.custom_volume_kb(),
    )
    await cb.answer()


@router.message(PurchaseStates.waiting_custom_volume, F.text)
async def custom_volume(message: Message, state: FSMContext, session):
    from app.utils.validators import parse_int

    data = await state.get_data()
    custom = data.get("custom") or {}
    min_v = await settings_service.get_int(session, "custom_min_volume", 1)
    max_v = await settings_service.get_int(session, "custom_max_volume", 1000)

    volume = parse_int(message.text or "")
    if volume is None or volume < min_v or volume > max_v:
        await message.answer(
            f"⚠️ فقط عدد صحیح بین {min_v} تا {max_v} مجاز است. دوباره ارسال کنید:",
            reply_markup=ik.custom_volume_kb(),
        )
        return

    min_d = await settings_service.get_int(session, "custom_min_days", 1)
    max_d = await settings_service.get_int(session, "custom_max_days", 365)
    await state.update_data(custom={"volume": volume, "days": None})
    await state.set_state(PurchaseStates.waiting_custom_days)
    await message.answer(
        "📌 مدت زمان دلخواه سرویس را به روز وارد کنید:\n\n"
        f"🔹 حداقل: {min_d} روز\n"
        f"🔹 حداکثر: {max_d} روز\n\n"
        "فقط عدد ارسال کنید. مثال:\n7",
        reply_markup=ik.custom_volume_kb(),
    )


@router.message(PurchaseStates.waiting_custom_days, F.text)
async def custom_days(message: Message, state: FSMContext, session):
    from app.utils.validators import parse_int, calc_custom_price

    data = await state.get_data()
    custom = data.get("custom") or {}
    if custom.get("volume") is None:
        await state.clear()
        await message.answer("فرآیند لغو شد. دوباره تلاش کنید.")
        return

    min_d = await settings_service.get_int(session, "custom_min_days", 1)
    max_d = await settings_service.get_int(session, "custom_max_days", 365)
    days = parse_int(message.text or "")
    if days is None or days < min_d or days > max_d:
        await message.answer(
            f"⚠️ فقط عدد صحیح بین {min_d} تا {max_d} مجاز است. دوباره ارسال کنید:",
            reply_markup=ik.custom_volume_kb(),
        )
        return

    base = await settings_service.get_int(session, "custom_base_price_per_gb", 10000)
    min_price = await settings_service.get_int(session, "custom_min_price", 50000)
    volume = int(custom["volume"])
    price = calc_custom_price(volume, days, base_price_per_gb=base, min_price=min_price)

    await state.update_data(custom={"volume": volume, "days": days, "price": price})
    await state.set_state(PurchaseStates.waiting_username)
    await message.answer(
        f"✅ قیمت محاسبه شد: <b>{money(price)} تومان</b>\n"
        f"({volume} گیگ × {days} روز)\n\n"
        "حالا یک نام کاربری دلخواه ارسال کنید.\n"
        "⚠️ فقط حروف انگلیسی، اعداد و _ (بدون @ و فاصله و خط تیره).",
        reply_markup=ik.username_kb(),
    )


@router.callback_query(F.data == "rnd:username", PurchaseStates.waiting_username)
async def cb_random_username(cb: CallbackQuery, state: FSMContext, session):
    """نام تصادفی امن و یکتا."""
    min_len = await settings_service.get_int(session, "username_min_len", 3)
    max_len = await settings_service.get_int(session, "username_max_len", 32)
    for _ in range(20):
        username = gen_random_username()
        ok, _ = validate_vpn_username(username, min_len, max_len)
        if not ok:
            continue
        exists = await session.scalar(
            select(VPNService.vpn_username).where(VPNService.vpn_username == username)
        )
        if exists is None:
            break
    else:
        await cb.answer("خطا در تولید نام، دوباره تلاش کنید.", show_alert=True)
        return
    await _proceed_with_username(cb.message, state, session, username)
    await cb.answer("🎲 نام تصادفی ساخته شد")


@router.message(PurchaseStates.waiting_username, F.text)
async def username_entered(message: Message, state: FSMContext, session):
    username = (message.text or "").strip()
    min_len = await settings_service.get_int(session, "username_min_len", 3)
    max_len = await settings_service.get_int(session, "username_max_len", 32)

    ok, err = validate_vpn_username(username, min_len, max_len)
    if not ok:
        await message.answer(
            "⚠️ نام کاربری وارد شده معتبر نیست.\n\n"
            "لطفاً فقط از حروف انگلیسی، اعداد و _ استفاده کنید.\n"
            f"طول مجاز: {min_len} تا {max_len} کاراکتر.\n"
            "دوباره ارسال کنید:",
            reply_markup=ik.username_kb(),
        )
        return

    # جلوگیری از نام تکراری
    exists = await session.scalar(
        select(VPNService.vpn_username).where(VPNService.vpn_username == username)
    )
    if exists is not None:
        await message.answer(
            "⚠️ این نام کاربری قبلاً استفاده شده است.\nلطفاً نام دیگری انتخاب کنید.",
            reply_markup=ik.username_kb(),
        )
        return

    await _proceed_with_username(message, state, session, username)


async def _proceed_with_username(target, state: FSMContext, session, username: str):
    data = await state.get_data()
    custom = data.get("custom")
    plan = None
    volume = days = amount = 0
    kind = "PLAN"

    if custom and custom.get("volume"):
        kind = "CUSTOM"
        volume = int(custom["volume"])
        days = int(custom["days"])
        amount = int(custom["price"])
    else:
        plan = await session.get(ServicePlan, data.get("plan_id"))
        if plan is None:
            await state.clear()
            await target.answer("خطا: سرویس یافت نشد. دوباره تلاش کنید.")
            return
        volume = plan.volume_gb
        days = plan.duration_days
        amount = plan.price
        kind = "PLAN"

    user = await user_service.get_by_telegram_id(session, target.chat.id)
    if user is None:
        await state.clear()
        await target.answer("ابتدا /start را بزنید.")
        return

    # Anti-duplicate: سفارش تکراری جدید نساز
    existing_invoice = await order_service.find_recent_pending_invoice(
        session, user.id, username, amount
    )
    if existing_invoice is not None:
        invoice = existing_invoice
        order = await order_service.get_order(session, existing_invoice.order_id)
    else:
        invoice, order = await order_service.create_service_invoice(
            session,
            user.id,
            plan=plan,
            vpn_username=username,
            volume_gb=float(volume),
            duration_days=days,
            amount=amount,
            service_kind=kind,
        )

    await state.clear()
    await show_invoice(target, session, invoice, order, username, volume, days, amount, kind)


async def show_invoice(
    target, session, invoice: Invoice, order, username: str,
    volume: float, days: int, amount: int, kind: str,
):
    balance = await wallet_service.get_balance(session, invoice.user_id)
    plan_name = await _plan_name(session, order.plan_id) if order.plan_id else "سرویس دلخواه"

    text = (
        "📇 پیش‌فاکتور شما:\n\n"
        f"👤 نام کاربری: <code>{username}</code>\n"
        f"🔐 نام سرویس: {plan_name}\n"
        f"📆 مدت اعتبار: {days} روز\n"
        f"💶 قیمت: {money(amount)} تومان\n"
        f"👥 حجم اکانت: {fmt_gb(volume)}\n"
        f"💵 موجودی کیف پول شما: {money(balance)} تومان\n\n"
        f"💰 سفارش شما آماده پرداخت است.\n"
        f"🧾 شناسه فاکتور: <code>{invoice.invoice_id}</code>"
    )
    wallet_ok = balance >= amount
    await target.answer(text, reply_markup=ik.invoice_kb(invoice.invoice_id, balance, amount, wallet_ok))


async def _plan_name(session, plan_id: int) -> str:
    plan = await session.get(ServicePlan, plan_id)
    return plan.name if plan else "سرویس"


@router.callback_query(F.data.startswith("inv:"))
async def cb_invoice_view(cb: CallbackQuery, session, state: FSMContext):
    invoice_id = cb.data.split(":", 1)[1]
    invoice = await order_service.get_invoice(session, invoice_id)
    if invoice is None or invoice.user_id != await _user_id(session, cb.from_user.id):
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return
    if invoice.status != InvoiceStatus.PENDING:
        await cb.answer("این فاکتور دیگر معتبر نیست.", show_alert=True)
        return
    order = await order_service.get_order(session, invoice.order_id)
    balance = await wallet_service.get_balance(session, invoice.user_id)
    await show_invoice(
        cb.message, session, invoice, order,
        order.vpn_username, order.volume_gb, order.duration_days, order.amount, order.service_kind,
    )
    await cb.answer()


async def _user_id(session, telegram_id: int) -> int:
    user = await user_service.get_by_telegram_id(session, telegram_id)
    return user.id if user else -1


@router.callback_query(F.data.startswith("pay:wallet:"))
async def cb_pay_wallet(cb: CallbackQuery, session, state: FSMContext):
    """پرداخت از کیف پول + provisioning."""
    invoice_id = cb.data.split(":")[2]
    user = await user_service.get_by_telegram_id(session, cb.from_user.id)
    invoice = await order_service.get_invoice(session, invoice_id)
    if user is None or invoice is None or invoice.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    ok, err = await order_service.pay_with_wallet(session, invoice)
    if not ok:
        balance = await wallet_service.get_balance(session, user.id)
        if "کافی نیست" in err:
            await cb.message.answer(
                "موجودی کیف پول شما برای این سفارش کافی نیست.\n"
                "لطفاً ابتدا کیف پول خود را شارژ کنید.",
                reply_markup=ik.kb(
                    [
                        [ik.btn("💰 افزایش موجودی", "wallet:dep")],
                        [ik.btn("🔙 بازگشت", f"inv:{invoice_id}")],
                    ]
                ),
            )
        else:
            await cb.message.answer(f"⚠️ {err}")
        await cb.answer()
        return

    await session.commit()  # قفل تراکنش مالی قبل از provisioning

    from app.services import provision_service

    await cb.answer("✅ پرداخت موفق! در حال ساخت سرویس...")
    await cb.message.answer("⏳ در حال ایجاد سرویس شما...")
    await provision_service.provision_order(invoice.order_id)


@router.callback_query(F.data.startswith("pay:card:"))
async def cb_pay_card(cb: CallbackQuery, session):
    invoice_id = cb.data.split(":")[2]
    invoice = await order_service.get_invoice(session, invoice_id)
    user = await user_service.get_by_telegram_id(session, cb.from_user.id)
    if invoice is None or user is None or invoice.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return
    if invoice.status != InvoiceStatus.PENDING:
        await cb.answer("این فاکتور قبلاً پردازش شده است.", show_alert=True)
        return

    from app.bot.handlers.receipts import send_card_info

    await send_card_info(cb.message, session, invoice)
    await cb.answer()
