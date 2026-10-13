from __future__ import annotations

import os
import shutil
import tempfile

from picard.plugin3.api import PluginApi

from .util import plugin_name


def lrc_base_path(filename: str) -> str:
    """Return the audio file path without its extension, used as the base for
    sidecar ``.lrc``/``.txt`` files."""
    dirname = os.path.dirname(filename)
    filename_no_ext = os.path.splitext(os.path.basename(filename))[0]
    return f"{dirname}/{filename_no_ext}"


def lyrics_lrc_path(filename: str, is_plain: bool, plain_as_txt: bool) -> str:
    """Return the sidecar path matching the given audio filename."""
    ext = ".txt" if (is_plain and plain_as_txt) else ".lrc"
    return f"{lrc_base_path(filename)}{ext}"


def read_lyrics_file(path: str) -> str:
    """Read a lyrics file and return its contents."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def remove_lrc_files(
    api: PluginApi, base_path: str, new_file: str | None = None
) -> None:
    """Delete stale lyrics sidecars, skipping ``new_file``"""
    for old_ext in (".txt", ".lrc"):
        old_file = base_path + old_ext
        if old_file == new_file or (
            old_ext == ".txt" and not has_matching_audio(api, base_path)
        ):
            continue
        elif os.path.exists(old_file):
            try:
                os.remove(old_file)
            except Exception:
                api.logger.exception(f"{plugin_name(api)}: Failed to delete {old_file}")


def write_lyrics_file(api: PluginApi, file_path: str, lyrics: str) -> str | None:
    """Write lyrics atomically, returning an error message on failure or None
    on success."""
    directory = os.path.dirname(file_path) or "."
    temp_path: str | None = None
    try:
        fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".lrc-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(lyrics)
        if os.path.exists(file_path):
            shutil.copymode(file_path, temp_path)
        else:
            os.chmod(temp_path, 0o644)
        os.replace(temp_path, file_path)
    except Exception as e:
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                api.logger.exception(
                    f"{plugin_name(api)}: Failed to remove temporary file {temp_path}"
                )
        api.logger.exception(f"{plugin_name(api)}: Failed to write .lrc file")
        return str(e)
    return None


def supported_audio_extensions(api: PluginApi) -> frozenset[str]:
    """Return Picard's supported audio extensions, lowercase and dotted."""
    return frozenset(
        ext if ext.startswith(".") else f".{ext}"
        for ext in api.tagger.format_registry.supported_extensions()
    )


def plugin_sidecar_extensions(api: PluginApi) -> set[str]:
    """Return the sidecar extensions this plugin may write"""
    extensions = {".lrc"}
    if api.plugin_config["plain_as_txt"]:
        extensions.add(".txt")
    return extensions


def has_matching_audio(api: PluginApi, base_path: str) -> bool:
    """Return True when a same-stem audio file exists next to ``base_path``"""
    return any(
        os.path.isfile(f"{base_path}{ext}") for ext in supported_audio_extensions(api)
    )


def find_orphaned_sidecars(api: PluginApi, root_dir: str) -> list[str]:
    """Return paths of orphaned lyrics sidecars under a directory.

    A sidecar is orphaned when no audio file in the same directory shares
    its base name, compared without regard to case. The list is empty when
    the directory or the audio format list is unavailable.
    """
    if not os.path.isdir(root_dir):
        api.logger.warning(f"{plugin_name(api)}: Directory does not exist: {root_dir}")
        return []

    audio_extensions = supported_audio_extensions(api)
    if not audio_extensions:
        api.logger.warning(
            f"{plugin_name(api)}: No supported audio formats found, aborting cleanup"
        )
        return []

    sidecar_extensions = plugin_sidecar_extensions(api)

    orphaned: list[str] = []

    try:
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            audio_stems: set[str] = set()
            for name in filenames:
                stem, ext = os.path.splitext(name)
                if ext.lower() in audio_extensions:
                    audio_stems.add(stem.lower())

            for name in filenames:
                stem, ext = os.path.splitext(name)
                if ext.lower() not in sidecar_extensions:
                    continue
                if stem.lower() in audio_stems:
                    continue
                orphaned.append(os.path.join(dirpath, name))

    except Exception:
        api.logger.exception(f"{plugin_name(api)}: Error scanning directory {root_dir}")

    return orphaned


def remove_sidecars(api: PluginApi, paths: list[str]) -> int:
    """Delete the given files and return the number removed."""
    removed = 0
    for path in paths:
        try:
            os.remove(path)
            removed += 1
            api.logger.debug(f"{plugin_name(api)}: Deleted orphaned file: {path}")
        except Exception:
            api.logger.exception(f"{plugin_name(api)}: Failed to delete {path}")
    return removed
