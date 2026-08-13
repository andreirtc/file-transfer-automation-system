"""
Dashboard widget for the File Transfer Automation System.
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    SimpleCardWidget,
    CardWidget,
    PrimaryPushButton,
    PushButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    StrongBodyLabel,
    BodyLabel,
    TitleLabel,
    SubtitleLabel,
    ComboBox
)

from core.models import FileStatus, TransferJob, TransferRecord
from gui.transfer_table import TransferTableWidget


class StatCard(SimpleCardWidget):
    """A single statistics card showing a count and label."""

    def __init__(
        self,
        label: str,
        color: str = "#333333",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setStyleSheet(f"""
            StatCard {{
                border-left: 4px solid {color};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        self._count_label = TitleLabel("0", self)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._count_label)

        self._name_label = BodyLabel(label.upper(), self)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        font = self._name_label.font()
        font.setBold(True)
        self._name_label.setFont(font)
        self._name_label.setStyleSheet("color: #666666;")
        layout.addWidget(self._name_label)

    def set_count(self, count: int) -> None:
        self._count_label.setText(str(count))


class DashboardWidget(QWidget):
    """
    Main dashboard showing job info, statistics, warnings, and transfer table.
    """

    start_monitoring_requested = Signal()
    stop_monitoring_requested = Signal()
    sync_now_requested = Signal()
    force_start_requested = Signal(str)
    job_switched = Signal(str) # job id

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # ── Job Info Panel ──
        self._job_group = SimpleCardWidget(self)
        job_layout = QGridLayout(self._job_group)
        job_layout.setContentsMargins(16, 16, 16, 16)
        job_layout.setVerticalSpacing(8)

        job_layout.addWidget(StrongBodyLabel("Job:", self._job_group), 0, 0)
        self.job_combo = ComboBox(self._job_group)
        self.job_combo.setMinimumWidth(200)
        self.job_combo.currentIndexChanged.connect(self._on_job_combo_changed)
        job_layout.addWidget(self.job_combo, 0, 1)

        job_layout.addWidget(StrongBodyLabel("Source:", self._job_group), 1, 0)
        self._source_label = BodyLabel("—", self._job_group)
        job_layout.addWidget(self._source_label, 1, 1)

        job_layout.addWidget(StrongBodyLabel("Destination:", self._job_group), 2, 0)
        self._dest_label = BodyLabel("—", self._job_group)
        job_layout.addWidget(self._dest_label, 2, 1)

        job_layout.addWidget(StrongBodyLabel("Monitoring:", self._job_group), 3, 0)
        self._monitor_status_label = BodyLabel("OFF", self._job_group)
        self._monitor_status_label.setStyleSheet("color: #C42B1C; font-weight: bold;")
        job_layout.addWidget(self._monitor_status_label, 3, 1)

        layout.addWidget(self._job_group)

        # ── Statistics Cards ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self._stat_cards: dict[str, StatCard] = {}
        card_configs = [
            ("DETECTED", "Detected", "#0078D4"),
            ("PROCESSING", "Processing", "#D83B01"),
            ("READY", "Ready", "#107C10"),
            ("QUEUED", "Queued", "#005FB8"),
            ("TRANSFERRING", "Transferring", "#00B7C3"),
            ("COMPLETED", "Completed", "#107C10"),
            ("FAILED", "Failed", "#C42B1C"),
            ("SKIPPED", "Skipped", "#797775"),
        ]

        for key, label, color in card_configs:
            card = StatCard(label, color, self)
            self._stat_cards[key] = card
            stats_layout.addWidget(card)

        layout.addLayout(stats_layout)

        # ── Warning Banner Container ──
        self._warning_layout = QVBoxLayout()
        self._warning_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._warning_layout)
        self._current_info_bar = None

        # ── Transfer Table ──
        self._transfer_table = TransferTableWidget(self)
        self._transfer_table.force_start_requested.connect(self.force_start_requested)
        layout.addWidget(self._transfer_table, stretch=1)

        # ── Control Buttons ──
        controls = QHBoxLayout()
        controls.setSpacing(12)

        self._btn_start = PushButton(FluentIcon.PLAY, "Start Monitoring", self)
        self._btn_start.clicked.connect(self.start_monitoring_requested)
        controls.addWidget(self._btn_start)

        self._btn_stop = PushButton(FluentIcon.PAUSE, "Stop Monitoring", self)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self.stop_monitoring_requested)
        controls.addWidget(self._btn_stop)

        controls.addStretch()

        self._btn_sync = PrimaryPushButton(FluentIcon.SYNC, "SYNC NOW", self)
        self._btn_sync.clicked.connect(self.sync_now_requested)
        controls.addWidget(self._btn_sync)

        layout.addLayout(controls)

    # ── Public update methods ──

    def update_job_info(self, job: Optional[TransferJob]) -> None:
        """Update the job information panel."""
        # Block signals to prevent triggering the combo box changed event
        self.job_combo.blockSignals(True)
        
        if job:
            # Set the combo box to the correct job if it's already in the list
            idx = self.job_combo.findData(job.id)
            if idx >= 0:
                self.job_combo.setCurrentIndex(idx)
            
            self._source_label.setText(job.source_folder)
            self._dest_label.setText(job.destination_folder)
        else:
            self.job_combo.clear()
            self._source_label.setText("—")
            self._dest_label.setText("—")
            
        self.job_combo.blockSignals(False)

    def update_job_list(self, jobs: list[TransferJob], current_job_id: Optional[str]) -> None:
        self.job_combo.blockSignals(True)
        self.job_combo.clear()
        
        if not jobs:
            self.job_combo.addItem("No job configured", userData=None)
        else:
            for job in jobs:
                self.job_combo.addItem(job.name, userData=job.id)
                
            if current_job_id:
                idx = self.job_combo.findData(current_job_id)
                if idx >= 0:
                    self.job_combo.setCurrentIndex(idx)
                    
        self.job_combo.blockSignals(False)

    def _on_job_combo_changed(self, index: int) -> None:
        job_id = self.job_combo.currentData()
        if job_id:
            self.job_switched.emit(job_id)

    def update_monitoring_status(self, is_monitoring: bool) -> None:
        """Update the monitoring status indicator and button states."""
        if is_monitoring:
            self._monitor_status_label.setText("ON — MONITORING")
            self._monitor_status_label.setStyleSheet("color: #107C10; font-weight: bold;")
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
        else:
            self._monitor_status_label.setText("OFF")
            self._monitor_status_label.setStyleSheet("color: #C42B1C; font-weight: bold;")
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)

    def _clear_info_bar(self):
        if self._current_info_bar:
            self._current_info_bar.deleteLater()
            self._current_info_bar = None

    def update_statistics(self, stats: dict[str, int]) -> None:
        """Update the statistics cards."""
        for key, card in self._stat_cards.items():
            card.set_count(stats.get(key, 0))

        # Update warning banner
        processing = stats.get("PROCESSING", 0)
        failed = stats.get("FAILED", 0)
        completed = stats.get("COMPLETED", 0)

        self._clear_info_bar()

        if failed > 0:
            self._current_info_bar = InfoBar.error(
                title="Errors Detected",
                content=f"{failed} transfer(s) failed.",
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.NONE,
                duration=-1,
                parent=self
            )
            self._warning_layout.addWidget(self._current_info_bar)
        elif processing > 0:
            self._current_info_bar = InfoBar.warning(
                title="Processing",
                content=f"{processing} file(s) still being processed.",
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.NONE,
                duration=-1,
                parent=self
            )
            self._warning_layout.addWidget(self._current_info_bar)
        elif completed > 0:
            self._current_info_bar = InfoBar.success(
                title="Transfers Complete",
                content=f"{completed} file(s) successfully transferred.",
                orient=Qt.Orientation.Horizontal,
                isClosable=False,
                position=InfoBarPosition.NONE,
                duration=-1,
                parent=self
            )
            self._warning_layout.addWidget(self._current_info_bar)

    def update_record(self, record: TransferRecord) -> None:
        """Update a single record in the transfer table."""
        self._transfer_table.update_record(record)

    def set_records(self, records: list[TransferRecord]) -> None:
        """Replace all records in the transfer table."""
        self._transfer_table.set_records(records)

    @property
    def transfer_table(self) -> TransferTableWidget:
        return self._transfer_table
