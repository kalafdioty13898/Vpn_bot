"""Integration tests for user flows: start/referral/purchase/wallet.

Simulates real Telegram updates (recorded-calls Bot + feed_update) against the
full dispatcher with the real DB session middleware — no network needed.

These cover the bugs found on 2026-11-05:
  - /start crashed with 'Message' object has no attribute 'get_args'
    -> users were never registered -> every other button said "ابتدا /start را بزنید"
  - the «🛍 خرید اشتراک» reply button had no handler at all
  - pur:cancel / wal:cancel inline buttons had no handler
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("BOT_TOKEN", "42:TEST")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402
from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    Update,
    User as TgUser,
)
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)

import app.bot.filters as filters_mod  # noqa: E402
from app.bot.handlers import setup_routers  # noqa: E402
from app.bot.middlewares.db import DbSessionMiddleware  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.init_db import ensure_schema, seed_defaults  # noqa: E402
from app.db.models import Referral  # noqa: E402
from app.services import settings_service, user_service  # noqa: E402
from app.services.notification_service import setup as setup_notifications  # noqa: E402

TOKEN = "42:TEST"

pytestmark = pytest.mark.asyncio(loop_scope="session")


class MockedBot(Bot):
    """Bot that records every API call and never touches the network."""

    def __init__(self, token: str = TOKEN) -> None:
        super().__init__(token=token)
        self.calls: list = []

    async def __call__(self, method, request_timeout=None):  # noqa: ANN001, ANN202
        self.calls.append(method)
        return MagicMock()


@pytest_asyncio.fixture(loop_scope="session", scope="session")
async def env():
    engine = create_async_engine("sqlite+aiosqlite://")
    sm = async_sessionmaker(engine, expire_on_commit=False)

    bot = MockedBot(TOKEN)
    setup_notifications(bot, [])
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbSessionMiddleware(sm))
    dp.include_router(setup_routers())
    yield dp, bot, sm, engine
    await bot.session.close()
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session", scope="function", autouse=True)
async def fresh(env):
    dp, bot, sm, engine = env
    filters_mod.db_admins.clear()
    if hasattr(dp.storage, "data"):
        dp.storage.data.clear()
    bot.calls.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with sm() as s:
        await seed_defaults(s)
        await settings_service.set_setting(s, "bot_username", "TestBotVPN")
        await s.commit()
    # like main.py: register DB admins into the in-memory admin cache
    async with sm() as s:
        from app.db.models import Admin

        for a in (await s.execute(select(Admin))).scalars().all():
            filters_mod.register_admin(a.telegram_id)
    yield


# ---------------- helpers ----------------


def tg_user(uid: int, first: str = "Ali") -> TgUser:
    return TgUser(id=uid, is_bot=False, first_name=first, username=f"u{uid}")


def msg_update(update_id: int, uid: int, text: str, first: str = "Ali") -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=uid, type="private"),
            from_user=tg_user(uid, first),
            text=text,
        ),
    )


def cb_update(update_id: int, uid: int, data: str, first: str = "Ali") -> Update:
    return Update(
        update_id=update_id,
        callback_query=CallbackQuery(
            id=str(update_id),
            from_user=tg_user(uid, first),
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=update_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=uid, type="private"),
                from_user=tg_user(uid, first),
                text="old message",
            ),
        ),
    )


def sent_texts(bot: MockedBot) -> list[str]:
    out = []
    for c in bot.calls:
        if isinstance(c, SendMessage) and c.text:
            out.append(c.text)
    return out


def kb_callback_datas(bot: MockedBot) -> set[str]:
    datas: set[str] = set()
    for c in bot.calls:
        if isinstance(c, SendMessage) and c.reply_markup is not None:
            for row in c.reply_markup.inline_keyboard or []:
                for b in row:
                    if b.callback_data:
                        datas.add(b.callback_data)
    return datas


async def start_user(dp, bot, uid: int) -> None:
    await dp.feed_update(bot, msg_update(uid, uid, "/start"))


# ---------------- tests ----------------


async def test_start_registers_user(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    assert any("خوش آمدید" in t for t in sent_texts(bot)), sent_texts(bot)
    async with sm() as s:
        user = await user_service.get_by_telegram_id(s, 100)
        assert user is not None


async def test_start_with_referral_payload(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 111)
    async with sm() as s:
        referrer = await user_service.get_by_telegram_id(s, 111)
        code = referrer.referral_code

    bot.calls.clear()
    await dp.feed_update(bot, msg_update(2, 222, f"/start ref_{code}"))
    async with sm() as s:
        new_user = await user_service.get_by_telegram_id(s, 222)
        assert new_user is not None
        assert new_user.referrer_id == referrer.id
        ref = await s.scalar(select(Referral).where(Referral.referred_id == new_user.id))
        assert ref is not None and ref.referrer_id == referrer.id
    assert any("لینک دعوت" in t for t in sent_texts(bot)), sent_texts(bot)


async def test_buy_button_opens_plans(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    bot.calls.clear()
    await dp.feed_update(bot, msg_update(2, 100, "🛍 خرید اشتراک"))
    texts = sent_texts(bot)
    assert any("سرویس مورد نظر" in t for t in texts), texts
    assert any(d.startswith("pl:") for d in kb_callback_datas(bot)), kb_callback_datas(bot)


async def test_full_purchase_flow(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    await dp.feed_update(bot, msg_update(2, 100, "🛍 خرید اشتراک"))
    bot.calls.clear()
    await dp.feed_update(bot, cb_update(3, 100, "pl:1"))
    assert any("نام کاربری" in t for t in sent_texts(bot)), sent_texts(bot)
    bot.calls.clear()
    await dp.feed_update(bot, msg_update(4, 100, "ali12"))
    texts = sent_texts(bot)
    assert any("پیش‌فاکتور" in t for t in texts), texts
    datas = kb_callback_datas(bot)
    assert any(d.startswith("pay:card:") for d in datas), datas
    # کیف پول خالی است (۰ < ۵۰۰۰۰) پس دکمه پرداخت از کیف پول نباید باشد
    assert not any(d.startswith("pay:wallet:") for d in datas), datas


async def test_purchase_cancel_button(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    await dp.feed_update(bot, msg_update(2, 100, "🛍 خرید اشتراک"))
    await dp.feed_update(bot, cb_update(3, 100, "pl:1"))
    bot.calls.clear()
    await dp.feed_update(bot, cb_update(4, 100, "pur:cancel"))
    assert any("لغو" in t for t in sent_texts(bot)), sent_texts(bot)


async def test_referral_menu_shows_link(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    bot.calls.clear()
    await dp.feed_update(bot, msg_update(2, 100, "🤝 زیرمجموعه‌گیری"))
    texts = sent_texts(bot)
    assert any("t.me/TestBotVPN?start=ref_" in t for t in texts), texts


async def test_wallet_menu(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    bot.calls.clear()
    await dp.feed_update(bot, msg_update(2, 100, "💰 کیف پول"))
    texts = sent_texts(bot)
    assert any("اطلاعات حساب کاربری" in t for t in texts), texts


async def test_wallet_cancel_button(env):
    dp, bot, sm, engine = env
    await start_user(dp, bot, 100)
    await dp.feed_update(bot, cb_update(2, 100, "wallet:dep"))
    bot.calls.clear()
    await dp.feed_update(bot, cb_update(3, 100, "wal:cancel"))
    assert any("لغو" in t for t in sent_texts(bot)), sent_texts(bot)
