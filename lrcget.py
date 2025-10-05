from functools import partial
from urllib.parse import (
    quote,
    urlencode,
)
import os

from PyQt5.QtNetwork import QNetworkRequest

from picard import config, log
from picard.metadata import register_track_metadata_processor
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
    "<b>Educational Use:</b> Lyrics are provided under LRCLIB's terms (non-commercial use only)<br/>"
    "<b>Smart Syncing:</b> Prefers synchronized lyrics when available, falls back to plain text<br/>"
    "<br/>"
    "<i>Based on Dylancyclone's original plugin with enhanced file export capabilities</i>"
)
PLUGIN_VERSION = "1.0.1"
PLUGIN_API_VERSIONS = ["2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"]
PLUGIN_LICENSE = "MIT"
PLUGIN_LICENSE_URL = "https://opensource.org/licenses/MIT"

lrclib_url = "https://lrclib.net/api/get"

def confirm_replace(parent, title, description):
    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            # No QApplication (headless) — be conservative and don't replace.
            return False
        parent_widget = QtWidgets.QApplication.activeWindow() if parent is None else parent
        reply = QtWidgets.QMessageBox.question(
            parent_widget,
            title,
            description,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        return reply == QtWidgets.QMessageBox.Yes
    except Exception:
        # If anything goes wrong with the dialog, don't overwrite.
        return False


def _request(ws, callback, queryargs=None, important=False):
    if not queryargs:
        queryargs = {}

    ws.get_url(
        url=lrclib_url,
        handler=callback,
        parse_response_type="json",
        priority=True,
        important=important,
        queryargs=queryargs,
        cacheloadcontrol=QNetworkRequest.PreferCache,
    )


def search_for_lyrics(method, album, metadata, linked_files, length=None):
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
        "{}: GET {}?{}".format(PLUGIN_NAME, quote(lrclib_url), urlencode(queryargs))
    )
    _request(
        album.tagger.webservice,
        partial(process_search_response, method, album, metadata, linked_files),
        queryargs,
    )


def process_search_response(method, album, metadata, linked_files, response, reply, error):
    if error or (response and not response.get("id", False)):
        album._requests -= 1
        album._finalize_loading(None)
        log.warning(
            '{}: lyrics NOT found for track "{}" by {}'.format(
                PLUGIN_NAME, metadata["title"], metadata["artist"]
            )
        )
        return

    try:
        lyrics = (
            response["syncedLyrics"]
            if response.get("syncedLyrics")
            else response["plainLyrics"]
        )
        metadata["lyrics"] = lyrics
        for file in linked_files:
            file_lrc = f"{file.metadata['~dirname']}/{file.metadata['~filename']}.lrc"
            set_file_lyrics = not method == "search_on_load" 
            if (file.metadata.get("lyrics") or os.path.exists(file_lrc)) and not config.setting["auto_overwrite"] \
                and not method == "search_on_load":
                title = "Overwrite file lyrics?"
                desc = (
                    'Lyrics already exist for "{}".\n\n'
                    "Overwrite?"
                ).format(file.metadata.get("title", "<file>"))
                parent = getattr(file, "tagger", None)
                # if file.tagger has a window, you could use file.tagger.window as parent. Use None as fallback.
                if not confirm_replace(getattr(parent, "window", None), title, desc):
                    set_file_lyrics = False

            if set_file_lyrics:
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

class LrclibLyricsMetadataProcessor:

    def __init__(self):
        super().__init__()

    def process_metadata(self, album, metadata, track, release):
        if config.setting["search_on_load"]:
            try:
                if not track.linked_files:
                    return
                length = None
                if track['~length']:
                    length = track.metadata["~length"].split(":")
                    length = int(length[0]) * 60 + int(length[1])
                search_for_lyrics("search_on_load", album, metadata, track.linked_files, length)
            except Exception as err:
                log.error(err)

class LrclibLyricsTrackAction(BaseAction):
    NAME = "Search for lyrics with LRCLIB..."

    def execute_on_track(self, track):
        try:
            if not track.linked_files: # If it's not in your local file then ignore
                return
            length = None
            if track.metadata["~length"]:
                length = track.metadata["~length"].split(":")
                length = int(length[0]) * 60 + int(length[1])
            search_for_lyrics("auto_search", track.album, track.metadata, track.linked_files, length)
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


register_track_metadata_processor(LrclibLyricsMetadataProcessor().process_metadata)
register_track_action(LrclibLyricsTrackAction())
register_album_action(LrclibLyricsTrackAction())
register_options_page(LrclibLyricsOptionsPage)
