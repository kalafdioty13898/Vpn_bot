"""Application entrypoint: python -m app.main"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.filters import register_admin, unregister_admin, db_admins
from app.bot.handlers import setup_routers
from app.bot.keyboards.reply import main_menu_kb
from app.bot.middlewares.access import AccessMiddleware
from app.bot.middlewares.db import DbSessionMiddleware
from app.bot.middlewares.throttle import ThrottleMiddleware
from app.config import settings
from app.db.base import make_engine, make_sessionmaker
from app.db.init_db import ensure_schema, seed_defaults
from app.logging_conf import setup_logging
from app.services import provision_service
from app.services.notification_service import setup as setup_notifications

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_logging(settings.log_level)

    if not settings.bot_token:
        logger.critical("BOT_TOKEN در .env تنظیم نشده است!")
        print("❌ BOT_TOKEN در فایل .env تنظیم نشده است. از .env.example کپی کنید.")
        sys.exit(1)

    logger.info("Starting VPN shop bot...")

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    await ensure_schema(engine)
    admins_changed = False
    async with sessionmaker() as session:
        await seed_defaults(session)
        # کش ادمین‌های دیتابیسی + همگام‌سازی با تنظیمات
        from sqlalchemy import select

        from app.db.models import Admin, UserRole

        admins = (await session.execute(select(Admin))).scalars().all()
        db_ids = {a.telegram_id for a in admins}
        wanted = set(settings.admin_ids)

        # ادمین‌هایی که دیگر در تنظیمات نیستند حذف می‌شوند (مثلاً آیدی قدیمی)
        for a in admins:
            if a.telegram_id not in wanted:
                await session.delete(a)
                unregister_admin(a.telegram_id)
                admins_changed = True
        # ادمین‌های جدید اضافه می‌شوند
        for aid in sorted(wanted - db_ids):
            session.add(Admin(telegram_id=aid, role=UserRole.SUPER_ADMIN))
            register_admin(aid)
            admins_changed = True
        if admins_changed:
            await session.commit()
            logger.info("Admin list synced with configuration")

    # --- لیست نهایی ادمین‌ها ---
    all_admins = list(dict.fromkeys([*settings.admin_ids, *db_admins]))
    if not all_admins:
        logger.warning(
            "No admins configured! Set the ADMIN_IDS secret "
            "(comma-separated Telegram numeric IDs)."
        )
    else:
        # برای دیباگ: فقط ۳ رقم آخر آیدی‌ها لاگ می‌شود (لاگ عمومی است)
        tails = ",".join("..." + str(a)[-3:] for a in all_admins)
        logger.info("Admins configured: %d [%s]", len(all_admins), tails)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware ها
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.update.outer_middleware(ThrottleMiddleware(interval=0.6))

    # Routers
    root_router = setup_routers()
    # Access (maintenance/ban/force-join) فقط روی هندلرهای کاربر عادی
    for name in ("user_root",):
        pass
    _attach_access(root_router)
    dp.include_router(root_router)

    # Provisioning + Notifications
    provision_service.init_provisioner(sessionmaker)

    admin_ids = all_admins
    setup_notifications(bot, admin_ids)

    # Error handler
    @dp.error()
    async def global_error_handler(event, **kwargs):  # noqa: ANN001
        import traceback

        exc = event.exception
        logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
        try:
            update = event.update
            if update.message:
                await update.message.answer("⚠️ خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.")
            elif update.callback_query:
                await update.callback_query.answer("⚠️ خطای غیرمنتظره", show_alert=True)
        except Exception:  # noqa: BLE001
            pass
        try:
            for aid in admin_ids[:3]:
                await bot.send_message(
                    aid,
                    f"⚠️ خطای مهم در ربات:\n<code>{str(exc)[:500]}</code>",
                )
        except Exception:  # noqa: BLE001
            pass
        return True

    # Bot info
    me = await bot.get_me()
    from app.services import settings_service

    async with sessionmaker() as session:
        await settings_service.set_setting(session, "bot_username", me.username)
        await session.commit()

    from aiogram.types import BotCommand, BotCommandScopeDefault

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="شروع / منوی اصلی"),
            BotCommand(command="myid", description="آیدی عددی من"),
            BotCommand(command="cancel", description="لغو عملیات"),
        ],
        scope=BotCommandScopeDefault(),
    )

    await bot.delete_webhook(drop_pending_updates=True)

    # --- پیام آنلاین‌شدن با منوی اصلی (دکمه پنل مدیریت) برای ادمین‌ها ---
    try:
        import time as _time

        from app.services import settings_service as _ss

        async with sessionmaker() as session:
            last_raw = await _ss.get_setting(session, "last_online_greet")
            now = int(_time.time())
            last = int(last_raw) if last_raw and str(last_raw).isdigit() else 0
            if admins_changed or now - last > 1800:  # تغییر ادمین‌ها یا گذشت ۳۰ دقیقه
                await _ss.set_setting(session, "last_online_greet", str(now))
                await session.commit()
                for aid in all_admins[:3]:
                    try:
                        await bot.send_message(
                            aid,
                            "🟢 ربات آنلاین شد و آماده استفاده است.\n\n🏠 منوی اصلی:",
                            reply_markup=main_menu_kb(True),
                        )
                    except Exception:  # noqa: BLE001
                        pass
    except Exception:  # noqa: BLE001
        logger.exception("admin online-greeting failed (non-fatal)")

    logger.info("Bot @%s started (polling)", me.username)
    print(f"✅ Bot @{me.username} is running... (Ctrl+C برای توقف)")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()
        logger.info("Bot stopped")


def _attach_access(root_router) -> None:
    """AccessMiddleware فقط روی router کاربران."""
    for sub in root_router.sub_routers:
        if sub.name == "user_root":
            sub.message.middleware(AccessMiddleware())
            sub.callback_query.middleware(AccessMiddleware())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Bot stopped.")
