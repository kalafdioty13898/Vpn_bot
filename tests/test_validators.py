"""Unit tests: username validation."""
from app.utils.validators import validate_vpn_username


def test_valid_usernames():
    for u in ("ali12", "mahdi", "ws1_ksdf", "vx0a1b2c3d"):
        ok, err = validate_vpn_username(u)
        assert ok, f"{u} should be valid ({err})"


def test_invalid_usernames():
    bad = ["ali_", "_mahdi", "tele@", "محسن", "ali reza", "ali-reza", "ab", "x" * 40, ""]
    for u in bad:
        ok, err = validate_vpn_username(u)
        assert not ok, f"{u} should be invalid"


def test_length_limits():
    ok, _ = validate_vpn_username("abc", 3, 32)
    assert ok
    ok, _ = validate_vpn_username("ab", 3, 32)
    assert not ok
    ok, _ = validate_vpn_username("a" * 33, 3, 32)
    assert not ok
