from __future__ import annotations

# Filenames currently being processed during a save hook. Picard allows only one
# concurrent save_hook per file, so this guards against re-entrant processing.
files_processing: set[str] = set()
