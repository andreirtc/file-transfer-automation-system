"""
Main application window for the File Transfer Automation System.

Integrates the Main Dashboard (multi-job concurrent control & notification feed) and the
Job Workspace (detailed file-level transfer workspace) with the TransferManager backend.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QWidget

from qfluentwidgets import (
    MSFluentWindow,
    FluentIcon,
    NavigationItemPosition,
    InfoBar,
    InfoBarPosition,
    MessageBox,
)

from core.models import FileStatus, TransferJob, TransferRecord, TransferResult
from core.transfer_manager import TransferManager
from gui.main_dashboard import MainDashboardWidget
from gui.dashboard import DashboardWidget
from gui.job_dialog import JobDialog
from gui.dialogs import (
    ConflictDialog,
    LogViewerDialog,
    ProcessingWarningDialog,
    SettingsDialog,
    SyncAction,
    TransferHistoryDialog,
)
from gui.help_dialog import UserDocumentationDialog
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService

logger = logging.getLogger("app")


class MainWindow(MSFluentWindow):
    """
    Main application window using Fluent Design.

    Features a Main Dashboard (all jobs overview & live activity feed)
    and a Job Workspace (detailed file-level monitoring table).
    All enabled jobs run concurrently in the background.
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

        # Create the central multi-job transfer manager
        self._manager = TransferManager(config, db, self)

        # Setup Window
        self.setWindowTitle("File Transfer Automation System")
        self.resize(1280, 850)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(icon_path)))

        # Create primary interfaces
        self._main_dashboard = MainDashboardWidget(self)
        self._main_dashboard.setObjectName("MainDashboardInterface")

        self._dashboard = DashboardWidget(self)
        self._dashboard.setObjectName("JobWorkspaceInterface")

        self._setup_navigation()
        self._connect_signals()

        # Load existing jobs on startup and start concurrent background monitoring
        self._load_initial_jobs()

    # ──────────────────────────────────────────────
    # Navigation Interface
    # ──────────────────────────────────────────────

    def _setup_navigation(self):
        # 1. Main Dashboard (Multi-Job Overview & Feed)
        self.addSubInterface(
            self._main_dashboard,
            FluentIcon.HOME,
            "Main Dashboard",
            position=NavigationItemPosition.TOP,
        )

        # 2. Detailed Job Workspace
        self.addSubInterface(
            self._dashboard,
            FluentIcon.FOLDER,
            "Job Workspace",
            position=NavigationItemPosition.TOP,
        )

        # Job Actions
        self.navigationInterface.addItem(
            routeKey="addJob",
            icon=FluentIcon.ADD,
            text="Add Job",
            onClick=self._on_add_job,
            position=NavigationItemPosition.SCROLL,
        )

        self.navigationInterface.addItem(
            routeKey="editJob",
            icon=FluentIcon.EDIT,
            text="Edit Job",
            onClick=self._on_edit_job,
            position=NavigationItemPosition.SCROLL,
        )

        self.navigationInterface.addItem(
            routeKey="history",
            icon=FluentIcon.HISTORY,
            text="Transfer History",
            onClick=self._on_view_history,
            position=NavigationItemPosition.SCROLL,
        )

        # Bottom Actions
        self.navigationInterface.addItem(
            routeKey="logs",
            icon=FluentIcon.DOCUMENT,
            text="View Logs",
            onClick=self._on_view_logs,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="Settings",
            onClick=self._on_settings,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.addItem(
            routeKey="about",
            icon=FluentIcon.INFO,
            text="About",
            onClick=self._on_about,
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.addItem(
            routeKey="help",
            icon=FluentIcon.HELP,
            text="User Guide",
            onClick=self._on_help,
            position=NavigationItemPosition.BOTTOM,
        )

    # ──────────────────────────────────────────────
    # Signal connections
    # ──────────────────────────────────────────────

    def _connect_signals(self):
        # Main Dashboard → Actions
        self._main_dashboard.add_job_requested.connect(self._on_add_job)
        self._main_dashboard.edit_job_requested.connect(self._on_edit_job_by_id)
        self._main_dashboard.delete_job_requested.connect(self._on_delete_job)
        self._main_dashboard.sync_job_requested.connect(self._on_sync_job_by_id)
        self._main_dashboard.toggle_job_monitoring_requested.connect(self._on_toggle_job_monitoring)
        self._main_dashboard.start_all_requested.connect(self._on_start_all_monitoring)
        self._main_dashboard.stop_all_requested.connect(self._on_stop_all_monitoring)
        self._main_dashboard.open_workspace_requested.connect(self._on_open_workspace_for_job)
        self._main_dashboard.refresh_all_requested.connect(self._refresh_all_ui)

        # Job Workspace Dashboard → actions
        self._dashboard.start_monitoring_requested.connect(self._on_start_monitoring)
        self._dashboard.stop_monitoring_requested.connect(self._on_stop_monitoring)
        self._dashboard.sync_now_requested.connect(self._on_sync_now)
        self._dashboard.force_start_requested.connect(self._manager.force_start)
        self._dashboard.job_switched.connect(self._on_job_switched)
        self._dashboard.delete_job_requested.connect(self._on_delete_job)

        # Manager → UI updates
        self._manager.file_detected.connect(self._on_file_detected)
        self._manager.files_detected.connect(self._on_files_detected)
        self._manager.file_status_changed.connect(self._on_file_status_changed)
        self._manager.transfer_completed.connect(self._on_transfer_completed)
        self._manager.stats_updated.connect(self._on_stats_updated)
        self._manager.monitoring_changed.connect(self._on_monitoring_changed)
        self._manager.conflict_detected.connect(self._on_conflict_detected)
        self._manager.log_message.connect(self._on_log_message)

        # Multi-job live signals for real-time Main Dashboard updates
        self._manager.job_file_detected.connect(self._on_job_file_detected)
        self._manager.job_file_status_changed.connect(self._on_job_file_status_changed)
        self._manager.job_transfer_progress.connect(self._on_job_transfer_progress)
        self._manager.job_transfer_completed.connect(self._on_job_transfer_completed)
        self._manager.job_stats_updated.connect(self._on_job_stats_updated)
        self._manager.job_status_changed.connect(self._on_job_status_changed)

        # UI timer for real-time window & multi-job status updates (every 1 second)
        self._ui_window_timer = QTimer(self)
        self._ui_window_timer.setInterval(1000)
        self._ui_window_timer.timeout.connect(self._update_all_status_indicators)
        self._ui_window_timer.start()

    # ──────────────────────────────────────────────
    # Initial setup & Refresh
    # ──────────────────────────────────────────────

    def _load_initial_jobs(self):
        """Load jobs on startup, start concurrent monitoring for all enabled jobs."""
        jobs = self._db.get_jobs()
        self._manager.reload_jobs()

        if jobs:
            active_job = jobs[0]
            self._manager.set_job(active_job)
            self._refresh_all_ui(active_job_id=active_job.id)

            records = self._manager.get_all_records()
            self._dashboard.set_records(records)

            logger.info("Loaded %d transfer jobs on startup", len(jobs))

            # Auto-start monitoring for all enabled jobs with auto_monitor=True
            if self._config.automatic_monitoring:
                for job in jobs:
                    if job.enabled and job.auto_monitor:
                        self._manager.start_job_monitoring(job.id)
                self._update_all_status_indicators()
        else:
            logger.info("No jobs found — prompting user to create one")
            self._refresh_all_ui()
            self._dashboard.update_job_list([], None)
            self._dashboard.update_job_info(None)
            self._dashboard.set_records([])

    def _refresh_all_ui(self, active_job_id: Optional[str] = None):
        """Refresh job lists and statistics on both Main Dashboard and Workspace."""
        jobs = self._db.get_jobs()
        all_stats = self._db.get_all_job_statistics()
        current_job = self._manager.current_job
        cur_id = active_job_id or (current_job.id if current_job else (jobs[0].id if jobs else None))

        exec_states = {j.id: self._manager.get_job_execution_state(j.id) for j in jobs}

        self._main_dashboard.set_jobs(
            jobs=jobs,
            job_stats=all_stats,
            execution_states=exec_states,
        )

        if jobs and cur_id:
            self._dashboard.update_job_list(jobs, cur_id)
            if current_job:
                self._dashboard.update_job_info(current_job)
                stats = self._db.get_statistics(current_job.id)
                self._dashboard.update_statistics(stats)

        self._update_all_status_indicators()

    def _update_all_status_indicators(self):
        """Update live status badges, count pills, and KPIs on Main Dashboard and Job Workspace."""
        jobs = self._db.get_jobs()
        all_stats = self._db.get_all_job_statistics()
        for job in jobs:
            state = self._manager.get_job_execution_state(job.id)
            self._main_dashboard.update_job_status(job.id, state)
            stats = all_stats.get(job.id, {})
            self._main_dashboard.update_job_counts(job.id, stats)

        # Update KPI tiles on Main Dashboard
        total_transferred = sum(s.get("COMPLETED", 0) for s in all_stats.values())
        total_issues = sum(s.get("FAILED", 0) + s.get("CONFLICT", 0) for s in all_stats.values())
        active_monitors = sum(
            1 for j in jobs if self._manager.get_job_execution_state(j.id) not in ("IDLE", "IDLE / STOPPED")
        )
        self._main_dashboard._kpi_jobs.set_value(str(len(jobs)), f"{len(jobs)} configured jobs")
        self._main_dashboard._kpi_monitoring.set_value(str(active_monitors), f"{active_monitors} active monitors")
        self._main_dashboard._kpi_transferred.set_value(str(total_transferred), "Files completed")
        self._main_dashboard._kpi_issues.set_value(str(total_issues), "Failures or conflicts")

        # Workspace status
        cur_job = self._manager.current_job
        if cur_job:
            is_mon = self._manager.is_monitoring
            in_win = self._manager.is_in_transfer_window
            win_info = f"{cur_job.window_start} - {cur_job.window_end}" if cur_job.schedule_mode == "window" else ""
            self._dashboard.update_monitoring_status(is_mon, in_win, win_info)

    # ──────────────────────────────────────────────
    # Navigation & Workspace helpers
    # ──────────────────────────────────────────────

    def _on_open_workspace_for_job(self, job_id: str):
        """Switch active job and navigate to the Job Workspace tab."""
        self._on_job_switched(job_id)
        self.switchTo(self._dashboard)

    # ──────────────────────────────────────────────
    # Action handlers (Add, Edit, Delete, Sync)
    # ──────────────────────────────────────────────

    def _on_add_job(self):
        """Add a new job and automatically start background monitoring."""
        dialog = JobDialog(parent=self)
        if dialog.exec() == JobDialog.DialogCode.Accepted:
            job = dialog.job
            self._db.save_job(job)

            self._manager.reload_jobs()
            self._manager.set_job(job)
            self._dashboard.set_records([])

            # Automatically start monitoring for this job
            self._manager.start_job_monitoring(job.id)
            self._refresh_all_ui(active_job_id=job.id)

            logger.info("Created new job: '%s'", job.name)
            self._on_log_message("SUCCESS", f"Job '{job.name}' created and monitoring started")

    def _on_edit_job(self):
        """Edit currently active job and restart monitoring on Save."""
        job = self._manager.current_job
        if not job:
            msg = MessageBox("No Job", "No job is currently active.", self)
            msg.exec()
            return
        self._on_edit_job_by_id(job.id)

    def _on_edit_job_by_id(self, job_id: str):
        """Edit specified job and automatically start monitoring on Save."""
        job = self._db.get_job(job_id)
        if not job:
            return

        self._manager.stop_job_monitoring(job_id)

        dialog = JobDialog(job=job, parent=self)
        if dialog.exec() == JobDialog.DialogCode.Accepted:
            updated_job = dialog.job
            self._db.save_job(updated_job)

            self._manager.reload_jobs()
            self._manager.set_job(updated_job)
            self._dashboard.update_job_info(updated_job)

            # Automatically start monitoring on Save
            self._manager.start_job_monitoring(updated_job.id)

            records = self._manager.get_history(job_id=updated_job.id, limit=100)
            active = self._manager.get_all_records(job_id=updated_job.id)
            merged = {r.id: r for r in records}
            merged.update({r.id: r for r in active})
            self._dashboard.set_records(list(merged.values()))

            self._refresh_all_ui(active_job_id=updated_job.id)

            logger.info("Updated job: '%s'", updated_job.name)
            self._on_log_message("SUCCESS", f"Job '{updated_job.name}' saved and monitoring started")

    def _on_job_switched(self, job_id: str):
        """Handle switching the active job view in the workspace."""
        jobs = self._db.get_jobs()
        job = next((j for j in jobs if j.id == job_id), None)
        if not job:
            return

        self._manager.set_job(job)
        self._dashboard.update_job_info(job)

        records = self._manager.get_history(job_id=job.id, limit=100)
        active = self._manager.get_all_records(job_id=job.id)
        merged = {r.id: r for r in records}
        merged.update({r.id: r for r in active})
        self._dashboard.set_records(list(merged.values()))

        self._refresh_all_ui(active_job_id=job.id)

    def _on_delete_job(self, job_id: str):
        job = self._db.get_job(job_id)
        job_name = job.name if job else "this job"

        msg = MessageBox(
            "Delete Job",
            f"Are you sure you want to delete '{job_name}' and all its transfer history?\nThis cannot be undone.",
            self,
        )
        if msg.exec():
            self._manager.stop_job_monitoring(job_id)
            self._db.delete_job(job_id)
            self._manager.reload_jobs()

            self._on_log_message("SUCCESS", f"Job '{job_name}' deleted")
            self._load_initial_jobs()

    def _on_toggle_job_monitoring(self, job_id: str):
        """Toggle monitoring for a specific job directly from the card button."""
        if self._manager.is_job_monitoring(job_id):
            self._manager.stop_job_monitoring(job_id)
        else:
            self._manager.start_job_monitoring(job_id)
        self._update_all_status_indicators()

    def _on_start_all_monitoring(self):
        """Start monitoring all enabled jobs."""
        self._manager.start_all_monitoring()
        self._update_all_status_indicators()
        self._on_log_message("SUCCESS", "Started monitoring all enabled jobs")

    def _on_stop_all_monitoring(self):
        """Stop monitoring all jobs."""
        self._manager.stop_all_monitoring()
        self._update_all_status_indicators()
        self._on_log_message("INFO", "Stopped monitoring all jobs")

    def _on_start_monitoring(self):
        """Start monitoring current workspace job."""
        if not self._manager.current_job:
            msg = MessageBox("No Job", "Please create a transfer job first.", self)
            msg.exec()
            return
        self._manager.start_monitoring()
        self._update_all_status_indicators()

    def _on_stop_monitoring(self):
        """Stop monitoring current workspace job."""
        self._manager.stop_monitoring()
        self._update_all_status_indicators()

    def _on_sync_job_by_id(self, job_id: str):
        """Sync a specific job directly from the Main Dashboard card."""
        ctrl = self._manager.get_controller(job_id)
        if not ctrl:
            return

        self._on_log_message("INFO", f"Scanning source folder for '{ctrl.job.name}'...")
        ready, processing = ctrl.sync_now()

        if self._manager.current_job and self._manager.current_job.id == job_id:
            self._dashboard.set_records(self._manager.get_all_records(job_id))

        if processing:
            dialog = ProcessingWarningDialog(
                processing_files=processing,
                ready_count=len(ready),
                parent=self,
            )
            if dialog.exec() and dialog.result_action == SyncAction.TRANSFER_READY:
                count = ctrl.transfer_ready_files()
                self._on_log_message("INFO", f"Queued {count} file(s) for transfer in '{ctrl.job.name}'")
        elif ready:
            count = ctrl.transfer_ready_files()
            self._on_log_message("INFO", f"Queued {count} file(s) for transfer in '{ctrl.job.name}'")
        else:
            self._on_log_message("INFO", f"No new files to transfer for '{ctrl.job.name}'")

        self._refresh_all_ui()

    def _on_sync_now(self):
        """Sync active workspace job."""
        if not self._manager.current_job:
            msg = MessageBox("No Job", "Please create a transfer job first.", self)
            msg.exec()
            return
        self._on_sync_job_by_id(self._manager.current_job.id)

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
            "Version 1.0.0 — Production Edition\n\n"
            "Automated one-way file transfer with:\n"
            "- Multi-job concurrent background monitoring\n"
            "- Central Main Dashboard & detailed Job Workspace\n"
            "- File safety lock & stability detection\n"
            "- SHA-256 integrity verification\n"
            "- Scheduled Transfer Windows & Batch Compression (ZipCrypto)\n"
            "- Persistent SQLite transfer history\n\n"
            "Files are safely copied and verified. Source files remain intact.",
            self,
        )
        msg.exec()

    def _on_help(self):
        dialog = UserDocumentationDialog(self)
        dialog.exec()

    # ──────────────────────────────────────────────
    # Manager signal handlers
    # ──────────────────────────────────────────────

    def _on_file_detected(self, file_path: str, record: TransferRecord):
        self._dashboard.update_record(record)

    def _on_files_detected(self, records: list):
        for record in records:
            self._dashboard.update_record(record)

    def _on_file_status_changed(self, record_id: str, status: FileStatus):
        record = self._manager._find_record_by_id(record_id)
        if record:
            self._dashboard.update_record(record)

    def _on_stats_updated(self, stats: dict):
        self._dashboard.update_statistics(stats)
        if self._manager.current_job:
            self._main_dashboard.update_job_counts(self._manager.current_job.id, stats)

    def _on_transfer_completed(self, record_id: str, result: TransferResult):
        record = self._manager._find_record_by_id(record_id)
        if record:
            self._dashboard.update_record(record)
            job = self._db.get_job(record.job_id)
            job_name = job.name if job else "Job"
            if result.success:
                self._on_log_message("SUCCESS", f"[{job_name}] Transferred: {record.file_name}")
            else:
                self._on_log_message("ERROR", f"[{job_name}] Failed: {record.file_name} — {result.error_message}")
            stats = self._db.get_statistics(record.job_id)
            self._dashboard.update_statistics(stats)
            self._main_dashboard.update_job_counts(record.job_id, stats)
            self._main_dashboard.update_job_status(record.job_id, self._manager.get_job_execution_state(record.job_id))

    # ── Multi-job live Main Dashboard handlers ──

    def _on_job_file_detected(self, job_id: str, file_path: str, record: TransferRecord):
        stats = self._db.get_statistics(job_id)
        self._main_dashboard.update_job_counts(job_id, stats)
        self._main_dashboard.update_job_status(job_id, self._manager.get_job_execution_state(job_id))

    def _on_job_file_status_changed(self, job_id: str, record_id: str, status: FileStatus):
        stats = self._db.get_statistics(job_id)
        self._main_dashboard.update_job_counts(job_id, stats)
        self._main_dashboard.update_job_status(job_id, self._manager.get_job_execution_state(job_id))

    def _on_job_transfer_progress(self, job_id: str, phase: str, current: int, total: int):
        self._main_dashboard.update_job_progress(job_id, phase, current, total)

    def _on_job_stats_updated(self, job_id: str, stats: dict):
        self._main_dashboard.update_job_counts(job_id, stats)
        self._main_dashboard.update_job_status(job_id, self._manager.get_job_execution_state(job_id))

    def _on_job_status_changed(self, job_id: str, execution_state: str):
        self._main_dashboard.update_job_status(job_id, execution_state)

    def _on_job_transfer_completed(self, job_id: str, record_id: str, result: TransferResult):
        stats = self._db.get_statistics(job_id)
        self._main_dashboard.update_job_counts(job_id, stats)
        self._main_dashboard.update_job_status(job_id, self._manager.get_job_execution_state(job_id))

    def _on_monitoring_changed(self, is_monitoring: bool):
        self._update_all_status_indicators()

    def _on_conflict_detected(self, record: TransferRecord):
        dialog = ConflictDialog(record, self)
        dialog.exec()
        resolution = dialog.result_resolution
        self._manager.resolve_conflict(record.id, resolution)

    def _on_log_message(self, level: str, message: str):
        job_name = self._manager.current_job.name if self._manager.current_job else "System"
        self._main_dashboard.add_activity_event(level, message, job_name)

        # Only display overlay popups for critical warnings, errors, and batch finishes to avoid GUI thread lock
        lvl = level.upper()
        if lvl in ("ERROR", "FAILED"):
            InfoBar.error(
                title="Error",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=5000,
                parent=self,
            )
        elif lvl in ("WARNING", "CONFLICT"):
            InfoBar.warning(
                title="Warning",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000,
                parent=self,
            )

    # ──────────────────────────────────────────────
    # Window lifecycle
    # ──────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent):
        """Clean shutdown when the window is closed."""
        self._manager.shutdown()
        logger.info("Application closing")
        event.accept()
