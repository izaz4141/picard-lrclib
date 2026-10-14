from __future__ import annotations

import os
import uuid
from functools import partial
from typing import Any
from urllib.parse import (
    quote,
    urlencode,
)

from picard.plugin3.api import (
    Album,
    File,
    Metadata,
    PluginApi,
)

from ..common import constants, state
from ..common.files import (
    lrc_base_path,
    lyrics_lrc_path,
    read_lyrics_file,
    remove_lrc_files,
    write_lyrics_file,
)
from ..common.util import pick_lyrics, plugin_name, truncate_text
from ..ui.dialogs import confirm_yes_no, show_critical
from ..ui.search_dialog import show_search_table
from .webservice import request


def fetch_lyrics(
    api: PluginApi,
    method: str,
    album: Album,
    metadata: Metadata,
    linked_files: list[File],
    length: int | None = None,
) -> None:
    """Build the LRCLIB request for a track and queue it."""
    artist = metadata["artist"]
    title = metadata["title"]
    album_name = metadata["album"]

    queryargs: dict[str, Any]
    if method == "search":
        url = constants.lrclib_search_url
        task_id = f"search_{title}_{album.id}_{uuid.uuid4().hex[:8]}"
        queryargs = {"q": title}
    else:
        url = constants.lrclib_get_url
        task_id = f"get_{artist}_{title}_{album.id}_{uuid.uuid4().hex[:8]}"
        queryargs = {
            "track_name": title,
            "artist_name": artist,
            "album_name": album_name,
        }
        if length:
            queryargs["duration"] = length

    api.logger.debug(
        f"{plugin_name(api)}: {'GET' if method != 'search' else 'SEARCH'} {quote(url)}?{urlencode(queryargs)}"
    )

    is_blocking = method == "get_on_load"

    request(
        api,
        url,
        album,
        task_id,
        partial(process_response, api, method, album, metadata, task_id, linked_files),
        queryargs,
        blocking=is_blocking,
        timeout=constants.GET_ON_LOAD_TIMEOUT if is_blocking else None,
    )


def process_response(
    api: PluginApi,
    method: str,
    album: Album,
    metadata: Metadata,
    task_id: str,
    linked_files: list[File],
    response: Any,
    reply: Any,
    error: Exception | None,
) -> None:
    """Embed returned lyrics and write sidecars for each linked file."""
    if error or (
        response and isinstance(response, dict) and not response.get("id", False)
    ):
        api.logger.warning(
            f'{plugin_name(api)}: lyrics NOT found for track "{metadata["title"]}" by {metadata["artist"]}'
        )
        if method == "get_on_save":
            for file in linked_files:
                state.files_processing.discard(file.filename)
        api.complete_album_task(album, task_id)
        return

    try:
        if method == "search":
            parent = getattr(api.tagger, "window", None)
            response = show_search_table(
                api, parent, metadata["title"], response, album
            )
            if response is None:
                return

        lyrics: str | None = None
        is_plain = False

        if (
            response.get("instrumental", False)
            or "(Instrumental)" in (response.get("trackName") or "")
            or "[au: instrumental]" in (response.get("plainLyrics") or "")
        ) and (api.plugin_config["ignore_instrumental"] and method != "search"):
            lyrics = None
        else:
            lyrics, is_plain = pick_lyrics(
                response, bool(api.plugin_config["prefer_synced_lyrics"])
            )
        if not isinstance(lyrics, str):
            return

        for file in linked_files:
            full_path = file.filename
            assert full_path is not None, "File path is None"
            base_path = lrc_base_path(full_path)
            file_lrc = lyrics_lrc_path(
                full_path, is_plain, api.plugin_config["plain_as_txt"]
            )
            file_lyrics = lyrics

            has_metadata_lyrics = bool(file.metadata.get("lyrics"))
            has_lrc_file = os.path.exists(file_lrc)

            if (
                has_metadata_lyrics
                and not has_lrc_file
                and api.plugin_config["save_lrc_file"]
                and method != "search"
            ):
                file_lyrics = file.metadata.get("lyrics")
                assert isinstance(file_lyrics, str), "Lyrics is not of type string"
            elif has_lrc_file and not has_metadata_lyrics and method != "search":
                file_lyrics = read_lyrics_file(file_lrc)
            elif (
                (
                    (has_metadata_lyrics and has_lrc_file)
                    or (has_metadata_lyrics and not api.plugin_config["save_lrc_file"])
                )
                and (not api.plugin_config["auto_overwrite"])
                and (method not in ["get_on_load", "get_on_save"])
            ):
                title = "Overwrite file lyrics?"
                desc = (
                    f'Overwrite Lyrics for "{file.metadata.get("title", "<file>")}".\n\n'
                    f"{truncate_text(file_lyrics, 5, 42)}"
                )
                parent = getattr(api.tagger, "window", None)
                if not confirm_yes_no(api.logger, parent, title, desc):
                    return

            file.metadata["lyrics"] = file_lyrics
            if api.plugin_config["save_lrc_file"]:
                write_error = write_lyrics_file(api, file_lrc, file_lyrics)
                if write_error is not None:
                    parent = getattr(api.tagger, "window", None)
                    show_critical(
                        api.logger,
                        parent,
                        "Failed to Save LRC File",
                        f"Could not save lyrics file:\n\n{file_lrc}\n\n"
                        f"Error: {write_error}",
                    )
                else:
                    remove_lrc_files(api, base_path, file_lrc)

        api.logger.debug(
            f'{plugin_name(api)}: lyrics loaded for track "{metadata["title"]}" by {metadata["artist"]}'
        )

    except (TypeError, KeyError, ValueError):
        api.logger.exception(
            f'{plugin_name(api)}: lyrics NOT loaded for track "{metadata["title"]}" by {metadata["artist"]}'
        )

    finally:
        if method == "get_on_save":
            for file in linked_files:
                file.save()

        api.complete_album_task(album, task_id)
