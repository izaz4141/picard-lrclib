from __future__ import annotations

from typing import cast

from picard.plugin3.api import Album, File, Track

from ..common.util import plugin_name
from ..services.lrclib import fetch_lyrics
from .shared_action import LrcLibAction


class LrcLibLyricsSearch(LrcLibAction):
    """Action that searches LRCLIB interactively."""

    TITLE = "Search lyrics manually with LRCLIB"

    def execute_on_track(self, track: Track) -> None:
        """Show the LRCLIB search dialog for a single track."""
        try:
            if not track.files:  # If it's not in your local file then ignore
                return
            album = track.album
            assert isinstance(album, Album), "Album is not of type Album"
            fetch_lyrics(
                self.api,
                "search",
                album,
                track.metadata,
                cast(list[File], track.files),
            )
        except Exception:
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error searching lyrics manually for {track}"
            )
