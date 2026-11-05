"""Admin: broadcast."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.bot.states import AdminStates
from app.db.models import User

logger = logging.getLogger(__name__)

router = Router(name="admin_broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:bcast")
async def cb_broadcast_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="broadcast")
    await cb.message.answer(
        "📨 پیام همگانی را بفرستید (متن، عکس با کپشن یا فایل):\n\n⚠️ برای همه کاربران ارسال می‌شود."
    )
    await cb.answer()


@router.message(AdminStates.waiting_value, F.photo)
async def broadcast_photo(message: Message, state: FSMContext, session):
    data = await state.get_data()
    if data.get("field") != "broadcast":
        return
    await state.update_data(bcast_file_id=message.photo[-1].file_id, bcast_type="PHOTO")
    await message.answer(
        "پیش‌نمایش بالا ارسال شد. ✅ ارسال کن؟",
        reply_markup=ik.broadcast_confirm_kb(),
    )


@router.message(AdminStates.waiting_value, F.text)
async def admin_text_input(message: Message, state: FSMContext, session, bot):
    """هندلر مرکزی ورودی‌های ادمین — بر اساس field مسیریابی می‌کند."""
    data = await state.get_data()
    field = data.get("field")
    if not field:
        return
    value = (message.text or "").strip()
    admin_id = message.from_user.id

    from app.bot.handlers.admin import prices as admin_prices
    from app.services import settings_service, user_service, wallet_service
    from app.utils.formatters import money
    from app.utils.validators import parse_float, parse_int, parse_signed_int, validate_card_number

    state_data = dict(data)

    async def finish(text: str):
        await state.clear()
        await message.answer(text)

    # ---------- broadcast ----------
    if field == "broadcast":
        await state.update_data(bcast_text=value, bcast_type="TEXT")
        await message.answer(
            "پیش‌نمایش:\n\n" + value[:1000] + "\n\n✅ ارسال کن؟",
            reply_markup=ik.broadcast_confirm_kb(),
        )
        return

    # ---------- user search ----------
    if field == "user_search":
        tg_id = parse_int(value)
        if tg_id is None:
            await message.answer("⚠️ شناسه عددی نامعتبر است. دوباره بفرستید:")
            return
        await state.clear()
        from app.bot.handlers.admin.users_admin import show_user_card

        await show_user_card(message, session, tg_id)
        return

    # ---------- wallet adjust ----------
    if field == "wallet_adjust":
        amount = parse_signed_int(value)
        tg_id = state_data.get("target_user")
        if amount is None or not tg_id:
            await message.answer("⚠️ مقدار نامعتبر. مثال: 50000 یا -20000")
            return
        user = await user_service.get_by_telegram_id(session, int(tg_id))
        if user is None:
            await finish("کاربر یافت نشد.")
            return
        balance = await wallet_service.adjust_balance(
            session, user.id, amount, tx_type="ADMIN_ADJUST", reference=f"admin-{admin_id}"
        )
        if balance is None:
            await message.answer("⚠️ کاهش بیش از موجودی مجاز نیست.")
            return
        from app.bot.handlers.admin.panel import _audit

        _audit(session, admin_id, "wallet_adjust", f"user:{tg_id}", str(amount))
        await state.clear()
        await message.answer(
            f"✅ انجام شد. موجودی جدید کاربر: {money(balance)} تومان"
        )
        await wallet_service  # keep import used
        return

    # ---------- admin add ----------
    if field == "admin_add":
        tg_id = parse_int(value)
        if tg_id is None:
            await message.answer("⚠️ شناسه نامعتبر. دوباره بفرستید:")
            return
        exists = await session.scalar(select(Admin).where(Admin.telegram_id == tg_id))
        if exists:
            await finish("این کاربر از قبل ادمین است.")
            return
        session.add(Admin(telegram_id=tg_id, role=UserRole.ADMIN, added_by=admin_id))
        register_admin(tg_id)
        from app.bot.handlers.admin.panel import _audit

        _audit(session, admin_id, "admin_add", f"admin:{tg_id}")
        await finish(f"✅ ادمین <code>{tg_id}</code> اضافه شد.")
        return

    # ---------- force join ----------
    if field == "fj_channel":
        await settings_service.set_setting(session, "force_join_channel", value)
        from app.bot.handlers.admin.panel import _audit

        _audit(session, admin_id, "fj_channel", details=value)
        await finish(f"✅ کانال ذخیره شد: {value}")
        return

    if field == "fj_url":
        if not value.startswith("http"):
            await message.answer("⚠️ لینک باید با http شروع شود:")
            return
        await settings_service.set_setting(session, "force_join_url", value)
        await finish("✅ لینک ذخیره شد.")

        return

    # ---------- card ----------
    if field == "card_number":
        if not validate_card_number(value):
            await message.answer("⚠️ شماره کارت معتبر نیست (۱۶ رقم با الگوریتم Luhn). دوباره بفرستید:")
            return
        await settings_service.set_setting(session, "card_number", value.replace(" ", ""))
        from app.bot.handlers.admin.panel import _audit

        _audit(session, admin_id, "card_number")
        await finish("✅ شماره کارت ذخیره شد.")
        return

    if field == "card_holder":
        await settings_service.set_setting(session, "card_holder", value)
        await finish(f"✅ صاحب کارت ذخیره شد: {value}")

        return

    # ---------- numeric settings ----------
    numeric_fields = {
        "referral_percent": ("referral_percent", 0, 100, parse_int),
        "trial_volume_gb": ("trial_volume_gb", 0.001, 100, parse_float),
        "trial_days": ("trial_days", 1, 365, parse_int),
        "custom_base_price_per_gb": ("custom_base_price_per_gb", 0, 10_000_000, parse_int),
        "custom_min_price": ("custom_min_price", 0, 10_000_000, parse_int),
        "custom_min_volume": ("custom_min_volume", 1, 10000, parse_int),
        "custom_max_volume": ("custom_max_volume", 1, 10000, parse_int),
        "custom_min_days": ("custom_min_days", 1, 3650, parse_int),
        "custom_max_days": ("custom_max_days", 1, 3650, parse_int),
        "wallet_min_deposit": ("wallet_min_deposit", 1000, 10_000_000_000, parse_int),
        "wallet_max_deposit": ("wallet_max_deposit", 1000, 10_000_000_000, parse_int),
        "plan_price": ("plan_price", 0, 10_000_000_000, parse_int),
        "plan_volume": ("plan_volume", 0.01, 100000, parse_float),
        "plan_days": ("plan_days", 1, 3650, parse_int),
        "panel_mode": ("panel_mode", None, None, None),
    }

    if field in numeric_fields:
        key, lo, hi, parser = numeric_fields[field]
        if key == "panel_mode":
            val = value.lower()
            if val not in ("mock", "pasargad"):
                await message.answer("⚠️ فقط mock یا pasargad:")
                return
            await settings_service.set_setting(session, "panel_mode", val)
            await finish(f"✅ حالت پنل: {val}")
            return

        parsed = parser(value)
        if parsed is None or (lo is not None and not (lo <= parsed <= hi)):
            await message.answer(f"⚠️ مقدار نامعتبر (بازه {lo} تا {hi}). دوباره بفرستید:")
            return

        # فیلدهای پلن
        if field.startswith("plan_"):
            plan_id = state_data.get("plan_id")
            plan = await session.get(ServicePlan, int(plan_id)) if plan_id else None
            if plan is None:
                await finish("سرویس یافت نشد.")
                return
            if field == "plan_price":
                plan.price = int(parsed)
            elif field == "plan_volume":
                plan.volume_gb = float(parsed)
            else:
                plan.duration_days = int(parsed)
            from app.bot.handlers.admin.panel import _audit

            _audit(session, admin_id, f"plan_edit:{field}", f"plan:{plan_id}", str(parsed))
            await state.clear()
            await message.answer(f"✅ ذخیره شد: {plan.name}")
            return

        await settings_service.set_setting(session, key, str(parsed))
        from app.bot.handlers.admin.panel import _audit

        _audit(session, admin_id, f"set:{key}", details=str(parsed))
        await finish(f"✅ ذخیره شد: {key} = {parsed}")
        return

    # ---------- add service wizard ----------
    if field.startswith("add_"):
        handled = False
        if field == "add_name":
            handled = await admin_prices.add_service_next(message, state, session, "add_name", value)
        elif field == "add_volume":
            parsed = parse_float(value)
            if parsed is None or parsed <= 0:
                await message.answer("⚠️ عدد معتبر بفرستید:")
                return
            handled = await admin_prices.add_service_next(message, state, session, "add_volume", parsed)
        elif field == "add_days":
            parsed = parse_int(value)
            if parsed is None or parsed <= 0:
                await message.answer("⚠️ عدد معتبر بفرستید:")
                return
            handled = await admin_prices.add_service_next(message, state, session, "add_days", parsed)
        elif field == "add_price":
            parsed = parse_int(value)
            if parsed is None or parsed < 0:
                await message.answer("⚠️ عدد معتبر بفرستید:")
                return
            handled = await admin_prices.add_service_next(message, state, session, "add_price", parsed)
        elif field == "add_active":
            handled = await admin_prices.add_service_next(message, state, session, "add_active", value)
        if handled:
            return

    # ---------- tutorials ----------
    if field == "tut_cat":
        from app.bot.handlers.admin.tutorials_admin import create_tutorial_step

        await create_tutorial_step(message, state, session, "tut_cat", value)
        return
    if field == "tut_title":
        from app.bot.handlers.admin.tutorials_admin import create_tutorial_step

        await create_tutorial_step(message, state, session, "tut_title", value)
        return
    if field == "tut_content":
        from app.bot.handlers.admin.tutorials_admin import create_tutorial_step

        await create_tutorial_step(message, state, session, "tut_content", value)
        return
    if field == "tut_edit":
        from app.bot.handlers.admin.tutorials_admin import edit_tutorial_content

        await edit_tutorial_content(message, state, session, value)
        return

    await state.clear()
    await message.answer("عملیات لغو شد.")


from app.db.models import ServicePlan, UserRole  # noqa: E402


@router.callback_query(F.data.startswith("adm:bcast:"))
async def cb_broadcast_confirm(cb: CallbackQuery, state: FSMContext, session, bot):
    action = cb.data.split(":")[2]
    if action == "cancel":
        await state.clear()
        await cb.message.answer("❌ ارسال همگانی لغو شد.")
        await cb.answer()
        return
    if action != "go":
        await cb.answer()
        return

    data = await state.get_data()
    await state.clear()
    btype = data.get("bcast_type")
    text = data.get("bcast_text")
    file_id = data.get("bcast_file_id")

    user_ids = (
        await session.execute(select(User.telegram_id).where(User.status == "ACTIVE"))
    ).scalars().all()

    await cb.answer(f"⏳ در حال ارسال به {len(user_ids)} کاربر...")

    from app.services.notification_service import send_safe

    ok = fail = 0

    async def send_one(chat_id: int) -> bool:
        if btype == "PHOTO" and file_id:
            return await send_safe(bot, chat_id, text or "", ) if False else await _send_photo(bot, chat_id, file_id, text or "")
        return await send_safe(bot, chat_id, text or "")

    async def _send_photo(bot_, chat_id, file_id_, caption_):
        try:
            await bot_.send_photo(chat_id, file_id_, caption=caption_ or None)
            return True
        except Exception:  # noqa: BLE001
            return False

    for uid in user_ids:
        try:
            success = await send_one(uid)
        except Exception:  # noqa: BLE001
            success = False
        ok += 1 if success else 0
        fail += 0 if success else 1
        import asyncio as _aio

        await _aio.sleep(0.05)

    from app.bot.handlers.admin.panel import _audit

    _audit(session, cb.from_user.id, "broadcast", details=f"ok:{ok} fail:{fail}")
    await cb.message.answer(f"📨 ارسال همگانی تمام شد.\n✅ موفق: {ok}\n❌ ناموفق: {fail}")
