"""
Dashboard widget for the File Transfer Automation System.

The central widget of the application that displays:
- Current job information
- Statistics cards with color-coded counts
- Warning banners for important states
- Transfer table with file status
- Control buttons (Start/Stop Monitoring, Sync Now)
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import FileStatus, TransferJob, TransferRecord
from gui.transfer_table import TransferTableWidget


class StatCard(QFrame):
    """A single statistics card showing a count and label."""

    def __init__(
        self,
        label: str,
        color: str = "#333333",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setStyleSheet(
            f"""
            StatCard {{
                background-color: {color};
                border-radius: 6px;
                padding: 8px;
                min-width: 80px;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        self._count_label = QLabel("0")
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._count_label.setFont(font)
        self._count_label.setStyleSheet("color: white;")
        layout.addWidget(self._count_label)

        self._name_label = QLabel(label)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet("color: rgba(255,255,255,0.85); font-size: 11px;")
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

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── Job Info Panel ──
        self._job_group = QGroupBox("Current Transfer Job")
        job_layout = QGridLayout()

        self._job_name_label = QLabel("No job configured")
        self._job_name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        job_layout.addWidget(QLabel("Job:"), 0, 0)
        job_layout.addWidget(self._job_name_label, 0, 1)

        self._source_label = QLabel("—")
        job_layout.addWidget(QLabel("Source:"), 1, 0)
        job_layout.addWidget(self._source_label, 1, 1)

        self._dest_label = QLabel("—")
        job_layout.addWidget(QLabel("Destination:"), 2, 0)
        job_layout.addWidget(self._dest_label, 2, 1)

        self._monitor_status_label = QLabel("OFF")
        self._monitor_status_label.setStyleSheet(
            "font-weight: bold; color: #EF5350;"
        )
        job_layout.addWidget(QLabel("Monitoring:"), 3, 0)
        job_layout.addWidget(self._monitor_status_label, 3, 1)

        self._job_group.setLayout(job_layout)
        layout.addWidget(self._job_group)

        # ── Statistics Cards ──
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(6)

        self._stat_cards: dict[str, StatCard] = {}
        card_configs = [
            ("DETECTED", "Detected", "#42A5F5"),
            ("PROCESSING", "Processing", "#FFA726"),
            ("READY", "Ready", "#66BB6A"),
            ("QUEUED", "Queued", "#29B6F6"),
            ("TRANSFERRING", "Transferring", "#26C6DA"),
            ("COMPLETED", "Completed", "#2E7D32"),
            ("FAILED", "Failed", "#E53935"),
            ("SKIPPED", "Skipped", "#757575"),
        ]

        for key, label, color in card_configs:
            card = StatCard(label, color)
            self._stat_cards[key] = card
            stats_layout.addWidget(card)

        layout.addLayout(stats_layout)

        # ── Warning Banner ──
        self._warning_frame = QFrame()
        self._warning_frame.setStyleSheet(
            """
            QFrame {
                background-color: #FFF3E0;
                border: 1px solid #FFB74D;
                border-radius: 4px;
                padding: 8px;
            }
            """
        )
        warning_layout = QHBoxLayout(self._warning_frame)
        warning_layout.setContentsMargins(8, 4, 8, 4)
        self._warning_icon = QLabel("⚠")
        self._warning_icon.setStyleSheet("font-size: 16px; color: #E65100;")
        warning_layout.addWidget(self._warning_icon)
        self._warning_text = QLabel("")
        self._warning_text.setStyleSheet("color: #E65100;")
        warning_layout.addWidget(self._warning_text)
        warning_layout.addStretch()
        self._warning_frame.setVisible(False)
        layout.addWidget(self._warning_frame)

        # ── Transfer Table ──
        self._transfer_table = TransferTableWidget(self)
        layout.addWidget(self._transfer_table, stretch=1)

        # ── Control Buttons ──
        controls = QHBoxLayout()

        self._btn_start = QPushButton("▶  Start Monitoring")
        self._btn_start.setMinimumHeight(36)
        self._btn_start.setStyleSheet(
            """
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #388E3C; }
            QPushButton:disabled { background-color: #666666; }
            """
        )
        self._btn_start.clicked.connect(self.start_monitoring_requested)
        controls.addWidget(self._btn_start)

        self._btn_stop = QPushButton("■  Stop Monitoring")
        self._btn_stop.setMinimumHeight(36)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            """
            QPushButton {
                background-color: #C62828;
                color: white;
                font-weight: bold;
                padding: 6px 16px;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #D32F2F; }
            QPushButton:disabled { background-color: #666666; }
            """
        )
        self._btn_stop.clicked.connect(self.stop_monitoring_requested)
        controls.addWidget(self._btn_stop)

        controls.addStretch()

        self._btn_sync = QPushButton("🔄  SYNC NOW")
        self._btn_sync.setMinimumHeight(36)
        self._btn_sync.setStyleSheet(
            """
            QPushButton {
                background-color: #1565C0;
                color: white;
                font-weight: bold;
                padding: 6px 24px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #1976D2; }
            QPushButton:disabled { background-color: #666666; }
            """
        )
        self._btn_sync.clicked.connect(self.sync_now_requested)
        controls.addWidget(self._btn_sync)

        layout.addLayout(controls)

    # ── Public update methods ──

    def update_job_info(self, job: Optional[TransferJob]) -> None:
        """Update the job information panel."""
        if job:
            self._job_name_label.setText(job.name)
            self._source_label.setText(job.source_folder)
            self._dest_label.setText(job.destination_folder)
        else:
            self._job_name_label.setText("No job configured")
            self._source_label.setText("—")
            self._dest_label.setText("—")

    def update_monitoring_status(self, is_monitoring: bool) -> None:
        """Update the monitoring status indicator and button states."""
        if is_monitoring:
            self._monitor_status_label.setText("ON — MONITORING")
            self._monitor_status_label.setStyleSheet(
                "font-weight: bold; color: #2E7D32;"
            )
            self._btn_start.setEnabled(False)
            self._btn_stop.setEnabled(True)
        else:
            self._monitor_status_label.setText("OFF")
            self._monitor_status_label.setStyleSheet(
                "font-weight: bold; color: #EF5350;"
            )
            self._btn_start.setEnabled(True)
            self._btn_stop.setEnabled(False)

    def update_statistics(self, stats: dict[str, int]) -> None:
        """Update the statistics cards."""
        for key, card in self._stat_cards.items():
            card.set_count(stats.get(key, 0))

        # Update warning banner
        processing = stats.get("PROCESSING", 0)
        failed = stats.get("FAILED", 0)
        completed = stats.get("COMPLETED", 0)

        if failed > 0:
            self._warning_frame.setVisible(True)
            self._warning_frame.setStyleSheet(
                """
                QFrame {
                    background-color: #FFEBEE;
                    border: 1px solid #EF5350;
                    border-radius: 4px;
                    padding: 8px;
                }
                """
            )
            self._warning_icon.setText("❌")
            self._warning_icon.setStyleSheet("font-size: 16px; color: #C62828;")
            self._warning_text.setText(f"{failed} transfer(s) failed")
            self._warning_text.setStyleSheet("color: #C62828;")
        elif processing > 0:
            self._warning_frame.setVisible(True)
            self._warning_frame.setStyleSheet(
                """
                QFrame {
                    background-color: #FFF3E0;
                    border: 1px solid #FFB74D;
                    border-radius: 4px;
                    padding: 8px;
                }
                """
            )
            self._warning_icon.setText("⚠")
            self._warning_icon.setStyleSheet("font-size: 16px; color: #E65100;")
            self._warning_text.setText(
                f"{processing} file(s) still being processed"
            )
            self._warning_text.setStyleSheet("color: #E65100;")
        elif completed > 0:
            self._warning_frame.setVisible(True)
            self._warning_frame.setStyleSheet(
                """
                QFrame {
                    background-color: #E8F5E9;
                    border: 1px solid #66BB6A;
                    border-radius: 4px;
                    padding: 8px;
                }
                """
            )
            self._warning_icon.setText("✓")
            self._warning_icon.setStyleSheet("font-size: 16px; color: #2E7D32;")
            self._warning_text.setText(
                f"{completed} file(s) successfully transferred"
            )
            self._warning_text.setStyleSheet("color: #2E7D32;")
        else:
            self._warning_frame.setVisible(False)

    def update_record(self, record: TransferRecord) -> None:
        """Update a single record in the transfer table."""
        self._transfer_table.update_record(record)

    def set_records(self, records: list[TransferRecord]) -> None:
        """Replace all records in the transfer table."""
        self._transfer_table.set_records(records)

    @property
    def transfer_table(self) -> TransferTableWidget:
        return self._transfer_table
