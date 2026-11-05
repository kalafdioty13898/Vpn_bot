"""Admin: VPN panel (Pasargad/Mock) settings."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.filters import IsAdmin
from app.bot.keyboards import inline as ik
from app.bot.states import AdminStates
from app.services import settings_service

router = Router(name="admin_panelcfg")
router.callback_query.filter(IsAdmin())


@router.callback_query(F.data == "adm:panelcfg")
async def cb_panelcfg_menu(cb: CallbackQuery, session):
    mode = await settings_service.get_setting(session, "panel_mode", "mock")
    url = await settings_service.get_setting(session, "panel_url")
    api = await settings_service.get_setting(session, "panel_api_url")
    key = await settings_service.get_setting(session, "panel_api_key")
    masked = (key[:6] + "...") if key else "—"
    text = (
        "⚙️ تنظیم پنل VPN\n\n"
        f"🧩 حالت: <b>{mode}</b> (mock = کانفیگ آزمایشی برای تست)\n"
        f"🌐 Panel URL: {url or '—'}\n"
        f"🔗 API URL: {api or '—'}\n"
        f"🔑 API Key: {masked}\n\n"
        "⚠️ برای اتصال به پنل پاسارگاد، مستندات API لازم است؛ تا آن زمان حالت mock پیشنهاد می‌شود."
    )
    await cb.message.answer(text, reply_markup=ik.panel_cfg_kb())
    await cb.answer()


@router.callback_query(F.data == "adm:panelcfg:test")
async def cb_panelcfg_test(cb: CallbackQuery, session):
    from app.vpn import PanelError, get_adapter

    cfg = await settings_service.get_all(session)
    adapter = get_adapter(cfg)
    try:
        msg = await adapter.check_connection()
        await cb.message.answer(msg)
        await cb.answer("✅ موفق")
    except PanelError as e:
        await cb.message.answer(f"❌ اتصال ناموفق بود.\nجزئیات: {e}")
        await cb.answer("❌ ناموفق", show_alert=True)
    except Exception:  # noqa: BLE001
        await cb.message.answer("❌ اتصال ناموفق بود. جزئیات خطا در لاگ ذخیره شد.")
        await cb.answer("❌ ناموفق", show_alert=True)


@router.callback_query(F.data == "adm:panelcfg:mode")
async def cb_panelcfg_mode(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="panel_mode")
    await cb.message.answer("🧩 حالت جدید را بفرستید: mock یا pasargad")
    await cb.answer()


@router.callback_query(F.data == "adm:panelcfg:url")
async def cb_panelcfg_url(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="panel_url")
    await cb.message.answer("🌐 Panel URL را بفرستید (مثال: https://panel.example.com):")
    await cb.answer()


@router.callback_query(F.data == "adm:panelcfg:apiurl")
async def cb_panelcfg_apiurl(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="panel_api_url")
    await cb.message.answer("🔗 API URL را بفرستید (مثال: https://panel.example.com/api):")
    await cb.answer()


@router.callback_query(F.data == "adm:panelcfg:key")
async def cb_panelcfg_key(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_value)
    await state.update_data(field="panel_api_key")
    await cb.message.answer("🔑 API Key را بفرستید (در پیام‌های بعدی نمایش داده نمی‌شود):")
    await cb.answer()
