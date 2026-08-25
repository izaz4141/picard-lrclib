# LRCLIB Lyrics Plugin for MusicBrainz Picard

A MusicBrainz Picard plugin that fetches lyrics from [LRCLIB](https://lrclib.net), embeds them in the audio file `lyrics` tag, and can create `.lrc` sidecar files.

This repository is a **Picard Plugin API 3.0** fork of [izaz4141/picard-lrclib](https://github.com/izaz4141/picard-lrclib).

## Features

- Fetch lyrics automatically when tracks are loaded or saved.
- Fetch lyrics manually for a track or album.
- Search LRCLIB manually and select a result.
- Prefer synchronized lyrics and fall back to plain lyrics.
- Embed lyrics in the `lyrics` metadata tag.
- Save synchronized lyrics as `.lrc` sidecars.
- Optionally save plain lyrics as `.txt` sidecars.
- Optionally ignore instrumental tracks.
- Protect existing lyrics from overwrite unless explicitly requested.
- Recursively remove orphaned `.lrc` files.

## Installation

Picard 3.x plugins use the Git-based Plugin API 3.0 format. Install this repository using Picard's plugin installation mechanism for v3 plugins, or clone the repository into your Picard plugins directory as appropriate for your Picard installation.

The plugin manifest is `MANIFEST.toml`; the plugin entry point is `__init__.py`.

## Usage

After installation, configure the plugin under:

`Options → Plugins → LRCLIB Lyrics`

Available options:

- **Search for lyrics when loading tracks**
- **Search for lyrics when saving files**
- **Auto overwrite existing lyrics**
- **Save .lrc file alongside audio files**
- **Ignore instrumental lyrics**
- **Save plain lyrics as .txt**
- **Clean Orphaned LRC Files**

Manual actions are available from the track and album context menus:

- **Get lyrics automatically with LRCLIB**
- **Search lyrics manually with LRCLIB**

## Compatibility

| Component | Support |
|---|---|
| Picard | Plugin API 3.0 / Picard 3.x |
| LRCLIB | `api/get` and `api/search` |
| Sidecars | `.lrc` and optional `.txt` |

## Credits

Based on the original [izaz4141/picard-lrclib](https://github.com/izaz4141/picard-lrclib) plugin.

## License

MIT

## Disclaimer

This plugin is unofficial. Verify lyrics accuracy and ensure your use of lyrics complies with applicable copyright and service terms.
