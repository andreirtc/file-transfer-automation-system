"""
Dialog windows for the File Transfer Automation System.

Provides:
- ProcessingWarningDialog: shown when sync requested with processing files
- ConflictDialog: shown when destination file conflicts
- LogViewerDialog: read-only log file viewer
- SettingsDialog: edit configuration values
- TransferHistoryDialog: browse past transfer records
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.models import ConflictResolution, FileStatus, SyncAction, TransferRecord
from services.configuration_service import ConfigurationService
from services.logging_service import get_log_file_paths


class ProcessingWarningDialog(QDialog):
    """
    Warning dialog shown when the user requests sync but files are still processing.
    Offers three choices: Transfer Ready, Wait, or Cancel.
    """

    def __init__(
        self,
        processing_files: list[TransferRecord],
        ready_count: int,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Transfer Warning")
        self.setMinimumWidth(500)
        self.result_action: SyncAction = SyncAction.CANCEL

        layout = QVBoxLayout(self)

        # Warning message
        msg = QLabel(
            f"<b>{len(processing_files)} file(s) are still being processed:</b>"
        )
        layout.addWidget(msg)

        # List processing files
        for record in processing_files[:10]:
            detail = QLabel(f"  • {record.file_name} — Status: {record.status.value}")
            detail.setStyleSheet("color: #FFB74D; padding-left: 16px;")
            layout.addWidget(detail)

        if len(processing_files) > 10:
            layout.addWidget(
                QLabel(f"  ... and {len(processing_files) - 10} more")
            )

        layout.addSpacing(16)

        if ready_count > 0:
            ready_msg = QLabel(
                f"<b>{ready_count} file(s) are ready to transfer.</b>"
            )
            layout.addWidget(ready_msg)

        layout.addWidget(QLabel("What would you like to do?"))
        layout.addSpacing(8)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_transfer = QPushButton(f"Transfer Ready Files ({ready_count})")
        btn_transfer.setEnabled(ready_count > 0)
        btn_transfer.clicked.connect(self._on_transfer_ready)
        btn_layout.addWidget(btn_transfer)

        btn_wait = QPushButton("Wait for All Files")
        btn_wait.clicked.connect(self._on_wait)
        btn_layout.addWidget(btn_wait)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def _on_transfer_ready(self):
        self.result_action = SyncAction.TRANSFER_READY
        self.accept()

    def _on_wait(self):
        self.result_action = SyncAction.WAIT_ALL
        self.accept()

    def _on_cancel(self):
        self.result_action = SyncAction.CANCEL
        self.reject()


class ConflictDialog(QDialog):
    """
    Dialog shown when a destination file conflicts with the source.
    Offers Overwrite, Skip, or Cancel.
    """

    def __init__(
        self,
        record: TransferRecord,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Destination Conflict")
        self.setMinimumWidth(450)
        self.result_resolution: ConflictResolution = ConflictResolution.CANCEL

        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(f"<b>{record.file_name}</b> already exists in the destination "
                   f"but its contents differ from the source.")
        )
        layout.addSpacing(8)

        info = QGroupBox("Details")
        info_layout = QFormLayout()
        info_layout.addRow("Source:", QLabel(record.source_path))
        info_layout.addRow("Destination:", QLabel(record.destination_path))
        info.setLayout(info_layout)
        layout.addWidget(info)

        layout.addSpacing(16)

        btn_layout = QHBoxLayout()

        btn_overwrite = QPushButton("Overwrite")
        btn_overwrite.setStyleSheet("background-color: #E65100; color: white;")
        btn_overwrite.clicked.connect(self._on_overwrite)
        btn_layout.addWidget(btn_overwrite)

        btn_skip = QPushButton("Skip")
        btn_skip.clicked.connect(self._on_skip)
        btn_layout.addWidget(btn_skip)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(btn_cancel)

        layout.addLayout(btn_layout)

    def _on_overwrite(self):
        self.result_resolution = ConflictResolution.OVERWRITE
        self.accept()

    def _on_skip(self):
        self.result_resolution = ConflictResolution.SKIP
        self.accept()

    def _on_cancel(self):
        self.result_resolution = ConflictResolution.CANCEL
        self.reject()


class LogViewerDialog(QDialog):
    """Read-only viewer for application log files."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Log Viewer")
        self.resize(800, 600)

        layout = QVBoxLayout(self)

        # Log file selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Log file:"))
        self._log_combo = QComboBox()
        self._log_paths = get_log_file_paths()
        for name in self._log_paths:
            self._log_combo.addItem(name)
        self._log_combo.currentTextChanged.connect(self._load_log)
        selector_layout.addWidget(self._log_combo)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh)
        selector_layout.addWidget(btn_refresh)

        layout.addLayout(selector_layout)

        # Log content
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(self._text.font())
        font = self._text.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        self._text.setFont(font)
        layout.addWidget(self._text)

        # Load first log
        if self._log_combo.count() > 0:
            self._load_log(self._log_combo.currentText())

    def _load_log(self, name: str) -> None:
        path = self._log_paths.get(name)
        if path and path.exists():
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                self._text.setPlainText(content)
                # Scroll to bottom
                scrollbar = self._text.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            except OSError:
                self._text.setPlainText(f"Could not read {path}")
        else:
            self._text.setPlainText("Log file not found or empty.")

    def _refresh(self) -> None:
        self._load_log(self._log_combo.currentText())


class SettingsDialog(QDialog):
    """Dialog for editing application configuration."""

    def __init__(
        self,
        config: ConfigurationService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self._config = config

        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Stability check interval
        self._stability_interval = QSpinBox()
        self._stability_interval.setRange(1, 120)
        self._stability_interval.setSuffix(" seconds")
        self._stability_interval.setValue(config.stability_check_interval)
        form.addRow("Stability check interval:", self._stability_interval)

        # Required stable checks
        self._stable_checks = QSpinBox()
        self._stable_checks.setRange(1, 20)
        self._stable_checks.setValue(config.required_stable_checks)
        form.addRow("Required stable checks:", self._stable_checks)

        # Max retries
        self._max_retries = QSpinBox()
        self._max_retries.setRange(0, 50)
        self._max_retries.setValue(config.max_retries)
        form.addRow("Max retries:", self._max_retries)

        # Retry delay
        self._retry_delay = QSpinBox()
        self._retry_delay.setRange(1, 600)
        self._retry_delay.setSuffix(" seconds")
        self._retry_delay.setValue(config.retry_delay)
        form.addRow("Retry delay:", self._retry_delay)

        # Reconciliation interval
        self._recon_interval = QSpinBox()
        self._recon_interval.setRange(5, 600)
        self._recon_interval.setSuffix(" seconds")
        self._recon_interval.setValue(config.reconciliation_interval)
        form.addRow("Reconciliation interval:", self._recon_interval)

        # Overwrite policy
        self._overwrite_policy = QComboBox()
        self._overwrite_policy.addItem("Ask (show dialog)", "ask")
        self._overwrite_policy.addItem("Always overwrite", "overwrite")
        self._overwrite_policy.addItem("Always skip", "skip")
        current_policy = config.overwrite_policy
        for i in range(self._overwrite_policy.count()):
            if self._overwrite_policy.itemData(i) == current_policy:
                self._overwrite_policy.setCurrentIndex(i)
                break
        form.addRow("Overwrite policy:", self._overwrite_policy)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self._config.set("stability_check_interval", self._stability_interval.value())
        self._config.set("required_stable_checks", self._stable_checks.value())
        self._config.set("max_retries", self._max_retries.value())
        self._config.set("retry_delay", self._retry_delay.value())
        self._config.set("reconciliation_interval", self._recon_interval.value())
        self._config.set("overwrite_policy", self._overwrite_policy.currentData())
        self._config.save()
        self.accept()


class TransferHistoryDialog(QDialog):
    """Dialog for browsing past transfer records."""

    def __init__(
        self,
        records: list[TransferRecord],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Transfer History")
        self.resize(900, 500)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"<b>{len(records)} records</b>"))

        table = QTableWidget()
        headers = ["File Name", "Status", "Size", "Transfer Time", "Hash", "Error"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(records))
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, record in enumerate(records):
            table.setItem(row, 0, QTableWidgetItem(record.file_name))
            table.setItem(row, 1, QTableWidgetItem(record.status.value))
            table.setItem(row, 2, QTableWidgetItem(record.display_size))
            table.setItem(
                row,
                3,
                QTableWidgetItem(
                    record.transfer_completed.strftime("%Y-%m-%d %H:%M:%S")
                    if record.transfer_completed
                    else ""
                ),
            )
            table.setItem(
                row, 4, QTableWidgetItem((record.source_hash or "")[:16])
            )
            table.setItem(row, 5, QTableWidgetItem(record.error_message or ""))

        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
