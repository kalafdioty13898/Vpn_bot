"""Application entrypoint: python -m app.main"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.filters import register_admin
from app.bot.handlers import setup_routers
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
    async with sessionmaker() as session:
        await seed_defaults(session)
        # کش ادمین‌های دیتابیسی
        from sqlalchemy import select

        from app.db.models import Admin

        admins = (await session.execute(select(Admin))).scalars().all()
        for a in admins:
            register_admin(a.telegram_id)

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

    admin_ids = list(settings.admin_ids)
    from app.bot.filters import db_admins

    for aid in db_admins:
        if aid not in admin_ids:
            admin_ids.append(aid)
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
