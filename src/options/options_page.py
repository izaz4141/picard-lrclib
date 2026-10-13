from __future__ import annotations

from PyQt6 import QtWidgets

from picard.plugin3.api import OptionsPage

from ..common.files import remove_sidecars, scan_orphaned_sidecars
from ..common.util import plugin_name
from ..ui.dialogs import (
    confirm_yes_no,
    select_directory,
    show_critical,
    show_info,
)
from ..ui.options_widget import LrclibOptionsWidget
from .config import OPTIONS


class LrclibLyricsOptionsPage(OptionsPage):
    """Options page for the LRCLIB Lyrics plugin."""

    NAME = "lrclib_lyrics"
    PARENT = "plugins"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the options page widgets."""
        super().__init__(parent)
        self.widget = LrclibOptionsWidget(self, OPTIONS)
        self.box = QtWidgets.QVBoxLayout(self)
        self.box.addWidget(self.widget)
        self.widget.cleanup_button.clicked.connect(self.clean_orphaned_lyrics_files)

    def load(self) -> None:
        """Initialise the checkboxes from the current plugin config."""
        for key, checkbox in self.widget.checkboxes.items():
            checkbox.setChecked(bool(self.api.plugin_config[key]))

    def save(self) -> None:
        """Store the checkbox states in the plugin config."""
        for key, checkbox in self.widget.checkboxes.items():
            self.api.plugin_config[key] = checkbox.isChecked()

    def clean_orphaned_lyrics_files(self) -> None:
        """Prompt for a directory and scan it for orphaned lyrics sidecars."""
        try:
            root_dir = select_directory(
                self.api.logger, None, "Select Music Library Root Directory"
            )
            if not root_dir:
                self.api.logger.info(
                    f"{plugin_name(self.api)}: User cancelled directory selection"
                )
                return

            self.api.logger.info(
                f"{plugin_name(self.api)}: Starting recursive scan of {root_dir}"
            )

            self.widget.cleanup_button.setEnabled(False)
            scan_orphaned_sidecars(self.api, root_dir, self._scan_finished)

        except Exception:
            self.widget.cleanup_button.setEnabled(True)
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error starting orphaned files scan"
            )

    def _scan_finished(
        self, result: list[str] | None = None, error: BaseException | None = None
    ) -> None:
        """Handle the scan result and delete the orphaned sidecars."""
        self.widget.cleanup_button.setEnabled(True)

        if error is not None:
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error cleaning orphaned files",
                exc_info=error,
            )
            show_critical(
                self.api.logger,
                None,
                "Cleanup Failed",
                f"An error occurred while scanning for orphaned files:\n{error}",
            )
            return

        try:
            orphaned = result or []

            if not orphaned:
                show_info(
                    self.api.logger,
                    None,
                    "Cleanup Complete",
                    "No orphaned lyrics files found",
                )
                self.api.logger.info(
                    f"{plugin_name(self.api)}: No orphaned lyrics files found"
                )
                return

            plural = "s" if len(orphaned) != 1 else ""
            if not confirm_yes_no(
                self.api.logger,
                None,
                "Confirm Cleanup",
                f"Delete {len(orphaned)} orphaned lyrics file{plural}?\n\n"
                "This cannot be undone.",
            ):
                self.api.logger.info(
                    f"{plugin_name(self.api)}: Cleanup cancelled by user"
                )
                return

            removed = remove_sidecars(self.api, orphaned)
            plural = "s" if removed != 1 else ""
            show_info(
                self.api.logger,
                None,
                "Cleanup Complete",
                f"Removed {removed} orphaned lyrics file{plural}",
            )
            self.api.logger.info(
                f"{plugin_name(self.api)}: Cleaned {removed} orphaned lyrics files"
            )

        except Exception:
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error cleaning orphaned files"
            )
