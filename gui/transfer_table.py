"""
Transfer table widget for the File Transfer Automation System.

Displays file transfer records in a sortable table with color-coded
status indicators. Uses QAbstractTableModel for efficient data binding.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
    QTimer,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from qfluentwidgets import TableView, ComboBox, BodyLabel

from core.models import FileStatus, TransferRecord, format_file_size

# Color scheme for statuses (Foreground text colors on light background)
_STATUS_COLORS: dict[FileStatus, str] = {
    FileStatus.DETECTED: "#0078D4",     # Windows Blue
    FileStatus.PROCESSING: "#D83B01",   # Deep Orange
    FileStatus.READY: "#107C10",        # Deep Green
    FileStatus.QUEUED: "#005FB8",       # Dark Blue
    FileStatus.TRANSFERRING: "#00B7C3", # Cyan
    FileStatus.VERIFYING: "#881798",    # Magenta
    FileStatus.COMPLETED: "#107C10",    # Deep Green
    FileStatus.FAILED: "#C42B1C",       # Deep Red
    FileStatus.SKIPPED: "#797775",      # Gray
    FileStatus.CONFLICT: "#D83B01",     # Deep Orange
    FileStatus.WAITING_FOR_WINDOW: "#CA5010", # Dark Orange
}

_COLUMNS = [
    "File Name",
    "Status",
    "Size",
    "Detected",
    "Last Modified",
    "Transfer Time",
    "Verification",
    "Error",
]


class TransferTableModel(QAbstractTableModel):
    """Table model backed by a list of TransferRecords."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._records: list[TransferRecord] = []
        self._record_idx: dict[str, int] = {}
        self._pending_updates: dict[int, TransferRecord] = {}
        self._pending_inserts: list[TransferRecord] = []
        self._pending_inserts_idx: dict[str, int] = {}
        
        self._batch_timer = QTimer(self)
        self._batch_timer.setInterval(250)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._apply_batch)

    def set_records(self, records: list[TransferRecord]) -> None:
        """Replace all records and refresh the view."""
        self._pending_updates.clear()
        self._pending_inserts.clear()
        self._pending_inserts_idx.clear()
        self.beginResetModel()
        self._records = list(records)
        self._record_idx = {r.id: i for i, r in enumerate(self._records)}
        self.endResetModel()

    def update_record(self, record: TransferRecord) -> None:
        """Queue a single record update/insert."""
        # Is it in existing records?
        if record.id in self._record_idx:
            i = self._record_idx[record.id]
            self._pending_updates[i] = record
            self._batch_timer.start()
            return
            
        # Is it in pending inserts?
        if record.id in self._pending_inserts_idx:
            i = self._pending_inserts_idx[record.id]
            self._pending_inserts[i] = record
            self._batch_timer.start()
            return
                
        # Otherwise, it's a new insert
        self._pending_inserts_idx[record.id] = len(self._pending_inserts)
        self._pending_inserts.append(record)
        self._batch_timer.start()

    def _apply_batch(self):
        """Apply all queued updates and inserts in bulk."""
        if self._pending_updates:
            # Apply updates
            for i, r in self._pending_updates.items():
                self._records[i] = r
                self.dataChanged.emit(self.index(i, 0), self.index(i, len(_COLUMNS) - 1))
            self._pending_updates.clear()
            
        if self._pending_inserts:
            # Apply inserts in bulk
            start_idx = len(self._records)
            self.beginInsertRows(QModelIndex(), start_idx, start_idx + len(self._pending_inserts) - 1)
            for r in self._pending_inserts:
                self._record_idx[r.id] = len(self._records)
                self._records.append(r)
            self.endInsertRows()
            self._pending_inserts.clear()
            self._pending_inserts_idx.clear()

    def get_record(self, row: int) -> Optional[TransferRecord]:
        """Get the record at the given row."""
        if 0 <= row < len(self._records):
            return self._records[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._records)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(_COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        record = self._records[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(record, col)
        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 1:  # Status column
                color = _STATUS_COLORS.get(record.status, "#000000")
                return QBrush(QColor(color))
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 7 and record.error_message:  # Error column
                return record.error_message

        return None

    def _display_data(self, record: TransferRecord, col: int) -> str:
        if col == 0:
            return record.file_name
        elif col == 1:
            return record.status.value
        elif col == 2:
            return format_file_size(record.file_size)
        elif col == 3:
            return self._format_dt(record.detected_at)
        elif col == 4:
            if record.source_modified:
                return datetime.fromtimestamp(record.source_modified).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            return ""
        elif col == 5:
            return self._format_dt(record.transfer_completed)
        elif col == 6:
            if record.verification_passed is None:
                return ""
            return "✓ Passed" if record.verification_passed else "✗ Failed"
        elif col == 7:
            return record.error_message or ""
        return ""

    @staticmethod
    def _format_dt(dt: Optional[datetime]) -> str:
        if dt:
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        return ""


class TransferTableWidget(QWidget):
    """
    Complete table widget with filter controls and the transfer table view.
    """

    row_selected = Signal(int)  # row index
    force_start_requested = Signal(str) # record id

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._model = TransferTableModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterKeyColumn(1)  # Filter on Status column

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(BodyLabel("Filter by status:"))

        self._filter_combo = ComboBox()
        self._filter_combo.addItem("All Statuses", userData="")
        for status in FileStatus:
            self._filter_combo.addItem(status.value, userData=status.value)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_combo)
        filter_layout.addStretch()

        layout.addLayout(filter_layout)

        # Table view
        self._table = TableView()
        self._table.setModel(self._proxy)
        from PySide6.QtWidgets import QAbstractItemView
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        # Column widths
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # File Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Status
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Detected
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Modified
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Transfer
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Verify
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)  # Error

        self._table.clicked.connect(
            lambda idx: self.row_selected.emit(self._proxy.mapToSource(idx).row())
        )

        layout.addWidget(self._table)

    @property
    def model(self) -> TransferTableModel:
        return self._model

    def set_records(self, records: list[TransferRecord]) -> None:
        self._model.set_records(records)

    def update_record(self, record: TransferRecord) -> None:
        self._model.update_record(record)

    def _on_filter_changed(self, index: int) -> None:
        filter_text = self._filter_combo.currentData()
        if filter_text:
            self._proxy.setFilterFixedString(filter_text)
        else:
            self._proxy.setFilterFixedString("")

    def _on_context_menu(self, pos) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
            
        source_idx = self._proxy.mapToSource(idx)
        record = self._model.get_record(source_idx.row())
        
        if record and record.status == FileStatus.WAITING_FOR_WINDOW:
            menu = QMenu(self)
            force_action = menu.addAction("Force Start Transfer")
            action = menu.exec(self._table.viewport().mapToGlobal(pos))
            if action == force_action:
                self.force_start_requested.emit(record.id)

