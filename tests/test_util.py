from __future__ import annotations

import pytest

from src.common.util import format_duration, parse_duration, truncate_text


def test_format_duration_minutes() -> None:
    assert format_duration(0) == "0:00"
    assert format_duration(59) == "0:59"
    assert format_duration(60) == "1:00"
    assert format_duration(3599) == "59:59"


def test_format_duration_hours() -> None:
    assert format_duration(3600) == "1:00:00"
    assert format_duration(3661) == "1:01:01"
    assert format_duration(86399) == "23:59:59"


def test_parse_duration_minutes() -> None:
    assert parse_duration("1:00") == 60
    assert parse_duration("0:59") == 59
    assert parse_duration("2:30 ") == 150


def test_parse_duration_hours() -> None:
    assert parse_duration("1:01:01") == 3661


def test_parse_duration_zero_padded() -> None:
    assert parse_duration("02:30") == 150
    assert parse_duration("01:02:30") == 3750
    assert parse_duration("00:00:00") == 0


@pytest.mark.parametrize("seconds", [0, 5, 60, 3599, 3600, 3661])
def test_parse_duration_roundtrip(seconds: int) -> None:
    assert parse_duration(format_duration(seconds)) == seconds


@pytest.mark.parametrize("value", ["", "abc", "1:x", "1:2:3:4"])
def test_parse_duration_invalid(value: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(value)


def test_truncate_text_short_unchanged() -> None:
    assert truncate_text("hello\nworld") == "hello\nworld"


def test_truncate_text_long_line() -> None:
    result = truncate_text("x" * 100, max_lines=5, max_chars_per_line=10)
    assert len(result.splitlines()) == 1
    assert result.endswith("…")


def test_truncate_text_max_lines() -> None:
    text = "\n".join(str(i) for i in range(10))
    result = truncate_text(text, max_lines=3)
    lines = result.splitlines()
    assert len(lines) == 3
    assert lines[-1].endswith("…")
