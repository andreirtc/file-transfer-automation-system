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
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QTableWidgetItem
)

from qfluentwidgets import (
    MessageBoxBase,
    MessageBox,
    PushButton,
    PrimaryPushButton,
    SubtitleLabel,
    BodyLabel,
    SpinBox,
    ComboBox,
    TableWidget,
    PlainTextEdit,
    SimpleCardWidget
)

from core.models import ConflictResolution, FileStatus, SyncAction, TransferRecord
from services.configuration_service import ConfigurationService
from services.logging_service import get_log_file_paths


class ProcessingWarningDialog(MessageBoxBase):
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
        self.result_action: SyncAction = SyncAction.CANCEL
        
        self.yesButton.hide()
        self.cancelButton.hide()
        
        self.titleLabel = SubtitleLabel("Transfer Warning", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)

        self.widget.setMinimumWidth(500)

        # Warning message
        msg = BodyLabel(f"<b>{len(processing_files)} file(s) are still being processed:</b>", self)
        self.viewLayout.addWidget(msg)

        # List processing files
        for record in processing_files[:10]:
            detail = BodyLabel(f"  • {record.file_name} — Status: {record.status.value}", self)
            detail.setStyleSheet("color: #D83B01; padding-left: 16px;")
            self.viewLayout.addWidget(detail)

        if len(processing_files) > 10:
            self.viewLayout.addWidget(BodyLabel(f"  ... and {len(processing_files) - 10} more", self))

        self.viewLayout.addSpacing(16)

        if ready_count > 0:
            ready_msg = BodyLabel(f"<b>{ready_count} file(s) are ready to transfer.</b>", self)
            self.viewLayout.addWidget(ready_msg)

        self.viewLayout.addWidget(BodyLabel("What would you like to do?", self))
        self.viewLayout.addSpacing(16)

        # Buttons
        btn_layout = QHBoxLayout()

        btn_transfer = PrimaryPushButton(f"Transfer Ready Files ({ready_count})", self)
        btn_transfer.setEnabled(ready_count > 0)
        btn_transfer.clicked.connect(self._on_transfer_ready)
        btn_layout.addWidget(btn_transfer)

        btn_wait = PushButton("Wait for All Files", self)
        btn_wait.clicked.connect(self._on_wait)
        btn_layout.addWidget(btn_wait)

        btn_cancel = PushButton("Cancel", self)
        btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(btn_cancel)

        self.viewLayout.addLayout(btn_layout)

    def _on_transfer_ready(self):
        self.result_action = SyncAction.TRANSFER_READY
        self.accept()

    def _on_wait(self):
        self.result_action = SyncAction.WAIT_ALL
        self.accept()

    def _on_cancel(self):
        self.result_action = SyncAction.CANCEL
        self.reject()


class ConflictDialog(MessageBoxBase):
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
        self.result_resolution: ConflictResolution = ConflictResolution.CANCEL
        
        self.yesButton.hide()
        self.cancelButton.hide()

        self.titleLabel = SubtitleLabel("Destination Conflict", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        self.widget.setMinimumWidth(450)

        self.viewLayout.addWidget(
            BodyLabel(f"<b>{record.file_name}</b> already exists in the destination "
                   f"but its contents differ from the source.", self)
        )
        self.viewLayout.addSpacing(8)

        info = SimpleCardWidget(self)
        info_layout = QFormLayout(info)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.addRow(BodyLabel("Source:", info), BodyLabel(record.source_path, info))
        info_layout.addRow(BodyLabel("Destination:", info), BodyLabel(record.destination_path, info))
        self.viewLayout.addWidget(info)

        self.viewLayout.addSpacing(16)

        btn_layout = QHBoxLayout()

        btn_overwrite = PrimaryPushButton("Overwrite", self)
        btn_overwrite.setStyleSheet("background-color: #C42B1C;")
        btn_overwrite.clicked.connect(self._on_overwrite)
        btn_layout.addWidget(btn_overwrite)

        btn_skip = PushButton("Skip", self)
        btn_skip.clicked.connect(self._on_skip)
        btn_layout.addWidget(btn_skip)

        btn_cancel = PushButton("Cancel", self)
        btn_cancel.clicked.connect(self._on_cancel)
        btn_layout.addWidget(btn_cancel)

        self.viewLayout.addLayout(btn_layout)

    def _on_overwrite(self):
        self.result_resolution = ConflictResolution.OVERWRITE
        self.accept()

    def _on_skip(self):
        self.result_resolution = ConflictResolution.SKIP
        self.accept()

    def _on_cancel(self):
        self.result_resolution = ConflictResolution.CANCEL
        self.reject()


class LogViewerDialog(MessageBoxBase):
    """Read-only viewer for application log files."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        self.yesButton.setText("Close")
        self.cancelButton.hide()

        self.titleLabel = SubtitleLabel("Log Viewer", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        self.widget.setMinimumWidth(800)
        self.widget.setMinimumHeight(600)

        # Log file selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(BodyLabel("Log file:", self))
        
        self._log_combo = ComboBox(self)
        self._log_paths = get_log_file_paths()
        for name in self._log_paths:
            self._log_combo.addItem(name)
        self._log_combo.currentTextChanged.connect(self._load_log)
        selector_layout.addWidget(self._log_combo)

        btn_refresh = PushButton("Refresh", self)
        btn_refresh.clicked.connect(self._refresh)
        selector_layout.addWidget(btn_refresh)

        self.viewLayout.addLayout(selector_layout)

        # Log content
        self._text = PlainTextEdit(self)
        self._text.setReadOnly(True)
        font = self._text.font()
        font.setFamily("Consolas")
        font.setPointSize(9)
        self._text.setFont(font)
        self.viewLayout.addWidget(self._text)

        # Load first log
        if len(self._log_paths) > 0:
            first_key = list(self._log_paths.keys())[0]
            self._load_log(first_key)

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


class SettingsDialog(MessageBoxBase):
    """Dialog for editing application configuration."""

    def __init__(
        self,
        config: ConfigurationService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._config = config
        
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")

        self.titleLabel = SubtitleLabel("Settings", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        self.widget.setMinimumWidth(450)

        form = QFormLayout()

        # Stability check interval
        self._stability_interval = SpinBox(self)
        self._stability_interval.setRange(1, 120)
        self._stability_interval.setValue(config.stability_check_interval)
        form.addRow(BodyLabel("Stability check interval (sec):", self), self._stability_interval)

        # Required stable checks
        self._stable_checks = SpinBox(self)
        self._stable_checks.setRange(1, 20)
        self._stable_checks.setValue(config.required_stable_checks)
        form.addRow(BodyLabel("Required stable checks:", self), self._stable_checks)

        # Max retries
        self._max_retries = SpinBox(self)
        self._max_retries.setRange(0, 50)
        self._max_retries.setValue(config.max_retries)
        form.addRow(BodyLabel("Max retries:", self), self._max_retries)

        # Retry delay
        self._retry_delay = SpinBox(self)
        self._retry_delay.setRange(1, 600)
        self._retry_delay.setValue(config.retry_delay)
        form.addRow(BodyLabel("Retry delay (sec):", self), self._retry_delay)

        # Reconciliation interval
        self._recon_interval = SpinBox(self)
        self._recon_interval.setRange(5, 600)
        self._recon_interval.setValue(config.reconciliation_interval)
        form.addRow(BodyLabel("Reconciliation interval (sec):", self), self._recon_interval)

        # Overwrite policy
        self._overwrite_policy = ComboBox(self)
        self._overwrite_policy.addItem("Ask (show dialog)", userData="ask")
        self._overwrite_policy.addItem("Always overwrite", userData="overwrite")
        self._overwrite_policy.addItem("Always skip", userData="skip")
        current_policy = config.overwrite_policy
        for i in range(self._overwrite_policy.count()):
            if self._overwrite_policy.itemData(i) == current_policy:
                self._overwrite_policy.setCurrentIndex(i)
                break
        form.addRow(BodyLabel("Overwrite policy:", self), self._overwrite_policy)

        self.viewLayout.addLayout(form)

    def validate(self) -> bool:
        self._config.set("stability_check_interval", self._stability_interval.value())
        self._config.set("required_stable_checks", self._stable_checks.value())
        self._config.set("max_retries", self._max_retries.value())
        self._config.set("retry_delay", self._retry_delay.value())
        self._config.set("reconciliation_interval", self._recon_interval.value())
        self._config.set("overwrite_policy", self._overwrite_policy.currentData())
        self._config.save()
        return True


class TransferHistoryDialog(MessageBoxBase):
    """Dialog for browsing past transfer records."""

    def __init__(
        self,
        records: list[TransferRecord],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        
        self.yesButton.setText("Close")
        self.cancelButton.hide()

        self.titleLabel = SubtitleLabel("Transfer History", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        
        self.widget.setMinimumWidth(900)
        self.widget.setMinimumHeight(500)

        self.viewLayout.addWidget(BodyLabel(f"<b>{len(records)} records</b>", self))

        table = TableWidget(self)
        headers = ["File Name", "Status", "Size", "Transfer Time", "Hash", "Error"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(records))
        table.setAlternatingRowColors(True)

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
        self.viewLayout.addWidget(table)
