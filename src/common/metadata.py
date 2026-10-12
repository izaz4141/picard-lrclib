from __future__ import annotations

from picard.plugin3.api import Metadata, PluginApi, Track

from .util import parse_duration, plugin_name


def get_track_duration(api: PluginApi, track: Track) -> int:
    """Return the track length in seconds, falling back to its first file."""
    metadata = track.metadata
    assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
    length = None
    if metadata["~length"]:
        length = parse_duration(str(metadata["~length"]))
    else:
        api.logger.warning(
            f'{plugin_name(api)}: length NOT found for in metadata for track "{metadata["title"]}", falling back to file length'
        )
        assert track.num_linked_files > 0, f"No files linked to {metadata['title']}"
        tr_metadata = track.files[0].metadata
        if tr_metadata["~length"]:
            length = parse_duration(str(tr_metadata["~length"]))
    assert isinstance(length, int), (
        "Length is type " + str(type(length)) + ", not of type integer"
    )
    return length
