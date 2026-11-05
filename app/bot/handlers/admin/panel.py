"""Admin panel: menu + user/sales stats + pending receipts + unprovisioned configs + audit log."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.db.models import (
    AuditLog,
    Order,
    OrderStatus,
    Receipt,
    ReceiptStatus,
    ServicePlan,
)
from app.services import stats_service
from app.utils.formatters import fmt_gb, jalali, money

logger = logging.getLogger(__name__)

router = Router(name="admin_panel")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _audit(session, admin_id: int, action: str, target_type: str = "", target_id: str = "", details: str = ""):
    session.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            details=details[:1000],
        )
    )


def _panel_text() -> str:
    return "🛠 پنل مدیریت:\n\nیکی از بخش‌ها را انتخاب کنید:"


async def show_panel(target, session, edit: bool = False):
    from app.services import settings_service

    bot_on = await settings_service.get_bool(session, "bot_enabled")
    sales_on = await settings_service.get_bool(session, "sales_enabled")
    ref_on = await settings_service.get_bool(session, "referral_enabled")
    trial_on = await settings_service.get_bool(session, "trial_enabled")
    fj_on = await settings_service.get_bool(session, "force_join_enabled")
    markup = ik.admin_panel_kb(bot_on, sales_on, ref_on, trial_on, fj_on)
    if edit:
        try:
            await target.edit_text(_panel_text(), reply_markup=markup)
            return
        except Exception:  # noqa: BLE001
            pass
    await target.answer(_panel_text(), reply_markup=markup)


@router.message(F.text == "🛠 پنل مدیریت")
async def menu_admin_panel(message: Message, session):
    await show_panel(message, session)


@router.callback_query(F.data == "adm:menu")
async def cb_admin_panel(cb: CallbackQuery, session):
    await show_panel(cb.message, session, edit=True)
    await cb.answer()


@router.callback_query(F.data == "adm:close")
async def cb_admin_close(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await cb.answer("بسته شد")


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


# ---------------- آمار کاربران ----------------
@router.callback_query(F.data == "adm:stat:u")
async def cb_user_stats(cb: CallbackQuery, session):
    s = await stats_service.user_stats(session)
    text = (
        "📊 آمار کاربران\n\n"
        f"👥 تعداد کل کاربران: {s['total']}\n"
        f"🆕 کاربران امروز: {s['today']}\n"
        f"📅 کاربران این هفته: {s['week']}\n"
        f"🗓 کاربران این ماه: {s['month']}\n"
        f"🚫 مسدودشده: {s['banned']}\n"
        f"🎁 تست گرفته: {s['trial_used']}\n"
        f"🛍 دارای سرویس فعال: {s['with_services']}"
    )
    await cb.message.answer(text, reply_markup=ik.admin_back_kb())
    await cb.answer()


# ---------------- آمار خرید ----------------
@router.callback_query(F.data == "adm:stat:s")
async def cb_sales_stats(cb: CallbackQuery, session):
    s = await stats_service.sales_stats(session)
    top = "-"
    if s["top_plan_id"]:
        plan = await session.get(ServicePlan, s["top_plan_id"])
        if plan:
            top = f"{plan.name} ({s['top_plan_count']} فروش)"
    text = (
        "🛒 آمار خرید\n\n"
        f"📦 کل سفارش‌ها: {s['total_orders']}\n"
        f"✅ سفارش‌های موفق: {s['ok_orders']}\n"
        f"⏳ در انتظار پرداخت: {s['pending_orders']}\n"
        f"❌ ردشده: {s['rejected_orders']}\n\n"
        f"💵 مبلغ کل فروش: {money(s['total_amount'])} تومان\n"
        f"🌞 فروش امروز: {money(s['today_amount'])} تومان\n"
        f"📅 فروش این هفته: {money(s['week_amount'])} تومان\n"
        f"🗓 فروش این ماه: {money(s['month_amount'])} تومان\n\n"
        f"🏆 پرفروش‌ترین: {top}\n"
        f"🧾 سرویس‌های فروخته‌شده: {s['sold_services']}\n"
        f"📊 مجموع حجم فروخته‌شده: {fmt_gb(s['sold_volume'])}\n"
        f"🧾 رسیدهای در انتظار: {s['pending_receipts']}"
    )
    await cb.message.answer(text, reply_markup=ik.admin_back_kb())
    await cb.answer()


# ---------------- رسیدهای در انتظار ----------------
@router.callback_query(F.data.startswith("adm:rc:"))
async def cb_pending_receipts(cb: CallbackQuery, session):
    try:
        page = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        page = 1

    PAGE = 5
    total = await session.scalar(
        select(func.count()).select_from(Receipt).where(Receipt.status == ReceiptStatus.PENDING)
    ) or 0
    if total == 0:
        await cb.message.answer("✅ رسید در انتظاری وجود ندارد.", reply_markup=ik.admin_back_kb())
        await cb.answer()
        return

    total_pages = max(1, (total + PAGE - 1) // PAGE)
    page = max(1, min(page, total_pages))
    items = (
        await session.execute(
            select(Receipt)
            .where(Receipt.status == ReceiptStatus.PENDING)
            .order_by(Receipt.created_at.desc())
            .offset((page - 1) * PAGE)
            .limit(PAGE)
        )
    ).scalars().all()

    rows = [
        [ik.btn(f"#{r.id} | {money(r.amount)} تومان | فاکتور {r.invoice_id}", f"adm:rcd:{r.id}")]
        for r in items
    ]
    nav = []
    if page > 1:
        nav.append(ik.btn("◀️", f"adm:rc:{page - 1}"))
    if page < total_pages:
        nav.append(ik.btn("▶️", f"adm:rc:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([ik.btn("🔙 بازگشت به پنل", "adm:menu")])

    await cb.message.answer(
        f"🧾 رسیدهای تأییدنشده (صفحه {page} از {total_pages}) | کل: {total}",
        reply_markup=ik.kb(rows),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm:rcd:"))
async def cb_receipt_detail(cb: CallbackQuery, session, bot):
    try:
        receipt_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    receipt = await session.get(Receipt, receipt_id)
    if receipt is None:
        await cb.answer("یافت نشد.", show_alert=True)
        return

    if receipt.file_type == "PHOTO" and receipt.file_id:
        await bot.send_photo(cb.from_user.id, receipt.file_id)
    elif receipt.file_type == "DOCUMENT" and receipt.file_id:
        await bot.send_document(cb.from_user.id, receipt.file_id)

    text = (
        "🧾 جزئیات رسید:\n\n"
        f"👤 کاربر: {receipt.user_id}\n"
        f"🧾 فاکتور: <code>{receipt.invoice_id}</code>\n"
        f"💰 مبلغ: {money(receipt.amount)} تومان\n"
        f"🕐 زمان: {jalali(receipt.created_at)}\n"
        f"🟢 وضعیت: {receipt.status}"
    )
    if receipt.status == ReceiptStatus.PENDING:
        markup = ik.receipt_action_kb(receipt.id)
    else:
        markup = ik.admin_back_kb("adm:rc:1")
    await cb.message.answer(text, reply_markup=markup)
    await cb.answer()


# ---------------- کانفیگ‌های ارسال‌نشده ----------------
@router.callback_query(F.data == "adm:provlist")
async def cb_unprovisioned(cb: CallbackQuery, session):
    rows = (
        await session.execute(
            select(Order)
            .where(Order.status.in_((OrderStatus.PROVISION_FAILED,)))
            .order_by(Order.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    if not rows:
        await cb.message.answer("✅ سفارش خرابی‌ای وجود ندارد.", reply_markup=ik.admin_back_kb())
        await cb.answer()
        return
    text = "📦 کانفیگ‌های ارسال‌نشده:\n\n" + "\n".join(
        f"• <code>{o.order_id}</code> | کاربر {o.user_id} | {money(o.amount)} تومان | {o.vpn_username}"
        for o in rows
    )
    kb_rows = [[ik.btn(f"🔄 {o.order_id}", f"adm:prov:{o.order_id}")] for o in rows]
    kb_rows.append([ik.btn("🔙 بازگشت به پنل", "adm:menu")])
    await cb.message.answer(text, reply_markup=ik.kb(kb_rows))
    await cb.answer()


# ---------------- لاگ رخدادها ----------------
@router.callback_query(F.data == "adm:aud")
async def cb_audit_log(cb: CallbackQuery, session):
    rows = (
        await session.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
        )
    ).scalars().all()
    if not rows:
        text = "🧮 لاگی ثبت نشده است."
    else:
        text = "🧮 آخرین رخدادها:\n\n" + "\n".join(
            f"• {jalali(a.created_at)} | ادمین {a.admin_id} | {a.action} {a.target_type} {a.target_id}"
            for a in rows
        )
    await cb.message.answer(text, reply_markup=ik.admin_back_kb())
    await cb.answer()
