from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from typing import Any

from picard.plugin3.api import (
    Album,
    BaseAction,
    Track,
)

from ..common.util import plugin_name


class LrcLibAction(BaseAction):
    """Shared context-menu callback dispatching to per-track handling."""

    def callback(self, objs: Iterable[Any]) -> None:
        """Dispatch the action to each selected track."""
        for item in (t for t in objs if isinstance(t, (Track, Album))):
            if isinstance(item, Track):
                self.api.logger.debug(f"{plugin_name(self.api)}: {item}, {item.album}")
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    self.api.logger.debug(f"{plugin_name(self.api)}: {track}, {item}")
                    self.execute_on_track(track)

    @abstractmethod
    def execute_on_track(self, track: Track) -> None:
        """Apply the action to a single track."""
