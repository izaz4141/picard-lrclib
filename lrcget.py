from __future__ import annotations

import json
import os
from functools import partial
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from picard.plugin3.api import (
    Album,
    BaseAction,
    File,
    Metadata,
    OptionsPage,
    PluginApi,
    Track,
)
from PyQt6 import QtCore, QtGui, QtWidgets


PLUGIN_NAME = "LRCLIB Lyrics"
PLUGIN_OPTIONS = {
    "get_on_load": False,
    "get_on_save": False,
    "auto_overwrite": False,
    "save_lrc_file": True,
    "ignore_instrumental": False,
    "plain_as_txt": False,
}

LRCLIB_GET_URL = "https://lrclib.net/api/get"
LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
files_processing: set[str] = set()


def format_duration(duration: int) -> str:
    hours, remainder = divmod(int(duration), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def truncate_text(text: str, max_lines: int = 5, max_chars_per_line: int = 46) -> str:
    lines: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if i >= max_lines:
            if lines:
                lines[-1] = lines[-1].rstrip() + " …"
            break
        if len(line) > max_chars_per_line:
            line = line[: max_chars_per_line - 1].rstrip() + "…"
        lines.append(line)
    return "\n".join(lines)


def parse_duration(time_str: str) -> int:
    parts = time_str.strip().split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid time format: {time_str}")
    if len(parts) == 2:
        minutes, seconds = map(int, parts)
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Unsupported time format: {time_str}")


def get_track_duration(api: PluginApi, track: Track) -> int:
    metadata = track.metadata
    if metadata["~length"]:
        return parse_duration(str(metadata["~length"]))

    api.logger.warning(
        '%s: length not found in metadata for track "%s"',
        PLUGIN_NAME,
        metadata.get("title", "<unknown>"),
    )
    if track.num_linked_files > 0 and track.files[0].metadata["~length"]:
        return parse_duration(str(track.files[0].metadata["~length"]))
    raise ValueError(f"Length is not available for {metadata.get('title', '<unknown>')}")


def confirm_replace(parent, title: str, description: str) -> bool:
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        reply = QtWidgets.QMessageBox.question(
            parent,
            title,
            description,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes
    except Exception:
        return False


def _fetch_json(api: PluginApi, url: str, params: dict) -> dict | list:
    try:
        full_url = f"{url}?{urlencode(params)}"
        request = Request(
            full_url,
            headers={"User-Agent": "Picard-LRCLIB/3.0"},
        )
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                api.logger.error("%s: HTTP error %s for %s", PLUGIN_NAME, response.status, full_url)
                return {}
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        api.logger.error("%s: request failed: %s", PLUGIN_NAME, exc)
        return {}


def show_search_table(api: PluginApi, parent, query: str, response, request_callback):
    parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Search Tracks")
    dialog.resize(700, 400)

    layout = QtWidgets.QVBoxLayout(dialog)
    search_layout = QtWidgets.QHBoxLayout()
    search_input = QtWidgets.QLineEdit()
    search_input.setText(query)
    search_input.setPlaceholderText("Enter search query...")
    search_button = QtWidgets.QPushButton("Search")
    search_button.setDefault(True)
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)

    table = QtWidgets.QTableWidget(dialog)
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(["#", "Name", "Artist", "Length", "Album", "Synced"])
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
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

    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(button_box)

    def populate_table(items):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        if not isinstance(items, list):
            return
        table.setRowCount(len(items))
        for row, item in enumerate(items):
            number = QtWidgets.QTableWidgetItem(str(row + 1))
            number.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, 0, number)
            has_synced = bool(item.get("syncedLyrics"))
            values = [
                item.get("trackName") or "?",
                item.get("artistName") or "?",
                format_duration(item.get("duration") or 0),
                item.get("albumName") or "?",
                "Yes" if has_synced else "No",
            ]
            for col, value in enumerate(values, start=1):
                cell = QtWidgets.QTableWidgetItem(str(value))
                if col in (3, 5):
                    cell.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
                if col == 5:
                    cell.setForeground(QtGui.QColor("#2ecc71" if has_synced else "#e74c3c"))
                table.setItem(row, col, cell)
        table.setSortingEnabled(True)

    populate_table(response)

    def on_search_clicked():
        search = search_input.text().strip()
        if not search:
            return
        try:
            result = request_callback(api, LRCLIB_SEARCH_URL, {"q": search})
            populate_table(result)
        except Exception as exc:
            api.logger.error("%s: search refresh failed: %s", PLUGIN_NAME, exc)

    search_button.clicked.connect(on_search_clicked)
    search_input.returnPressed.connect(on_search_clicked)
    table.doubleClicked.connect(lambda index: dialog.accept() if index.isValid() else None)
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        selected = table.currentRow()
        items = response
        if selected >= 0:
            # Re-read the displayed query so a refresh is reflected in the selected result.
            items = request_callback(api, LRCLIB_SEARCH_URL, {"q": search_input.text().strip()})
            if isinstance(items, list) and selected < len(items):
                return items[selected]
    return None


def _request(
    api: PluginApi,
    url: str,
    callback,
    queryargs: dict | None = None,
    important: bool = False,
):
    api.web_service.get_url(
        url=url,
        handler=callback,
        parse_response_type="json",
        priority=True,
        important=important,
        queryargs=queryargs or {},
    )


def fetch_lyrics(
    api: PluginApi,
    method: str,
    album: Album,
    metadata: Metadata,
    linked_files: list[File],
    length: int | None = None,
):
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

    api.logger.debug("%s: request %s?%s", PLUGIN_NAME, url, urlencode(queryargs))

    task_id = f"lyrics_{id(album)}_{id(linked_files[0]) if linked_files else id(album)}"
    if method in {"get_on_load", "get_on_save"}:
        api.add_album_task(
            album,
            task_id,
            "Fetching LRCLIB lyrics",
            timeout=30,
            blocking=(method == "get_on_load"),
        )

    def request_factory():
        return api.web_service.get_url(
            url=url,
            handler=partial(
                process_response,
                api,
                method,
                album,
                metadata,
                linked_files,
                task_id,
            ),
            parse_response_type="json",
            priority=True,
            queryargs=queryargs,
        )

    if method in {"get_on_load", "get_on_save"}:
        api.set_album_task_request(album, task_id, request_factory())
    else:
        request_factory()


def process_response(
    api: PluginApi,
    method: str,
    album: Album,
    metadata: Metadata,
    linked_files: list[File],
    task_id: str,
    response,
    reply,
    error,
):
    try:
        if error or not response:
            api.logger.warning(
                '%s: lyrics not found for track "%s" by %s',
                PLUGIN_NAME,
                metadata.get("title", "<unknown>"),
                metadata.get("artist", "<unknown>"),
            )
            return

        if method == "search":
            parent = api.tagger.window
            response = show_search_table(
                api, parent, metadata.get("title", ""), response, _fetch_json
            )
            if response is None:
                return

        if not isinstance(response, dict):
            return

        if (
            response.get("instrumental", False)
            or "(Instrumental)" in (response.get("trackName") or "")
            or "[au: instrumental]" in (response.get("plainLyrics") or "")
        ) and api.plugin_config["ignore_instrumental"] and method != "search":
            return

        lyrics = response.get("syncedLyrics") or response.get("plainLyrics")
        is_plain = not bool(response.get("syncedLyrics"))
        if not isinstance(lyrics, str):
            return

        for file in linked_files:
            full_path = file.filename
            if not full_path:
                continue
            dirname = os.path.dirname(full_path)
            filename_no_ext = os.path.splitext(os.path.basename(full_path))[0]
            base_path = os.path.join(dirname, filename_no_ext)
            ext = ".txt" if is_plain and api.plugin_config["plain_as_txt"] else ".lrc"
            lyrics_path = base_path + ext

            has_metadata_lyrics = bool(file.metadata.get("lyrics"))
            has_lrc_file = os.path.exists(lyrics_path)

            if (
                has_metadata_lyrics
                and not has_lrc_file
                and api.plugin_config["save_lrc_file"]
                and method != "search"
            ):
                lyrics = file.metadata.get("lyrics")
                if not isinstance(lyrics, str):
                    continue
            elif has_lrc_file and not has_metadata_lyrics and method != "search":
                with open(lyrics_path, "r", encoding="utf-8") as handle:
                    lyrics = handle.read()
            elif (
                (has_metadata_lyrics and has_lrc_file)
                or (has_metadata_lyrics and not api.plugin_config["save_lrc_file"])
            ) and not api.plugin_config["auto_overwrite"] and method not in {"get_on_load", "get_on_save"}:
                if not confirm_replace(
                    api.tagger.window,
                    "Overwrite file lyrics?",
                    f'Overwrite Lyrics for "{file.metadata.get("title", "<file>")}".\n\n'
                    f"{truncate_text(lyrics, 5, 42)}",
                ):
                    continue

            file.metadata["lyrics"] = lyrics
            if api.plugin_config["save_lrc_file"]:
                for old_ext in (".txt", ".lrc"):
                    old_path = base_path + old_ext
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError as exc:
                            api.logger.error("%s: failed to delete %s: %s", PLUGIN_NAME, old_path, exc)
                try:
                    with open(lyrics_path, "w", encoding="utf-8") as handle:
                        handle.write(lyrics)
                except OSError as exc:
                    api.logger.error("%s: failed to write %s: %s", PLUGIN_NAME, lyrics_path, exc)
                    QtWidgets.QMessageBox.critical(
                        api.tagger.window,
                        "Failed to Save Lyrics File",
                        f"Could not save lyrics file:\n\n{lyrics_path}\n\nError: {exc}",
                    )

        api.logger.debug(
            '%s: lyrics loaded for track "%s" by %s',
            PLUGIN_NAME,
            metadata.get("title", "<unknown>"),
            metadata.get("artist", "<unknown>"),
        )
    except (TypeError, KeyError, ValueError, OSError) as exc:
        api.logger.error(
            '%s: lyrics processing failed for "%s": %s',
            PLUGIN_NAME,
            metadata.get("title", "<unknown>"),
            exc,
            exc_info=True,
        )
    finally:
        if method == "get_on_save":
            for file in linked_files:
                if file.filename:
                    files_processing.discard(file.filename)
                file.save()
        if method in {"get_on_load", "get_on_save"}:
            api.complete_album_task(album, task_id)


class LrclibLyricsOptionsPage(OptionsPage):
    NAME = "lrclib_lyrics"
    TITLE = "LRCLIB Lyrics"
    PARENT = "plugins"

    AUDIO_EXTENSIONS = {
        "aac", "ac3", "aif", "aifc", "aiff", "ape", "asf", "dff", "dsf",
        "eac3", "flac", "kar", "m2a", "ofr", "ofs", "oga", "ogg", "oggflac",
        "oggtheora", "ogv", "ogx", "opus", "spx", "tak", "tta", "wav", "webm",
        "wma", "wmv", "wv", "xwma",
    }

    def __init__(self):
        super().__init__()
        box = QtWidgets.QVBoxLayout(self)
        self.get_on_load = QtWidgets.QCheckBox("Search for lyrics when loading tracks")
        self.get_on_save = QtWidgets.QCheckBox("Search for lyrics when saving files")
        self.auto_overwrite = QtWidgets.QCheckBox("Auto overwrite existing lyrics")
        self.save_lrc = QtWidgets.QCheckBox("Save .lrc file alongside audio files")
        self.ignore_instrumental = QtWidgets.QCheckBox("Ignore instrumental lyrics")
        self.plain_as_txt = QtWidgets.QCheckBox("Save plain lyrics as .txt")
        for widget in (
            self.get_on_load, self.get_on_save, self.auto_overwrite,
            self.save_lrc, self.ignore_instrumental, self.plain_as_txt,
        ):
            box.addWidget(widget)

        box.addSpacing(20)
        label = QtWidgets.QLabel("Cleanup Tools:")
        label.setStyleSheet("font-weight: bold;")
        box.addWidget(label)
        self.cleanup_button = QtWidgets.QPushButton("Clean Orphaned LRC Files")
        self.cleanup_button.setToolTip("Recursively scan a directory for .lrc files without matching audio files")
        self.cleanup_button.clicked.connect(self.clean_orphaned_lrc_files)
        box.addWidget(self.cleanup_button)
        box.addItem(QtWidgets.QSpacerItem(0, 0, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding))
        box.addWidget(QtWidgets.QLabel(
            "LRCLIB provides lyrics from a crowdsourced database.\n"
            "Lyrics are intended for educational and personal use.\n"
            "Searching for lyrics when loading tracks can slow the loading process."
        ))

    def load(self):
        self.get_on_load.setChecked(bool(self.api.plugin_config["get_on_load"]))
        self.get_on_save.setChecked(bool(self.api.plugin_config["get_on_save"]))
        self.auto_overwrite.setChecked(bool(self.api.plugin_config["auto_overwrite"]))
        self.save_lrc.setChecked(bool(self.api.plugin_config["save_lrc_file"]))
        self.ignore_instrumental.setChecked(bool(self.api.plugin_config["ignore_instrumental"]))
        self.plain_as_txt.setChecked(bool(self.api.plugin_config["plain_as_txt"]))

    def save(self):
        self.api.plugin_config["get_on_load"] = self.get_on_load.isChecked()
        self.api.plugin_config["get_on_save"] = self.get_on_save.isChecked()
        self.api.plugin_config["auto_overwrite"] = self.auto_overwrite.isChecked()
        self.api.plugin_config["save_lrc_file"] = self.save_lrc.isChecked()
        self.api.plugin_config["ignore_instrumental"] = self.ignore_instrumental.isChecked()
        self.api.plugin_config["plain_as_txt"] = self.plain_as_txt.isChecked()

    def clean_orphaned_lrc_files(self):
        parent = QtWidgets.QApplication.activeWindow()
        root_dir = QtWidgets.QFileDialog.getExistingDirectory(
            parent,
            "Select Music Library Root Directory",
            "",
            QtWidgets.QFileDialog.Option.ShowDirsOnly | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
        )
        if not root_dir:
            return
        count = self._clean_directory_recursive(root_dir)
        QtWidgets.QMessageBox.information(
            parent,
            "Cleanup Complete",
            f"Removed {count} orphaned .lrc file{'s' if count != 1 else ''}" if count else "No orphaned .lrc files found",
        )

    def _clean_directory_recursive(self, root_dir: str) -> int:
        if not os.path.isdir(root_dir):
            return 0
        count = 0
        for dirpath, _, filenames in os.walk(root_dir):
            for lrc_file in (f for f in filenames if f.lower().endswith(".lrc")):
                base_name = os.path.splitext(lrc_file)[0]
                if not any(os.path.exists(os.path.join(dirpath, base_name + "." + ext)) for ext in self.AUDIO_EXTENSIONS):
                    try:
                        os.remove(os.path.join(dirpath, lrc_file))
                        count += 1
                    except OSError as exc:
                        self.api.logger.error("%s: failed to delete orphan %s: %s", PLUGIN_NAME, lrc_file, exc)
        return count


def get_on_load(api: PluginApi, track: Track, file: File) -> None:
    if not api.plugin_config["get_on_load"] or not track.files:
        return
    try:
        fetch_lyrics(api, "get_on_load", track.album, track.metadata, track.files, get_track_duration(api, track))
    except Exception as exc:
        api.logger.error("%s: error in get_on_load: %s", PLUGIN_NAME, exc, exc_info=True)


def get_on_save(api: PluginApi, file: File) -> None:
    if not api.plugin_config["get_on_save"] or not file.filename:
        return
    if file.filename in files_processing:
        files_processing.discard(file.filename)
        return
    try:
        files_processing.add(file.filename)
        album = file.parent.album
        metadata = file.metadata
        length = parse_duration(str(metadata["~length"])) if metadata["~length"] else None
        if length is None:
            raise ValueError("Length is not available")
        fetch_lyrics(api, "get_on_save", album, metadata, [file], length)
    except Exception as exc:
        files_processing.discard(file.filename)
        api.logger.error("%s: error in get_on_save: %s", PLUGIN_NAME, exc, exc_info=True)


class LrcLibLyricsGet(BaseAction):
    TITLE = "Get lyrics automatically with LRCLIB"

    def execute_on_track(self, track: Track):
        try:
            if not track.linked_files:
                return
            fetch_lyrics(self.api, "get", track.album, track.metadata, track.files, get_track_duration(self.api, track))
        except Exception as exc:
            self.api.logger.error("%s: manual get failed: %s", PLUGIN_NAME, exc, exc_info=True)

    def callback(self, objs):
        for item in objs:
            if isinstance(item, Track):
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    self.execute_on_track(track)


class LrcLibLyricsSearch(BaseAction):
    TITLE = "Search lyrics manually with LRCLIB"

    def execute_on_track(self, track: Track):
        try:
            if track.linked_files:
                fetch_lyrics(self.api, "search", track.album, track.metadata, track.linked_files)
        except Exception as exc:
            self.api.logger.error("%s: manual search failed: %s", PLUGIN_NAME, exc, exc_info=True)

    def callback(self, objs):
        for item in objs:
            if isinstance(item, Track):
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    self.execute_on_track(track)


def enable(api: PluginApi):
    for key, default in PLUGIN_OPTIONS.items():
        api.plugin_config.register_option(key, default)

    api.register_file_post_addition_to_track_processor(get_on_load)
    api.register_file_post_save_processor(get_on_save)
    api.register_track_action(LrcLibLyricsSearch)
    api.register_album_action(LrcLibLyricsSearch)
    api.register_track_action(LrcLibLyricsGet)
    api.register_album_action(LrcLibLyricsGet)
    api.register_options_page(LrclibLyricsOptionsPage)
    api.logger.info("%s loaded", PLUGIN_NAME)
