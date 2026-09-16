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
    QTableWidgetItem,
    QFrame
)

from qfluentwidgets import (
    MessageBoxBase,
    MessageBox,
    PushButton,
    PrimaryPushButton,
    SubtitleLabel,
    BodyLabel,
    StrongBodyLabel,
    SpinBox,
    ComboBox,
    TableWidget,
    PlainTextEdit,
    SimpleCardWidget,
    SwitchButton,
    LineEdit,
    PasswordLineEdit,
    ScrollArea
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
        self.viewLayout.addSpacing(6)
        
        self.widget.setMinimumWidth(640)
        self.widget.setMaximumWidth(700)

        # Scroll container to prevent vertical squishing
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("border: none; background: transparent;")
        scroll.setMinimumHeight(460)
        scroll.setMaximumHeight(540)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(4, 4, 16, 4)
        content_layout.setSpacing(14)

        def make_section(title_text: str) -> QFormLayout:
            hdr = StrongBodyLabel(title_text, container)
            hdr.setStyleSheet("color: #0078D4; font-size: 13px; font-weight: 600; margin-top: 4px;")
            content_layout.addWidget(hdr)
            f = QFormLayout()
            f.setContentsMargins(8, 2, 8, 2)
            f.setVerticalSpacing(8)
            f.setHorizontalSpacing(16)
            content_layout.addLayout(f)
            return f

        # Section 1: Transfer Mode & Operational Cycle
        f_transfer = make_section("Transfer Protocol & Operational Cycle")

        self._transfer_mode = ComboBox(container)
        self._transfer_mode.addItem("Direct Stream (Raw 1:1, Robocopy-style)", userData="direct")
        self._transfer_mode.addItem("Batch ZIP Archive", userData="zip")
        self._transfer_mode.setMinimumHeight(32)
        curr_mode = getattr(config, "transfer_mode", "direct")
        for i in range(self._transfer_mode.count()):
            if self._transfer_mode.itemData(i) == curr_mode:
                self._transfer_mode.setCurrentIndex(i)
                break
        f_transfer.addRow(BodyLabel("Transfer Mode:", container), self._transfer_mode)

        self._cycle_start = LineEdit(container)
        self._cycle_start.setPlaceholderText("18:00")
        self._cycle_start.setText(getattr(config, "operational_cycle_start", "18:00"))
        self._cycle_start.setMinimumHeight(32)
        f_transfer.addRow(BodyLabel("Operational Cycle Start:", container), self._cycle_start)

        self._cycle_end = LineEdit(container)
        self._cycle_end.setPlaceholderText("12:00")
        self._cycle_end.setText(getattr(config, "operational_cycle_end", "12:00"))
        self._cycle_end.setMinimumHeight(32)
        f_transfer.addRow(BodyLabel("Operational Cycle Cut-Off:", container), self._cycle_end)

        self._smart_verification = SwitchButton("Smart Verification", container)
        self._smart_verification.setOnText("Enabled (Exact size + 24MB block SHA-256 for >2GB)")
        self._smart_verification.setOffText("Disabled (Full Hash Pass)")
        self._smart_verification.setChecked(getattr(config, "smart_verification_enabled", True))
        f_transfer.addRow(BodyLabel("Verification Mode:", container), self._smart_verification)

        self._max_concurrent = ComboBox(container)
        self._max_concurrent.addItem("1 (Strictly Sequential)", userData=1)
        self._max_concurrent.addItem("2 Jobs at once", userData=2)
        self._max_concurrent.addItem("3 Jobs at once", userData=3)
        self._max_concurrent.addItem("4 Jobs at once", userData=4)
        self._max_concurrent.addItem("5 Jobs at once", userData=5)
        self._max_concurrent.addItem("All at once (Unlimited)", userData=0)
        self._max_concurrent.setMinimumHeight(32)
        curr_conc = config.max_concurrent_transfers
        for i in range(self._max_concurrent.count()):
            if self._max_concurrent.itemData(i) == curr_conc:
                self._max_concurrent.setCurrentIndex(i)
                break
        f_transfer.addRow(BodyLabel("Max Concurrent Jobs:", container), self._max_concurrent)

        self._transfer_threads = ComboBox(container)
        self._transfer_threads.addItem("1 (Single Thread)", userData=1)
        self._transfer_threads.addItem("2 Threads", userData=2)
        self._transfer_threads.addItem("4 Threads (Recommended)", userData=4)
        self._transfer_threads.addItem("8 Threads (Fast Network)", userData=8)
        self._transfer_threads.addItem("16 Threads (High-Performance)", userData=16)
        self._transfer_threads.addItem("32 Threads (Server)", userData=32)
        self._transfer_threads.addItem("64 Threads (Enterprise Server)", userData=64)
        self._transfer_threads.addItem("128 Threads (Max Robocopy Limit)", userData=128)
        self._transfer_threads.setMinimumHeight(32)
        curr_threads = config.transfer_threads
        for i in range(self._transfer_threads.count()):
            if self._transfer_threads.itemData(i) == curr_threads:
                self._transfer_threads.setCurrentIndex(i)
                break
        f_transfer.addRow(BodyLabel("Transfer Threads (/MT):", container), self._transfer_threads)

        # Section 2: File Stability & Locks
        f_stability = make_section("File Stability & Locking Checks")

        self._stability_interval = SpinBox(container)
        self._stability_interval.setRange(1, 120)
        self._stability_interval.setValue(config.stability_check_interval)
        self._stability_interval.setMinimumHeight(32)
        f_stability.addRow(BodyLabel("Stability check interval (sec):", container), self._stability_interval)

        self._stable_checks = SpinBox(container)
        self._stable_checks.setRange(1, 20)
        self._stable_checks.setValue(config.required_stable_checks)
        self._stable_checks.setMinimumHeight(32)
        f_stability.addRow(BodyLabel("Required stable checks:", container), self._stable_checks)

        self._max_retries = SpinBox(container)
        self._max_retries.setRange(0, 50)
        self._max_retries.setValue(config.max_retries)
        self._max_retries.setMinimumHeight(32)
        f_stability.addRow(BodyLabel("Max retries:", container), self._max_retries)

        self._retry_delay = SpinBox(container)
        self._retry_delay.setRange(1, 600)
        self._retry_delay.setValue(config.retry_delay)
        self._retry_delay.setMinimumHeight(32)
        f_stability.addRow(BodyLabel("Retry delay (sec):", container), self._retry_delay)

        self._recon_interval = SpinBox(container)
        self._recon_interval.setRange(5, 600)
        self._recon_interval.setValue(config.reconciliation_interval)
        self._recon_interval.setMinimumHeight(32)
        f_stability.addRow(BodyLabel("Reconciliation interval (sec):", container), self._recon_interval)

        self._overwrite_policy = ComboBox(container)
        self._overwrite_policy.addItem("Ask (show dialog)", userData="ask")
        self._overwrite_policy.addItem("Always overwrite", userData="overwrite")
        self._overwrite_policy.addItem("Always skip", userData="skip")
        self._overwrite_policy.setMinimumHeight(32)
        current_policy = config.overwrite_policy
        for i in range(self._overwrite_policy.count()):
            if self._overwrite_policy.itemData(i) == current_policy:
                self._overwrite_policy.setCurrentIndex(i)
                break
        f_stability.addRow(BodyLabel("Overwrite policy:", container), self._overwrite_policy)

        # Section 3: Network & Retention
        f_network = make_section("Network Drive & Source File Retention")

        self._network_mode = SwitchButton("Network Drive Mode", container)
        self._network_mode.setOnText("Enabled (Fast Polling)")
        self._network_mode.setOffText("Disabled")
        self._network_mode.setChecked(config.network_drive_mode)
        f_network.addRow(BodyLabel("Shared Network:", container), self._network_mode)

        self._auto_cleanup = SwitchButton("Auto Cleanup", container)
        self._auto_cleanup.setOnText("Enabled (Periodic deletion of transferred files)")
        self._auto_cleanup.setOffText("Disabled")
        self._auto_cleanup.setChecked(config.auto_cleanup_enabled)
        f_network.addRow(BodyLabel("Source Cleanup:", container), self._auto_cleanup)

        self._auto_cleanup_days = SpinBox(container)
        self._auto_cleanup_days.setRange(1, 365)
        self._auto_cleanup_days.setValue(config.auto_cleanup_days)
        self._auto_cleanup_days.setMinimumHeight(32)
        f_network.addRow(BodyLabel("Cleanup Retention (Days):", container), self._auto_cleanup_days)

        # Section 4: Compression & Encryption
        f_zip = make_section("ZIP Compression & Encryption (Archive Mode Only)")

        self._batch_compression = SwitchButton("Batch Compression", container)
        self._batch_compression.setOnText("Enabled (Zip queued files together)")
        self._batch_compression.setOffText("Disabled")
        self._batch_compression.setChecked(config.batch_compression_enabled)
        f_zip.addRow(BodyLabel("Compression:", container), self._batch_compression)

        self._zip_password = PasswordLineEdit(container)
        self._zip_password.setText(config.zip_password)
        self._zip_password.setMinimumHeight(32)
        f_zip.addRow(BodyLabel("Zip Password:", container), self._zip_password)

        scroll.setWidget(container)
        self.viewLayout.addWidget(scroll)

    def validate(self) -> bool:
        self._config.set("stability_check_interval", self._stability_interval.value())
        self._config.set("required_stable_checks", self._stable_checks.value())
        self._config.set("max_retries", self._max_retries.value())
        self._config.set("retry_delay", self._retry_delay.value())
        self._config.set("reconciliation_interval", self._recon_interval.value())
        self._config.set("overwrite_policy", self._overwrite_policy.currentData())
        self._config.set("network_drive_mode", self._network_mode.isChecked())
        self._config.set("auto_cleanup_enabled", self._auto_cleanup.isChecked())
        self._config.set("auto_cleanup_days", self._auto_cleanup_days.value())
        self._config.set("batch_compression_enabled", self._batch_compression.isChecked())
        self._config.set("zip_password", self._zip_password.text())
        self._config.set("transfer_mode", self._transfer_mode.currentData())
        self._config.set("operational_cycle_start", self._cycle_start.text().strip() or "18:00")
        self._config.set("operational_cycle_end", self._cycle_end.text().strip() or "12:00")
        self._config.set("smart_verification_enabled", self._smart_verification.isChecked())
        self._config.set("max_concurrent_transfers", self._max_concurrent.currentData())
        self._config.set("transfer_threads", self._transfer_threads.currentData())
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
