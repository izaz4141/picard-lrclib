from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.common.metadata import get_track_duration


class FakeFile:
    def __init__(self, metadata: Any) -> None:
        self.metadata = metadata


class FakeTrack:
    def __init__(self, metadata: Any, files: list[Any] | None = None) -> None:
        self.metadata = metadata
        self.files = files or []

    @property
    def num_linked_files(self) -> int:
        return len(self.files)


def test_get_track_duration_from_metadata(
    make_api: Callable[..., Any], make_metadata: Callable[..., Any]
) -> None:
    api = make_api()
    track: Any = FakeTrack(make_metadata("3:20"))

    assert get_track_duration(api, track) == 200


def test_get_track_duration_falls_back_to_file(
    make_api: Callable[..., Any], make_metadata: Callable[..., Any]
) -> None:
    api = make_api()
    file = FakeFile(make_metadata("1:05"))
    track: Any = FakeTrack(make_metadata(), files=[file])

    assert get_track_duration(api, track) == 65
    assert api.logger.warnings


def test_get_track_duration_missing_raises(
    make_api: Callable[..., Any], make_metadata: Callable[..., Any]
) -> None:
    api = make_api()
    track: Any = FakeTrack(make_metadata(), files=[])

    with pytest.raises(AssertionError):
        get_track_duration(api, track)
