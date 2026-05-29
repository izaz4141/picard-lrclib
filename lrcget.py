from __future__ import annotations
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

from picard import config, log
from picard.album import Album
from picard.config import BoolOption
from picard.file import (
    File,
    register_file_post_addition_to_track_processor,
    register_file_post_save_processor,
)
from picard.metadata import Metadata
from picard.track import Track
from picard.ui.itemviews import (
    BaseAction,
    register_album_action,
    register_track_action,
)
from picard.ui.options import (
    OptionsPage,
    register_options_page,
)
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtNetwork import QNetworkRequest

PLUGIN_NAME = "LRCLIB Lyrics"
PLUGIN_AUTHOR = "Glicole"

PLUGIN_DESCRIPTION = (
    "Fetch and embed lyrics from LRCLIB's crowdsourced database<br/>"
    "<b>Automatic Integration:</b> Save lyrics to both audio file metadata <i>and</i> .lrc sidecar files<br/>"
    "<b>Jellyfin/Plex Ready:</b> Generated .lrc files work seamlessly with media servers and Kodi<br/>"
    "<b>Configurable Workflow:</b> Toggle auto-fetching and .lrc file creation in plugin settings<br/>"
    "<b>Smart Fetch:</b> Prefers synchronized lyrics when available, falls back to plain text<br/>"
    "<br/>"
    "<i>Based on Dylancyclone's plugin</i>"
)
PLUGIN_VERSION = "1.2.0"
PLUGIN_API_VERSIONS = ["2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"]
PLUGIN_LICENSE = "MIT"
PLUGIN_LICENSE_URL = "https://opensource.org/licenses/MIT"
PLUGIN_USER_GUIDE_URL = "https://github.com/izaz4141/picard-lrclib"

PLUGIN_OPTIONS = {
    "get_on_load": False,
    "get_on_save": False,
    "auto_overwrite": False,
    "save_lrc_file": True,
    "ignore_instrumental": False,
    "plain_as_txt": False,
}

lrclib_get_url = "https://lrclib.net/api/get"
lrclib_search_url = "https://lrclib.net/api/search"
files_processing: set = set()


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


def confirm_replace(parent, title, description):
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        reply = QtWidgets.QMessageBox.question(
            parent,
            title,
            description,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        return reply == QtWidgets.QMessageBox.Yes
    except Exception:
        return False


def show_search_table(parent, query, response, request_callback):
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
    hheader.setDefaultAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)  # type: ignore
    hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
    hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.Interactive)
    hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
    hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.Interactive)
    hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeToContents)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    layout.addWidget(table)

    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
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
            num_item.setTextAlignment(QtCore.Qt.AlignCenter)  # type: ignore
            num_item.setData(QtCore.Qt.EditRole, row + 1)  # type: ignore
            table.setItem(row, 0, num_item)

            has_synced = item.get("syncedLyrics")
            values = [
                item.get("trackName", ""),
                item.get("artistName", ""),
                format_durasi(item.get("duration", 0)),
                item.get("albumName", ""),
                "V" if has_synced else "X",
            ]
            for col, val in enumerate(values, start=1):
                cell_item = QtWidgets.QTableWidgetItem(str(val))
                if col in [3, 5]:
                    cell_item.setTextAlignment(QtCore.Qt.AlignCenter)  # type: ignore
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
            response = request_callback(lrclib_search_url, params)
            populate_table(response)
            log.debug(f"Search refreshed: {len(response)} results")
        except Exception as e:
            log.error(f"Error during search refresh: {e}")

    search_button.clicked.connect(on_search_clicked)
    search_input.returnPressed.connect(on_search_clicked)

    def on_double_click(index):
        if index.isValid():
            dialog.accept()

    table.doubleClicked.connect(on_double_click)

    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    result = dialog.exec_()
    if result == QtWidgets.QDialog.Accepted:
        selected = table.currentRow()
        return response[selected] if selected >= 0 else None
    else:
        return None


def _request(ws, url, callback, queryargs=None, important=False):
    if not queryargs:
        queryargs = {}

    ws.get_url(
        url=url,
        handler=callback,
        parse_response_type="json",
        priority=True,
        important=important,
        queryargs=queryargs,
        cacheloadcontrol=QNetworkRequest.PreferNetwork,
    )


def _fetch_json(url, params):
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
                log.error(f"{PLUGIN_NAME}: HTTP error {resp.status} for {full_url}")
                return {}
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception as e:
        log.error(f"{PLUGIN_NAME}: fetch_json: failed to request {url} — {e}")
        return {}


def fetch_lyrics(
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
        queryargs = {"q": title}
    else:
        url = lrclib_get_url
        queryargs = {
            "track_name": title,
            "artist_name": artist,
            "album_name": albumName,
        }
        if length:
            queryargs["duration"] = length

    album._requests += 1
    log.debug(
        "{}: {} {}?{}".format(
            PLUGIN_NAME,
            "GET" if method != "search" else "SEARCH",
            quote(url),
            urlencode(queryargs),
        )
    )
    _request(
        album.tagger.webservice,  # type: ignore
        url,
        partial(process_response, method, album, metadata, linked_files),
        queryargs,
    )


def process_response(
    method: str,
    album: Album,
    metadata: Metadata,
    linked_files: list[File],
    response,
    reply,
    error,
):
    if error or (
        response and isinstance(response, dict) and not response.get("id", False)
    ):
        log.warning(
            '{}: lyrics NOT found for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            )
        )
        if method == "get_on_save":
            for file in linked_files:
                files_processing.discard(file.filename)
        album._requests -= 1
        album._finalize_loading(None)
        return

    try:
        if method == "search":
            parent = album.tagger.window if hasattr(album, "tagger") else None  # type: ignore
            response = show_search_table(
                parent, metadata["title"], response, _fetch_json
            )
            if response is None:
                return

        lyrics = None
        is_plain = False

        if (
            response.get("instrumental", False)
            or "(Instrumental)" in (response.get("trackName") or "")
            or "[au: instrumental]" in (response.get("plainLyrics") or "")
        ) and (config.setting["ignore_instrumental"] and method != "search"):
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
            ext = ".txt" if (is_plain and config.setting["plain_as_txt"]) else ".lrc"
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
                and config.setting["save_lrc_file"]
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
                    or (has_metadata_lyrics and not config.setting["save_lrc_file"])
                )
                and (not config.setting["auto_overwrite"])
                and (method not in ["get_on_load", "get_on_save"])
            ):
                title = "Overwrite file lyrics?"
                desc = ('Overwrite Lyrics for "{}".\n\n{}').format(
                    file.metadata.get("title", "<file>"),
                    truncate_text(lyrics, 5, 42),
                )
                parent = getattr(file, "tagger", None)
                if not confirm_replace(getattr(parent, "window", None), title, desc):
                    return

            file.metadata["lyrics"] = lyrics
            if config.setting["save_lrc_file"]:
                for old_ext in [".txt", ".lrc"]:
                    old_file = base_path + old_ext
                    if os.path.exists(old_file):
                        try:
                            os.remove(old_file)
                        except Exception as e:
                            log.error(
                                f"{PLUGIN_NAME}: Failed to delete {old_file}: {e}"
                            )

                try:
                    with open(file_lrc, "w", encoding="utf-8") as f:
                        f.write(lyrics)
                except Exception as e:
                    log.error(f"{PLUGIN_NAME}: Failed to write .lrc file: {e}")
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
        log.debug(
            '{}: lyrics loaded for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            )
        )

    except (TypeError, KeyError, ValueError) as e:
        log.error(
            '{}: lyrics NOT loaded for track "{}" by {}: {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"], e
            ),
            exc_info=True,
        )

    finally:
        if method == "get_on_save":
            for file in linked_files:
                file.save()
        album._requests -= 1
        album._finalize_loading(None)


class LrclibLyricsOptionsPage(OptionsPage):
    NAME = "lrclib_lyrics"
    TITLE = "LRCLIB Lyrics"
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

    options = [
        BoolOption("setting", key, PLUGIN_OPTIONS[key]) for key in PLUGIN_OPTIONS.keys()
    ]

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
            0, 0, QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
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
        self.get_on_load.setChecked(bool(config.setting["get_on_load"]))
        self.get_on_save.setChecked(bool(config.setting["get_on_save"]))
        self.auto_overwrite.setChecked(bool(config.setting["auto_overwrite"]))
        self.save_lrc.setChecked(bool(config.setting["save_lrc_file"]))
        self.ignore_instrumental.setChecked(bool(config.setting["ignore_instrumental"]))
        self.plain_as_txt.setChecked(bool(config.setting["plain_as_txt"]))

    def save(self):
        config.setting["get_on_load"] = self.get_on_load.isChecked()
        config.setting["get_on_save"] = self.get_on_save.isChecked()
        config.setting["auto_overwrite"] = self.auto_overwrite.isChecked()
        config.setting["save_lrc_file"] = self.save_lrc.isChecked()
        config.setting["ignore_instrumental"] = self.ignore_instrumental.isChecked()
        config.setting["plain_as_txt"] = self.plain_as_txt.isChecked()

    def clean_orphaned_lrc_files(self):
        try:
            parent = QtWidgets.QApplication.activeWindow()

            root_dir = QtWidgets.QFileDialog.getExistingDirectory(
                parent,
                "Select Music Library Root Directory",
                "",
                QtWidgets.QFileDialog.ShowDirsOnly
                | QtWidgets.QFileDialog.DontResolveSymlinks,
            )

            if not root_dir:
                log.info(f"{PLUGIN_NAME}: User cancelled directory selection")
                return

            log.info(f"{PLUGIN_NAME}: Starting recursive scan of {root_dir}")
            orphaned_count = self._clean_directory_recursive(root_dir)

            if orphaned_count > 0:
                QtWidgets.QMessageBox.information(
                    parent,
                    "Cleanup Complete",
                    f"Removed {orphaned_count} orphaned .lrc file{'s' if orphaned_count != 1 else ''}",
                )
                log.info(f"{PLUGIN_NAME}: Cleaned {orphaned_count} orphaned .lrc files")
            else:
                QtWidgets.QMessageBox.information(
                    parent, "Cleanup Complete", "No orphaned .lrc files found"
                )
                log.info(f"{PLUGIN_NAME}: No orphaned .lrc files found")

        except Exception as err:
            log.error(
                f"{PLUGIN_NAME}: Error cleaning orphaned files: {err}", exc_info=True
            )

    def _clean_directory_recursive(self, root_dir):
        if not os.path.isdir(root_dir):
            log.warning(f"{PLUGIN_NAME}: Directory does not exist: {root_dir}")
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
                            log.debug(
                                f"{PLUGIN_NAME}: Deleted orphaned file: {lrc_path}"
                            )
                        except Exception as e:
                            log.error(
                                f"{PLUGIN_NAME}: Failed to delete {lrc_path}: {e}"
                            )

        except Exception as e:
            log.error(f"{PLUGIN_NAME}: Error scanning directory {root_dir}: {e}")

        return orphaned_count


def get_on_load(track: Track, file: File) -> None:
    if not config.setting["get_on_load"]:
        return
    try:
        if not track.files:
            return
        album = track.album
        assert isinstance(album, Album), "Album is not of type Album"
        metadata = track.metadata
        assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
        length = None
        if metadata["~length"]:
            length = parse_duration(str(track.metadata["~length"]))
        assert isinstance(length, int), "Length is not of type integer"
        fetch_lyrics("get_on_load", album, metadata, track.files, length)
    except Exception as err:
        log.error(f"{PLUGIN_NAME}: Error in get_on_load: {err}")


def get_on_save(file: File) -> None:
    if not config.setting["get_on_save"]:
        return
    if file.filename in files_processing:
        return files_processing.discard(
            file.filename
        )  # Picard only allow one concurrent save_hook
    try:
        files_processing.add(file.filename)
        album = file.parent.album  # type: ignore
        assert isinstance(album, Album), "Album is not of type Album"
        metadata = file.metadata
        assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
        length = None
        if metadata["~length"]:
            length = parse_duration(str(metadata["~length"]))
        assert isinstance(length, int), "Length is not of type integer"
        fetch_lyrics("get_on_save", album, metadata, [file], length)
    except Exception as err:
        log.error(f"{PLUGIN_NAME}: Error in get_on_save: {err}")
        files_processing.discard(file.filename)


class LrcLibLyricsGet(BaseAction):
    NAME = "Get lyrics automatically with LRCLIB"

    def execute_on_track(self, track):
        try:
            if not track.linked_files:  # If it's not in your local file then ignore
                return
            album = track.album
            assert isinstance(album, Album), "Album is not of type Album"
            metadata = track.metadata
            assert isinstance(metadata, Metadata), "Metadata is not of type Metadata"
            length = None
            if metadata["~length"]:
                length = parse_duration(str(metadata["~length"]))
            assert isinstance(length, int), "Length is not of type integer"
            fetch_lyrics("get", album, metadata, track.files, length)
        except Exception as err:
            log.error(err)

    def callback(self, objs):
        for item in (t for t in objs if isinstance(t, Track) or isinstance(t, Album)):
            if isinstance(item, Track):
                log.debug("{}: {}, {}".format(PLUGIN_NAME, item, item.album))
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    log.debug("{}: {}, {}".format(PLUGIN_NAME, track, item))
                    self.execute_on_track(track)


class LrcLibLyricsSearch(BaseAction):
    NAME = "Search lyrics manually with LRCLIB"

    def execute_on_track(self, track):
        try:
            if not track.linked_files:  # If it's not in your local file then ignore
                return
            fetch_lyrics("search", track.album, track.metadata, track.linked_files)
        except Exception as err:
            log.error(err)

    def callback(self, objs):
        for item in (t for t in objs if isinstance(t, Track) or isinstance(t, Album)):
            if isinstance(item, Track):
                log.debug("{}: {}, {}".format(PLUGIN_NAME, item, item.album))
                self.execute_on_track(item)
            elif isinstance(item, Album):
                for track in item.tracks:
                    log.debug("{}: {}, {}".format(PLUGIN_NAME, track, item))
                    self.execute_on_track(track)


register_file_post_addition_to_track_processor(get_on_load)
register_file_post_save_processor(get_on_save)

register_track_action(LrcLibLyricsSearch())
register_album_action(LrcLibLyricsSearch())

register_track_action(LrcLibLyricsGet())
register_album_action(LrcLibLyricsGet())

register_options_page(LrclibLyricsOptionsPage)
