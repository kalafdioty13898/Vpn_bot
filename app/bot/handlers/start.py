"""Start, main menu, force join check, cancel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.inline import force_join_kb, main_menu_inline
from app.bot.keyboards.reply import main_menu_kb, CANCEL
from app.bot.middlewares.access import FORCE_JOIN_TEXT
from app.config import settings
from app.db.models import InvoiceType
from app.services import settings_service, user_service
from app.utils.formatters import user_display_name
from sqlalchemy import select
from app.db.models import Receipt, ReceiptStatus

router = Router(name="start")


def _welcome_text(name: str) -> str:
    return (
        f"درود {name} به ربات خوش آمدید 👋\n\n"
        "یکی از دکمه‌های زیر را انتخاب کنید."
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session,
    bot,
):
    await state.clear()

    payload = message.get_args() or ""
    ref_code = None
    if payload.startswith("ref_"):
        ref_code = payload[4:]

    user, referrer = await user_service.register_user(
        session,
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name or "",
        last_name=message.from_user.last_name,
        telegram_username=message.from_user.username,
        ref_code=ref_code,
    )

    # اگر سفارش پرداخت‌شده بدون کانفیگ دارد، یادآوری کن
    from app.db.models import Order, OrderStatus

    stuck = await session.scalar(
        select(Order).where(
            Order.user_id == user.id,
            Order.status == OrderStatus.PROVISION_FAILED,
        )
    )

    if referrer is not None:
        await user_service.get_wallet(session, user.id)

    is_admin = settings.admin_ids and message.from_user.id in settings.admin_ids
    from app.bot.filters import is_admin_id

    is_admin = is_admin_id(message.from_user.id)

    # Force join gate
    if await settings_service.get_bool(session, "force_join_enabled"):
        channel = await settings_service.get_setting(session, "force_join_channel")
        if channel:
            from app.bot.middlewares.access import _check_member

            ok = await _check_member(bot, channel, message.from_user.id)
            if not ok:
                url = await settings_service.get_setting(session, "force_join_url")
                if not url:
                    url = f"https://t.me/{channel.lstrip('@')}"
                await message.answer(
                    FORCE_JOIN_TEXT + f"\n\n👤 {user_display_name(user.first_name, user.telegram_id)}",
                    reply_markup=force_join_kb(url),
                )
                return

    text = _welcome_text(user_display_name(user.first_name, user.telegram_id))
    if referrer is not None:
        try:
            from app.services.notification_service import notify

            await notify(
                "user",
                "🎉 یک نفر با لینک دعوت شما وارد ربات شد!",
                user_id=referrer.telegram_id,
            )
        except Exception:  # noqa: BLE001
            pass

    extra = ""
    if stuck is not None:
        extra = (
            "\n\n⚠️ یک سفارش پرداخت‌شده دارید که کانفیگ آن ساخته نشد؛ "
            "به‌زودی توسط ادمین پیگیری می‌شود."
        )

    await message.answer(text + extra, reply_markup=main_menu_kb(is_admin))


@router.callback_query(F.data == "fj:check")
async def cb_check_membership(cb: CallbackQuery, session, bot):
    channel = await settings_service.get_setting(session, "force_join_channel")
    if not channel:
        await cb.answer("خطا: کانال تنظیم نشده است.", show_alert=True)
        return
    ok = await _check_member(bot, channel, cb.from_user.id)
    if not ok:
        await cb.answer("❌ هنوز عضو کانال نشده‌اید!", show_alert=True)
        return
    await cb.answer("عضویت شما تأیید شد ✅", show_alert=True)
    try:
        await cb.message.answer(
            "عضویت شما تأیید شد ✅\n\nیکی از دکمه‌های پایین را انتخاب کنید.",
            reply_markup=main_menu_kb(False),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "main:menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext, session):
    await state.clear()
    from app.bot.filters import is_admin_id

    is_admin = is_admin_id(cb.from_user.id)
    try:
        await cb.message.answer(
            "🏠 منوی اصلی:", reply_markup=main_menu_kb(is_admin)
        )
        await cb.answer()
    except Exception:  # noqa: BLE001
        await cb.answer()


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"🆔 آیدی عددی شما: <code>{message.from_user.id}</code>")


@router.message(Command("cancel"))
@router.message(F.text == CANCEL)
async def cmd_cancel(message: Message, state: FSMContext, session):
    await state.clear()
    from app.bot.filters import is_admin_id

    is_admin = is_admin_id(message.from_user.id)
    await message.answer("✅ عملیات لغو شد.\n\n🏠 منوی اصلی:", reply_markup=main_menu_kb(is_admin))


@router.message(Command("start_help"))
async def cmd_help(message: Message):
    await message.answer("برای شروع /start را بزنید. برای لغو عملیات: /cancel")
