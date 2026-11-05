"""Unique ID generators (cryptographically random, collision-safe)."""
from __future__ import annotations

import secrets

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _rand_suffix(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def gen_service_invoice_id() -> str:
    return f"TP-{_rand_suffix(10)}"


def gen_wallet_invoice_id() -> str:
    return f"WALLET-{_rand_suffix(8)}"


def gen_order_id() -> str:
    return f"ORD-{_rand_suffix(10)}"


def gen_payment_id() -> str:
    return f"PAY-{_rand_suffix(10)}"


def gen_referral_code() -> str:
    return _rand_suffix(8)


def gen_random_username(prefix: str = "vx") -> str:
    return f"{prefix}{secrets.token_hex(4)}"
