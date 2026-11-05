"""Admin settings: toggles, force join, card, referral percent, trial, custom pricing, deposit limits.
متن‌های ورودی از طریق AdminStates.waiting_value + data['field'] مدیریت می‌شوند (input_router).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.services import settings_service
from app.utils.formatters import money

router = Router(name="admin_settings")
router.callback_query.filter(IsAdmin())


def _audit(session: AsyncSession, admin_id: int, action: str, details: str = ""):
    from app.db.models import AuditLog

    session.add(AuditLog(admin_id=admin_id, action=action, details=details[:1000]))


# ---------------- Toggles ----------------
@router.callback_query(F.data.startswith("adm:tg:"))
async def cb_toggle(cb: CallbackQuery, session):
    key_map = {
        "bot": "bot_enabled",
        "sales": "sales_enabled",
        "ref": "referral_enabled",
        "trial": "trial_enabled",
    }
    key = key_map.get(cb.data.split(":")[2])
    if not key:
        await cb.answer("نامعتبر", show_alert=True)
        return
    new_value = await settings_service.toggle(session, key)
    _audit(session, cb.from_user.id, f"toggle:{key}", str(new_value))
    await cb.answer(f"✅ {'روشن' if new_value else 'خاموش'} شد")
    from app.bot.handlers.admin.panel import show_panel

    await show_panel(cb.message, session, edit=True)


# ---------------- Force join ----------------
@router.callback_query(F.data == "adm:fj")
async def cb_force_join_menu(cb: CallbackQuery, session):
    enabled = await settings_service.get_bool(session, "force_join_enabled")
    channel = await settings_service.get_setting(session, "force_join_channel")
    url = await settings_service.get_setting(session, "force_join_url")
    text = (
        "📢 تنظیم کانال جوین اجباری\n\n"
        f"وضعیت: {'🟢 روشن' if enabled else '🔴 خاموش'}\n"
        f"کانال: {channel or '— تنظیم نشده —'}\n"
        f"لینک: {url or '— از یوزرنیم کانال ساخته می‌شود —'}\n\n"
        "⚠️ ربات باید در کانال ادمین باشد تا عضویت بررسی شود."
    )
    await cb.message.answer(text, reply_markup=ik.force_join_admin_kb(enabled, channel))
    await cb.answer()


@router.callback_query(F.data == "adm:fj:toggle")
async def cb_fj_toggle(cb: CallbackQuery, session):
    new_value = await settings_service.toggle(session, "force_join_enabled")
    _audit(session, cb.from_user.id, "toggle:force_join", str(new_value))
    enabled = new_value
    channel = await settings_service.get_setting(session, "force_join_channel")
    await cb.message.answer(
        f"📢 عضویت اجباری: {'🟢 روشن' if enabled else '🔴 خاموش'}",
        reply_markup=ik.force_join_admin_kb(enabled, channel),
    )
    await cb.answer("انجام شد")


@router.callback_query(F.data == "adm:fj:ch")
async def cb_fj_channel(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="fj_channel")
    await cb.message.answer("📢 یوزرنیم کانال را بفرستید (مثال: @mychannel یا -1001234567890):")
    await cb.answer()


@router.callback_query(F.data == "adm:fj:url")
async def cb_fj_url(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="fj_url")
    await cb.message.answer("🔗 لینک دعوت کانال را بفرستید (https://t.me/...):")
    await cb.answer()


@router.callback_query(F.data == "adm:fj:test")
async def cb_fj_test(cb: CallbackQuery, session, bot):
    channel = await settings_service.get_setting(session, "force_join_channel")
    if not channel:
        await cb.answer("کانال تنظیم نشده است.", show_alert=True)
        return
    try:
        me = await bot.get_chat_member(chat_id=channel, user_id=cb.from_user.id)
        status = me.status
        text = f"🔍 وضعیت عضویت شما: {status}\n"
        try:
            chat = await bot.get_chat(chat_id=channel)
            text += f"📌 عنوان کانال: {chat.title}\nنوع: {chat.type}"
        except Exception:  # noqa: BLE001
            pass
        await cb.message.answer(text)
        await cb.answer("تست انجام شد")
    except Exception as e:  # noqa: BLE001
        await cb.answer(f"❌ خطا: {type(e).__name__} — احتمالاً ربات ادمین کانال نیست.", show_alert=True)


# ---------------- Card ----------------
@router.callback_query(F.data == "adm:card")
async def cb_card_menu(cb: CallbackQuery, session):
    card = await settings_service.get_setting(session, "card_number")
    holder = await settings_service.get_setting(session, "card_holder")
    text = (
        "💳 اطلاعات پرداخت\n\n"
        f"شماره کارت: {card or '— تنظیم نشده —'}\n"
        f"صاحب کارت: {holder or '— تنظیم نشده —'}"
    )
    await cb.message.answer(text, reply_markup=ik.card_admin_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:card:num")
async def cb_card_number(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="card_number")
    await cb.message.answer("💳 شماره کارت جدید را بفرستید (۱۶ رقم):")
    await cb.answer()


@router.callback_query(F.data == "adm:card:hold")
async def cb_card_holder(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="card_holder")
    await cb.message.answer("👤 نام صاحب کارت را بفرستید:")
    await cb.answer()


# ---------------- Referral percent ----------------
@router.callback_query(F.data == "adm:refpct")
async def cb_ref_percent(cb: CallbackQuery, session, state):
    from app.bot.states import AdminStates

    current = await settings_service.get_int(session, "referral_percent", 5)
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="referral_percent")
    await cb.message.answer(
        f"🤝 درصد پورسانت فعلی: {current}٪\n\nدرصد جدید (0 تا 100) را بفرستید:"
    )
    await cb.answer()


# ---------------- Trial settings ----------------
@router.callback_query(F.data == "adm:trial")
async def cb_trial_menu(cb: CallbackQuery, session):
    vol = await settings_service.get_float(session, "trial_volume_gb", 0.01)
    days = await settings_service.get_int(session, "trial_days", 1)
    enabled = await settings_service.get_bool(session, "trial_enabled")
    text = (
        "🎁 تنظیم تست رایگان\n\n"
        f"وضعیت: {'🟢 روشن' if enabled else '🔴 خاموش'}\n"
        f"📦 حجم: {vol} GB\n"
        f"📆 مدت: {days} روز"
    )
    await cb.message.answer(text, reply_markup=ik.trial_admin_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:trial:vol")
async def cb_trial_vol(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="trial_volume_gb")
    await cb.message.answer("📦 حجم تست را به گیگابایت بفرستید (مثال: 0.01):")
    await cb.answer()


@router.callback_query(F.data == "adm:trial:days")
async def cb_trial_days(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="trial_days")
    await cb.message.answer("📆 مدت تست را به روز بفرستید:")
    await cb.answer()


# ---------------- Custom service pricing ----------------
@router.callback_query(F.data == "adm:custp")
async def cb_custom_menu(cb: CallbackQuery, session):
    base = await settings_service.get_int(session, "custom_base_price_per_gb", 10000)
    minp = await settings_service.get_int(session, "custom_min_price", 50000)
    minv = await settings_service.get_int(session, "custom_min_volume", 1)
    maxv = await settings_service.get_int(session, "custom_max_volume", 1000)
    mind = await settings_service.get_int(session, "custom_min_days", 1)
    maxd = await settings_service.get_int(session, "custom_max_days", 365)
    text = (
        "✂️ قیمت‌گذاری سرویس دلخواه\n\n"
        f"قیمت پایه هر GB: {money(base)} تومان\n"
        f"حداقل قیمت: {money(minp)} تومان\n"
        f"حداقل/حداکثر حجم: {minv} / {maxv} گیگ\n"
        f"حداقل/حداکثر روز: {mind} / {maxd} روز\n\n"
        "فرمول: قیمت هر گیگ × حجم × روز ÷ ۳۰ (با حداقل قیمت)"
    )
    await cb.message.answer(text, reply_markup=ik.custom_price_admin_kb())
    await cb.answer()


_FIELDS = {
    "adm:custp:base": ("custom_base_price_per_gb", "قیمت پایه هر گیگ (تومان):"),
    "adm:custp:min": ("custom_min_price", "حداقل قیمت (تومان):"),
    "adm:custp:minv": ("custom_min_volume", "حداقل حجم (گیگ):"),
    "adm:custp:maxv": ("custom_max_volume", "حداکثر حجم (گیگ):"),
    "adm:custp:mind": ("custom_min_days", "حداقل روز:"),
    "adm:custp:maxd": ("custom_max_days", "حداکثر روز:"),
    "adm:dep:min": ("wallet_min_deposit", "حداقل شارژ کیف پول (تومان):"),
    "adm:dep:max": ("wallet_max_deposit", "حداکثر شارژ کیف پول (تومان):"),
}


@router.callback_query(F.data.startswith("adm:custp:"))
async def cb_custom_field(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    field, prompt = _FIELDS[cb.data]
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field=field)
    await cb.message.answer(f"مقدار جدید را بفرستید:\n{prompt}")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:dep:"))
async def cb_deposit_field(cb: CallbackQuery, state):
    from app.bot.states import AdminStates

    field, prompt = _FIELDS[cb.data]
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field=field)
    await cb.message.answer(f"مقدار جدید را بفرستید:\n{prompt}")
    await cb.answer()


@router.callback_query(F.data == "adm:dep")
async def cb_dep_menu(cb: CallbackQuery, session):
    min_d = await settings_service.get_int(session, "wallet_min_deposit", 20000)
    max_d = await settings_service.get_int(session, "wallet_max_deposit", 100000000)
    text = (
        "💰 حدود شارژ کیف پول\n\n"
        f"حداقل: {money(min_d)} تومان\n"
        f"حداکثر: {money(max_d)} تومان"
    )
    await cb.message.answer(text, reply_markup=ik.deposit_admin_kb())
    await cb.answer()
