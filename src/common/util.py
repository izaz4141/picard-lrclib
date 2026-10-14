from __future__ import annotations

from picard.plugin3.api import PluginApi


def plugin_name(api: PluginApi) -> str:
    """Display name for this plugin, taken from MANIFEST.toml."""
    return api.manifest.name_i18n()


def format_duration(duration: int) -> str:
    """Format seconds as ``M:SS`` or ``H:MM:SS``."""
    hours, remainder = divmod(int(duration), 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def truncate_text(text: str, max_lines: int = 5, max_chars_per_line: int = 46) -> str:
    """Truncate text to a max number of lines and characters per line."""
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


def parse_duration(time_str: str) -> int:
    """Parse an ``M:SS`` or ``H:MM:SS`` string into total seconds."""
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
