"""Inline keyboards + callback-data registry.

Callback scheme (کوتاه و امن):
  fj:check                      بررسی عضویت
  main:menu                     بازگشت به منو
  svc:buy                       لیست سرویس‌ها
  pl:<id>                       انتخاب پلن
  pl:<id>:rnd                   نام تصادفی
  cust:start                    سرویس دلخواه
  inv:<invoice_id>              فاکتور
  pay:card:<invoice_id>         کارت به کارت
  pay:wallet:<invoice_id>       پرداخت از کیف پول
  rc:send:<invoice_id>          ارسال رسید
  rc:ok:<invoice_id>  rc:no:<invoice_id>   تأیید کاربر
  svc:mine  svc:page:<n>  svc:detail:<id>  svc:link:<id>  svc:copy:<id>  svc:del:<id>  svc:del2:<id>
  svc:search
  trial:start
  adm:...                       پنل ادمین
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

BTN_BACK = "🔙 بازگشت"
BTN_MAIN = "🔙 بازگشت به منوی اصلی"
BTN_CLOSE = "❌ بستن"


def kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def btn(text: str, cd: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cd)


def btn_url(text: str, url: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, url=url)


def main_menu_inline() -> InlineKeyboardMarkup:
    return kb([[btn(BTN_MAIN, "main:menu")]])


def force_join_kb(join_url: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn_url("📢 عضویت در کانال", join_url)],
            [btn("🔍 بررسی عضویت", "fj:check")],
        ]
    )


def plans_kb(plans, sales_enabled: bool = True) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if sales_enabled:
        for p in plans:
            rows.append(
                [
                    btn(
                        f"{p.name} - {p.price:,} تومان",
                        f"pl:{p.id}",
                    )
                ]
            )
        rows.append([btn("✂️ سرویس دلخواه", "cust:start")])
    else:
        rows.append([btn("⚠️ فروش موقتاً غیرفعال است", "noop")])
    rows.append([btn(BTN_MAIN, "main:menu")])
    return kb(rows)


def username_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🎲 نام تصادفی", "rnd:username")],
            [btn("❌ لغو", "pur:cancel"), btn(BTN_MAIN, "main:menu")],
        ]
    )


def custom_volume_kb() -> InlineKeyboardMarkup:
    return kb([[btn("❌ لغو", "pur:cancel"), btn(BTN_MAIN, "main:menu")]])


def invoice_kb(invoice_id: str, wallet_balance: int, amount: int, wallet_pay_enabled: bool = True) -> InlineKeyboardMarkup:
    rows = [
        [btn("💳 کارت به کارت", f"pay:card:{invoice_id}")],
    ]
    if wallet_pay_enabled:
        rows.append([btn("💰 پرداخت از کیف پول", f"pay:wallet:{invoice_id}")])
    rows.append([btn("🧾 مشاهده مجدد فاکتور", f"inv:{invoice_id}")])
    rows.append([btn(BTN_MAIN, "main:menu")])
    return kb(rows)


def card_pay_kb(invoice_id: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("📸 ارسال رسید واریزی", f"rc:send:{invoice_id}")],
            [btn("🔙 برگشت به فاکتور", f"inv:{invoice_id}")],
            [btn(BTN_MAIN, "main:menu")],
        ]
    )


def receipt_confirm_kb(invoice_id: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("✅ تأیید", f"rc:ok:{invoice_id}"), btn("❌ خیر", f"rc:no:{invoice_id}")],
        ]
    )


def wallet_menu_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("💸 افزایش موجودی", "wallet:dep")],
            [btn(BTN_MAIN, "main:menu")],
        ]
    )


def deposit_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("50 هزار تومان", "dep:50000"), btn("100 هزار تومان", "dep:100000")],
            [btn("❌ لغو", "wal:cancel"), btn(BTN_MAIN, "main:menu")],
        ]
    )


def services_list_kb(items, page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [btn(s.vpn_username, f"svc:detail:{s.id}")] for s in items
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(btn("◀️ قبلی", f"svc:page:{page - 1}"))
    if page < total_pages:
        nav.append(btn("بعدی ▶️", f"svc:page:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔍 جستجو سریع", "svc:search")])
    rows.append([btn(BTN_MAIN, "main:menu")])
    return kb(rows)


def service_detail_kb(service_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🔄 دریافت لینک جدید", f"svc:link:{service_id}")],
            [btn("📋 کپی اطلاعات", f"svc:copy:{service_id}")],
            [btn("❌ حذف سرویس", f"svc:del:{service_id}")],
            [btn("🔙 بازگشت", "svc:mine")],
        ]
    )


def delete_confirm_kb(service_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🗑 بله، حذف کن", f"svc:del2:{service_id}")],
            [btn("انصراف", f"svc:detail:{service_id}")],
        ]
    )


# ---------------- Admin ----------------
def admin_panel_kb(
    bot_on: bool, sales_on: bool, ref_on: bool, trial_on: bool, fj_on: bool
) -> InlineKeyboardMarkup:
    def state(v: bool) -> str:
        return "🟢 روشن" if v else "🔴 خاموش"

    return kb(
        [
            [btn("📊 آمار کاربران", "adm:stat:u"), btn("🛒 آمار خرید", "adm:stat:s")],
            [btn("🧾 رسیدهای در انتظار", "adm:rc:1"), btn("📦 کانفیگ‌های ارسال‌نشده", "adm:provlist")],
            [
                btn(f"ربات: {state(bot_on)}", "adm:tg:bot"),
                btn(f"فروش: {state(sales_on)}", "adm:tg:sales"),
            ],
            [
                btn(f"زیرمجموعه: {state(ref_on)}", "adm:tg:ref"),
                btn(f"تست رایگان: {state(trial_on)}", "adm:tg:trial"),
            ],
            [btn(f"📢 کانال اجباری: {state(fj_on)}", "adm:fj")],
            [btn("💳 اطلاعات کارت", "adm:card"), btn("🤝 درصد زیرمجموعه", "adm:refpct")],
            [btn("🎁 تنظیم تست رایگان", "adm:trial"), btn("✂️ قیمت سرویس دلخواه", "adm:custp")],
            [btn("💰 حدود شارژ کیف پول", "adm:dep")],
            [btn("🛍 قیمت سرویس‌ها", "adm:prices"), btn("➕ سرویس جدید", "adm:pladd")],
            [btn("⚙️ تنظیم پنل VPN", "adm:panelcfg"), btn("📚 آموزش‌ها", "adm:tut")],
            [btn("🔍 جستجوی کاربر", "adm:usearch"), btn("👥 مدیریت ادمین‌ها", "adm:admins")],
            [btn("🧮 لاگ رخدادها", "adm:aud"), btn("📨 پیام همگانی", "adm:bcast")],
            [btn(BTN_CLOSE, "adm:close")],
        ]
    )


def admin_back_kb(target: str = "adm:menu") -> InlineKeyboardMarkup:
    return kb([[btn("🔙 بازگشت به پنل", target)]])


def receipt_action_kb(receipt_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("✅ تأیید رسید و ارسال کانفیگ", f"adm:rcap:{receipt_id}")],
            [btn("⏳ در انتظار", f"adm:rcwa:{receipt_id}"), btn("❌ رد کردن رسید", f"adm:rcrj:{receipt_id}")],
        ]
    )


def provision_retry_kb(order_id: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🔄 تلاش مجدد ساخت کانفیگ", f"adm:prov:{order_id}")],
            [btn("💵 عودت به کیف پول کاربر", f"adm:refund:{order_id}")],
        ]
    )


def force_join_admin_kb(enabled: bool, channel: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🟢 روشن" if not enabled else "🔴 خاموش", "adm:fj:toggle")],
            [btn("📢 تنظیم کانال", "adm:fj:ch")],
            [btn("🔗 تنظیم لینک دعوت", "adm:fj:url")],
            [btn("🔍 تست عضویت", "adm:fj:test")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def card_admin_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("💳 تغییر شماره کارت", "adm:card:num")],
            [btn("👤 تغییر نام صاحب کارت", "adm:card:hold")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def plan_admin_kb(plan_id: int, active: bool) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("💰 تغییر قیمت", f"adm:pl:{plan_id}:price"), btn("📦 تغییر حجم", f"adm:pl:{plan_id}:vol")],
            [btn("📆 تغییر مدت", f"adm:pl:{plan_id}:days")],
            [btn("🟢 غیرفعال کن" if active else "🔴 فعال کن", f"adm:pl:{plan_id}:toggle")],
            [btn("🔙 بازگشت", "adm:prices")],
        ]
    )


def panel_cfg_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("🔌 تست اتصال", "adm:panelcfg:test")],
            [btn("🧩 تغییر حالت (mock/pasargad)", "adm:panelcfg:mode")],
            [btn("🌐 Panel URL", "adm:panelcfg:url")],
            [btn("🔗 API URL", "adm:panelcfg:apiurl")],
            [btn("🔑 API Key", "adm:panelcfg:key")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def trial_admin_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("📦 حجم تست", "adm:trial:vol"), btn("📆 مدت تست", "adm:trial:days")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def custom_price_admin_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("قیمت پایه هر GB", "adm:custp:base"), btn("حداقل قیمت", "adm:custp:min")],
            [btn("حداکثر حجم", "adm:custp:maxv"), btn("حداقل حجم", "adm:custp:minv")],
            [btn("حداکثر روز", "adm:custp:maxd"), btn("حداقل روز", "adm:custp:mind")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def deposit_admin_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("حداقل شارژ", "adm:dep:min"), btn("حداکثر شارژ", "adm:dep:max")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def user_card_kb(tg_id: int, banned: bool) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("💰 تغییر کیف پول", f"adm:u:{tg_id}:wal")],
            [
                btn("🚫 مسدودسازی" if not banned else "✅ رفع مسدودی", f"adm:u:{tg_id}:ban" if not banned else f"adm:u:{tg_id}:unban"),
            ],
            [btn("🔙 بازگشت", "adm:usearch")],
        ]
    )


def tutorial_admin_kb(tut_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("✏️ ویرایش محتوا", f"adm:tut:{tut_id}:edit"), btn("🔴 غیرفعال/فعال", f"adm:tut:{tut_id}:toggle")],
            [btn("🗑 حذف", f"adm:tut:{tut_id}:del")],
            [btn("🔙 بازگشت", "adm:tut")],
        ]
    )


def admin_list_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("➕ افزودن ادمین", "adm:admadd")],
            [btn("🔙 بازگشت به پنل", "adm:menu")],
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return kb(
        [
            [btn("✅ ارسال کن", "adm:bcast:go"), btn("❌ لغو", "adm:bcast:cancel")],
        ]
    )


def support_reply_kb(msg_id: int) -> InlineKeyboardMarkup:
    return kb([[btn("✉️ پاسخ", f"adm:sreply:{msg_id}")]])


def noop_kb() -> InlineKeyboardMarkup:
    return kb([[btn("باشه", "noop")]])
