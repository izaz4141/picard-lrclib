from __future__ import annotations

from picard.plugin3.api import (
    Album,
    File,
    Metadata,
    PluginApi,
    Track,
)

from ..common import state
from ..common.util import parse_duration, plugin_name
from ..services.lrclib import fetch_lyrics


def get_on_save(api: PluginApi, file: File) -> None:
    """Fetch lyrics when a file is saved.

    Only runs when the get_on_save option is enabled.
    """
    if not api.plugin_config["get_on_save"]:
        return
    filename = file.filename
    if filename in state.files_processing:
        state.files_processing.discard(filename)
        return  # Picard only allow one concurrent save_hook
    try:
        parent = file.parent_item
        album = parent.album if isinstance(parent, Track) else None
        if album is None:
            return  # file is not part of a track in an album, nothing to fetch
        state.files_processing.add(filename)
        assert isinstance(album, Album), "Album is not of type Album"
        metadata = file.metadata
        assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
        length = None
        if metadata["~length"]:
            length = parse_duration(str(metadata["~length"]))
        assert isinstance(length, int), "Length is not of type integer"
        fetch_lyrics(api, "get_on_save", album, metadata, [file], length)
    except Exception:
        api.logger.exception(f"{plugin_name(api)}: Error in get_on_save for {filename}")
        state.files_processing.discard(filename)
