"""
Main window for the File Transfer Automation System.

The top-level MSFluentWindow that contains:
- Left navigation bar
- Dashboard as the central widget
- Status messages
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import QApplication

from qfluentwidgets import (
    MSFluentWindow,
    NavigationItemPosition,
    FluentIcon,
    MessageBox,
    InfoBar,
    InfoBarPosition,
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


class MainWindow(MSFluentWindow):
    """
    Main application window using Fluent Design.

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

        # Remove the default title bar text if desired, or keep it.
        # self.titleBar.titleLabel.hide()

        self._dashboard = DashboardWidget(self)
        self._dashboard.setObjectName("DashboardInterface")

        self._setup_navigation()
        self._connect_signals()

        # Load existing job on startup
        self._load_initial_job()

    # ──────────────────────────────────────────────
    # Navigation Interface
    # ──────────────────────────────────────────────

    def _setup_navigation(self):
        # Add the main dashboard
        self.addSubInterface(
            self._dashboard,
            FluentIcon.HOME,
            "Dashboard",
            position=NavigationItemPosition.TOP
        )

        # Add Job Actions
        self.navigationInterface.addItem(
            routeKey="addJob",
            icon=FluentIcon.ADD,
            text="Add Job",
            onClick=self._on_add_job,
            position=NavigationItemPosition.SCROLL
        )
        
        self.navigationInterface.addItem(
            routeKey="editJob",
            icon=FluentIcon.EDIT,
            text="Edit Job",
            onClick=self._on_edit_job,
            position=NavigationItemPosition.SCROLL
        )

        self.navigationInterface.addItem(
            routeKey="history",
            icon=FluentIcon.HISTORY,
            text="Transfer History",
            onClick=self._on_view_history,
            position=NavigationItemPosition.SCROLL
        )

        # Bottom Actions
        self.navigationInterface.addItem(
            routeKey="logs",
            icon=FluentIcon.DOCUMENT,
            text="View Logs",
            onClick=self._on_view_logs,
            position=NavigationItemPosition.BOTTOM
        )

        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="Settings",
            onClick=self._on_settings,
            position=NavigationItemPosition.BOTTOM
        )
        
        self.navigationInterface.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text="About",
            onClick=self._on_about,
            position=NavigationItemPosition.BOTTOM
        )

    # ──────────────────────────────────────────────
    # Signal connections
    # ──────────────────────────────────────────────

    def _connect_signals(self):
        # Dashboard → actions
        self._dashboard.start_monitoring_requested.connect(self._on_start_monitoring)
        self._dashboard.stop_monitoring_requested.connect(self._on_stop_monitoring)
        self._dashboard.sync_now_requested.connect(self._on_sync_now)
        self._dashboard.force_start_requested.connect(self._manager.force_start)
        self._dashboard.job_switched.connect(self._on_job_switched)

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
            self._dashboard.update_job_list(jobs, job.id)
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
            
            jobs = self._db.get_jobs()
            self._dashboard.update_job_list(jobs, job.id)
            
            self._manager.set_job(job)
            self._dashboard.update_job_info(job)
            self._dashboard.set_records([])
            logger.info("Created new job: '%s'", job.name)
            self._on_log_message("INFO", f"Job '{job.name}' created")

    def _on_edit_job(self):
        job = self._manager.current_job
        if not job:
            msg = MessageBox("No Job", "No job is currently active.", self)
            msg.exec()
            return

        was_monitoring = self._manager.is_monitoring
        if was_monitoring:
            self._manager.stop_monitoring()

        dialog = JobDialog(job=job, parent=self)
        if dialog.exec() == JobDialog.DialogCode.Accepted:
            updated_job = dialog.job
            self._db.save_job(updated_job)
            
            jobs = self._db.get_jobs()
            self._dashboard.update_job_list(jobs, updated_job.id)
            
            self._manager.set_job(updated_job)
            self._dashboard.update_job_info(updated_job)
            logger.info("Updated job: '%s'", updated_job.name)

            if was_monitoring:
                self._on_start_monitoring()

    def _on_job_switched(self, job_id: str):
        """Handle when the user selects a different job from the dropdown."""
        jobs = self._db.get_jobs()
        job = next((j for j in jobs if j.id == job_id), None)
        if not job:
            return
            
        was_monitoring = self._manager.is_monitoring
        if was_monitoring:
            self._manager.stop_monitoring()
            
        self._manager.set_job(job)
        self._dashboard.update_job_info(job)
        
        # Load active records for the new job
        records = self._manager.get_all_records()
        self._dashboard.set_records(records)
        
        self._on_log_message("INFO", f"Switched to job: {job.name}")
        
        # Auto-start monitoring if configured
        if job.auto_monitor and self._config.automatic_monitoring:
            QTimer.singleShot(500, self._on_start_monitoring)


    def _on_start_monitoring(self):
        if not self._manager.current_job:
            msg = MessageBox("No Job", "Please create a transfer job first.", self)
            msg.exec()
            return
        self._manager.start_monitoring()

    def _on_stop_monitoring(self):
        self._manager.stop_monitoring()

    def _on_sync_now(self):
        if not self._manager.current_job:
            msg = MessageBox("No Job", "Please create a transfer job first.", self)
            msg.exec()
            return

        self._on_log_message("INFO", "Scanning source folder...")

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
                self._on_log_message("INFO", f"Queued {count} file(s) for transfer")
            elif action == SyncAction.WAIT_ALL:
                self._on_log_message("INFO", "Waiting for all files to become ready...")
            else:
                self._on_log_message("INFO", "Sync cancelled")
        elif ready:
            count = self._manager.transfer_ready_files()
            self._on_log_message("INFO", f"Queued {count} file(s) for transfer")
        else:
            self._on_log_message("INFO", "No new files to transfer")

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
        msg = MessageBox(
            "About File Transfer Automation System",
            "Version 1.0.0 — Local Prototype\n\n"
            "Automated one-way file transfer with:\n"
            "- File safety detection (incomplete file protection)\n"
            "- SHA-256 integrity verification\n"
            "- Persistent transfer history\n"
            "- Automatic and manual sync modes\n\n"
            "Files are always copied, never moved. Source files are never modified or deleted.",
            self
        )
        msg.exec()

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
                self._on_log_message("SUCCESS", f"Transferred: {record.file_name}")
            else:
                self._on_log_message("ERROR", f"Failed: {record.file_name} — {result.error_message}")

    def _on_monitoring_changed(self, is_monitoring: bool):
        self._dashboard.update_monitoring_status(is_monitoring)
        if is_monitoring:
            self._on_log_message("INFO", "Monitoring active")
        else:
            self._on_log_message("INFO", "Monitoring stopped")

    def _on_conflict_detected(self, record: TransferRecord):
        dialog = ConflictDialog(record, self)
        dialog.exec()
        resolution = dialog.result_resolution
        self._manager.resolve_conflict(record.id, resolution)

    def _on_log_message(self, level: str, message: str):
        if level == "INFO":
            InfoBar.info(
                title="Info",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        elif level == "SUCCESS":
            InfoBar.success(
                title="Success",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000,
                parent=self
            )
        elif level == "ERROR":
            InfoBar.error(
                title="Error",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self
            )
        elif level == "WARNING":
            InfoBar.warning(
                title="Warning",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self
            )

    # ──────────────────────────────────────────────
    # Window lifecycle
    # ──────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        """Clean shutdown when the window is closed."""
        self._manager.shutdown()
        logger.info("Application closing")
        event.accept()
