from __future__ import annotations

from src.options.config import OPTIONS


def test_option_keys_unique() -> None:
    keys = [option.key for option in OPTIONS]
    assert len(keys) == len(set(keys))
