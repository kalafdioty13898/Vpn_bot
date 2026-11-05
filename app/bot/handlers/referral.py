"""Referral system."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.bot.keyboards import inline as ik
from app.services import settings_service, user_service
from app.utils.formatters import money

router = Router(name="referral")


@router.message(F.text == "🤝 زیرمجموعه‌گیری")
async def menu_referral(message: Message, session, bot):
    if not await settings_service.get_bool(session, "referral_enabled"):
        await message.answer("⚠️ سیستم زیرمجموعه‌گیری در حال حاضر غیرفعال است.")
        return

    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer("ابتدا /start را بزنید.")
        return

    bot_username = await settings_service.get_setting(session, "bot_username")
    if not bot_username:
        try:
            me = await bot.get_me()
            bot_username = me.username
        except Exception:  # noqa: BLE001
            bot_username = ""

    link = f"https://t.me/{bot_username}?start=ref_{user.referral_code}" if bot_username else (
        f"لینک شما با کد: ref_{user.referral_code}"
    )

    count = await user_service.referrals_count(session, user.id)
    purchases, total_amount = await user_service.total_purchases_of_referrals(session, user.id)
    commissions = await user_service.total_commissions(session, user.id)
    percent = await settings_service.get_int(session, "referral_percent", 5)

    text = (
        "💼 زیرمجموعه‌گیری و هدیه خوش‌آمد\n\n"
        "با دعوت دوستان از طریق لینک اختصاصی، بدون پرداخت حتی ۱ ریال کیف پولت شارژ میشه و از خدمات ربات استفاده می‌کنی!\n\n"
        f"💸 پورسانت خرید:\n"
        f"• {percent} درصد از مبلغ خرید زیرمجموعه به شما تعلق می‌گیرد.\n\n"
        "📊 آمار شما:\n"
        f"• 👥 زیرمجموعه‌ها: {count}\n"
        f"• 🛒 خریدها: {purchases}\n"
        f"• 💵 مجموع خرید: {money(total_amount)} تومان\n"
        f"• 🎁 پورسانت دریافتی: {money(commissions)} تومان\n\n"
        "📢 دعوت کن، هدیه بگیر، رشد کن!\n\n"
        "لینک شما:\n"
        f"{link}"
    )
    await message.answer(text, reply_markup=ik.main_menu_inline())
