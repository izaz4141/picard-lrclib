from __future__ import annotations

from typing import NamedTuple

from picard.plugin3.api import PluginApi


class Option(NamedTuple):
    """A plugin option: config key, checkbox label, and default value."""

    key: str
    desc: str
    default: bool


# All plugin options in display order.
OPTIONS: tuple[Option, ...] = (
    Option(
        "prefer_synced_lyrics", "Prefer synchronized lyrics over plain lyrics", True
    ),
    Option("get_on_load", "Search for lyrics when loading tracks", False),
    Option("get_on_save", "Search for lyrics when saving files", False),
    Option("auto_overwrite", "Auto overwrite existing lyrics", False),
    Option("save_lrc_file", "Save .lrc file alongside audio files", False),
    Option("ignore_instrumental", "Ignore instrumental lyrics", False),
    Option("plain_as_txt", "Save plain lyrics as .txt", False),
)


def register_options(api: PluginApi) -> None:
    """Register all plugin options with their default values."""
    for option in OPTIONS:
        api.plugin_config.register_option(option.key, option.default)
