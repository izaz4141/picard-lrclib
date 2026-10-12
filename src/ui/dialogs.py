from __future__ import annotations

from PyQt6 import QtWidgets


def confirm_replace(
    parent: QtWidgets.QWidget | None, title: str, description: str
) -> bool:
    """Ask the user to confirm replacing lyrics; return their choice."""
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        reply = QtWidgets.QMessageBox.question(
            parent,
            title,
            description,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes
    except Exception:
        return False


def show_write_error(
    parent: QtWidgets.QWidget | None, file_path: str, error: str
) -> None:
    """Show an error dialog when writing a lyrics file fails."""
    parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
    QtWidgets.QMessageBox.critical(
        parent,
        "Failed to Save LRC File",
        f"Could not save lyrics file:\n\n{file_path}\n\nError: {error}",
    )
