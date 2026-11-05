"""Admin: user search, wallet adjust, ban, admins management."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import func, select

from app.bot.filters import IsAdmin, is_admin_id, register_admin, unregister_admin
from app.bot.keyboards import inline as ik
from app.bot.states import AdminStates
from app.db.models import Admin, User, UserRole, VPNService
from app.services import user_service, wallet_service
from app.utils.formatters import jalali, money

router = Router(name="admin_users")
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:usearch")
async def cb_user_search(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="user_search")
    await cb.message.answer("🔍 شناسه عددی کاربر (Telegram ID) را بفرستید:")
    await cb.answer()


@router.callback_query(F.data.startswith("adm:u:"))
async def cb_user_actions(cb: CallbackQuery, state: FSMContext, session):
    parts = cb.data.split(":")
    try:
        tg_id = int(parts[2])
        action = parts[3] if len(parts) > 3 else ""
    except (ValueError, IndexError):
        await cb.answer("نامعتبر", show_alert=True)
        return

    user = await user_service.get_by_telegram_id(session, tg_id)
    if user is None:
        await cb.answer("کاربر یافت نشد.", show_alert=True)
        return

    if action == "wal":
        await state.set_state(AdminStates.waiting_value)
        await state.update_data(field="wallet_adjust", target_user=tg_id)
        balance = await user_service.get_wallet_balance(session, user.id)
        await cb.message.answer(
            f"💰 موجودی فعلی کاربر: {money(balance)} تومان\n\n"
            "مبلغ تغییر را بفرستید (مثبت = افزایش، منفی = کاهش):\n"
            "مثال: 50000 یا -20000"
        )
        await cb.answer()
        return

    if action in ("ban", "unban"):
        banned = action == "ban"
        ok = await user_service.set_banned(session, tg_id, banned)
        from app.bot.handlers.admin.panel import _audit

        _audit(session, cb.from_user.id, "user_ban" if banned else "user_unban", f"user:{tg_id}")
        await cb.answer("انجام شد ✅" if ok else "خطا", show_alert=not ok)
        await show_user_card(cb.message, session, tg_id)
        return

    await show_user_card(cb.message, session, tg_id)
    await cb.answer()


async def show_user_card(target, session, tg_id: int):
    user = await user_service.get_by_telegram_id(session, tg_id)
    if user is None:
        await target.answer("کاربر یافت نشد.")
        return
    balance = await user_service.get_wallet_balance(session, user.id)
    services = await user_service.services_count(session, user.id)
    refs = await user_service.referrals_count(session, user.id)
    text = (
        "👤 اطلاعات کاربر:\n\n"
        f"🆔 Telegram ID: <code>{user.telegram_id}</code>\n"
        f"👤 نام: {user.first_name or '-'} {user.last_name or ''}\n"
        f"🔗 یوزرنیم: @{user.telegram_username or '-'}\n"
        f"📅 ثبت‌نام: {jalali(user.created_at)}\n"
        f"💰 موجودی: {money(balance)} تومان\n"
        f"🛍 سرویس‌های فعال: {services}\n"
        f"🤝 زیرمجموعه‌ها: {refs}\n"
        f"وضعیت: {'🚫 مسدود' if user.status == 'BANNED' else '🟢 فعال'}\n"
        f"🎁 تست رایگان: {'✅ گرفته' if user.free_trial_used else '❌ نگرفته'}"
    )
    await target.answer(text, reply_markup=ik.user_card_kb(tg_id, user.status == "BANNED"))


# ---------------- Admins management (SUPER_ADMIN only) ----------------
@router.callback_query(F.data == "adm:admins")
async def cb_admins_list(cb: CallbackQuery, session):
    from app.config import settings

    if cb.from_user.id not in settings.admin_ids[:1]:
        # فقط سوپر ادمین (اولین ID در env)
        pass  # نمایش بدون اجازه حذف

    rows = (await session.execute(select(Admin))).scalars().all()
    text = "👥 ادمین‌ها:\n\n" + "\n".join(
        f"• <code>{a.telegram_id}</code> — {a.role}" for a in rows
    ) or "هیچ ادمینی ثبت نشده."
    await cb.message.answer(text, reply_markup=ik.admin_list_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:admadd")
async def cb_admin_add(cb: CallbackQuery, state: FSMContext):
    from app.config import settings

    if cb.from_user.id not in settings.admin_ids[:1]:
        await cb.answer("فقط سوپر ادمین می‌تواند ادمین اضافه کند.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="admin_add")
    await cb.message.answer("➕ شناسه عددی ادمین جدید را بفرستید:")
    await cb.answer()
