"""Tutorials (content stored in DB, editable from admin panel)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.keyboards import inline as ik
from app.db.models import Tutorial

router = Router(name="tutorial")

CATEGORY_LABELS = {
    "ANDROID": "📱 اندروید",
    "IOS": "🍎 iOS",
    "WINDOWS": "💻 ویندوز",
    "V2RAY": "📖 V2Ray",
    "V2BOX": "📖 V2Box",
}


@router.message(F.text == "📚 آموزش")
async def menu_tutorial(message: Message, session):
    cats = (
        await session.execute(
            select(Tutorial.category).where(Tutorial.is_active.is_(True)).distinct()
        )
    ).scalars().all()
    if not cats:
        await message.answer("فعلاً آموزشی ثبت نشده است.")
        return

    rows = [[ik.btn(CATEGORY_LABELS.get(c, c), f"tut:cat:{c}")] for c in cats]
    rows.append([ik.btn("🔙 بازگشت به منوی اصلی", "main:menu")])
    await message.answer("📚 یک دسته آموزشی انتخاب کنید:", reply_markup=ik.kb(rows))


@router.callback_query(F.data.startswith("tut:cat:"))
async def cb_tutorial_cat(cb: CallbackQuery, session):
    cat = cb.data.split(":", 2)[2]
    items = (
        await session.execute(
            select(Tutorial)
            .where(Tutorial.category == cat, Tutorial.is_active.is_(True))
            .order_by(Tutorial.sort_order)
        )
    ).scalars().all()
    if not items:
        await cb.answer("موردی یافت نشد.", show_alert=True)
        return
    label = CATEGORY_LABELS.get(cat, cat)
    rows = [[ik.btn(t.title, f"tut:show:{t.id}")] for t in items]
    rows.append([ik.btn("🔙 بازگشت", "tut:back")])
    await cb.message.answer(f"{label}\n\nیک آموزش انتخاب کنید:", reply_markup=ik.kb(rows))
    await cb.answer()


@router.callback_query(F.data == "tut:back")
async def cb_tutorial_back(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("tut:show:"))
async def cb_tutorial_show(cb: CallbackQuery, session):
    try:
        tut_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    tut = await session.get(Tutorial, tut_id)
    if tut is None or not tut.is_active:
        await cb.answer("یافت نشد.", show_alert=True)
        return
    await cb.message.answer(f"📖 {tut.title}\n\n{tut.content}", reply_markup=ik.main_menu_inline())
    await cb.answer()
