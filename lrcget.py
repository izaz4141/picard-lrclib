from __future__ import annotations
from picard.plugin3.api import PluginApi

from picard.plugin3.api import (
    Album,
    BaseAction,
    File,
    Metadata,
    OptionsPage,
    Track,
)

import json
import os
from functools import partial
from urllib.parse import (
    quote,
    urlencode,
)
from urllib.request import (
    Request,
    urlopen,
)

from PyQt6 import QtCore, QtGui, QtWidgets
# from PyQt6.QtNetwork import QNetworkRequest

lrclib_get_url = "https://lrclib.net/api/get"
lrclib_search_url = "https://lrclib.net/api/search"
files_processing: set = set()


def plugin_name(api) -> str:
    """Display name for this plugin, taken from MANIFEST.toml."""
    return api.manifest.name_i18n()


def format_durasi(durasi: int) -> str:
    hours, remainder = divmod(int(durasi), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def truncate_text(text: str, max_lines=5, max_chars_per_line=46):
    lines: list[str] = []
    for i, line in enumerate(text.splitlines()):
        if i >= max_lines:
            lines[-1] = lines[-1].rstrip() + " …"
            break
        if len(line) > max_chars_per_line:
            line = line[: max_chars_per_line - 1].rstrip() + "…"
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + " …"
    return "\n".join(lines)


def parse_duration(time_str: str):
    parts = time_str.strip().split(":")
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid time format: {time_str}")

    if len(parts) == 2:
        minutes, seconds = map(int, parts)
        total_seconds = minutes * 60 + seconds
    elif len(parts) == 3:
        hours, minutes, seconds = map(int, parts)
        total_seconds = hours * 60**2 + minutes * 60 + seconds
    else:
        raise ValueError(f"Unsupported time format: {time_str}")

    return total_seconds

def get_track_duration(api, track: Track) -> int:
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
    assert isinstance(length, int), "Length is type " + str(type(length))+ ", not of type integer"
    return length

def confirm_replace(parent, title, description):
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        reply = QtWidgets.QMessageBox.question(
            parent,
            title,
            description,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes
    except Exception:
        return False


def show_search_table(api, parent, query, response, request_callback):
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
    search_button.setAutoDefault(True)
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)

    table = QtWidgets.QTableWidget(dialog)
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(
        ["#", "Name", "Artist", "Length", "Album", "Synced"]
    )
    vheader = table.verticalHeader()
    assert vheader is not None, "VHeader is unexpectedly None"
    vheader.setVisible(False)
    hheader = table.horizontalHeader()
    assert hheader is not None, "HHeader is unexpectedly None"
    hheader.setDefaultAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)  # type: ignore
    hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
    hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
    hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Interactive)
    hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    layout.addWidget(table)

    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(button_box)

    def populate_table(response):
        table.setSortingEnabled(False)
        table.setRowCount(0)
        if not response:
            return
        table.setRowCount(len(response))
        for row, item in enumerate(response):
            num_item = QtWidgets.QTableWidgetItem()
            num_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)  # type: ignore
            num_item.setData(QtCore.Qt.ItemDataRole.EditRole, row + 1)  # type: ignore
            table.setItem(row, 0, num_item)

            has_synced = item.get("syncedLyrics") or False
            values = [
                item.get("trackName") or "?",
                item.get("artistName") or "?",
                format_durasi(item.get("duration", None) or 0),
                item.get("albumName") or "?",
                "V" if has_synced else "X",
            ]
            for col, val in enumerate(values, start=1):
                cell_item = QtWidgets.QTableWidgetItem(str(val))
                if col in [3, 5]:
                    cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)  # type: ignore
                    if col == 5:
                        cell_item.setForeground(
                            QtGui.QColor("#2ecc71" if has_synced else "#e74c3c")
                        )
                table.setItem(row, col, cell_item)
        table.setSortingEnabled(True)

    populate_table(response)

    def on_search_clicked():
        nonlocal response
        query = search_input.text().strip()
        if not query:
            return
        try:
            params = {"q": query}
            response = request_callback(api, lrclib_search_url, params)
            populate_table(response)
            api.logger.debug(f"Search refreshed: {len(response)} results")
        except Exception as e:
            api.logger.error(f"Error during search refresh: {e}")

    search_button.clicked.connect(on_search_clicked)
    search_input.returnPressed.connect(on_search_clicked)

    def on_double_click(index):
        if index.isValid():
            dialog.accept()

    table.doubleClicked.connect(on_double_click)

    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    result = dialog.exec()
    if result == QtWidgets.QDialog.DialogCode.Accepted:
        selected = table.currentRow()
        return response[selected] if selected >= 0 else None
    else:
        return None


def _request(api, url, album, task_id, callback, queryargs=None, important=False):
    if not queryargs:
        queryargs = {}

    def create_request():
        return api.web_service.get_url(
            url=url,
            handler=callback,
            parse_response_type="json",
            priority=True,
            important=important,
            queryargs=queryargs,
            #cacheloadcontrol=QNetworkRequest.PreferNetwork,
        )
    
    api.add_album_task(
        album,
        task_id,
        'Fetching data',
        request_factory=create_request,
    )


def _fetch_json(api, url, params):
    try:
        query = urlencode(params)
        full_url = f"{url}?{query}"

        req = Request(
            full_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            },
        )
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                api.logger.error(f"{plugin_name(api)}: HTTP error {resp.status} for {full_url}")
                return {}
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception as e:
        api.logger.error(f"{plugin_name(api)}: fetch_json: failed to request {url} — {e}")
        return {}


def fetch_lyrics(
    api,
    method: str,
    album: Album,
    metadata: Metadata,
    linked_files: list[File],
    length: int | None = None,
):
    artist = metadata["artist"]
    title = metadata["title"]
    albumName = metadata["album"]

    if method == "search":
        url = lrclib_search_url
        task_id = f"search_{title}_{album.id}"
        queryargs = {"q": title}
    else:
        url = lrclib_get_url
        task_id = f"get_{artist}_{title}_{album.id}" # I guess it is possible for two tracks to have the same id
                                                     # if they have the same name, artist and album id. But that
                                                     # seems weird to happen and if it does it just prints a warning
                                                     # in Picard's logs when the tasks end
        queryargs = {
            "track_name": title,
            "artist_name": artist,
            "album_name": albumName,
        }
        if length:
            queryargs["duration"] = length

    # album._requests += 1
    api.logger.debug(
        f"{plugin_name(api)}: {'GET' if method != 'search' else 'SEARCH'} {quote(url)}?{urlencode(queryargs)}"
    )

    _request(
        api,  # type: ignore
        url,
        album,
        task_id,
        partial(process_response, api, method, album, metadata, task_id, linked_files),
        queryargs,
    )


def process_response(
    api,
    method: str,
    album: Album,
    metadata: Metadata,
    task_id: str,
    linked_files: list[File],
    response,
    reply,
    error,
):
    if error or (
        response and isinstance(response, dict) and not response.get("id", False)
    ):
        api.logger.warning(
            f'{plugin_name(api)}: lyrics NOT found for track "{metadata["title"]}" by {metadata["artist"]}'
        )
        if method == "get_on_save":
            for file in linked_files:
                files_processing.discard(file.filename)
        # album._requests -= 1
        # album._finalize_loading(None)
        api.complete_album_task(album, task_id)
        return

    try:
        if method == "search":
            parent = album.tagger.window if hasattr(album, "tagger") else None  # type: ignore
            response = show_search_table(
                api, parent, metadata["title"], response, _fetch_json
            )
            if response is None:
                return

        lyrics = None
        is_plain = False

        if (
            response.get("instrumental", False)
            or "(Instrumental)" in (response.get("trackName") or "")
            or "[au: instrumental]" in (response.get("plainLyrics") or "")
        ) and (api.plugin_config["ignore_instrumental"] and method != "search"):
            lyrics = None
        elif response.get("syncedLyrics"):
            lyrics = response.get("syncedLyrics")
            is_plain = False
        else:
            lyrics = response.get("plainLyrics", None)
            is_plain = True
        if not isinstance(lyrics, str):
            return

        for file in linked_files:
            ext = ".txt" if (is_plain and api.plugin_config["plain_as_txt"]) else ".lrc"
            full_path = file.filename
            assert full_path is not None, "File path is None"
            dirname = os.path.dirname(full_path)
            filename_no_ext = os.path.splitext(os.path.basename(full_path))[0]
            base_path = f"{dirname}/{filename_no_ext}"
            file_lrc = f"{base_path}{ext}"

            has_metadata_lyrics = bool(file.metadata.get("lyrics"))
            has_lrc_file = os.path.exists(file_lrc)

            if (
                has_metadata_lyrics
                and not has_lrc_file
                and api.plugin_config["save_lrc_file"]
                and method != "search"
            ):
                lyrics = file.metadata.get("lyrics")
                assert isinstance(lyrics, str), "Lyrics is not of type string"
            elif has_lrc_file and not has_metadata_lyrics and method != "search":
                with open(file_lrc, "r", encoding="utf-8") as f:
                    lyrics = f.read()
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
                    f"{truncate_text(lyrics, 5, 42)}"
                )
                parent = getattr(file, "tagger", None)
                if not confirm_replace(getattr(parent, "window", None), title, desc):
                    return

            file.metadata["lyrics"] = lyrics
            if api.plugin_config["save_lrc_file"]:
                for old_ext in [".txt", ".lrc"]:
                    old_file = base_path + old_ext
                    if os.path.exists(old_file):
                        try:
                            os.remove(old_file)
                        except Exception as e:
                            api.logger.error(
                                f"{plugin_name(api)}: Failed to delete {old_file}: {e}"
                            )

                try:
                    with open(file_lrc, "w", encoding="utf-8") as f:
                        f.write(lyrics)
                except Exception as e:
                    api.logger.error(f"{plugin_name(api)}: Failed to write .lrc file: {e}")
                    parent_widget = getattr(
                        getattr(file, "tagger", None), "window", None
                    )
                    if not isinstance(parent_widget, QtWidgets.QWidget):
                        parent_widget = QtWidgets.QApplication.activeWindow()
                    QtWidgets.QMessageBox.critical(
                        parent_widget,
                        "Failed to Save LRC File",
                        f"Could not save lyrics file:\n\n{file_lrc}\n\nError: {e}",
                    )
        api.logger.debug(
            f'{plugin_name(api)}: lyrics loaded for track "{metadata["title"]}" by {metadata["artist"]}'
        )

    except (TypeError, KeyError, ValueError) as e:
        api.logger.error(
            f'{plugin_name(api)}: lyrics NOT loaded for track "{metadata["title"]}" by {metadata["artist"]}: {e}',
            exc_info=True,
        )

    finally:
        if method == "get_on_save":
            for file in linked_files:
                file.save()

        api.complete_album_task(album, task_id)
        # album._requests -= 1
        # album._finalize_loading(None)


class LrclibLyricsOptionsPage(OptionsPage):
    NAME = "lrclib_lyrics"
    PARENT = "plugins"

    AUDIO_EXTENSIONS = {
        "aac",
        "ac3",
        "aif",
        "aifc",
        "aiff",
        "ape",
        "asf",
        "dff",
        "dsf",
        "eac3",
        "flac",
        "kar",
        "m2a",
        "ofr",
        "ofs",
        "oga",
        "ogg",
        "oggflac",
        "oggtheora",
        "ogv",
        "ogx",
        "opus",
        "spx",
        "tak",
        "tta",
        "wav",
        "webm",
        "wma",
        "wmv",
        "wv",
        "xwma",
    }


    def __init__(self, parent=None):
        super().__init__(parent)
        self.box = QtWidgets.QVBoxLayout(self)

        self.get_on_load = QtWidgets.QCheckBox(
            "Search for lyrics when loading tracks", self
        )
        self.box.addWidget(self.get_on_load)

        self.get_on_save = QtWidgets.QCheckBox(
            "Search for lyrics when saving files", self
        )
        self.box.addWidget(self.get_on_save)

        self.auto_overwrite = QtWidgets.QCheckBox(
            "Auto overwrite existing lyrics", self
        )
        self.box.addWidget(self.auto_overwrite)

        self.save_lrc = QtWidgets.QCheckBox(
            "Save .lrc file alongside audio files", self
        )
        self.box.addWidget(self.save_lrc)

        self.ignore_instrumental = QtWidgets.QCheckBox(
            "Ignore instrumental lyrics", self
        )
        self.box.addWidget(self.ignore_instrumental)

        self.plain_as_txt = QtWidgets.QCheckBox("Save plain lyrics as .txt", self)
        self.box.addWidget(self.plain_as_txt)

        self.box.addSpacing(20)

        cleanup_label = QtWidgets.QLabel("Cleanup Tools:", self)
        cleanup_label.setStyleSheet("font-weight: bold;")
        self.box.addWidget(cleanup_label)

        self.cleanup_button = QtWidgets.QPushButton("Clean Orphaned LRC Files", self)
        self.cleanup_button.setToolTip(
            "Recursively scan a directory for .lrc files without matching audio files"
        )
        self.cleanup_button.clicked.connect(self.clean_orphaned_lrc_files)
        self.box.addWidget(self.cleanup_button)

        self.spacer = QtWidgets.QSpacerItem(
            0, 0, QtWidgets.QSizePolicy.Policy.Minimum, QtWidgets.QSizePolicy.Policy.Expanding
        )
        self.box.addItem(self.spacer)

        self.description = QtWidgets.QLabel(self)
        self.description.setText(
            "LRCLIB Music provides millions of lyrics from artist all around the world.\n"
            "Lyrics provided are for educational purposes and personal use only. Commercial use is not allowed.\n"
            "If searching for lyrics when loading tracks, the loading process will be slowed significantly."
        )
        self.description.setOpenExternalLinks(True)
        self.box.addWidget(self.description)

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
        try:
            parent = QtWidgets.QApplication.activeWindow()

            root_dir = QtWidgets.QFileDialog.getExistingDirectory(
                parent,
                "Select Music Library Root Directory",
                "",
                QtWidgets.QFileDialog.Option.ShowDirsOnly
                | QtWidgets.QFileDialog.Option.DontResolveSymlinks,
            )

            if not root_dir:
                self.api.logger.info(f"{plugin_name(self.api)}: User cancelled directory selection")
                return

            self.api.logger.info(f"{plugin_name(self.api)}: Starting recursive scan of {root_dir}")
            orphaned_count = self._clean_directory_recursive(root_dir)

            if orphaned_count > 0:
                QtWidgets.QMessageBox.information(
                    parent,
                    "Cleanup Complete",
                    f"Removed {orphaned_count} orphaned .lrc file{'s' if orphaned_count != 1 else ''}",
                )
                self.api.logger.info(f"{plugin_name(self.api)}: Cleaned {orphaned_count} orphaned .lrc files")
            else:
                QtWidgets.QMessageBox.information(
                    parent, "Cleanup Complete", "No orphaned .lrc files found"
                )
                self.api.logger.info(f"{plugin_name(self.api)}: No orphaned .lrc files found")

        except Exception as err:
            self.api.logger.error(
                f"{plugin_name(self.api)}: Error cleaning orphaned files: {err}", exc_info=True
            )

    def _clean_directory_recursive(self, root_dir):
        if not os.path.isdir(root_dir):
            self.api.logger.warning(f"{plugin_name(self.api)}: Directory does not exist: {root_dir}")
            return 0

        orphaned_count = 0

        try:
            for dirpath, dirnames, filenames in os.walk(root_dir):
                lrc_files = [f for f in filenames if f.lower().endswith(".lrc")]

                for lrc_file in lrc_files:
                    lrc_path = os.path.join(dirpath, lrc_file)
                    base_name = os.path.splitext(lrc_file)[0]

                    audio_file_exists = False
                    for ext in self.AUDIO_EXTENSIONS:
                        audio_path = os.path.join(dirpath, base_name + ext)
                        if os.path.exists(audio_path):
                            audio_file_exists = True
                            break

                    if not audio_file_exists:
                        try:
                            os.remove(lrc_path)
                            orphaned_count += 1
                            self.api.logger.debug(
                                f"{plugin_name(self.api)}: Deleted orphaned file: {lrc_path}"
                            )
                        except Exception as e:
                            self.api.logger.error(
                                f"{plugin_name(self.api)}: Failed to delete {lrc_path}: {e}"
                            )

        except Exception as e:
            self.api.logger.error(f"{plugin_name(self.api)}: Error scanning directory {root_dir}: {e}")

        return orphaned_count


def get_on_load(api, track: Track, file: File) -> None:
    if not api.plugin_config["get_on_load"]:
        return
    try:
        if not track.files:
            return
        album = track.album
        assert isinstance(album, Album), "Album is not of type Album"
        length = get_track_duration(api, track)
        fetch_lyrics(api, "get_on_load", album, track.metadata, track.files, length)
    except Exception as err:
        api.logger.error(f"{plugin_name(api)}: Error in get_on_load: {err}")


def get_on_save(api, file: File) -> None:
    if not api.plugin_config["get_on_save"]:
        return
    if file.filename in files_processing:
        return files_processing.discard(
            file.filename
        )  # Picard only allow one concurrent save_hook
    try:
        files_processing.add(file.filename)
        album = file.parent_item.album  # type: ignore
        assert isinstance(album, Album), "Album is not of type Album"
        metadata = file.metadata
        assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
        length = None
        if metadata["~length"]:
            length = parse_duration(str(metadata["~length"]))
        assert isinstance(length, int), "Length is not of type integer"
        fetch_lyrics(api, "get_on_save", album, metadata, [file], length)
    except Exception as err:
        api.logger.error(f"{plugin_name(api)}: Error in get_on_save: {err}")
        files_processing.discard(file.filename)


class LrcLibLyricsGet(BaseAction):
    TITLE = "Get lyrics automatically with LRCLIB"

    def execute_on_track(self, track):
        try:
            if not track.files:  # If it's not in your local file then ignore
                return
            album = track.album
            assert isinstance(album, Album), "Album is not of type Album"
            length = get_track_duration(self.api, track)
            fetch_lyrics(self.api, "get", album, track.metadata, track.files, length)
        except Exception as err:
            self.api.logger.error(err)


    def callback(self, objs):
        for item in (t for t in objs if isinstance(t, Track) or isinstance(t, Album)):
            if isinstance(item, Track):
                self.api.logger.debug(f"{plugin_name(self.api)}: {item}, {item.album}")
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    self.api.logger.debug(f"{plugin_name(self.api)}: {track}, {item}")
                    self.execute_on_track(track)


class LrcLibLyricsSearch(BaseAction):
    TITLE = "Search lyrics manually with LRCLIB"

    def execute_on_track(self, track):
        try:
            if not track.files:  # If it's not in your local file then ignore
                return
            fetch_lyrics(self.api, "search", track.album, track.metadata, track.files)
        except Exception as err:
            self.api.logger.error(err)

    def callback(self, objs):
        for item in (t for t in objs if isinstance(t, Track) or isinstance(t, Album)):
            if isinstance(item, Track):
                self.api.logger.debug(f"{plugin_name(self.api)}: {item}, {item.album}")
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    self.api.logger.debug(f"{plugin_name(self.api)}: {track}, {item}")
                    self.execute_on_track(track)


def enable(api: PluginApi):
    """Called when plugin is enabled."""
    api.register_file_post_addition_to_track_processor(get_on_load)
    api.register_file_post_save_processor(get_on_save)
    api.register_track_action(LrcLibLyricsSearch)
    api.register_album_action(LrcLibLyricsSearch)
    api.register_track_action(LrcLibLyricsGet)
    api.register_album_action(LrcLibLyricsGet)

    api.plugin_config.register_option("get_on_load", False)
    api.plugin_config.register_option("get_on_save", False)
    api.plugin_config.register_option("auto_overwrite", False)
    api.plugin_config.register_option("save_lrc_file", False)
    api.plugin_config.register_option("ignore_instrumental", False)
    api.plugin_config.register_option("plain_as_txt", False)

    api.register_options_page(LrclibLyricsOptionsPage)
