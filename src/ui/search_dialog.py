from __future__ import annotations

from typing import Any

from PyQt6 import QtCore, QtGui, QtWidgets

from picard.plugin3.api import Album, PluginApi

from ..common.models import LrclibTrack
from ..common.util import format_duration, plugin_name
from ..services.webservice import search_refresh
from .dialogs import show_critical


def show_search_table(
    api: PluginApi,
    parent: QtWidgets.QWidget | None,
    query: str,
    response: list[LrclibTrack],
    album: Album,
) -> LrclibTrack | None:
    """Show LRCLIB results and return the selected track, if any."""
    parent = QtWidgets.QApplication.activeWindow() if parent is None else parent
    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Search Tracks")
    dialog.resize(700, 400)

    layout = QtWidgets.QVBoxLayout(dialog)

    search_layout = QtWidgets.QHBoxLayout()
    search_input = QtWidgets.QLineEdit()
    search_input.setText(query)
    search_input.setPlaceholderText("Enter search query...")
    search_button = QtWidgets.QPushButton("Search")
    search_button.setDefault(True)
    search_button.setAutoDefault(True)
    search_layout.addWidget(search_input)
    search_layout.addWidget(search_button)
    layout.addLayout(search_layout)

    table = QtWidgets.QTableWidget(dialog)
    table.setColumnCount(6)
    table.setHorizontalHeaderLabels(
        ["#", "Name", "Artist", "Length", "Album", "Synced"]
    )
    vheader = table.verticalHeader()
    assert vheader is not None, "VHeader is unexpectedly None"
    vheader.setVisible(False)
    hheader = table.horizontalHeader()
    assert hheader is not None, "HHeader is unexpectedly None"
    hheader.setDefaultAlignment(
        QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter
    )  # type: ignore
    hheader.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    hheader.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
    hheader.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Interactive)
    hheader.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    hheader.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Interactive)
    hheader.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    layout.addWidget(table)

    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok
        | QtWidgets.QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(button_box)

    def populate_table(response: list[LrclibTrack]) -> None:
        """Fill the results table with the given tracks."""
        table.setSortingEnabled(False)
        table.setRowCount(0)
        if not response:
            return
        table.setRowCount(len(response))
        for row, item in enumerate(response):
            num_item = QtWidgets.QTableWidgetItem()
            num_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)  # type: ignore
            num_item.setData(QtCore.Qt.ItemDataRole.EditRole, row + 1)  # type: ignore
            num_item.setData(QtCore.Qt.ItemDataRole.UserRole, item.get("id"))
            table.setItem(row, 0, num_item)

            has_synced = item.get("syncedLyrics") or False
            values = [
                item.get("trackName") or "?",
                item.get("artistName") or "?",
                format_duration(item.get("duration", None) or 0),
                item.get("albumName") or "?",
                "V" if has_synced else "X",
            ]
            for col, val in enumerate(values, start=1):
                cell_item = QtWidgets.QTableWidgetItem(str(val))
                cell_item.setData(QtCore.Qt.ItemDataRole.UserRole, item.get("id"))
                if col in [3, 5]:
                    cell_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)  # type: ignore
                    if col == 5:
                        cell_item.setForeground(
                            QtGui.QColor("#2ecc71" if has_synced else "#e74c3c")
                        )
                table.setItem(row, col, cell_item)
        table.setSortingEnabled(True)

    populate_table(response)

    def on_search_clicked() -> None:
        """Re-run the LRCLIB search with the current query."""
        nonlocal response
        query = search_input.text().strip()
        if not query:
            return
        try:

            def refresh_done(
                new_response: list[LrclibTrack],
                reply: Any,
                error: Exception | None,
            ) -> None:
                """Update the table when a refreshed search completes."""
                nonlocal response
                if error:
                    api.logger.warning(
                        f"{plugin_name(api)}: search refresh failed: {error}"
                    )
                    return
                response = new_response
                try:
                    populate_table(response)
                except RuntimeError:
                    return  # dialog was closed while request was in flight
                api.logger.debug(
                    f"{plugin_name(api)}: search refreshed: {len(response)} results"
                )

            search_refresh(api, album, query, refresh_done)
        except Exception:
            api.logger.exception(f"{plugin_name(api)}: Error during search refresh")

    search_button.clicked.connect(on_search_clicked)
    search_input.returnPressed.connect(on_search_clicked)

    def selected_track_id() -> int | None:
        """Resolve the selected track id from the sorted selection model."""
        model = table.model()
        selection = table.selectionModel()
        rows: list[QtCore.QModelIndex] = []
        if selection is not None:
            rows = selection.selectedRows(0)
        if not rows and table.currentIndex().isValid():
            rows = [table.currentIndex()]
        if model is None:
            return None
        for idx in rows:
            value = model.data(idx, QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(value, int):
                return value
        return None

    def on_double_click(index: QtCore.QModelIndex) -> None:
        """Accept the dialog when a row is double-clicked."""
        if index.isValid():
            dialog.accept()

    table.doubleClicked.connect(on_double_click)

    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)

    result = dialog.exec()
    if result != QtWidgets.QDialog.DialogCode.Accepted:
        return None  # cancelled by the user - not an error

    track_id = selected_track_id()
    match = (
        next((t for t in response if t.get("id") == track_id), None)
        if track_id is not None
        else None
    )
    if match is None:
        if track_id is None:
            message = "No track was selected in the search results."
        else:
            message = (
                f"The selected track (id={track_id}) is no longer in the results."
            )
        api.logger.error(f"{plugin_name(api)}: {message}")
        show_critical(api.logger, dialog, "LRCLIB search", message)
        return None
    return match
