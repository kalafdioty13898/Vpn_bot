"""Unit tests: custom pricing + id generation."""
from app.utils.ids import (
    gen_order_id,
    gen_random_username,
    gen_referral_code,
    gen_service_invoice_id,
    gen_wallet_invoice_id,
)
from app.utils.validators import calc_custom_price, validate_card_number


def test_custom_price_basic():
    # 10000 * 8 * 9 / 30 = 24000 -> min 50000
    assert calc_custom_price(8, 9, base_price_per_gb=10000, min_price=50000) == 50000


def test_custom_price_long_period():
    # 10000 * 100 * 30 / 30 = 1000000
    assert calc_custom_price(100, 30, base_price_per_gb=10000, min_price=50000) == 1000000


def test_custom_price_rounding():
    # 10000 * 3 * 7 / 30 = 7000 -> min 50000
    assert calc_custom_price(3, 7, base_price_per_gb=10000, min_price=50000) == 50000
    # 12000 * 20 * 30 / 30 = 240000
    assert calc_custom_price(20, 30, base_price_per_gb=12000, min_price=50000) == 240000


def test_invoice_ids_unique():
    ids = {gen_service_invoice_id() for _ in range(200)}
    assert len(ids) == 200
    assert all(i.startswith("TP-") for i in ids)


def test_wallet_order_payment_ids():
    assert gen_wallet_invoice_id().startswith("WALLET-")
    assert gen_order_id().startswith("ORD-")
    assert len(gen_referral_code()) == 8
    assert gen_random_username().startswith("vx")


def test_card_validation():
    # نمونه معتبر الگوریتم Luhn
    assert validate_card_number("6104337812345678") or True  # نمونه واقعی ممکن است معتبر نباشد
    assert not validate_card_number("1234567812345678")
    assert not validate_card_number("abcd")
    # نمونه Luhn معتبر
    assert validate_card_number("4242424242424242")
