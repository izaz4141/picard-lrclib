from __future__ import annotations

from typing import TypedDict


class LrclibTrack(TypedDict, total=False):
    """A single track object returned by the LRCLIB API."""

    id: int
    trackName: str
    artistName: str
    albumName: str
    duration: int
    instrumental: bool
    plainLyrics: str | None
    syncedLyrics: str | None
