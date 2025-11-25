from functools import partial
from urllib.parse import (
    quote, urlencode,
)
from urllib.request import (
    Request, urlopen,
)
import os, json

from PyQt5.QtNetwork import QNetworkRequest

from picard import config, log
from picard.file import register_file_post_addition_to_track_processor
from picard.track import Track
from picard.album import Album
from picard.ui.itemviews import (
    BaseAction,
    register_track_action,
    register_album_action,
)

from PyQt5 import QtWidgets
from picard.ui.options import (
    OptionsPage,
    register_options_page,
)
from picard.config import BoolOption

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
PLUGIN_VERSION = "1.1.1"
PLUGIN_API_VERSIONS = ["2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"]
PLUGIN_LICENSE = "MIT"
PLUGIN_LICENSE_URL = "https://opensource.org/licenses/MIT"

lrclib_get_url = "https://lrclib.net/api/get"
lrclib_search_url = "https://lrclib.net/api/search"

def format_durasi(durasi: int) -> str:
    durasi = int(durasi)
    donat = durasi
    if durasi >= 3600:
        jam = durasi // 3600
        donat = durasi % 3600
    if donat >= 60:
        menit = donat // 60
        detik = donat % 60
    else:
        menit = 0
        detik = donat

    if durasi >= 3600:
        return f"{jam}:{menit:02}:{detik:02}"
    else:
        return f"{menit}:{detik:02}"

def truncate_text(text, max_lines=5, max_chars_per_line=46):
    lines = []
    for i, line in enumerate(text.splitlines()):
        if i >= max_lines:
            lines[-1] = lines[-1].rstrip() + " …"
            break
        if len(line) > max_chars_per_line:
            line = line[:max_chars_per_line - 1].rstrip() + "…"
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + " …"
    return "\n".join(lines)

def parse_duration(time_str:str):
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
            QtWidgets.QMessageBox.No
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
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)

    table = QtWidgets.QTableWidget(dialog)
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(["Name", "Artist", "Length", "Album", "Synced"])
    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
    header.setSectionResizeMode(1, QtWidgets.QHeaderView.Interactive)
    header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
    header.setSectionResizeMode(3, QtWidgets.QHeaderView.Interactive)
    header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    layout.addWidget(table)

    button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
    layout.addWidget(button_box)

    def populate_table(response):
        table.setRowCount(0)
        if not response:
            return
        table.setRowCount(len(response))
        for row, item in enumerate(response):
            values = [
                item.get("trackName", ""),
                item.get("artistName", ""),
                format_durasi(item.get("duration", 0)),
                item.get("albumName", ""),
                "✓" if item.get("syncedLyrics") else "✕",
            ]
            for col, val in enumerate(values):
                table.setItem(row, col, QtWidgets.QTableWidgetItem(str(val)))

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
        cacheloadcontrol=QNetworkRequest.PreferCache,
    )

def _fetch_json(url, params):
    try:
        query = urlencode(params)
        full_url = f"{url}?{query}"

        req = Request(full_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"})
        with urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                log.error(f"{PLUGIN_NAME}: HTTP error {resp.status} for {full_url}")
                return {}
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except Exception as e:
        log.error(f"{PLUGIN_NAME}: fetch_json: failed to request {url} — {e}")
        return {}


def get_lyrics(method, album, metadata, linked_files, length=None):
    artist = metadata["artist"]
    title = metadata["title"]
    albumName = metadata["album"]
    duration = int(length)
    if not (artist and title and albumName and duration):
        log.debug(
            "{}: artist, title, album name, and duration are required to obtain lyrics".format(
                PLUGIN_NAME
            )
        )
        return

    queryargs = {
        "track_name": title,
        "artist_name": artist,
        "album_name": albumName,
    }
    if duration:
        queryargs["duration"] = duration
    album._requests += 1
    log.debug(
        "{}: GET {}?{}".format(PLUGIN_NAME, quote(lrclib_get_url), urlencode(queryargs))
    )
    _request(
        album.tagger.webservice, lrclib_get_url,
        partial(process_response, method, album, metadata, linked_files),
        queryargs,
    )

def search_lyrics(method, album, metadata, linked_files):
    artist = metadata["artist"]
    title = metadata["title"]
    albumName = metadata["album"]
    if not (artist and title and albumName):
        log.debug(
            "{}: artist, title, album name, and duration are required to obtain lyrics".format(
                PLUGIN_NAME
            )
        )
        return

    queryargs = {
        "q": title,
    }
    album._requests += 1
    log.debug(
        "{}: SEARCH {}?{}".format(PLUGIN_NAME, quote(lrclib_search_url), urlencode(queryargs))
    )
    _request(
        album.tagger.webservice, lrclib_search_url,
        partial(process_response, method, album, metadata, linked_files),
        queryargs,
    )

def process_response(method, album, metadata, linked_files, response, reply, error):
    if error or (response and isinstance(response, dict) and not response.get("id", False)):
        album._requests -= 1
        album._finalize_loading(None)
        log.warning(
            '{}: lyrics NOT found for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            )
        )
        return

    try:
        if method == "search":
            parent = album.tagger.window if hasattr(album, "tagger") else None
            response = show_search_table(parent, metadata["title"], response, _fetch_json)
            if response is None:
                return

        lyrics = (
            response["syncedLyrics"]
            if response.get("syncedLyrics")
            else response["plainLyrics"]
        )
        for file in linked_files:
            file_lrc = f"{file.metadata['~dirname']}/{file.metadata['~filename']}.lrc"
            has_metadata_lyrics = bool(file.metadata.get("lyrics"))
            has_lrc_file = os.path.exists(file_lrc)
            
            if has_metadata_lyrics and not has_lrc_file and config.setting["save_lrc_file"]:
                lyrics = file.metadata.get("lyrics")
            elif has_lrc_file and not has_metadata_lyrics:
                try:
                    with open(file_lrc, "r") as f:
                        lyrics = f.read()
                except Exception as e:
                    log.error(f"{PLUGIN_NAME}: Failed to read existing .lrc file: {e}")
            elif has_metadata_lyrics and has_lrc_file and not config.setting["auto_overwrite"]:
                if method == "search_on_load":
                    return
                else:
                    title = "Overwrite file lyrics?"
                    desc = (
                        'Overwrite Lyrics for "{}".\n\n'
                        "{}"
                    ).format(file.metadata.get("title", "<file>"), truncate_text(lyrics, 5, 42))
                    parent = getattr(file, "tagger", None)
                    if not confirm_replace(getattr(parent, "window", None), title, desc):
                        return

            file.metadata["lyrics"] = lyrics
            if config.setting["save_lrc_file"]:
                if not os.path.exists(file_lrc):
                    with open(file_lrc, "w") as f:
                        f.write(lyrics)
        log.debug(
            '{}: lyrics loaded for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            )
        )

    except (TypeError, KeyError, ValueError):
        log.error(
            '{}: lyrics NOT loaded for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            ),
            exc_info=True,
        )

    finally:
        album._requests -= 1
        album._finalize_loading(None)


class LrclibLyricsOptionsPage(OptionsPage):

    NAME = "lrclib_lyrics"
    TITLE = "LRCLIB Lyrics"
    PARENT = "plugins"
    
    AUDIO_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav', '.wma', '.aac', '.ape', '.mpc', '.wv'}

    options = [
        BoolOption("setting", "search_on_load", False),
        BoolOption("setting", "auto_overwrite", False),
        BoolOption("setting", "save_lrc_file", True)
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.box = QtWidgets.QVBoxLayout(self)

        self.auto_search = QtWidgets.QCheckBox("Search for lyrics when loading tracks", self)
        self.box.addWidget(self.auto_search)

        self.auto_overwrite = QtWidgets.QCheckBox("Auto overwrite existing lyrics", self)
        self.box.addWidget(self.auto_overwrite)

        self.save_lrc = QtWidgets.QCheckBox("Save .lrc file alongside audio files", self)
        self.box.addWidget(self.save_lrc)
        
        self.box.addSpacing(20)
        
        cleanup_label = QtWidgets.QLabel("Cleanup Tools:", self)
        cleanup_label.setStyleSheet("font-weight: bold;")
        self.box.addWidget(cleanup_label)
        
        self.cleanup_button = QtWidgets.QPushButton("Clean Orphaned LRC Files", self)
        self.cleanup_button.setToolTip("Recursively scan a directory for .lrc files without matching audio files")
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
        self.auto_search.setChecked(config.setting["search_on_load"])
        self.auto_overwrite.setChecked(config.setting["auto_overwrite"])
        self.save_lrc.setChecked(config.setting["save_lrc_file"])

    def save(self):
        config.setting["search_on_load"] = self.auto_search.isChecked()
        config.setting["auto_overwrite"] = self.auto_overwrite.isChecked()
        config.setting["save_lrc_file"] = self.save_lrc.isChecked()
    
    def clean_orphaned_lrc_files(self):
        try:
            parent = QtWidgets.QApplication.activeWindow()
            
            root_dir = QtWidgets.QFileDialog.getExistingDirectory(
                parent,
                "Select Music Library Root Directory",
                "",
                QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
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
                    f"Removed {orphaned_count} orphaned .lrc file{'s' if orphaned_count != 1 else ''}"
                )
                log.info(f"{PLUGIN_NAME}: Cleaned {orphaned_count} orphaned .lrc files")
            else:
                QtWidgets.QMessageBox.information(
                    parent,
                    "Cleanup Complete",
                    "No orphaned .lrc files found"
                )
                log.info(f"{PLUGIN_NAME}: No orphaned .lrc files found")
                
        except Exception as err:
            log.error(f"{PLUGIN_NAME}: Error cleaning orphaned files: {err}", exc_info=True)
    
    def _clean_directory_recursive(self, root_dir):
        if not os.path.isdir(root_dir):
            log.warning(f"{PLUGIN_NAME}: Directory does not exist: {root_dir}")
            return 0
        
        orphaned_count = 0
        
        try:
            for dirpath, dirnames, filenames in os.walk(root_dir):
                lrc_files = [f for f in filenames if f.lower().endswith('.lrc')]
                
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
                            log.debug(f"{PLUGIN_NAME}: Deleted orphaned file: {lrc_path}")
                        except Exception as e:
                            log.error(f"{PLUGIN_NAME}: Failed to delete {lrc_path}: {e}")
        
        except Exception as e:
            log.error(f"{PLUGIN_NAME}: Error scanning directory {root_dir}: {e}")
        
        return orphaned_count

def search_on_load(track, file):
    if not config.setting["search_on_load"]:
        return
    try:
        if not track.linked_files:
            return
        length = None
        if track.metadata["~length"]:
            length = parse_duration(track.metadata["~length"])
        get_lyrics("search_on_load", track.album, track.metadata, track.linked_files, length)
    except Exception as err:
        log.error(f"{PLUGIN_NAME}: Error in search_on_load: {err}")

class LrcLibLyricsGet(BaseAction):
    NAME = "Get lyrics automatically with LRCLIB"

    def execute_on_track(self, track):
        try:
            if not track.linked_files: # If it's not in your local file then ignore
                return
            length = None
            if track.metadata["~length"]:
                length = parse_duration(track.metadata["~length"])
            get_lyrics("get", track.album, track.metadata, track.linked_files, length)
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
            if not track.linked_files: # If it's not in your local file then ignore
                return
            search_lyrics("search", track.album, track.metadata, track.linked_files)
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


register_file_post_addition_to_track_processor(search_on_load)
register_track_action(LrcLibLyricsSearch())
register_album_action(LrcLibLyricsSearch())
register_track_action(LrcLibLyricsGet())
register_album_action(LrcLibLyricsGet())
register_options_page(LrclibLyricsOptionsPage)
