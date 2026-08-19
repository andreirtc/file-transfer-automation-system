"""
Main Dashboard widget for the File Transfer Automation System.

Provides a unified central control view of all jobs, aggregate system KPIs,
individual job status cards with per-job delete/sync/monitor controls,
and a live multi-job notification stream.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
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
)

from core.models import FileStatus, TransferJob


class OverviewKpiCard(SimpleCardWidget):
    """KPI summary card for the Main Dashboard overview row."""

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
                border-left: 4px solid {accent_color};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        self._value_label = TitleLabel(value, self)
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._value_label)

        self._title_label = StrongBodyLabel(title.upper(), self)
        self._title_label.setStyleSheet("color: #666666;")
        layout.addWidget(self._title_label)

        self._subtitle_label = CaptionLabel(subtitle, self)
        self._subtitle_label.setStyleSheet("color: #888888;")
        layout.addWidget(self._subtitle_label)

    def set_value(self, value: str, subtitle: Optional[str] = None) -> None:
        self._value_label.setText(value)
        if subtitle is not None:
            self._subtitle_label.setText(subtitle)


class JobOverviewCard(CardWidget):
    """Card displaying a single job's status, paths, stats, and action buttons."""

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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Top Row: Job Name, Badges & Action Buttons ──
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self._name_label = SubtitleLabel(self.job.name, self)
        top_layout.addWidget(self._name_label)

        # Monitoring Status Badge
        self._status_badge = BodyLabel("IDLE", self)
        self._status_badge.setStyleSheet("""
            background-color: #F3F3F3;
            color: #555555;
            padding: 3px 10px;
            border-radius: 6px;
            font-weight: bold;
            font-size: 11px;
        """)
        top_layout.addWidget(self._status_badge)

        # Schedule Badge
        self._schedule_badge = BodyLabel(
            f"⏰ Window: {self.job.window_start} - {self.job.window_end}"
            if self.job.schedule_mode == "window"
            else "🔄 Continuous",
            self,
        )
        self._schedule_badge.setStyleSheet("""
            background-color: #EBF3FC;
            color: #005A9E;
            padding: 3px 10px;
            border-radius: 6px;
            font-size: 11px;
        """)
        top_layout.addWidget(self._schedule_badge)

        top_layout.addStretch()

        # Monitor Toggle Button (Play / Pause)
        self._btn_toggle_monitor = PushButton("Start Monitoring", self, FluentIcon.PLAY)
        self._btn_toggle_monitor.clicked.connect(lambda: self.toggle_monitor_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_toggle_monitor)

        # Sync Button
        self._btn_sync = PushButton("Sync Now", self, FluentIcon.SYNC)
        self._btn_sync.clicked.connect(lambda: self.sync_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_sync)

        # Edit Button
        self._btn_edit = ToolButton(FluentIcon.EDIT, self)
        self._btn_edit.setToolTip("Edit Job Configuration")
        self._btn_edit.clicked.connect(lambda: self.edit_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_edit)

        # Delete Button
        self._btn_delete = ToolButton(FluentIcon.DELETE, self)
        self._btn_delete.setToolTip("Delete Transfer Job")
        self._btn_delete.clicked.connect(lambda: self.delete_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_delete)

        # Open Workspace Button
        self._btn_workspace = PrimaryPushButton("Open Workspace", self, FluentIcon.FOLDER)
        self._btn_workspace.setToolTip("Open detailed file table for this job")
        self._btn_workspace.clicked.connect(lambda: self.open_workspace_clicked.emit(self.job.id))
        top_layout.addWidget(self._btn_workspace)

        layout.addLayout(top_layout)

        # ── Middle Row: Source & Destination Paths ──
        path_layout = QGridLayout()
        path_layout.setHorizontalSpacing(12)
        path_layout.setVerticalSpacing(4)

        path_layout.addWidget(StrongBodyLabel("Source:", self), 0, 0)
        self._src_label = BodyLabel(self.job.source_folder, self)
        self._src_label.setStyleSheet("color: #444444;")
        path_layout.addWidget(self._src_label, 0, 1)

        path_layout.addWidget(StrongBodyLabel("Destination:", self), 1, 0)
        self._dst_label = BodyLabel(self.job.destination_folder, self)
        self._dst_label.setStyleSheet("color: #444444;")
        path_layout.addWidget(self._dst_label, 1, 1)

        path_layout.setColumnStretch(1, 1)
        layout.addLayout(path_layout)

        # ── Bottom Row: Status Pill Counters ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(8)

        self._pill_detected = self._create_stat_pill("Detected", "0", "#0078D4")
        self._pill_processing = self._create_stat_pill("Processing", "0", "#D83B01")
        self._pill_waiting = self._create_stat_pill("Waiting Window", "0", "#69797E")
        self._pill_completed = self._create_stat_pill("Completed", "0", "#107C10")
        self._pill_failed = self._create_stat_pill("Failed", "0", "#C42B1C")

        stats_layout.addWidget(self._pill_detected)
        stats_layout.addWidget(self._pill_processing)
        stats_layout.addWidget(self._pill_waiting)
        stats_layout.addWidget(self._pill_completed)
        stats_layout.addWidget(self._pill_failed)
        stats_layout.addStretch()

        layout.addLayout(stats_layout)

    def _create_stat_pill(self, label: str, val: str, color: str) -> QWidget:
        pill = QFrame(self)
        pill.setStyleSheet(f"""
            QFrame {{
                background-color: {color}15;
                border: 1px solid {color}40;
                border-radius: 6px;
                padding: 2px 8px;
            }}
        """)
        p_layout = QHBoxLayout(pill)
        p_layout.setContentsMargins(6, 3, 6, 3)
        p_layout.setSpacing(6)

        v_lbl = StrongBodyLabel(val, pill)
        v_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        lbl = CaptionLabel(label, pill)
        lbl.setStyleSheet(f"color: {color};")

        p_layout.addWidget(v_lbl)
        p_layout.addWidget(lbl)
        pill.val_label = v_lbl
        return pill

    def update_status(self, is_monitoring: bool, in_window: bool = True):
        self._is_monitoring = is_monitoring
        if is_monitoring:
            self._btn_toggle_monitor.setText("Stop Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PAUSE)

            if self.job.schedule_mode == "window":
                if in_window:
                    self._status_badge.setText("● ACTIVE (In Window)")
                    self._status_badge.setStyleSheet("""
                        background-color: #DFF6DD;
                        color: #107C10;
                        padding: 3px 10px;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 11px;
                    """)
                else:
                    self._status_badge.setText("⏳ WAITING (Outside Window)")
                    self._status_badge.setStyleSheet("""
                        background-color: #FFF4CE;
                        color: #795B00;
                        padding: 3px 10px;
                        border-radius: 6px;
                        font-weight: bold;
                        font-size: 11px;
                    """)
            else:
                self._status_badge.setText("● MONITORING")
                self._status_badge.setStyleSheet("""
                    background-color: #DFF6DD;
                    color: #107C10;
                    padding: 3px 10px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 11px;
                """)
        else:
            self._btn_toggle_monitor.setText("Start Monitoring")
            self._btn_toggle_monitor.setIcon(FluentIcon.PLAY)
            self._status_badge.setText("○ IDLE / STOPPED")
            self._status_badge.setStyleSheet("""
                background-color: #F3F3F3;
                color: #666666;
                padding: 3px 10px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            """)

    def update_counts(self, stats: dict[str, int]):
        self._pill_detected.val_label.setText(str(stats.get("DETECTED", 0)))
        self._pill_processing.val_label.setText(str(stats.get("PROCESSING", 0)))
        self._pill_waiting.val_label.setText(str(stats.get("WAITING_FOR_WINDOW", 0)))
        self._pill_completed.val_label.setText(str(stats.get("COMPLETED", 0)))
        self._pill_failed.val_label.setText(str(stats.get("FAILED", 0)))


class MainDashboardWidget(QWidget):
    """
    Top-level Main Dashboard widget showing all jobs, global KPIs,
    and unified system notification feed.
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
            "System Overview & Central Control for all Transfer Jobs", container
        )
        self._subtitle_label.setStyleSheet("color: #666666;")

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

        # ── KPI Overview Row ──
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(12)

        self._kpi_jobs = OverviewKpiCard("Total Jobs", "0", "Configured jobs", "#0078D4", container)
        self._kpi_monitoring = OverviewKpiCard("Active Monitors", "0", "Currently running", "#107C10", container)
        self._kpi_transferred = OverviewKpiCard("Total Transferred", "0", "Files completed", "#0099BC", container)
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

        self._empty_label = BodyLabel("No transfer jobs configured. Click '+ Add Job' above to get started.", container)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #888888; padding: 40px;")
        self._jobs_container.addWidget(self._empty_label)

        # ── Live Activity & Notifications Stream ──
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
        self._activity_table.setHorizontalHeaderLabels(["Timestamp", "Job", "Type", "Message"])
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
        job_stats: dict[str, dict[str, int]],
        monitoring_states: Optional[dict[str, bool]] = None,
        window_states: Optional[dict[str, bool]] = None,
    ) -> None:
        """Update all job cards and recalculate global KPIs."""
        mon_states = monitoring_states or {}
        win_states = window_states or {}

        # Clear existing cards
        for card in list(self._job_cards.values()):
            self._jobs_container.removeWidget(card)
            card.deleteLater()
        self._job_cards.clear()

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
            card = JobOverviewCard(job, self)
            card.open_workspace_clicked.connect(self.open_workspace_requested.emit)
            card.edit_clicked.connect(self.edit_job_requested.emit)
            card.delete_clicked.connect(self.delete_job_requested.emit)
            card.sync_clicked.connect(self.sync_job_requested.emit)
            card.toggle_monitor_clicked.connect(self.toggle_job_monitoring_requested.emit)

            is_mon = mon_states.get(job.id, False)
            in_win = win_states.get(job.id, True)
            card.update_status(is_mon, in_win)

            if is_mon:
                active_monitors += 1

            stats = job_stats.get(job.id, {})
            card.update_counts(stats)
            total_transferred += stats.get("COMPLETED", 0)
            total_issues += stats.get("FAILED", 0) + stats.get("CONFLICT", 0)

            self._job_cards[job.id] = card
            self._jobs_container.addWidget(card)

        self._kpi_jobs.set_value(str(len(jobs)), f"{len(jobs)} configured jobs")
        self._kpi_monitoring.set_value(str(active_monitors), f"{active_monitors} currently monitoring")
        self._kpi_transferred.set_value(str(total_transferred), "Files completed")
        self._kpi_issues.set_value(str(total_issues), "Failures or conflicts")

    def update_job_status(
        self, job_id: str, is_monitoring: bool, in_window: bool = True
    ) -> None:
        if job_id in self._job_cards:
            self._job_cards[job_id].update_status(is_monitoring, in_window)

    def update_job_counts(self, job_id: str, stats: dict[str, int]) -> None:
        if job_id in self._job_cards:
            self._job_cards[job_id].update_counts(stats)

    def add_activity_event(
        self, level: str, message: str, job_name: str = "System"
    ) -> None:
        """Add a new live event to the activity table."""
        row = 0
        self._activity_table.insertRow(row)

        time_str = datetime.now().strftime("%H:%M:%S")
        self._activity_table.setItem(row, 0, QTableWidgetItem(time_str))
        self._activity_table.setItem(row, 1, QTableWidgetItem(job_name))

        type_item = QTableWidgetItem(level.upper())
        if level.upper() in ("ERROR", "FAILED"):
            type_item.setForeground(QColor("#C42B1C"))
        elif level.upper() in ("SUCCESS", "COMPLETED"):
            type_item.setForeground(QColor("#107C10"))
        elif level.upper() in ("WARNING", "CONFLICT"):
            type_item.setForeground(QColor("#D83B01"))
        else:
            type_item.setForeground(QColor("#0078D4"))

        self._activity_table.setItem(row, 2, type_item)
        self._activity_table.setItem(row, 3, QTableWidgetItem(message))

        if self._activity_table.rowCount() > 200:
            self._activity_table.removeRow(self._activity_table.rowCount() - 1)

    def _clear_activity_feed(self) -> None:
        self._activity_table.setRowCount(0)
