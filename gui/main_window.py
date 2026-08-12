"""
Main window for the File Transfer Automation System.

The top-level QMainWindow that contains:
- Menu bar (File, Jobs, View, Help)
- Toolbar with quick actions
- Dashboard as the central widget
- Status bar showing monitoring state and last activity

Coordinates all GUI components with the TransferManager backend.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from core.models import (
    ConflictResolution,
    FileStatus,
    SyncAction,
    TransferJob,
    TransferRecord,
    TransferResult,
)
from core.transfer_manager import TransferManager
from gui.dashboard import DashboardWidget
from gui.dialogs import (
    ConflictDialog,
    LogViewerDialog,
    ProcessingWarningDialog,
    SettingsDialog,
    TransferHistoryDialog,
)
from gui.job_dialog import JobDialog
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService

logger = logging.getLogger("app")


class MainWindow(QMainWindow):
    """
    Main application window.

    Connects the DashboardWidget (GUI) with the TransferManager (backend).
    """

    def __init__(
        self,
        config: ConfigurationService,
        db: DatabaseService,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._db = db

        # Create the transfer manager
        self._manager = TransferManager(config, db, self)

        # Setup UI
        self.setWindowTitle("File Transfer Automation System")
        self.resize(1200, 800)

        self._dashboard = DashboardWidget(self)
        self.setCentralWidget(self._dashboard)

        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_status_bar()
        self._connect_signals()

        # Load existing job on startup
        self._load_initial_job()

    # ──────────────────────────────────────────────
    # Menu bar
    # ──────────────────────────────────────────────

    def _setup_menu_bar(self):
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&File")
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Jobs menu
        jobs_menu = menu_bar.addMenu("&Jobs")
        add_job_action = QAction("&Add Transfer Job...", self)
        add_job_action.setShortcut("Ctrl+N")
        add_job_action.triggered.connect(self._on_add_job)
        jobs_menu.addAction(add_job_action)

        edit_job_action = QAction("&Edit Current Job...", self)
        edit_job_action.triggered.connect(self._on_edit_job)
        jobs_menu.addAction(edit_job_action)

        # View menu
        view_menu = menu_bar.addMenu("&View")

        logs_action = QAction("View &Logs...", self)
        logs_action.setShortcut("Ctrl+L")
        logs_action.triggered.connect(self._on_view_logs)
        view_menu.addAction(logs_action)

        history_action = QAction("Transfer &History...", self)
        history_action.setShortcut("Ctrl+H")
        history_action.triggered.connect(self._on_view_history)
        view_menu.addAction(history_action)

        view_menu.addSeparator()

        settings_action = QAction("&Settings...", self)
        settings_action.triggered.connect(self._on_settings)
        view_menu.addAction(settings_action)

        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    # ──────────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────────

    def _setup_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._start_action = QAction("▶ Start Monitoring", self)
        self._start_action.triggered.connect(self._on_start_monitoring)
        toolbar.addAction(self._start_action)

        self._stop_action = QAction("■ Stop Monitoring", self)
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._on_stop_monitoring)
        toolbar.addAction(self._stop_action)

        toolbar.addSeparator()

        self._sync_action = QAction("🔄 SYNC NOW", self)
        self._sync_action.triggered.connect(self._on_sync_now)
        toolbar.addAction(self._sync_action)

        toolbar.addSeparator()

        add_job_action = QAction("+ Add Job", self)
        add_job_action.triggered.connect(self._on_add_job)
        toolbar.addAction(add_job_action)

        settings_action = QAction("⚙ Settings", self)
        settings_action.triggered.connect(self._on_settings)
        toolbar.addAction(settings_action)

        logs_action = QAction("📋 Logs", self)
        logs_action.triggered.connect(self._on_view_logs)
        toolbar.addAction(logs_action)

    # ──────────────────────────────────────────────
    # Status bar
    # ──────────────────────────────────────────────

    def _setup_status_bar(self):
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._status_label = QStatusBar()
        self._status_bar.showMessage("Ready")

    # ──────────────────────────────────────────────
    # Signal connections
    # ──────────────────────────────────────────────

    def _connect_signals(self):
        # Dashboard → actions
        self._dashboard.start_monitoring_requested.connect(self._on_start_monitoring)
        self._dashboard.stop_monitoring_requested.connect(self._on_stop_monitoring)
        self._dashboard.sync_now_requested.connect(self._on_sync_now)

        # Manager → dashboard
        self._manager.file_detected.connect(self._on_file_detected)
        self._manager.file_status_changed.connect(self._on_file_status_changed)
        self._manager.transfer_completed.connect(self._on_transfer_completed)
        self._manager.stats_updated.connect(self._dashboard.update_statistics)
        self._manager.monitoring_changed.connect(self._on_monitoring_changed)
        self._manager.conflict_detected.connect(self._on_conflict_detected)
        self._manager.log_message.connect(self._on_log_message)

    # ──────────────────────────────────────────────
    # Initial setup
    # ──────────────────────────────────────────────

    def _load_initial_job(self):
        """Load the first available job, or prompt to create one."""
        jobs = self._db.get_jobs()
        if jobs:
            job = jobs[0]
            self._manager.set_job(job)
            self._dashboard.update_job_info(job)

            # Load active records into the table
            records = self._manager.get_all_records()
            self._dashboard.set_records(records)

            logger.info("Loaded job: '%s'", job.name)

            # Auto-start monitoring if configured
            if job.auto_monitor and self._config.automatic_monitoring:
                QTimer.singleShot(500, self._on_start_monitoring)
        else:
            logger.info("No jobs found — prompting user to create one")

    # ──────────────────────────────────────────────
    # Action handlers
    # ──────────────────────────────────────────────

    def _on_add_job(self):
        dialog = JobDialog(parent=self)
        if dialog.exec() == JobDialog.DialogCode.Accepted:
            job = dialog.job
            self._db.save_job(job)
            self._manager.set_job(job)
            self._dashboard.update_job_info(job)
            self._dashboard.set_records([])
            logger.info("Created new job: '%s'", job.name)
            self._status_bar.showMessage(f"Job '{job.name}' created", 5000)

    def _on_edit_job(self):
        job = self._manager.current_job
        if not job:
            QMessageBox.information(self, "No Job", "No job is currently active.")
            return

        was_monitoring = self._manager.is_monitoring
        if was_monitoring:
            self._manager.stop_monitoring()

        dialog = JobDialog(job=job, parent=self)
        if dialog.exec() == JobDialog.DialogCode.Accepted:
            updated_job = dialog.job
            self._db.save_job(updated_job)
            self._manager.set_job(updated_job)
            self._dashboard.update_job_info(updated_job)
            logger.info("Updated job: '%s'", updated_job.name)

            if was_monitoring:
                self._on_start_monitoring()

    def _on_start_monitoring(self):
        if not self._manager.current_job:
            QMessageBox.warning(
                self,
                "No Job",
                "Please create a transfer job first.",
            )
            return
        self._manager.start_monitoring()

    def _on_stop_monitoring(self):
        self._manager.stop_monitoring()

    def _on_sync_now(self):
        if not self._manager.current_job:
            QMessageBox.warning(self, "No Job", "Please create a transfer job first.")
            return

        self._status_bar.showMessage("Scanning source folder...")

        ready, processing = self._manager.sync_now()

        # Refresh table with current records
        self._dashboard.set_records(self._manager.get_all_records())

        if processing:
            dialog = ProcessingWarningDialog(
                processing_files=processing,
                ready_count=len(ready),
                parent=self,
            )
            dialog.exec()
            action = dialog.result_action

            if action == SyncAction.TRANSFER_READY:
                count = self._manager.transfer_ready_files()
                self._status_bar.showMessage(
                    f"Queued {count} file(s) for transfer", 5000
                )
            elif action == SyncAction.WAIT_ALL:
                self._status_bar.showMessage(
                    "Waiting for all files to become ready...", 5000
                )
            else:
                self._status_bar.showMessage("Sync cancelled", 3000)
        elif ready:
            count = self._manager.transfer_ready_files()
            self._status_bar.showMessage(
                f"Queued {count} file(s) for transfer", 5000
            )
        else:
            self._status_bar.showMessage("No new files to transfer", 5000)

    def _on_settings(self):
        dialog = SettingsDialog(self._config, self)
        dialog.exec()

    def _on_view_logs(self):
        dialog = LogViewerDialog(self)
        dialog.exec()

    def _on_view_history(self):
        records = self._manager.get_history()
        dialog = TransferHistoryDialog(records, self)
        dialog.exec()

    def _on_about(self):
        QMessageBox.about(
            self,
            "About File Transfer Automation System",
            "<h3>File Transfer Automation System</h3>"
            "<p>Version 1.0.0 — Local Prototype</p>"
            "<p>Automated one-way file transfer with:</p>"
            "<ul>"
            "<li>File safety detection (incomplete file protection)</li>"
            "<li>SHA-256 integrity verification</li>"
            "<li>Persistent transfer history</li>"
            "<li>Automatic and manual sync modes</li>"
            "</ul>"
            "<p>Files are always <b>copied</b>, never moved.</p>"
            "<p>Source files are never modified or deleted.</p>",
        )

    # ──────────────────────────────────────────────
    # Manager signal handlers
    # ──────────────────────────────────────────────

    def _on_file_detected(self, file_path: str, record: TransferRecord):
        self._dashboard.update_record(record)

    def _on_file_status_changed(self, record_id: str, status: FileStatus):
        # Find record and update the table
        record = self._manager._find_record_by_id(record_id)
        if record:
            self._dashboard.update_record(record)

    def _on_transfer_completed(self, record_id: str, result: TransferResult):
        record = self._manager._find_record_by_id(record_id)
        if record:
            self._dashboard.update_record(record)
            if result.success:
                self._status_bar.showMessage(
                    f"✓ Transferred: {record.file_name}", 5000
                )
            else:
                self._status_bar.showMessage(
                    f"✗ Failed: {record.file_name} — {result.error_message}",
                    10000,
                )

    def _on_monitoring_changed(self, is_monitoring: bool):
        self._dashboard.update_monitoring_status(is_monitoring)
        self._start_action.setEnabled(not is_monitoring)
        self._stop_action.setEnabled(is_monitoring)
        if is_monitoring:
            self._status_bar.showMessage("Monitoring active", 3000)
        else:
            self._status_bar.showMessage("Monitoring stopped", 3000)

    def _on_conflict_detected(self, record: TransferRecord):
        dialog = ConflictDialog(record, self)
        dialog.exec()
        resolution = dialog.result_resolution
        self._manager.resolve_conflict(record.id, resolution)

    def _on_log_message(self, level: str, message: str):
        self._status_bar.showMessage(message, 5000)

    # ──────────────────────────────────────────────
    # Window lifecycle
    # ──────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        """Clean shutdown when the window is closed."""
        self._manager.shutdown()
        logger.info("Application closing")
        event.accept()
