"""Formatting helpers: money, dates (Asia/Tehran + Jalali), volumes."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo

    TEHRAN = ZoneInfo("Asia/Tehran")
except Exception:  # pragma: no cover
    TEHRAN = timezone(timedelta(hours=3, minutes=30))

try:
    import jdatetime  # type: ignore
except Exception:  # pragma: no cover
    jdatetime = None


def money(amount: int | float) -> str:
    return f"{int(amount):,}"


def to_tehran(dt: datetime) -> datetime:
    if dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TEHRAN)


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    return to_tehran(dt).strftime("%Y-%m-%d %H:%M")


def jalali(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    t = to_tehran(dt)
    if jdatetime is not None:
        try:
            j = jdatetime.datetime.fromgregorian(datetime=t)
            return j.strftime("%Y/%m/%d %H:%M")
        except Exception:
            pass
    return t.strftime("%Y-%m-%d %H:%M")


def fmt_gb(volume_gb: float) -> str:
    if volume_gb < 1:
        return f"{int(round(volume_gb * 1024))} مگابایت"
    if volume_gb == int(volume_gb):
        return f"{int(volume_gb)} گیگابایت"
    return f"{volume_gb:g} گیگابایت"


def user_display_name(first_name: str | None, telegram_id: int) -> str:
    name = (first_name or "").strip()
    return name if name else f"کاربر گرامی ({telegram_id})"
