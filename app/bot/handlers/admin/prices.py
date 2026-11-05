"""Admin: price management + add service."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.bot.states import AdminStates
from app.db.models import ServicePlan
from app.services import settings_service
from app.utils.formatters import money

router = Router(name="admin_prices")
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:prices")
async def cb_prices(cb: CallbackQuery, session):
    plans = (
        await session.execute(select(ServicePlan).order_by(ServicePlan.sort_order))
    ).scalars().all()
    if not plans:
        await cb.message.answer("سرویسی ثبت نشده است. از «➕ سرویس جدید» اضافه کنید.")
        await cb.answer()
        return
    rows = [
        [
            ik.btn(
                f"{'🟢' if p.is_active else '🔴'} {p.name} | {money(p.price)} | {p.volume_gb:g}GB | {p.duration_days}d",
                f"adm:pl:{p.id}",
            )
        ]
        for p in plans
    ]
    rows.append([ik.btn("➕ سرویس جدید", "adm:pladd")])
    rows.append([ik.btn("🔙 بازگشت به پنل", "adm:menu")])
    await cb.message.answer("🛍 مدیریت قیمت سرویس‌ها:", reply_markup=ik.kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:pl:"))
async def cb_plan_menu(cb: CallbackQuery, state: FSMContext, session):
    parts = cb.data.split(":")
    try:
        plan_id = int(parts[2])
    except (ValueError, IndexError):
        await cb.answer("نامعتبر", show_alert=True)
        return

    plan = await session.get(ServicePlan, plan_id)
    if plan is None:
        await cb.answer("یافت نشد", show_alert=True)
        return

    action = parts[3] if len(parts) > 3 else ""

    if action == "toggle":
        plan.is_active = not plan.is_active
        from app.bot.handlers.admin.panel import _audit

        _audit(session, cb.from_user.id, "plan_toggle", f"plan:{plan_id}", str(plan.is_active))
        await cb.answer("انجام شد ✅")
        await cb.message.answer(
            f"وضعیت {plan.name}: {'🟢 فعال' if plan.is_active else '🔴 غیرفعال'}",
            reply_markup=ik.plan_admin_kb(plan.id, plan.is_active),
        )
        return

    if action in ("price", "vol", "days"):
        field = {"price": "plan_price", "vol": "plan_volume", "days": "plan_days"}[action]
        await state.set_state(AdminStates.waiting_value)
        await state.update_data(field=field, plan_id=plan_id)
        prompt = {
            "price": f"💰 قیمت جدید برای {plan.name} (تومان):",
            "vol": f"📦 حجم جدید برای {plan.name} (گیگ):",
            "days": f"📆 مدت جدید برای {plan.name} (روز):",
        }[action]
        await cb.message.answer(prompt)
        await cb.answer()
        return

    # منوی پلن
    text = (
        f"🛍 {plan.name}\n\n"
        f"💰 قیمت: {money(plan.price)} تومان\n"
        f"📦 حجم: {plan.volume_gb:g} گیگ\n"
        f"📆 مدت: {plan.duration_days} روز\n"
        f"وضعیت: {'🟢 فعال' if plan.is_active else '🔴 غیرفعال'}"
    )
    await cb.message.answer(text, reply_markup=ik.plan_admin_kb(plan.id, plan.is_active))
    await cb.answer()


@router.callback_query(F.data == "adm:pladd")
async def cb_add_service(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="add_name", add_data={})
    await cb.message.answer("➕ نام سرویس جدید را بفرستید (مثال: 200 گیگ):")
    await cb.answer()


async def add_service_next(message, state: FSMContext, session, step: str, value):
    """مرحله‌به‌مرحله افزودن سرویس — از input_router صدا زده می‌شود."""
    data = await state.get_data()
    add = data.get("add_data") or {}
    if step == "add_name":
        add["name"] = value
        await state.update_data(add_data=add, field="add_volume")
        await message.answer(f"📦 حجم «{value}» را به گیگابایت بفرستید (عدد):")
        return True
    if step == "add_volume":
        add["volume"] = value
        await state.update_data(add_data=add, field="add_days")
        await message.answer("📆 مدت اعتبار را به روز بفرستید (عدد):")
        return True
    if step == "add_days":
        add["days"] = value
        await state.update_data(add_data=add, field="add_price")
        await message.answer("💰 قیمت را به تومان بفرستید (عدد):")
        return True
    if step == "add_price":
        add["price"] = value
        await state.update_data(add_data=add, field="add_active")
        await message.answer("وضعیت اولیه: فعال باشد؟ (بله / خیر)")
        return True
    if step == "add_active":
        active = value.strip().lower() in ("بله", "yes", "1", "y", "بله.")
        name = add.get("name", "سرویس")
        code = f"plan_{int(__import__('time').time())}"
        plan = ServicePlan(
            code=code,
            name=name,
            volume_gb=float(add.get("volume", 1)),
            duration_days=int(add.get("days", 30)),
            price=int(add.get("price", 0)),
            is_active=active,
            sort_order=99,
        )
        session.add(plan)
        await session.flush()
        from app.bot.handlers.admin.panel import _audit

        _audit(session, message.from_user.id, "plan_add", f"plan:{plan.id}", name)
        await state.clear()
        await message.answer(
            f"✅ سرویس «{name}» اضافه شد.\n"
            f"{'🟢 فعال' if active else '🔴 غیرفعال (باید از بخش قیمت‌ها فعالش کنید)'}"
        )
        return True
    return False
