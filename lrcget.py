from __future__ import annotations

import json
import os
from functools import partial
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from picard.album_requests import TaskType
from picard.plugin3.api import Album, BaseAction, File, Metadata, OptionsPage, PluginApi, Track
from PyQt6 import QtCore, QtGui, QtWidgets

PLUGIN_NAME = "LRCLIB Lyrics"
LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"

DEFAULTS = {
    "get_on_load": False,
    "get_on_save": False,
    "auto_overwrite": False,
    "save_lrc_file": True,
    "ignore_instrumental": False,
    "plain_as_txt": False,
}

files_processing: set[str] = set()


def format_duration(duration: int) -> str:
    hours, remainder = divmod(int(duration), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


def parse_duration(value: str) -> int:
    parts = value.strip().split(":")
    if not all(part.isdigit() for part in parts):
        raise ValueError(f"Invalid time format: {value}")
    if len(parts) == 2:
        minutes, seconds = map(int, parts)
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Unsupported time format: {value}")


def get_track_duration(api: PluginApi, track: Track) -> int:
    if track.metadata["~length"]:
        return parse_duration(str(track.metadata["~length"]))
    if track.files and track.files[0].metadata["~length"]:
        return parse_duration(str(track.files[0].metadata["~length"]))
    raise ValueError(f"Length is not available for {track.metadata.get('title', '<unknown>')}")


def confirm_replace(parent, filename: str, lyrics: str) -> bool:
    preview = "\n".join(lyrics.splitlines()[:5])
    if len(preview) > 220:
        preview = preview[:219] + "…"
    reply = QtWidgets.QMessageBox.question(
        parent,
        "Overwrite file lyrics?",
        f'Overwrite lyrics for "{filename}"?\n\n{preview}',
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    return reply == QtWidgets.QMessageBox.StandardButton.Yes


def fetch_search_json(api: PluginApi, query: str):
    try:
        request = Request(
            f"{LRCLIB_SEARCH_URL}?{urlencode({'q': query})}",
            headers={"User-Agent": "Picard-LRCLIB/3.0"},
        )
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8")) if response.status == 200 else []
    except Exception as exc:
        api.logger.error("%s: search request failed: %s", PLUGIN_NAME, exc)
        return []


def show_search_table(api: PluginApi, query: str, response):
    dialog = QtWidgets.QDialog(api.tagger.window)
    dialog.setWindowTitle("Search Tracks")
    dialog.resize(700, 400)
    layout = QtWidgets.QVBoxLayout(dialog)
    search_layout = QtWidgets.QHBoxLayout()
    search_input = QtWidgets.QLineEdit(query)
    search_button = QtWidgets.QPushButton("Search")
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)

    table = QtWidgets.QTableWidget(dialog)
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(["#", "Name", "Artist", "Length", "Album", "Synced"])
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
    header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Interactive)
    header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    layout.addWidget(table)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)
    current_response = list(response) if isinstance(response, list) else []

    def populate(items):
        nonlocal current_response
        current_response = list(items) if isinstance(items, list) else []
        table.setRowCount(len(current_response))
        for row, item in enumerate(current_response):
            values = [
                str(row + 1), item.get("trackName") or "?", item.get("artistName") or "?",
                format_duration(item.get("duration") or 0), item.get("albumName") or "?",
                "Yes" if item.get("syncedLyrics") else "No",
            ]
            for col, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                if col in (0, 3, 5):
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if col == 5:
                    cell.setForeground(QtGui.QColor("#2ecc71" if item.get("syncedLyrics") else "#e74c3c"))
                table.setItem(row, col, cell)

    populate(current_response)

    def search():
        text = search_input.text().strip()
        if text:
            populate(fetch_search_json(api, text))

    search_button.clicked.connect(search)
    search_input.returnPressed.connect(search)
    table.doubleClicked.connect(lambda index: dialog.accept() if index.isValid() else None)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        row = table.currentRow()
        return current_response[row] if 0 <= row < len(current_response) else None
    return None


def request_lyrics(api: PluginApi, method: str, album: Album, metadata: Metadata, files: list[File], length: int | None = None):
    if method == "search":
        url = LRCLIB_SEARCH_URL
        queryargs = {"q": metadata.get("title", "")}
    else:
        url = LRCLIB_GET_URL
        queryargs = {
            "track_name": metadata.get("title", ""),
            "artist_name": metadata.get("artist", ""),
            "album_name": metadata.get("album", ""),
        }
        if length:
            queryargs["duration"] = length

    task_id = f"lrclib_{method}_{id(album)}_{id(files[0]) if files else id(album)}"

    def create_request():
        return api.web_service.get_url(
            url=url,
            handler=partial(process_response, api, method, album, metadata, files, task_id),
            parse_response_type="json",
            priority=True,
            queryargs=queryargs,
        )

    if method in {"get_on_load", "get_on_save"}:
        album.add_task(
            task_id,
            TaskType.PLUGIN,
            "Fetching LRCLIB lyrics",
            timeout=30,
            plugin_id=api.plugin_id,
            request_factory=create_request,
        )
    else:
        create_request()


def process_response(api: PluginApi, method: str, album: Album, metadata: Metadata, files: list[File], task_id: str, response, reply, error):
    try:
        if error or not response:
            api.logger.warning('%s: lyrics not found for "%s"', PLUGIN_NAME, metadata.get("title", "<unknown>"))
            return
        if method == "search":
            response = show_search_table(api, metadata.get("title", ""), response)
            if response is None:
                return
        if not isinstance(response, dict):
            return

        instrumental = (
            response.get("instrumental", False)
            or "(Instrumental)" in (response.get("trackName") or "")
            or "[au: instrumental]" in (response.get("plainLyrics") or "")
        )
        if instrumental and api.plugin_config["ignore_instrumental"] and method != "search":
            return

        synced = bool(response.get("syncedLyrics"))
        lyrics = response.get("syncedLyrics") or response.get("plainLyrics")
        if not isinstance(lyrics, str):
            return

        for file in files:
            if not file.filename:
                continue
            base = os.path.splitext(file.filename)[0]
            ext = ".txt" if not synced and api.plugin_config["plain_as_txt"] else ".lrc"
            sidecar = base + ext
            has_embedded = bool(file.metadata.get("lyrics"))
            has_sidecar = os.path.exists(sidecar)

            if has_embedded and not has_sidecar and api.plugin_config["save_lrc_file"] and method != "search":
                lyrics = file.metadata["lyrics"]
            elif has_sidecar and not has_embedded and method != "search":
                with open(sidecar, encoding="utf-8") as handle:
                    lyrics = handle.read()
            elif (
                (has_embedded and has_sidecar) or (has_embedded and not api.plugin_config["save_lrc_file"])
            ) and not api.plugin_config["auto_overwrite"] and method not in {"get_on_load", "get_on_save"}:
                if not confirm_replace(api.tagger.window, file.metadata.get("title", "<file>"), lyrics):
                    continue

            file.metadata["lyrics"] = lyrics
            if api.plugin_config["save_lrc_file"]:
                for old_ext in (".txt", ".lrc"):
                    old_path = base + old_ext
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError as exc:
                            api.logger.error("%s: cannot remove %s: %s", PLUGIN_NAME, old_path, exc)
                try:
                    with open(sidecar, "w", encoding="utf-8") as handle:
                        handle.write(lyrics)
                except OSError as exc:
                    api.logger.error("%s: cannot write %s: %s", PLUGIN_NAME, sidecar, exc)
    except (TypeError, KeyError, ValueError, OSError) as exc:
        api.logger.error("%s: processing failed: %s", PLUGIN_NAME, exc, exc_info=True)
    finally:
        if method == "get_on_save":
            for file in files:
                if file.filename:
                    files_processing.discard(file.filename)
                file.save()
        if method in {"get_on_load", "get_on_save"}:
            api.complete_album_task(album, task_id)


def get_on_load(api: PluginApi, track: Track, file: File):
    if not api.plugin_config["get_on_load"] or not track.files:
        return
    try:
        request_lyrics(api, "get_on_load", track.album, track.metadata, track.files, get_track_duration(api, track))
    except Exception as exc:
        api.logger.error("%s: load failed: %s", PLUGIN_NAME, exc, exc_info=True)


def get_on_save(api: PluginApi, file: File):
    if not api.plugin_config["get_on_save"] or not file.filename:
        return
    if file.filename in files_processing:
        files_processing.discard(file.filename)
        return
    try:
        files_processing.add(file.filename)
        metadata = file.metadata
        length = parse_duration(str(metadata["~length"])) if metadata["~length"] else None
        if length is None:
            raise ValueError("Length is not available")
        request_lyrics(api, "get_on_save", file.parent.album, metadata, [file], length)
    except Exception as exc:
        files_processing.discard(file.filename)
        api.logger.error("%s: save failed: %s", PLUGIN_NAME, exc, exc_info=True)


class LrclibLyricsOptionsPage(OptionsPage):
    NAME = "lrclib_lyrics"
    TITLE = "LRCLIB Lyrics"
    PARENT = "plugins"

    AUDIO_EXTENSIONS = {
        "aac", "ac3", "aif", "aifc", "aiff", "ape", "asf", "dff", "dsf", "eac3", "flac",
        "kar", "m2a", "ofr", "ofs", "oga", "ogg", "oggflac", "oggtheora", "ogv", "ogx",
        "opus", "spx", "tak", "tta", "wav", "webm", "wma", "wmv", "wv", "xwma",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api = self.__class__.api
        box = QtWidgets.QVBoxLayout(self)
        self.get_on_load = QtWidgets.QCheckBox("Search for lyrics when loading tracks")
        self.get_on_save = QtWidgets.QCheckBox("Search for lyrics when saving files")
        self.auto_overwrite = QtWidgets.QCheckBox("Auto overwrite existing lyrics")
        self.save_lrc = QtWidgets.QCheckBox("Save .lrc file alongside audio files")
        self.ignore_instrumental = QtWidgets.QCheckBox("Ignore instrumental lyrics")
        self.plain_as_txt = QtWidgets.QCheckBox("Save plain lyrics as .txt")
        for widget in (self.get_on_load, self.get_on_save, self.auto_overwrite, self.save_lrc, self.ignore_instrumental, self.plain_as_txt):
            box.addWidget(widget)
        box.addSpacing(20)
        box.addWidget(QtWidgets.QLabel("Cleanup Tools:"))
        self.cleanup_button = QtWidgets.QPushButton("Clean Orphaned LRC Files")
        self.cleanup_button.clicked.connect(self.clean_orphaned_lrc_files)
        box.addWidget(self.cleanup_button)
        box.addItem(QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding))
        box.addWidget(QtWidgets.QLabel(
            "LRCLIB provides lyrics from a crowdsourced database.\n"
            "Lyrics are intended for educational and personal use.\n"
            "Searching for lyrics when loading tracks can slow the loading process."
        ))

    def load(self):
        for name, widget in (
            ("get_on_load", self.get_on_load), ("get_on_save", self.get_on_save),
            ("auto_overwrite", self.auto_overwrite), ("save_lrc_file", self.save_lrc),
            ("ignore_instrumental", self.ignore_instrumental), ("plain_as_txt", self.plain_as_txt),
        ):
            widget.setChecked(bool(self.api.plugin_config[name]))

    def save(self):
        for name, widget in (
            ("get_on_load", self.get_on_load), ("get_on_save", self.get_on_save),
            ("auto_overwrite", self.auto_overwrite), ("save_lrc_file", self.save_lrc),
            ("ignore_instrumental", self.ignore_instrumental), ("plain_as_txt", self.plain_as_txt),
        ):
            self.api.plugin_config[name] = widget.isChecked()

    def clean_orphaned_lrc_files(self):
        parent = QtWidgets.QApplication.activeWindow()
        root = QtWidgets.QFileDialog.getExistingDirectory(parent, "Select Music Library Root Directory", "")
        if not root:
            return
        count = 0
        for dirpath, _, filenames in os.walk(root):
            for name in filenames:
                if not name.lower().endswith(".lrc"):
                    continue
                stem = os.path.splitext(name)[0]
                if not any(os.path.exists(os.path.join(dirpath, f"{stem}.{ext}")) for ext in self.AUDIO_EXTENSIONS):
                    try:
                        os.remove(os.path.join(dirpath, name))
                        count += 1
                    except OSError as exc:
                        self.api.logger.error("%s: cleanup failed for %s: %s", PLUGIN_NAME, name, exc)
        QtWidgets.QMessageBox.information(parent, "Cleanup Complete", f"Removed {count} orphaned .lrc file{'s' if count != 1 else ''}")


class LrcLibLyricsGet(BaseAction):
    TITLE = "Get lyrics automatically with LRCLIB"

    def callback(self, objs):
        for item in objs:
            tracks = [item] if isinstance(item, Track) else item.tracks if isinstance(item, Album) else []
            for track in tracks:
                if track.linked_files:
                    try:
                        request_lyrics(self.api, "get", track.album, track.metadata, track.files, get_track_duration(self.api, track))
                    except Exception as exc:
                        self.api.logger.error("%s: manual get failed: %s", PLUGIN_NAME, exc, exc_info=True)


class LrcLibLyricsSearch(BaseAction):
    TITLE = "Search lyrics manually with LRCLIB"

    def callback(self, objs):
        for item in objs:
            tracks = [item] if isinstance(item, Track) else item.tracks if isinstance(item, Album) else []
            for track in tracks:
                if track.linked_files:
                    request_lyrics(self.api, "search", track.album, track.metadata, track.files)


def enable(api: PluginApi):
    for key, default in DEFAULTS.items():
        api.plugin_config.register_option(key, default)
    api.register_file_post_addition_to_track_processor(get_on_load)
    api.register_file_post_save_processor(get_on_save)
    api.register_track_action(LrcLibLyricsSearch)
    api.register_album_action(LrcLibLyricsSearch)
    api.register_track_action(LrcLibLyricsGet)
    api.register_album_action(LrcLibLyricsGet)
    api.register_options_page(LrclibLyricsOptionsPage)
    api.logger.info("%s loaded", PLUGIN_NAME)
