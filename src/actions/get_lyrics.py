from __future__ import annotations

from picard.plugin3.api import Album, Track

from ..common.metadata import get_track_duration
from ..common.util import plugin_name
from ..services.lrclib import fetch_lyrics
from .shared_action import LrcLibAction


class LrcLibLyricsGet(LrcLibAction):
    """Action that fetches lyrics automatically from LRCLIB."""

    TITLE = "Get lyrics automatically with LRCLIB"

    def execute_on_track(self, track: Track) -> None:
        """Fetch and embed lyrics for a single track."""
        try:
            if not track.files:  # If it's not in your local file then ignore
                return
            album = track.album
            assert isinstance(album, Album), "Album is not of type Album"
            length = get_track_duration(self.api, track)
            fetch_lyrics(self.api, "get", album, track.metadata, track.files, length)
        except Exception:
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error getting lyrics automatically for {track}"
            )
