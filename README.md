# LRCLIB Lyrics Plugin for Picard

A MusicBrainz Picard plugin to fetch lyrics from [LRCLIB](https://lrclib.net) and save them to both **audio file metadata** and **.lrc sidecar files** for Jellyfin compatibility.


## Features
- 🎵 Fetches lyrics from LRCLIB's crowdsourced database
- 💾 Saves lyrics to:
  - `lyrics` metadata tag (for players like MusicBee/iTunes)
  - `.lrc` files (for Jellyfin, Plex, Kodi, etc.)
- ⚡ Optional automatic lyric fetching on track load
- 🚫 Never overwrites existing `.lrc` files

## Installation
1. **Download Plugin Files**:
   - Get the latest `.py` files from [GitHub Releases](#) *(https://raw.githubusercontent.com/izaz4141/picard-lrclib/refs/heads/main/lrcget.py)*
   
2. **Install in Picard**:
   - Open Picard → `Options` → `Plugins`
   - Click `Install Plugin` 
   - Select the downloaded `.py` file(s)

## Usage
### Automatic Fetching
1. Enable auto-fetch:  
   `Options` → `Plugins` → `LRCLIB Lyrics` → Check "Search for lyrics when loading tracks"

### Manual Fetching
1. Right-click track/album →  
   `Search for lyrics with LRCLIB...`

.lyrics files will be saved as:  
`[audio filename].lrc` (e.g. `Song Name.lrc`)

## Compatibility
| Component           | Supported          |
|---------------------|--------------------|
| Picard Versions     | 2.0+ (API v2.0-2.6)|
| Audio Formats       | All (MP3, FLAC, etc.) |
| Media Servers       | Jellyfin, Plex, Emby |
| Players             | MusicBee, Foobar2000, AIMP |

## Notes
- Lyrics are saved in UTF-8 encoding
- `.lrc` files match your audio filenames automatically
- Lyrics provided under [LRCLIB's terms](https://lrclib.net/terms)

## Disclaimer
This plugin is unofficial. Always verify lyrics accuracy. Commercial use of lyrics may require licensing.