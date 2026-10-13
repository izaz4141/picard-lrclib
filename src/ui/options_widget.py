from __future__ import annotations

from collections.abc import Sequence

from PyQt6 import QtWidgets

from ..options.config import Option, OPTIONS


class LrclibOptionsWidget(QtWidgets.QWidget):
    """Widget containing LRCLIB options UI elements."""

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        options: Sequence[Option] | None = None,
    ) -> None:
        super().__init__(parent)
        opts = options or OPTIONS

        self.box = QtWidgets.QVBoxLayout(self)

        self.checkboxes: dict[str, QtWidgets.QCheckBox] = {}
        for option in opts:
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
