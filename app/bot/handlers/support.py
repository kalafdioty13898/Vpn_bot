"""Support: user sends message → saved + forwarded to admins; admin can reply."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import inline as ik
from app.bot.keyboards.reply import cancel_kb, CANCEL
from app.bot.states import SupportStates
from app.db.models import SupportMessage
from app.services import settings_service
from app.services.notification_service import send_safe
from app.utils.formatters import jalali

logger = logging.getLogger(__name__)

router = Router(name="support")


class ReplyStates(StatesGroup):
    waiting_reply = State()


@router.message(F.text == "🎧 پشتیبانی")
async def menu_support(message: Message, state: FSMContext, session):
    if not await settings_service.get_bool(session, "support_enabled"):
        await message.answer("⚠️ پشتیبانی موقتاً غیرفعال است.")
        return
    await state.set_state(SupportStates.waiting_message)
    await message.answer(
        "پیامتون رو همینجا بفرستید، من برای مدیر می‌فرستم.",
        reply_markup=cancel_kb(),
    )


@router.message(SupportStates.waiting_message)
async def support_message(message: Message, state: FSMContext, session, bot):
    if message.text and message.text == CANCEL:
        await state.clear()
        await message.answer("✅ لغو شد.")
        return

    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, message.from_user.id)
    if user is None:
        await state.clear()
        await message.answer("ابتدا /start را بزنید.")
        return

    content = message.text or (message.caption or "[فایل/رسانه]")
    sm = SupportMessage(user_id=user.id, message=content)
    session.add(sm)
    await session.flush()

    await state.clear()

    # کپی برای ادمین‌ها (media هم فوروارد شود)
    caption = (
        "🎧 پیام پشتیبانی جدید\n\n"
        f"🆔 User ID: <code>{message.from_user.id}</code>\n"
        f"👤 Name: {message.from_user.first_name or '-'}\n"
        f"🔗 Username: @{message.from_user.username or '-'}\n"
        f"🕐 Date: {jalali(datetime.now(timezone.utc))}\n\n"
        f"💬 پیام:\n{content[:1500]}"
    )

    from app.config import settings
    from app.bot.filters import db_admins

    admin_ids = list(settings.admin_ids) + [a for a in db_admins if a not in settings.admin_ids]
    for admin_id in admin_ids:
        try:
            if message.photo and message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id)
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id)
        except Exception:  # noqa: BLE001
            pass
        await send_safe(bot, admin_id, caption, reply_markup=ik.support_reply_kb(sm.id))

    await message.answer("✅ پیام شما برای مدیر ارسال شد. به‌زودی پاسخ می‌گیرید.")


@router.callback_query(F.data.startswith("adm:sreply:"))
async def cb_support_reply(cb: CallbackQuery, state: FSMContext):
    try:
        msg_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    await state.set_state(ReplyStates.waiting_reply)
    await state.update_data(support_id=msg_id)
    await cb.message.answer("✉️ پاسخ خود را بنویسید:")
    await cb.answer()


@router.message(ReplyStates.waiting_reply, F.text)
async def support_reply_send(message: Message, state: FSMContext, session):
    data = await state.get_data()
    support_id = data.get("support_id")
    await state.clear()

    sm = await session.get(SupportMessage, support_id)
    if sm is None:
        await message.answer("پیام یافت نشد.")
        return

    from sqlalchemy import select

    from app.db.models import User

    user = await session.scalar(select(User).where(User.id == sm.user_id))

    sm.admin_reply = message.text
    sm.status = "REPLIED"
    await session.commit()

    if user is not None:
        await send_safe(
            message.bot,
            user.telegram_id,
            f"🎧 پاسخ پشتیبانی:\n\n{message.text}",
        )
    await message.answer("✅ پاسخ ارسال شد.")
