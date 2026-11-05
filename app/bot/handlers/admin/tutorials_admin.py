"""Admin: tutorials management."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.bot.states import AdminStates
from app.db.models import AuditLog, Tutorial

router = Router(name="admin_tutorials")
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:tut")
async def cb_tutorials(cb: CallbackQuery, session):
    items = (
        await session.execute(select(Tutorial).order_by(Tutorial.category, Tutorial.sort_order))
    ).scalars().all()
    rows = [
        [ik.btn(f"{'🟢' if t.is_active else '🔴'} [{t.category}] {t.title[:40]}", f"adm:tut:{t.id}")]
        for t in items
    ]
    rows.append([ik.btn("➕ آموزش جدید", "adm:tutadd")])
    rows.append([ik.btn("🔙 بازگشت به پنل", "adm:menu")])
    await cb.message.answer("📚 مدیریت آموزش‌ها:", reply_markup=ik.kb(rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm:tut:"))
async def cb_tutorial_actions(cb: CallbackQuery, state: FSMContext, session):
    parts = cb.data.split(":")
    try:
        tut_id = int(parts[2])
    except (ValueError, IndexError):
        await cb.answer("نامعتبر", show_alert=True)
        return
    tut = await session.get(Tutorial, tut_id)
    if tut is None:
        await cb.answer("یافت نشد", show_alert=True)
        return

    action = parts[3] if len(parts) > 3 else ""
    if action == "toggle":
        tut.is_active = not tut.is_active
        session.add(
            AuditLog(admin_id=cb.from_user.id, action="tut_toggle", target_id=str(tut_id))
        )
        await cb.answer("انجام شد ✅")
        await cb.message.answer(
            f"وضعیت: {'🟢 فعال' if tut.is_active else '🔴 غیرفعال'}",
            reply_markup=ik.tutorial_admin_kb(tut_id),
        )
        return
    if action == "del":
        await session.delete(tut)
        session.add(AuditLog(admin_id=cb.from_user.id, action="tut_delete", target_id=str(tut_id)))
        await cb.answer("حذف شد 🗑")
        await cb.message.answer("🗑 آموزش حذف شد.")
        return
    if action == "edit":
        await state.set_state(AdminStates.waiting_value)
        await state.update_data(field="tut_edit", tut_id=tut_id)
        await cb.message.answer(
            f"✏️ محتوای جدید برای «{tut.title}» را بفرستید:"
        )
        await cb.answer()
        return

    await cb.message.answer(
        f"📚 [{tut.category}] {tut.title}\n\n{tut.content[:2000]}",
        reply_markup=ik.tutorial_admin_kb(tut.id),
    )
    await cb.answer()


@router.callback_query(F.data == "adm:tutadd")
async def cb_tutorial_add(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="tut_cat", tut_data={})
    await cb.message.answer(
        "دسته آموزش را بفرستید (ANDROID / IOS / WINDOWS / V2RAY / V2BOX):"
    )
    await cb.answer()


async def create_tutorial_step(message: Message, state: FSMContext, session, step: str, value: str):
    data = await state.get_data()
    td = data.get("tut_data") or {}
    if step == "tut_cat":
        td["category"] = value.upper()
        await state.update_data(tut_data=td, field="tut_title")
        await message.answer("✏️ عنوان آموزش را بفرستید:")
        return
    if step == "tut_title":
        td["title"] = value
        await state.update_data(tut_data=td, field="tut_content")
        await message.answer("📝 محتوای آموزش را بفرستید (می‌تواند چند خط باشد):")
        return
    if step == "tut_content":
        tut = Tutorial(
            category=td.get("category", "V2RAY"),
            title=td.get("title", "آموزش"),
            content=value,
            is_active=True,
            sort_order=10,
        )
        session.add(tut)
        await session.flush()
        session.add(AuditLog(admin_id=message.from_user.id, action="tut_add", target_id=str(tut.id)))
        await state.clear()
        await message.answer("✅ آموزش اضافه شد.")
        return


async def edit_tutorial_content(message: Message, state: FSMContext, session, value: str):
    data = await state.get_data()
    tut_id = data.get("tut_id")
    tut = await session.get(Tutorial, int(tut_id)) if tut_id else None
    if tut is None:
        await state.clear()
        await message.answer("آموزش یافت نشد.")
        return
    tut.content = value
    session.add(AuditLog(admin_id=message.from_user.id, action="tut_edit", target_id=str(tut.id)))
    await state.clear()
    await message.answer("✅ محتوا به‌روزرسانی شد.")
