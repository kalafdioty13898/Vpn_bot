"""Reply keyboards (main menu)."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

MAIN_BUY = "🛍 خرید اشتراک"
MAIN_TRIAL = "🎁 تست رایگان"
MAIN_WALLET = "💰 کیف پول"
MAIN_SERVICES = "📦 سرویس‌های من"
MAIN_TUTORIAL = "📚 آموزش"
MAIN_SUPPORT = "🎧 پشتیبانی"
MAIN_REFERRAL = "🤝 زیرمجموعه‌گیری"
ADMIN_PANEL = "🛠 پنل مدیریت"

CANCEL = "❌ لغو"


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = [
        [KeyboardButton(text=MAIN_BUY)],
        [KeyboardButton(text=MAIN_TRIAL)],
        [KeyboardButton(text=MAIN_WALLET), KeyboardButton(text=MAIN_SERVICES)],
        [KeyboardButton(text=MAIN_TUTORIAL), KeyboardButton(text=MAIN_SUPPORT)],
        [KeyboardButton(text=MAIN_REFERRAL)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=ADMIN_PANEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


remove_kb = ReplyKeyboardRemove()
