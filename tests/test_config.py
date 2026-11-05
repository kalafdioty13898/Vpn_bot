"""Tests for admin ID parsing robustness (config._parse_admin_ids)."""
from app.config import _parse_admin_ids


def test_plain_id():
    assert _parse_admin_ids("8581608010") == (8581608010,)


def test_comma_separated():
    assert _parse_admin_ids("111,222,333") == (111, 222, 333)


def test_quotes_and_brackets():
    assert _parse_admin_ids('"8581608010"') == (8581608010,)
    assert _parse_admin_ids("[111, 222]") == (111, 222)
    assert _parse_admin_ids("(111)") == (111,)


def test_persian_and_semicolon_separators():
    assert _parse_admin_ids("111؛222") == (111, 222)
    assert _parse_admin_ids("111،222") == (111, 222)


def test_noise_ignored():
    assert _parse_admin_ids("admin, @user, , 42") == (42,)


def test_empty_and_none():
    assert _parse_admin_ids("") == ()
    assert _parse_admin_ids(None) == ()


def test_no_duplicates():
    assert _parse_admin_ids("111,111, 111") == (111,)
