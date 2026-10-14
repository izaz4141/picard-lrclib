from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from picard.plugin3.api import Metadata

DEFAULT_CONFIG: dict[str, Any] = {"plain_as_txt": False, "prefer_synced_lyrics": True}
DEFAULT_EXTENSIONS = [".mp3", ".flac", ".ogg"]


class FakeManifest:
    def name_i18n(self) -> str:
        return "LRCLIB Lyrics"


class FakeLogger:
    """Collects log calls so tests can assert on them."""

    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.debugs: list[str] = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def exception(self, message: str) -> None:
        self.errors.append(message)

    def debug(self, message: str) -> None:
        self.debugs.append(message)


class FakeFormatRegistry:
    def __init__(self, extensions: list[str]) -> None:
        self._extensions = extensions

    def supported_extensions(self) -> list[str]:
        return list(self._extensions)


class FakeTagger:
    def __init__(self, extensions: list[str]) -> None:
        self.format_registry = FakeFormatRegistry(extensions)


class FakePluginConfig:
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class FakeApi:
    """A stand-in for ``PluginApi``.

    The real ``PluginApi`` requires a manifest, a live tagger and Qt, so the
    plugin's logic is exercised against this minimal fake instead.
    """

    def __init__(self, config: dict[str, Any], extensions: list[str]) -> None:
        self.logger = FakeLogger()
        self.manifest = FakeManifest()
        self.tagger = FakeTagger(extensions)
        self.plugin_config = FakePluginConfig(config)


@pytest.fixture
def make_api() -> Callable[..., Any]:
    """Return a factory that builds a fake ``PluginApi``.

    The factory is typed as returning ``Any`` so the fake can stand in for the
    real ``PluginApi`` at call sites without static type errors.
    """

    def _make(
        config: dict[str, Any] | None = None,
        extensions: list[str] | None = None,
    ) -> Any:
        return FakeApi(
            dict(DEFAULT_CONFIG) if config is None else config,
            list(DEFAULT_EXTENSIONS) if extensions is None else extensions,
        )

    return _make


@pytest.fixture
def make_metadata() -> Callable[..., Any]:
    """Return a factory that builds real Picard ``Metadata`` objects."""

    def _make(length: str | None = None) -> Any:
        metadata = Metadata()
        metadata["title"] = "Song"
        if length is not None:
            metadata["~length"] = length
        return metadata

    return _make
