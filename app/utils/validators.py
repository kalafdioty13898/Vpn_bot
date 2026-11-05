"""Input validation helpers (pure, testable — no aiogram imports)."""
from __future__ import annotations

import re

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def validate_vpn_username(
    value: str, min_len: int = 3, max_len: int = 32
) -> tuple[bool, str]:
    """Validate VPN service username. Returns (ok, error_code)."""
    value = value.strip()
    if not value:
        return False, "empty"
    if "@" in value or " " in value or "-" in value:
        return False, "bad_chars"
    if not value.isascii():
        return False, "non_english"
    if not USERNAME_RE.match(value):
        return False, "bad_chars"
    if len(value) < min_len:
        return False, "too_short"
    if len(value) > max_len:
        return False, "too_long"
    if value.startswith("_") or value.endswith("_"):
        return False, "bad_chars"
    return True, ""


def validate_card_number(value: str) -> bool:
    digits = re.sub(r"[\s-]", "", value.strip())
    if not digits.isdigit() or not (16 <= len(digits) <= 19):
        return False
    # Luhn check
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def parse_int(value: str) -> int | None:
    value = value.strip().replace(",", "").replace("،", "")
    if not re.match(r"^\d+$", value):
        return None
    return int(value)


def parse_signed_int(value: str) -> int | None:
    value = value.strip().replace(",", "").replace("،", "")
    if not re.match(r"^[+-]?\d+$", value):
        return None
    return int(value)


def parse_float(value: str) -> float | None:
    value = value.strip().replace(",", "").replace("،", "")
    if not re.match(r"^\d+(\.\d+)?$", value):
        return None
    return float(value)


def calc_custom_price(
    volume_gb: int,
    days: int,
    *,
    base_price_per_gb: int,
    min_price: int,
) -> int:
    """قیمت سرویس دلخواه: base_price_per_gb * volume * days / 30 با حداقل قیمت."""
    raw = base_price_per_gb * volume_gb * days / 30
    return max(min_price, int(round(raw / 1000.0) * 1000))
