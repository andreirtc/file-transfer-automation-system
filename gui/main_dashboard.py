"""
Main Dashboard widget for the File Transfer Automation System.

Provides a unified corporate Windows 11 Fluent control view of all jobs,
aggregate system KPIs, individual job cards with sequential transfer status,
per-job actions (Sync, Monitor, Edit, Delete, Workspace), and a live notification stream.
Strictly designed for enterprise environments (zero emojis).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QFrame,
    QTableWidgetItem,
    QHeaderView,
)

from qfluentwidgets import (
    SimpleCardWidget,
    CardWidget,
    PrimaryPushButton,
    PushButton,
    ToolButton,
    FluentIcon,
    StrongBodyLabel,
    BodyLabel,
    TitleLabel,
    SubtitleLabel,
    CaptionLabel,
    TableWidget,
    SmoothScrollArea,
    ProgressBar,
)

from core.models import TransferJob


class OverviewKpiCard(SimpleCardWidget):
    """Corporate Windows 11 KPI summary card."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        subtitle: str = "",
        accent_color: str = "#0078D4",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setStyleSheet(f"""
            OverviewKpiCard {{
                border-left: 3px solid {accent_color};
                background-color: #FFFFFF;
                border-radius: 6px;
                border-top: 1px solid #E5E5E5;
                border-right: 1px solid #E5E5E5;
                border-bottom: 1px solid #E5E5E5;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(3)

        self._value_label = TitleLabel(value, self)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._value_label)

        self._title_label = StrongBodyLabel(title.upper(), self)
        self._title_label.setStyleSheet("color: #616161; font-size: 11px; letter-spacing: 0.5px;")
        layout.addWidget(self._title_label)

        self._subtitle_label = CaptionLabel(subtitle, self)
        self._subtitle_label.setStyleSheet("color: #7A7A7A;")
        layout.addWidget(self._subtitle_label)

    def set_value(self, value: str, subtitle: Optional[str] = None) -> None:
        self._value_label.setText(value)
        if subtitle is not None:
            self._subtitle_label.setText(subtitle)


class JobOverviewCard(CardWidget):
    """Corporate Windows 11 card displaying a single job's status, paths, metrics, and actions."""

    open_workspace_clicked = Signal(str)
    edit_clicked = Signal(str)
    delete_clicked = Signal(str)
    sync_clicked = Signal(str)
    toggle_monitor_clicked = Signal(str)

    def __init__(self, job: TransferJob, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.job = job
        self._is_monitoring = False
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("""
            JobOverviewCard {
                background-color: #FFFFFF;
                border: 1px solid #E5E5E5;
                border-radius: 8px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Top Row: Job Name, Badges & Action Buttons ──
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self._name_label = SubtitleLabel(self.job.name, self)
        top_layout.addWidget(self._name_label)

        # Status Badge
        self._status_badge = BodyLabel("IDLE", self)
        self._status_badge.setStyleSheet("""
            background-color: #F3F4F6;
            color: #4B5563;
            border: 1px solid #E5E7EB;
            padding: 3px 10px;
            border-radius: 4px;
            font-weight: 600;
            font-size: 11px;
            letter-spacing: 0.3px;
        """)
        top_layout.addWidget(self._status_badge)

        # Schedule Badge
        schedule_text = (
            f"Window: {self.job.window_start} - {self.job.window_end}"
            if self.job.schedule_mode == "window"
            else "Continuous Mode"
        )
        self._schedule_badge = BodyLabel(schedule_text, self)
        self._schedule_badge.setStyleSheet("""
            background-color: #F8FAFC;
            color: #334155;
            border: 1px solid #E2E8F0;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        """)
        top_layout.addWidget(self._schedule_badge)

        top_layout.addStretch()

        # Action Buttons
        self._btn_toggle_monitor = PushButton("Start Monitoring", self, FluentIcon.PLAY)
        self._btn_toggle_monitor.clicked.connect(lambda: self.toggle_monitor_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_toggle_monitor)

        self._btn_sync = PushButton("Sync Now", self, FluentIcon.SYNC)
        self._btn_sync.clicked.connect(lambda: self.sync_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_sync)

        self._btn_edit = ToolButton(FluentIcon.EDIT, self)
        self._btn_edit.setToolTip("Edit Job Configuration")
        self._btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_edit)

        self._btn_delete = ToolButton(FluentIcon.DELETE, self)
        self._btn_delete.setToolTip("Delete Transfer Job")
        self._btn_delete.clicked.connect(lambda: self.delete_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_delete)

        self._btn_workspace = PrimaryPushButton("Open Workspace", self, FluentIcon.FOLDER)
        self._btn_workspace.setToolTip("Open detailed file table for this job")
        self._btn_workspace.clicked.connect(lambda: self.open_workspace_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_workspace)

        layout.addLayout(top_layout)

        # ── Middle Row: Source & Destination Paths ──
        path_layout = QGridLayout()
        path_layout.setHorizontalSpacing(12)
        path_layout.setVerticalSpacing(4)

        lbl_src = StrongBodyLabel("Source:", self)
        lbl_src.setStyleSheet("color: #475569; font-size: 12px;")
        path_layout.addWidget(lbl_src, 0, 0)

        self._src_label = BodyLabel(self.job.source_folder, self)
        self._src_label.setStyleSheet("color: #1E293B; font-size: 12px;")
        path_layout.addWidget(self._src_label, 0, 1)

        lbl_dst = StrongBodyLabel("Destination:", self)
        lbl_dst.setStyleSheet("color: #475569; font-size: 12px;")
        path_layout.addWidget(lbl_dst, 1, 0)

        self._dst_label = BodyLabel(self.job.destination_folder, self)
        self._dst_label.setStyleSheet("color: #1E293B; font-size: 12px;")
        path_layout.addWidget(self._dst_label, 1, 1)

        path_layout.setColumnStretch(1, 1)
        layout.addLayout(path_layout)

        # ── Bottom Row: Corporate Status Metric Pills ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)

        self._pill_detected = self._create_stat_pill("Detected", "0", "#0067C0", "#F0F6FF", "#D0E1FD")
        self._pill_processing = self._create_stat_pill("Processing", "0", "#B45309", "#FFFBEB", "#FDE68A")
        self._pill_waiting = self._create_stat_pill("Waiting for Window", "0", "#475569", "#F8FAFC", "#E2E8F0")
        self._pill_completed = self._create_stat_pill("Completed", "0", "#15803D", "#F0FDF4", "#BBF7D0")
        self._pill_failed = self._create_stat_pill("Failed", "0", "#B91C1C", "#FEF2F2", "#FECACA")

        stats_layout.addWidget(self._pill_detected)
        stats_layout.addWidget(self._pill_processing)
        stats_layout.addWidget(self._pill_waiting)
        stats_layout.addWidget(self._pill_completed)
        stats_layout.addWidget(self._pill_failed)
        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # ── Progress Bar Row (Live Progress Indicator) ──
        self._progress_container = QWidget(self)
        prog_layout = QVBoxLayout(self._progress_container)
        prog_layout.setContentsMargins(0, 4, 0, 0)
        prog_layout.setSpacing(3)

        prog_header = QHBoxLayout()
        self._progress_label = CaptionLabel("Transfer in Progress...", self._progress_container)
        self._progress_label.setStyleSheet("color: #0067C0; font-size: 11px; font-weight: 600;")
        self._progress_percent = CaptionLabel("0%", self._progress_container)
        self._progress_percent.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        prog_header.addWidget(self._progress_label)
        prog_header.addStretch()
        prog_header.addWidget(self._progress_percent)
        prog_layout.addLayout(prog_header)

        self._progress_bar = ProgressBar(self._progress_container)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setValue(0)
        prog_layout.addWidget(self._progress_bar)

        self._progress_container.hide()
        layout.addWidget(self._progress_container)

    def _create_stat_pill(
        self, label: str, val: str, text_color: str, bg_color: str, border_color: str
    ) -> QWidget:
        pill = QFrame(self)
        pill.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 4px;
            }}
        """)
        p_layout = QHBoxLayout(pill)
        p_layout.setContentsMargins(8, 4, 8, 4)
        p_layout.setSpacing(6)

        v_lbl = StrongBodyLabel(val, pill)
        v_lbl.setStyleSheet(f"color: {text_color}; font-weight: 700; font-size: 12px;")

        lbl = CaptionLabel(label, pill)
        lbl.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: 500;")

        p_layout.addWidget(v_lbl)
        p_layout.addWidget(lbl)
        pill.val_label = v_lbl
        return pill

    def update_progress(self, phase: str, current: int, total: int):
        """Update live progress bar and label for this job."""
        self._progress_container.show()
        if total > 0:
            pct = int((current / total) * 100)
            pct = max(0, min(100, pct))
            self._progress_bar.setValue(pct)
            self._progress_percent.setText(f"{pct}%")
            if phase == "compressing":
                self._progress_label.setText(f"Compressing Archive ({pct}%)")
            elif phase == "copy":
                cur_mb = current / (1024 * 1024)
                tot_mb = total / (1024 * 1024)
                self._progress_label.setText(f"Transferring Archive ({cur_mb:.1f} MB / {tot_mb:.1f} MB)")
            elif phase == "hashing":
                self._progress_label.setText(f"Verifying SHA-256 Checksum ({pct}%)")
            else:
                self._progress_label.setText(f"Processing ({phase})...")

    def update_status(self, execution_state: str):
        """Update job status badge according to the sequential execution state."""
        state = execution_state.upper()
        if state == "TRANSFERRING":
            self._status_badge.setText("TRANSFERRING")
            self._status_badge.setStyleSheet("""
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px solid #BFDBFE;
                padding: 3px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 11px;
            """)
            self._btn_toggle_monitor.setText("Stop Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PAUSE)
            self._progress_container.show()

        elif state == "QUEUED":
            self._status_badge.setText("QUEUED (IN LINE)")
            self._status_badge.setStyleSheet("""
                background-color: #FFFBEB;
                color: #B45309;
                border: 1px solid #FDE68A;
                padding: 3px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 11px;
            """)
            self._btn_toggle_monitor.setText("Stop Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PAUSE)
            self._progress_container.show()
            self._progress_bar.setValue(0)
            self._progress_label.setText("Queued in Line — Waiting for previous transfer to complete...")
            self._progress_percent.setText("In Queue")

        elif state in ("MONITORING", "IN_WINDOW"):
            label = "MONITORING (IN WINDOW)" if state == "IN_WINDOW" else "MONITORING"
            self._status_badge.setText(label)
            self._status_badge.setStyleSheet("""
                background-color: #F0FDF4;
                color: #15803D;
                border: 1px solid #BBF7D0;
                padding: 3px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 11px;
            """)
            self._btn_toggle_monitor.setText("Stop Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PAUSE)
            self._progress_container.hide()

        elif state == "OUTSIDE_WINDOW":
            self._status_badge.setText("WAITING (OUTSIDE WINDOW)")
            self._status_badge.setStyleSheet("""
                background-color: #FFFBEB;
                color: #92400E;
                border: 1px solid #FDE68A;
                padding: 3px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 11px;
            """)
            self._btn_toggle_monitor.setText("Stop Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PAUSE)
            self._progress_container.hide()

        else:  # IDLE / STOPPED
            self._status_badge.setText("IDLE / STOPPED")
            self._status_badge.setStyleSheet("""
                background-color: #F3F4F6;
                color: #4B5563;
                border: 1px solid #E5E7EB;
                padding: 3px 10px;
                border-radius: 4px;
                font-weight: 600;
                font-size: 11px;
            """)
            self._btn_toggle_monitor.setText("Start Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PLAY)
            self._progress_container.hide()

    def update_counts(self, stats: dict[str, int]):
        self._pill_detected.val_label.setText(str(stats.get("DETECTED", 0)))
        self._pill_processing.val_label.setText(str(stats.get("PROCESSING", 0)))
        self._pill_waiting.val_label.setText(str(stats.get("WAITING_FOR_WINDOW", 0)))
        self._pill_completed.val_label.setText(str(stats.get("COMPLETED", 0)))
        self._pill_failed.val_label.setText(str(stats.get("FAILED", 0)))


class MainDashboardWidget(QWidget):
    """
    Corporate Main Dashboard interface showing all configured transfer jobs,
    global system KPIs, and live activity stream.
    """

    add_job_requested = Signal()
    edit_job_requested = Signal(str)
    delete_job_requested = Signal(str)
    open_workspace_requested = Signal(str)
    sync_job_requested = Signal(str)
    toggle_job_monitoring_requested = Signal(str)
    start_all_requested = Signal()
    stop_all_requested = Signal()
    refresh_all_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._job_cards: dict[str, JobOverviewCard] = {}
        self._setup_ui()

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self._scroll = SmoothScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        root_layout.addWidget(self._scroll)

        container = QWidget()
        self._scroll.setWidget(container)

        self._content_layout = QVBoxLayout(container)
        self._content_layout.setSpacing(20)
        self._content_layout.setContentsMargins(28, 24, 28, 24)

        # ── Header Row ──
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)

        self._title_label = TitleLabel("Main Dashboard", container)
        self._subtitle_label = BodyLabel(
            "System Overview & Multi-Job Central Control", container
        )
        self._subtitle_label.setStyleSheet("color: #616161; font-size: 13px;")

        header_text_layout.addWidget(self._title_label)
        header_text_layout.addWidget(self._subtitle_label)
        header_layout.addLayout(header_text_layout)

        header_layout.addStretch()

        self._btn_start_all = PushButton("Start All", container, FluentIcon.PLAY)
        self._btn_start_all.clicked.connect(self.start_all_requested.emit)
        header_layout.addWidget(self._btn_start_all)

        self._btn_stop_all = PushButton("Stop All", container, FluentIcon.PAUSE)
        self._btn_stop_all.clicked.connect(self.stop_all_requested.emit)
        header_layout.addWidget(self._btn_stop_all)

        self._btn_refresh = PushButton("Refresh", container, FluentIcon.SYNC)
        self._btn_refresh.clicked.connect(self.refresh_all_requested.emit)
        header_layout.addWidget(self._btn_refresh)

        self._btn_add_job = PrimaryPushButton("Add Job", container, FluentIcon.ADD)
        self._btn_add_job.clicked.connect(self.add_job_requested.emit)
        header_layout.addWidget(self._btn_add_job)

        self._content_layout.addLayout(header_layout)

        # ── Corporate KPI Row ──
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(12)

        self._kpi_jobs = OverviewKpiCard("Total Jobs", "0", "Configured jobs", "#0078D4", container)
        self._kpi_monitoring = OverviewKpiCard("Active Monitors", "0", "Currently running", "#107C10", container)
        self._kpi_transferred = OverviewKpiCard("Files Transferred", "0", "Completed transfers", "#0099BC", container)
        self._kpi_issues = OverviewKpiCard("System Issues", "0", "Failures & conflicts", "#C42B1C", container)

        kpi_layout.addWidget(self._kpi_jobs)
        kpi_layout.addWidget(self._kpi_monitoring)
        kpi_layout.addWidget(self._kpi_transferred)
        kpi_layout.addWidget(self._kpi_issues)

        self._content_layout.addLayout(kpi_layout)

        # ── All Jobs Section ──
        jobs_header_layout = QHBoxLayout()
        self._jobs_section_title = SubtitleLabel("Transfer Jobs", container)
        jobs_header_layout.addWidget(self._jobs_section_title)
        jobs_header_layout.addStretch()
        self._content_layout.addLayout(jobs_header_layout)

        self._jobs_container = QVBoxLayout()
        self._jobs_container.setSpacing(12)
        self._content_layout.addLayout(self._jobs_container)

        self._empty_label = BodyLabel("No transfer jobs configured. Click 'Add Job' above to get started.", container)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #7A7A7A; padding: 40px;")
        self._jobs_container.addWidget(self._empty_label)

        # ── Activity & Transfer Feed ──
        activity_header_layout = QHBoxLayout()
        activity_title = SubtitleLabel("System Activity & Transfer Feed", container)
        activity_header_layout.addWidget(activity_title)
        activity_header_layout.addStretch()

        self._btn_clear_feed = PushButton("Clear Feed", container, FluentIcon.DELETE)
        self._btn_clear_feed.clicked.connect(self._clear_activity_feed)
        activity_header_layout.addWidget(self._btn_clear_feed)

        self._content_layout.addLayout(activity_header_layout)

        self._activity_table = TableWidget(container)
        self._activity_table.setColumnCount(4)
        self._activity_table.setHorizontalHeaderLabels(["Timestamp", "Job", "Level", "Message"])
        self._activity_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._activity_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._activity_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._activity_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._activity_table.setMinimumHeight(240)
        self._activity_table.setAlternatingRowColors(True)

        self._content_layout.addWidget(self._activity_table)

    def set_jobs(
        self,
        jobs: list[TransferJob],
        job_stats: Optional[dict[str, dict[str, int]]] = None,
        execution_states: Optional[dict[str, str]] = None,
    ) -> None:
        """Update job overview cards in place without destroying and recreating widgets."""
        job_stats = job_stats or {}
        states = execution_states or {}
        job_ids = {j.id for j in jobs}

        # Remove cards for jobs that no longer exist
        for jid in list(self._job_cards.keys()):
            if jid not in job_ids:
                card = self._job_cards.pop(jid)
                self._jobs_container.removeWidget(card)
                card.deleteLater()

        if not jobs:
            self._empty_label.show()
            self._kpi_jobs.set_value("0", "0 configured jobs")
            self._kpi_monitoring.set_value("0", "0 active monitors")
            self._kpi_transferred.set_value("0", "0 files completed")
            self._kpi_issues.set_value("0", "0 failures")
            return

        self._empty_label.hide()

        total_transferred = 0
        total_issues = 0
        active_monitors = 0

        for job in jobs:
            state = states.get(job.id, "IDLE")
            stats = job_stats.get(job.id, {})

            if job.id in self._job_cards:
                card = self._job_cards[job.id]
                card.job = job
                card._name_label.setText(job.name)
                card._src_label.setText(job.source_folder)
                card._dst_label.setText(job.destination_folder)
                schedule_text = (
                    f"Window: {job.window_start} - {job.window_end}"
                    if job.schedule_mode == "window"
                    else "Continuous Mode"
                )
                card._schedule_badge.setText(schedule_text)
                card.update_status(state)
                card.update_counts(stats)
            else:
                card = JobOverviewCard(job, self)
                card.open_workspace_clicked.connect(self.open_workspace_requested.emit)
                card.edit_clicked.connect(self.edit_job_requested.emit)
                card.delete_clicked.connect(self.delete_job_requested.emit)
                card.sync_clicked.connect(self.sync_job_requested.emit)
                card.toggle_monitor_clicked.connect(self.toggle_job_monitoring_requested.emit)
                card.update_status(state)
                card.update_counts(stats)

                self._job_cards[job.id] = card
                self._jobs_container.addWidget(card)

            if state not in ("IDLE", "IDLE / STOPPED"):
                active_monitors += 1

            total_transferred += stats.get("COMPLETED", 0)
            total_issues += stats.get("FAILED", 0) + stats.get("CONFLICT", 0)

        self._kpi_jobs.set_value(str(len(jobs)), f"{len(jobs)} configured jobs")
        self._kpi_monitoring.set_value(str(active_monitors), f"{active_monitors} active monitors")
        self._kpi_transferred.set_value(str(total_transferred), "Files completed")
        self._kpi_issues.set_value(str(total_issues), "Failures or conflicts")

    def update_job_status(self, job_id: str, execution_state: str) -> None:
        if job_id in self._job_cards:
            self._job_cards[job_id].update_status(execution_state)

    def update_job_counts(self, job_id: str, stats: dict[str, int]) -> None:
        if job_id in self._job_cards:
            self._job_cards[job_id].update_counts(stats)

    def update_job_progress(self, job_id: str, phase: str, current: int, total: int) -> None:
        if job_id in self._job_cards:
            self._job_cards[job_id].update_progress(phase, current, total)

    def add_activity_event(
        self, level: str, message: str, job_name: str = "System"
    ) -> None:
        """Add a professional event entry to the live activity feed."""
        row = 0
        self._activity_table.insertRow(row)

        time_str = datetime.now().strftime("%H:%M:%S")
        self._activity_table.setItem(row, 0, QTableWidgetItem(time_str))
        self._activity_table.setItem(row, 1, QTableWidgetItem(job_name))

        type_item = QTableWidgetItem(level.upper())
        lvl_upper = level.upper()
        if lvl_upper in ("ERROR", "FAILED"):
            type_item.setForeground(QColor("#B91C1C"))
        elif lvl_upper in ("SUCCESS", "COMPLETED"):
            type_item.setForeground(QColor("#15803D"))
        elif lvl_upper in ("WARNING", "CONFLICT"):
            type_item.setForeground(QColor("#B45309"))
        elif lvl_upper == "TRANSFER":
            type_item.setForeground(QColor("#1D4ED8"))
        else:
            type_item.setForeground(QColor("#0067C0"))

        self._activity_table.setItem(row, 2, type_item)
        self._activity_table.setItem(row, 3, QTableWidgetItem(message))

        if self._activity_table.rowCount() > 200:
            self._activity_table.removeRow(self._activity_table.rowCount() - 1)

    def _clear_activity_feed(self) -> None:
        self._activity_table.setRowCount(0)
