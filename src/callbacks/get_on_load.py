from __future__ import annotations

from typing import cast

from picard.plugin3.api import (
    Album,
    File,
    PluginApi,
    Track,
)

from ..common.metadata import get_track_duration
from ..common.util import plugin_name
from ..services.lrclib import fetch_lyrics


def get_on_load(api: PluginApi, track: Track, file: File) -> None:
    """Fetch lyrics when a file is added to a track.

    Only runs when the get_on_load option is enabled.
    """
    if not api.plugin_config["get_on_load"]:
        return
    try:
        if not track.files:
            return
        album = track.album
        assert isinstance(album, Album), "Album is not of type Album"
        length = get_track_duration(api, track)
        fetch_lyrics(
            api,
            "get_on_load",
            album,
            track.metadata,
            cast(list[File], track.files),
            length,
        )
    except Exception:
        api.logger.exception(f"{plugin_name(api)}: Error in get_on_load for {track}")
