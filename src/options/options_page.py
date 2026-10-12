from __future__ import annotations

from PyQt6 import QtWidgets

from picard.plugin3.api import OptionsPage

from ..common.files import find_orphaned_sidecars, remove_sidecars
from ..common.util import plugin_name
from .config import OPTIONS


class LrclibLyricsOptionsPage(OptionsPage):
    """Options page for the LRCLIB Lyrics plugin."""

    NAME = "lrclib_lyrics"
    PARENT = "plugins"

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Build the options page widgets."""
        super().__init__(parent)
        self.box = QtWidgets.QVBoxLayout(self)

        self.checkboxes: dict[str, QtWidgets.QCheckBox] = {}
        for option in OPTIONS:
            checkbox = QtWidgets.QCheckBox(option.desc, self)
            self.box.addWidget(checkbox)
            self.checkboxes[option.key] = checkbox

        self.box.addSpacing(20)

        cleanup_label = QtWidgets.QLabel("Cleanup Tools:", self)
        cleanup_label.setStyleSheet("font-weight: bold;")
        self.box.addWidget(cleanup_label)

        self.cleanup_button = QtWidgets.QPushButton("Clean Orphaned Lyrics Files", self)
        self.cleanup_button.setToolTip(
            "Recursively scan a directory for lyrics files without matching audio files"
        )
        self.cleanup_button.clicked.connect(self.clean_orphaned_lyrics_files)
        self.box.addWidget(self.cleanup_button)

        self.spacer = QtWidgets.QSpacerItem(
            0,
            0,
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Expanding,
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

    def load(self) -> None:
        """Initialise the checkboxes from the current plugin config."""
        for key, checkbox in self.checkboxes.items():
            checkbox.setChecked(bool(self.api.plugin_config[key]))

    def save(self) -> None:
        """Store the checkbox states in the plugin config."""
        for key, checkbox in self.checkboxes.items():
            self.api.plugin_config[key] = checkbox.isChecked()

    def clean_orphaned_lyrics_files(self) -> None:
        """Prompt for a directory and delete orphaned lyrics sidecars."""
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
                self.api.logger.info(
                    f"{plugin_name(self.api)}: User cancelled directory selection"
                )
                return

            self.api.logger.info(
                f"{plugin_name(self.api)}: Starting recursive scan of {root_dir}"
            )
            orphaned = find_orphaned_sidecars(self.api, root_dir)

            if not orphaned:
                QtWidgets.QMessageBox.information(
                    parent, "Cleanup Complete", "No orphaned lyrics files found"
                )
                self.api.logger.info(
                    f"{plugin_name(self.api)}: No orphaned lyrics files found"
                )
                return

            plural = "s" if len(orphaned) != 1 else ""
            confirm = QtWidgets.QMessageBox.question(
                parent,
                "Confirm Cleanup",
                f"Delete {len(orphaned)} orphaned lyrics file{plural}?\n\n"
                "This cannot be undone.",
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )

            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                self.api.logger.info(
                    f"{plugin_name(self.api)}: Cleanup cancelled by user"
                )
                return

            removed = remove_sidecars(self.api, orphaned)
            QtWidgets.QMessageBox.information(
                parent,
                "Cleanup Complete",
                f"Removed {removed} orphaned lyrics file{'s' if removed != 1 else ''}",
            )
            self.api.logger.info(
                f"{plugin_name(self.api)}: Cleaned {removed} orphaned lyrics files"
            )

        except Exception:
            self.api.logger.exception(
                f"{plugin_name(self.api)}: Error cleaning orphaned files"
            )
