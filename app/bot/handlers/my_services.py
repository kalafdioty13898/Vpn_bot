"""My services: list, pagination, detail, renew link, copy, delete, quick search."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from app.bot.keyboards import inline as ik
from app.bot.keyboards.reply import cancel_kb, CANCEL
from app.bot.states import ServiceSearchStates
from app.db.models import VPNService
from app.services import settings_service
from app.utils.formatters import fmt_gb, jalali

logger = logging.getLogger(__name__)

router = Router(name="my_services")
PAGE_SIZE = 5


@router.message(F.text == "📦 سرویس‌های من")
async def menu_services(message: Message, session):
    await show_services_list(message, message.from_user.id, session, page=1)


@router.callback_query(F.data == "svc:mine")
async def cb_services(cb: CallbackQuery, session):
    await show_services_list(cb.message, cb.from_user.id, session, page=1, edit=True)
    await cb.answer()


async def show_services_list(target, telegram_id: int, session, page: int, edit: bool = False):
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, telegram_id)
    if user is None:
        await target.answer("ابتدا /start را بزنید.")
        return

    total = await session.scalar(
        select(func.count()).select_from(VPNService).where(
            VPNService.user_id == user.id, VPNService.status == "ACTIVE"
        )
    ) or 0

    if total == 0:
        text = "شما هیچ سرویس فعالی ندارید."
        markup = ik.main_menu_inline()
        if edit:
            try:
                await target.edit_text(text, reply_markup=markup)
                return
            except Exception:  # noqa: BLE001
                pass
        await target.answer(text, reply_markup=markup)
        return

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    items = (
        await session.execute(
            select(VPNService)
            .where(VPNService.user_id == user.id, VPNService.status == "ACTIVE")
            .order_by(VPNService.created_at.desc())
            .offset((page - 1) * PAGE_SIZE)
            .limit(PAGE_SIZE)
        )
    ).scalars().all()

    text = (
        "🛍 اشتراک‌های خریداری‌شده توسط شما\n\n"
        "⚠️ برای مشاهده اطلاعات و مدیریت روی نام کاربری کلیک کنید.\n"
        "🔴 همچنین برای پیدا کردن سریع سرویس خود و مدیریت آن می‌توانید از دکمه «🔍 جستجو سریع» استفاده کنید.\n\n"
        f"📄 صفحه {page} از {total_pages} | 📊 کل: {total} سرویس"
    )
    markup = ik.services_list_kb(items, page, total_pages)
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup)
            return
        except Exception:  # noqa: BLE001
            pass
    await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("svc:page:"))
async def cb_services_page(cb: CallbackQuery, session):
    try:
        page = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        page = 1
    await show_services_list(cb.message, cb.from_user.id, session, page, edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("svc:detail:"))
async def cb_service_detail(cb: CallbackQuery, session):
    try:
        service_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return

    service = await session.get(VPNService, service_id)
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, cb.from_user.id)
    if service is None or user is None or service.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    status_map = {"ACTIVE": "🟢 فعال", "EXPIRED": "⌛️ منقضی", "DISABLED": "🔴 غیرفعال", "DELETED": "🗑 حذف‌شده"}
    text = service_detail_text(service, status_map)
    await cb.message.answer(text, reply_markup=ik.service_detail_kb(service.id))
    await cb.answer()


def service_detail_text(service: VPNService, status_map: dict[str, str] | None = None) -> str:
    status_map = status_map or {"ACTIVE": "🟢 فعال"}
    return (
        "🛍 اطلاعات سرویس:\n\n"
        f"👤 نام کاربری: <code>{service.vpn_username}</code>\n"
        f"📦 حجم: {fmt_gb(service.volume_gb)}\n"
        f"📆 مدت: {service.duration_days} روز\n"
        f"📅 تاریخ ایجاد: {jalali(service.created_at)}\n"
        f"⏰ تاریخ انقضا: {jalali(service.expires_at)}\n"
        f"🟢 وضعیت: {status_map.get(service.status, service.status)}\n"
        f"🔗 لینک اتصال:\n<code>{service.subscription_url}</code>"
    )


@router.callback_query(F.data.startswith("svc:link:"))
async def cb_service_new_link(cb: CallbackQuery, session):
    try:
        service_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    service = await session.get(VPNService, service_id)
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, cb.from_user.id)
    if service is None or user is None or service.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    from app.vpn import get_adapter

    cfg = await settings_service.get_all(session)
    adapter = get_adapter(cfg)
    try:
        new_url = await adapter.generate_subscription(service.vpn_username)
        service.subscription_url = new_url
        await session.commit()
        await cb.message.answer(
            "🔄 لینک جدید دریافت شد:\n" f"<code>{new_url}</code>"
        )
        await cb.answer("لینک آپدیت شد ✅")
    except Exception as e:  # noqa: BLE001
        logger.warning("New link failed: %s", type(e).__name__)
        await cb.answer("خطا در دریافت لینک جدید", show_alert=True)


@router.callback_query(F.data.startswith("svc:copy:"))
async def cb_service_copy(cb: CallbackQuery, session):
    try:
        service_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    service = await session.get(VPNService, service_id)
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, cb.from_user.id)
    if service is None or user is None or service.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return
    await cb.message.answer(service_detail_text(service))
    await cb.answer("اطلاعات ارسال شد 📋")


@router.callback_query(F.data.startswith("svc:del:"))
async def cb_service_delete_ask(cb: CallbackQuery, session):
    try:
        service_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    service = await session.get(VPNService, service_id)
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, cb.from_user.id)
    if service is None or user is None or service.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return
    await cb.message.answer(
        f"⚠️ مطمئن هستید سرویس <code>{service.vpn_username}</code> حذف شود؟\n"
        "این عملیات قابل بازگشت نیست.",
        reply_markup=ik.delete_confirm_kb(service.id),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("svc:del2:"))
async def cb_service_delete_confirm(cb: CallbackQuery, session):
    try:
        service_id = int(cb.data.split(":")[2])
    except (ValueError, IndexError):
        await cb.answer("داده نامعتبر", show_alert=True)
        return
    service = await session.get(VPNService, service_id)
    from app.services.user_service import get_by_telegram_id

    user = await get_by_telegram_id(session, cb.from_user.id)
    if service is None or user is None or service.user_id != user.id:
        await cb.answer("❌ دسترسی غیرمجاز.", show_alert=True)
        return

    from app.vpn import PanelError, get_adapter

    cfg = await settings_service.get_all(session)
    adapter = get_adapter(cfg)
    try:
        await adapter.delete_user(service.vpn_username)
    except PanelError as e:
        logger.warning("Panel delete failed: %s", e)

    service.status = "DELETED"
    await session.commit()
    await cb.message.answer(f"🗑 سرویس <code>{service.vpn_username}</code> حذف شد.")
    await cb.answer("حذف شد")


@router.callback_query(F.data == "svc:search")
async def cb_service_search(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ServiceSearchStates.waiting_username)
    await cb.message.answer("نام کاربری سرویس را وارد کنید:", reply_markup=cancel_kb())
    await cb.answer()


@router.message(ServiceSearchStates.waiting_username, F.text)
async def service_search(message: Message, state: FSMContext, session):
    if (message.text or "").strip() == CANCEL:
        await state.clear()
        await message.answer("✅ لغو شد.")
        return

    from app.services.user_service import get_by_telegram_id

    await state.clear()
    user = await get_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer("ابتدا /start را بزنید.")
        return

    username = (message.text or "").strip()
    service = await session.scalar(
        select(VPNService).where(
            VPNService.user_id == user.id,
            VPNService.vpn_username == username,
            VPNService.status == "ACTIVE",
        )
    )
    if service is None:
        # کاربر نباید سرویس دیگران را ببیند
        await message.answer("سرویسی با این نام در سرویس‌های شما یافت نشد.")
        return
    await message.answer(service_detail_text(service), reply_markup=ik.service_detail_kb(service.id))
