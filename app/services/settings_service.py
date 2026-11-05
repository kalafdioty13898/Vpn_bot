"""Key-value settings service (all values editable from admin panel)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotSetting
from app.db.init_db import SETTINGS_DEFAULTS


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    value = await session.scalar(select(BotSetting.value).where(BotSetting.key == key))
    if value is None:
        return SETTINGS_DEFAULTS.get(key, default)
    return value


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(BotSetting, key)
    if row is None:
        session.add(BotSetting(key=key, value=value))
    else:
        row.value = value
    await session.flush()


async def get_bool(session: AsyncSession, key: str) -> bool:
    return (await get_setting(session, key)) in ("1", "true", "True", "yes")


async def get_int(session: AsyncSession, key: str, default: int = 0) -> int:
    try:
        return int(await get_setting(session, key))
    except (TypeError, ValueError):
        return default


async def get_float(session: AsyncSession, key: str, default: float = 0.0) -> float:
    try:
        return float(await get_setting(session, key))
    except (TypeError, ValueError):
        return default


async def get_all(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(BotSetting))).scalars().all()
    data = dict(SETTINGS_DEFAULTS)
    for row in rows:
        data[row.key] = row.value
    return data


async def toggle(session: AsyncSession, key: str) -> bool:
    new_value = not await get_bool(session, key)
    await set_setting(session, key, "1" if new_value else "0")
    return new_value
