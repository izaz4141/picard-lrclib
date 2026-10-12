from picard.plugin3.api import PluginApi

from .src.actions.get_lyrics import LrcLibLyricsGet
from .src.actions.search_lyrics import LrcLibLyricsSearch
from .src.callbacks.get_on_load import get_on_load
from .src.callbacks.get_on_save import get_on_save
from .src.options.config import register_options
from .src.options.options_page import LrclibLyricsOptionsPage


def enable(api: PluginApi) -> None:
    """Called when plugin is enabled."""
    api.register_file_post_addition_to_track_processor(get_on_load)
    api.register_file_post_save_processor(get_on_save)
    api.register_track_action(LrcLibLyricsSearch)
    api.register_album_action(LrcLibLyricsSearch)
    api.register_track_action(LrcLibLyricsGet)
    api.register_album_action(LrcLibLyricsGet)

    register_options(api)
    api.register_options_page(LrclibLyricsOptionsPage)
