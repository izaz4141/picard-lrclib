from __future__ import annotations

from PyQt6 import QtWidgets

from picard.plugin3.api import PluginLogger


def select_directory(
    logger: PluginLogger,
    parent: QtWidgets.QWidget | None,
    title: str,
    initial_dir: str = "",
    show_dirs_only: bool = True,
    resolve_symlinks: bool = False,
) -> str | None:
    """Prompt user to select a directory. Returns path or None if cancelled."""
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        options = QtWidgets.QFileDialog.Option(0)
        if show_dirs_only:
            options |= QtWidgets.QFileDialog.Option.ShowDirsOnly
        if not resolve_symlinks:
            options |= QtWidgets.QFileDialog.Option.DontResolveSymlinks
        root = QtWidgets.QFileDialog.getExistingDirectory(
            parent, title, initial_dir, options
        )
        return root or None
    except Exception:
        logger.exception("Error selecting directory")
        return None


def show_info(
    logger: PluginLogger,
    parent: QtWidgets.QWidget | None,
    title: str,
    text: str,
) -> None:
    """Show an information message dialog."""
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        QtWidgets.QMessageBox.information(parent, title, text)
    except Exception:
        logger.exception("Error showing info dialog")


def show_critical(
    logger: PluginLogger,
    parent: QtWidgets.QWidget | None,
    title: str,
    text: str,
) -> None:
    """Show a critical error dialog."""
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        QtWidgets.QMessageBox.critical(parent, title, text)
    except Exception:
        logger.exception("Error showing critical dialog")


def confirm_yes_no(
    logger: PluginLogger,
    parent: QtWidgets.QWidget | None,
    title: str,
    text: str,
    default_no: bool = True,
) -> bool:
    """Generic yes/no confirmation. Returns True if user clicks Yes."""
    try:
        parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
        default = (
            QtWidgets.QMessageBox.StandardButton.No
            if default_no
            else QtWidgets.QMessageBox.StandardButton.Yes
        )
        reply = QtWidgets.QMessageBox.question(
            parent,
            title,
            text,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            default,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Yes
    except Exception:
        logger.exception("Error showing confirmation dialog")
        return False
