from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.common.files import (
    find_orphaned_sidecars,
    lrc_base_path,
    lyrics_lrc_path,
    read_lyrics_file,
    remove_lrc_files,
    remove_sidecars,
    write_lyrics_file,
)


def test_lrc_base_path() -> None:
    assert lrc_base_path("/music/artist/song.mp3") == "/music/artist/song"
    assert lrc_base_path("/m/song.flac") == "/m/song"
    assert lrc_base_path("/a/b/with.dots.name.ogg") == "/a/b/with.dots.name"


def test_lyrics_lrc_path() -> None:
    assert lyrics_lrc_path("/m/song.mp3", False, False) == "/m/song.lrc"
    assert lyrics_lrc_path("/m/song.mp3", True, False) == "/m/song.lrc"
    assert lyrics_lrc_path("/m/song.mp3", True, True) == "/m/song.txt"
    assert lyrics_lrc_path("/m/song.mp3", False, True) == "/m/song.lrc"


def test_read_write_roundtrip(tmp_path: Path, make_api: Callable[..., Any]) -> None:
    api = make_api()
    target = tmp_path / "song.lrc"
    assert write_lyrics_file(api, str(target), "héllo\nworld") is None
    assert read_lyrics_file(str(target)) == "héllo\nworld"


def test_write_lyrics_file_preserves_permissions(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api()
    target = tmp_path / "song.lrc"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, 0o640)

    assert write_lyrics_file(api, str(target), "new") is None

    assert target.stat().st_mode & 0o777 == 0o640


def test_write_lyrics_file_error(tmp_path: Path, make_api: Callable[..., Any]) -> None:
    api = make_api()
    bad_path = tmp_path / "missing" / "song.lrc"
    error = write_lyrics_file(api, str(bad_path), "x")
    assert error is not None
    assert api.logger.errors


def test_write_lyrics_file_preserves_old_on_failure(
    tmp_path: Path, make_api: Callable[..., Any], monkeypatch: Any
) -> None:
    api = make_api()
    target = tmp_path / "song.lrc"
    target.write_text("old", encoding="utf-8")

    def fail_replace(*args: Any, **kwargs: Any) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", fail_replace)

    error = write_lyrics_file(api, str(target), "new")

    assert error is not None
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".lrc-*.tmp"))


def test_remove_lrc_files(tmp_path: Path, make_api: Callable[..., Any]) -> None:
    api = make_api()
    base = tmp_path / "song"
    lrc = tmp_path / "song.lrc"
    txt = tmp_path / "song.txt"
    lrc.write_text("a", encoding="utf-8")
    txt.write_text("b", encoding="utf-8")

    remove_lrc_files(api, str(base))

    assert not lrc.exists()
    assert not txt.exists()


def test_remove_lrc_files_skips_new_file(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api()
    base = tmp_path / "song"
    lrc = tmp_path / "song.lrc"
    txt = tmp_path / "song.txt"
    lrc.write_text("a", encoding="utf-8")
    txt.write_text("b", encoding="utf-8")

    remove_lrc_files(api, str(base), str(lrc))

    assert lrc.exists()
    assert not txt.exists()


def test_find_orphaned_sidecars(tmp_path: Path, make_api: Callable[..., Any]) -> None:
    api = make_api(config={"plain_as_txt": False})
    (tmp_path / "song.mp3").write_text("", encoding="utf-8")
    (tmp_path / "song.lrc").write_text("", encoding="utf-8")
    (tmp_path / "orphan.lrc").write_text("", encoding="utf-8")
    (tmp_path / "plain.txt").write_text("", encoding="utf-8")

    assert find_orphaned_sidecars(api, str(tmp_path)) == [str(tmp_path / "orphan.lrc")]


def test_find_orphaned_sidecars_case_insensitive(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api(config={"plain_as_txt": False})
    (tmp_path / "Song.MP3").write_text("", encoding="utf-8")
    (tmp_path / "song.lrc").write_text("", encoding="utf-8")

    assert find_orphaned_sidecars(api, str(tmp_path)) == []


def test_find_orphaned_sidecars_txt(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api(config={"plain_as_txt": True})
    (tmp_path / "song.mp3").write_text("", encoding="utf-8")
    (tmp_path / "orphan.txt").write_text("", encoding="utf-8")
    (tmp_path / "stale.lrc").write_text("", encoding="utf-8")

    result = sorted(find_orphaned_sidecars(api, str(tmp_path)))
    expected = sorted([str(tmp_path / "orphan.txt"), str(tmp_path / "stale.lrc")])
    assert result == expected


def test_find_orphaned_sidecars_missing_dir(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api()
    assert find_orphaned_sidecars(api, str(tmp_path / "nope")) == []
    assert api.logger.warnings


def test_find_orphaned_sidecars_no_formats(
    tmp_path: Path, make_api: Callable[..., Any]
) -> None:
    api = make_api(config={"plain_as_txt": False}, extensions=[])
    (tmp_path / "orphan.lrc").write_text("", encoding="utf-8")

    assert find_orphaned_sidecars(api, str(tmp_path)) == []
    assert api.logger.warnings


def test_remove_sidecars(tmp_path: Path, make_api: Callable[..., Any]) -> None:
    api = make_api()
    first = tmp_path / "a.lrc"
    second = tmp_path / "b.lrc"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    removed = remove_sidecars(
        api, [str(first), str(second), str(tmp_path / "missing.lrc")]
    )

    assert removed == 2
    assert not first.exists()
    assert not second.exists()
