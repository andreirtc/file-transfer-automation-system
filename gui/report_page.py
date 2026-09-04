"""
Corporate TFSPH Daily Backup Checklist & Report Interface.

Provides:
- Real-time interactive preview of the daily backup checklist
- Date selector with CalendarPicker
- Manual and automated Excel (.xlsx) report generation using the corporate template
- Live evaluation of Daily Control Checks 1-7
- Supervisor Master Checklist Configurator Dialog to add/edit/remove monitored systems
  and configure sign-off metadata (defaults to Philip M. Bayudan).
"""

from __future__ import annotations

import getpass
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CalendarPicker,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBoxBase,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SimpleCardWidget,
    SubtitleLabel,
    SwitchButton,
    TableWidget,
    TitleLabel,
)

from services.configuration_service import ConfigurationService, _DEFAULT_CHECKLIST_SYSTEMS
from services.report_service import ReportService

logger = logging.getLogger("app")


class ChecklistConfigDialog(MessageBoxBase):
    """
    Supervisor Master Checklist Configurator.
    Allows IT supervisors to add, edit, remove checklist systems and
    configure default sign-off names.
    """

    def __init__(
        self,
        config: ConfigurationService,
        db: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._config = config
        self._db = db
        self._available_jobs = [j.name for j in self._db.get_jobs()] if (self._db and hasattr(self._db, "get_jobs")) else []

        self.yesButton.setText("Save Configuration")
        self.cancelButton.setText("Cancel")

        self.titleLabel = SubtitleLabel("Checklist Master Configuration", self)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(8)

        desc = BodyLabel(
            "Configure the master systems list for the TFSPH Daily Backup Checklist.\n"
            "Systems can be added, modified, or mapped to specific transfer jobs for testing.",
            self,
        )
        desc.setStyleSheet("color: #616161; font-size: 13px;")
        self.viewLayout.addWidget(desc)
        self.viewLayout.addSpacing(12)

        self.widget.setMinimumWidth(920)
        self.widget.setMinimumHeight(580)

        # Settings Form: Checked By & Auto Generate
        form = QFormLayout()
        form.setSpacing(10)

        self._checked_by_edit = LineEdit(self)
        self._checked_by_edit.setText(config.report_checked_by)
        self._checked_by_edit.setPlaceholderText("e.g. Philip M. Bayudan")
        form.addRow(BodyLabel("Checked By (Supervisor):", self), self._checked_by_edit)

        self._repo_tag_edit = LineEdit(self)
        self._repo_tag_edit.setText(config.report_repository_tag)
        self._repo_tag_edit.setPlaceholderText("e.g. TFSPH-PRIMARY-REPO")
        form.addRow(BodyLabel("Backup Repository Tag:", self), self._repo_tag_edit)

        self._auto_gen_switch = SwitchButton("Auto-generate report", self)
        self._auto_gen_switch.setOnText("Enabled (auto-export when window transfers complete)")
        self._auto_gen_switch.setOffText("Disabled")
        self._auto_gen_switch.setChecked(config.report_auto_generate)
        form.addRow(BodyLabel("Automatic Generation:", self), self._auto_gen_switch)

        self.viewLayout.addLayout(form)
        self.viewLayout.addSpacing(14)

        # Systems Table Toolbar
        tbl_bar = QHBoxLayout()
        tbl_bar.addWidget(SubtitleLabel("Monitored Systems", self))
        tbl_bar.addStretch()

        btn_add = PushButton("Add System", self, FluentIcon.ADD)
        btn_add.clicked.connect(self._on_add_row)
        tbl_bar.addWidget(btn_add)

        btn_delete = PushButton("Delete Selected", self, FluentIcon.DELETE)
        btn_delete.clicked.connect(self._on_delete_row)
        tbl_bar.addWidget(btn_delete)

        btn_reset = PushButton("Reset Defaults", self, FluentIcon.SYNC)
        btn_reset.clicked.connect(self._on_reset_defaults)
        tbl_bar.addWidget(btn_reset)

        self.viewLayout.addLayout(tbl_bar)

        # Systems Table
        self._table = TableWidget(self)
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "No.",
            "Corporate System",
            "Linked App Job (Mapping)",
            "Filename Pattern",
            "File Type",
            "Content / Description",
            "Expected Location",
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self._table.setMinimumHeight(240)

        self._load_systems(self._config.checklist_systems)
        self.viewLayout.addWidget(self._table)

    def _load_systems(self, systems: list[dict[str, Any]]) -> None:
        self._table.setRowCount(len(systems))
        for r, sys_item in enumerate(systems):
            no_item = QTableWidgetItem(str(sys_item.get("no", r + 1)))
            no_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r, 0, no_item)

            self._table.setItem(r, 1, QTableWidgetItem(sys_item.get("job_name", "")))

            # Linked Job Dropdown
            combo = ComboBox(self)
            combo.addItem("(Match by Name)")
            for jname in self._available_jobs:
                combo.addItem(jname)
            curr_linked = sys_item.get("linked_job", "")
            if curr_linked and curr_linked in self._available_jobs:
                combo.setCurrentText(curr_linked)
            else:
                combo.setCurrentIndex(0)
            self._table.setCellWidget(r, 2, combo)

            self._table.setItem(r, 3, QTableWidgetItem(sys_item.get("pattern", "")))

            type_item = QTableWidgetItem(sys_item.get("file_type", "FILE"))
            type_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r, 4, type_item)

            self._table.setItem(r, 5, QTableWidgetItem(sys_item.get("description", "")))
            self._table.setItem(r, 6, QTableWidgetItem(sys_item.get("expected_location", "")))

    def _on_add_row(self) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        no_item = QTableWidgetItem(str(r + 1))
        no_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(r, 0, no_item)
        self._table.setItem(r, 1, QTableWidgetItem(f"SYSTEM{r + 1}"))

        combo = ComboBox(self)
        combo.addItem("(Match by Name)")
        for jname in self._available_jobs:
            combo.addItem(jname)
        combo.setCurrentIndex(0)
        self._table.setCellWidget(r, 2, combo)

        self._table.setItem(r, 3, QTableWidgetItem(f"SYSTEM{r + 1}_<YYYYMMDD>"))
        type_item = QTableWidgetItem("ZIP")
        type_item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(r, 4, type_item)
        self._table.setItem(r, 5, QTableWidgetItem("System Backup"))
        self._table.setItem(r, 6, QTableWidgetItem(""))

    def _on_delete_row(self) -> None:
        curr = self._table.currentRow()
        if curr >= 0:
            self._table.removeRow(curr)
            # Re-number
            for i in range(self._table.rowCount()):
                item = self._table.item(i, 0)
                if item:
                    item.setText(str(i + 1))

    def _on_reset_defaults(self) -> None:
        self._load_systems(_DEFAULT_CHECKLIST_SYSTEMS)
        self._checked_by_edit.setText("Philip M. Bayudan")
        self._repo_tag_edit.setText("TFSPH-PRIMARY-REPO")

    def validate(self) -> bool:
        # Collect systems from table
        systems = []
        for r in range(self._table.rowCount()):
            no_val = r + 1
            job_name = self._table.item(r, 1).text().strip() if self._table.item(r, 1) else ""

            combo = self._table.cellWidget(r, 2)
            linked_job = combo.currentText().strip() if combo else ""
            if linked_job in ("(Match by Name)", "(None)", ""):
                linked_job = ""

            pattern = self._table.item(r, 3).text().strip() if self._table.item(r, 3) else ""
            file_type = self._table.item(r, 4).text().strip() if self._table.item(r, 4) else "FILE"
            desc = self._table.item(r, 5).text().strip() if self._table.item(r, 5) else ""
            exp_loc = self._table.item(r, 6).text().strip() if self._table.item(r, 6) else ""

            if not job_name:
                job_name = f"System {no_val}"
            if not pattern:
                pattern = f"{job_name}_<YYYYMMDD>"

            systems.append({
                "no": no_val,
                "job_name": job_name,
                "linked_job": linked_job,
                "pattern": pattern,
                "file_type": file_type,
                "description": desc,
                "expected_location": exp_loc,
            })

        self._config.checklist_systems = systems
        self._config.report_checked_by = self._checked_by_edit.text().strip() or "Philip M. Bayudan"
        self._config.report_repository_tag = self._repo_tag_edit.text().strip() or "TFSPH-PRIMARY-REPO"
        self._config.report_auto_generate = self._auto_gen_switch.isChecked()
        self._config.save()
        return True


class ReportPageWidget(QWidget):
    """
    Dedicated in-app Daily Backup Checklist Report View & Generator.
    """

    def __init__(
        self,
        report_service: ReportService,
        config: ConfigurationService,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._report_service = report_service
        self._config = config
        self.setObjectName("DailyReportInterface")

        self._setup_ui()
        self._refresh_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(16)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        self._title = TitleLabel("TFSPH Daily Backup Checklist & Executive Report", self)
        self._subtitle = BodyLabel(
            "Audit-ready corporate daily backup checklist and verification sign-off sheet.",
            self,
        )
        self._subtitle.setStyleSheet("color: #616161; font-size: 13px;")
        title_box.addWidget(self._title)
        title_box.addWidget(self._subtitle)
        root_layout.addLayout(title_box)

        # Scroll Area for the entire page content
        self._scroll = ScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self._container_layout = QVBoxLayout(container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(16)

        # 1. Action & Toolbar Card
        self._setup_toolbar()

        # 2. Statistics Summary Cards
        self._setup_stat_cards()

        # 3. Master Verification Table (Table 1)
        self._setup_table()

        # 4. Daily Control Checks & Sign-Off Section
        self._setup_checks_and_signoff()

        self._scroll.setWidget(container)
        root_layout.addWidget(self._scroll)

    def _setup_toolbar(self) -> None:
        card = SimpleCardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(14)

        # Row 1: Date Picker, Operator, Repo Tag
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        # Date Picker
        date_box = QVBoxLayout()
        date_box.setSpacing(4)
        date_box.addWidget(CaptionLabel("Batch Date:", self))
        self._date_picker = CalendarPicker(self)
        self._date_picker.setDate(QDate.currentDate())
        self._date_picker.dateChanged.connect(self._on_date_changed)
        date_box.addWidget(self._date_picker)
        row1.addLayout(date_box)

        # Operator Field
        op_box = QVBoxLayout()
        op_box.setSpacing(4)
        op_box.addWidget(CaptionLabel("Batch Operator:", self))
        self._operator_edit = LineEdit(self)
        default_op = self._config.report_operator_name.strip()
        if not default_op:
            try:
                default_op = getpass.getuser().upper()
            except Exception:
                default_op = "OPERATOR"
        self._operator_edit.setText(default_op)
        self._operator_edit.textChanged.connect(self._on_operator_changed)
        op_box.addWidget(self._operator_edit)
        row1.addLayout(op_box)

        # Repo Tag Field
        repo_box = QVBoxLayout()
        repo_box.setSpacing(4)
        repo_box.addWidget(CaptionLabel("Backup Repository Tag:", self))
        self._repo_tag_edit = LineEdit(self)
        self._repo_tag_edit.setText(self._config.report_repository_tag)
        self._repo_tag_edit.textChanged.connect(self._on_repo_tag_changed)
        repo_box.addWidget(self._repo_tag_edit)
        row1.addLayout(repo_box)

        card_layout.addLayout(row1)

        # Row 2: Action Buttons
        row2 = QHBoxLayout()
        row2.setSpacing(12)

        self._btn_generate = PrimaryPushButton(
            "Generate Report (.xlsx)", self, FluentIcon.DOCUMENT
        )
        self._btn_generate.setFixedHeight(36)
        self._btn_generate.clicked.connect(self._on_generate_clicked)
        row2.addWidget(self._btn_generate)

        self._btn_open_folder = PushButton(
            "Open Reports Folder", self, FluentIcon.FOLDER
        )
        self._btn_open_folder.setFixedHeight(36)
        self._btn_open_folder.clicked.connect(self._on_open_folder_clicked)
        row2.addWidget(self._btn_open_folder)

        self._btn_config = PushButton(
            "Configure Checklist", self, FluentIcon.SETTING
        )
        self._btn_config.setFixedHeight(36)
        self._btn_config.clicked.connect(self._on_config_clicked)
        row2.addWidget(self._btn_config)

        self._btn_refresh = PushButton(
            "Refresh Data", self, FluentIcon.SYNC
        )
        self._btn_refresh.setFixedHeight(36)
        self._btn_refresh.clicked.connect(self._refresh_data)
        row2.addWidget(self._btn_refresh)

        row2.addStretch()
        card_layout.addLayout(row2)

        self._container_layout.addWidget(card)

    def _setup_stat_cards(self) -> None:
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(12)

        self._card_total = self._create_stat_card("Total Systems", "0", FluentIcon.TILES, "#0078D4")
        self._card_verified = self._create_stat_card("Verified", "0", FluentIcon.COMPLETED, "#107C10")
        self._card_pending = self._create_stat_card("Pending", "0", FluentIcon.HISTORY, "#CA5010")
        self._card_failed = self._create_stat_card("Failed / Exceptions", "0", FluentIcon.INFO, "#C42B1C")

        stats_layout.addWidget(self._card_total)
        stats_layout.addWidget(self._card_verified)
        stats_layout.addWidget(self._card_pending)
        stats_layout.addWidget(self._card_failed)

        self._container_layout.addLayout(stats_layout)

    def _create_stat_card(
        self, title: str, value: str, icon: FluentIcon, accent_color: str
    ) -> SimpleCardWidget:
        card = SimpleCardWidget(self)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(12)

        icon_widget = IconWidget(icon, self)
        icon_widget.setFixedSize(28, 28)
        card_layout.addWidget(icon_widget)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        val_label = SubtitleLabel(value, self)
        val_label.setStyleSheet(f"color: {accent_color}; font-size: 20px; font-weight: bold;")
        title_label = CaptionLabel(title, self)
        title_label.setStyleSheet("color: #616161;")

        text_layout.addWidget(val_label)
        text_layout.addWidget(title_label)
        card_layout.addLayout(text_layout)
        card_layout.addStretch()

        card._val_label = val_label
        return card

    def _setup_table(self) -> None:
        card = SimpleCardWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.addWidget(SubtitleLabel("Table 1: Backup Verification Details", self))
        header_row.addStretch()
        lbl_hint = CaptionLabel("Columns match the corporate Excel template layout", self)
        lbl_hint.setStyleSheet("color: #797775;")
        header_row.addWidget(lbl_hint)
        card_layout.addLayout(header_row)

        self._table = TableWidget(self)
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "No.",
            "Backup Filename Pattern",
            "File Type",
            "Content / Description",
            "Expected Location",
            "File Size",
            "Completed",
            "Status",
            "Integrity Check",
            "Remarks / Exception",
        ])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(8, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.Stretch)
        self._table.setMinimumHeight(280)

        card_layout.addWidget(self._table)
        self._container_layout.addWidget(card)

    def _setup_checks_and_signoff(self) -> None:
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        # Section 2: Daily Control Checks Live Status
        checks_card = SimpleCardWidget(self)
        checks_layout = QVBoxLayout(checks_card)
        checks_layout.setContentsMargins(16, 16, 16, 16)
        checks_layout.setSpacing(10)

        checks_header = QHBoxLayout()
        checks_header.addWidget(SubtitleLabel("Section 2: Daily Control Checks", self))
        checks_header.addStretch()
        checks_layout.addLayout(checks_header)

        self._checks_table = TableWidget(self)
        self._checks_table.setColumnCount(4)
        self._checks_table.setHorizontalHeaderLabels([
            "No.",
            "Control Check",
            "Result",
            "Remarks",
        ])
        c_hdr = self._checks_table.horizontalHeader()
        c_hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        c_hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        c_hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        c_hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        self._checks_table.setMinimumHeight(230)
        checks_layout.addWidget(self._checks_table)

        split_layout.addWidget(checks_card, 65)

        # Section 3: Sign-Off & Approval Summary
        signoff_card = SimpleCardWidget(self)
        signoff_layout = QVBoxLayout(signoff_card)
        signoff_layout.setContentsMargins(16, 16, 16, 16)
        signoff_layout.setSpacing(12)

        signoff_layout.addWidget(SubtitleLabel("Section 3: Sign-Off & Approval", self))

        self._signoff_prep = BodyLabel("Prepared By (Operator):", self)
        self._signoff_prep_val = SubtitleLabel("-", self)
        self._signoff_prep_val.setStyleSheet("color: #0078D4; font-size: 15px; font-weight: bold;")

        self._signoff_chk = BodyLabel("Checked By (Supervisor):", self)
        self._signoff_chk_val = SubtitleLabel("Philip M. Bayudan", self)
        self._signoff_chk_val.setStyleSheet("color: #107C10; font-size: 15px; font-weight: bold;")

        self._signoff_status = CaptionLabel(
            "Values will automatically sign the exported daily checklist Excel sheet.",
            self,
        )
        self._signoff_status.setStyleSheet("color: #616161;")

        signoff_layout.addWidget(self._signoff_prep)
        signoff_layout.addWidget(self._signoff_prep_val)
        signoff_layout.addSpacing(6)
        signoff_layout.addWidget(self._signoff_chk)
        signoff_layout.addWidget(self._signoff_chk_val)
        signoff_layout.addSpacing(6)
        signoff_layout.addWidget(self._signoff_status)
        signoff_layout.addStretch()

        split_layout.addWidget(signoff_card, 35)

        self._container_layout.addLayout(split_layout)

    def _selected_py_date(self) -> date:
        qd = self._date_picker.getDate()
        if qd.isValid() and qd.year() > 2000:
            return date(qd.year(), qd.month(), qd.day())
        return datetime.now().date()

    def _on_date_changed(self, qdate: QDate) -> None:
        self._refresh_data()

    def _on_operator_changed(self, text: str) -> None:
        self._signoff_prep_val.setText(text.strip() or "OPERATOR")

    def _on_repo_tag_changed(self, text: str) -> None:
        pass

    def _refresh_data(self) -> None:
        target_date = self._selected_py_date()
        try:
            data = self._report_service.get_report_data(target_date)
        except Exception as e:
            logger.error("Failed to load report data: %s", e)
            return

        logger.info("Daily Report UI refreshed for %s (%d rows)", target_date, len(data.get("table_rows", [])))

        # Update Sign-Off Labels
        op_name = self._operator_edit.text().strip() or data["batch_operator"]
        self._signoff_prep_val.setText(op_name)
        self._signoff_chk_val.setText(self._config.report_checked_by)

        # Update Table 1 Rows
        rows = data["table_rows"]
        self._table.setRowCount(len(rows))

        verified_cnt = 0
        pending_cnt = 0
        failed_cnt = 0

        for r_idx, r_data in enumerate(rows):
            # 0: No
            item_no = QTableWidgetItem(str(r_data["no"]))
            item_no.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r_idx, 0, item_no)

            # 1: Pattern
            self._table.setItem(r_idx, 1, QTableWidgetItem(r_data["pattern"]))

            # 2: Type
            item_type = QTableWidgetItem(r_data["file_type"])
            item_type.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r_idx, 2, item_type)

            # 3: Description
            self._table.setItem(r_idx, 3, QTableWidgetItem(r_data["description"]))

            # 4: Expected Location
            self._table.setItem(r_idx, 4, QTableWidgetItem(r_data["expected_location"]))

            # 5: File Size
            item_size = QTableWidgetItem(r_data["file_size"])
            item_size.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r_idx, 5, item_size)

            # 6: Completed Time
            item_time = QTableWidgetItem(r_data["completion_time"])
            item_time.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(r_idx, 6, item_time)

            # 7: Verification Status (Color Coded)
            status_str = r_data["verification_status"]
            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignCenter)
            if status_str == "Verified":
                item_status.setForeground(QColor("#107C10"))
                verified_cnt += 1
            elif status_str == "Failed":
                item_status.setForeground(QColor("#C42B1C"))
                failed_cnt += 1
            elif status_str == "Not Applicable":
                item_status.setForeground(QColor("#797775"))
            else:
                item_status.setForeground(QColor("#CA5010"))
                pending_cnt += 1
            self._table.setItem(r_idx, 7, item_status)

            # 8: Integrity Check
            integ_str = r_data["integrity_check"]
            item_integ = QTableWidgetItem(integ_str)
            item_integ.setTextAlignment(Qt.AlignCenter)
            if integ_str == "Passed":
                item_integ.setForeground(QColor("#107C10"))
            elif integ_str == "Failed":
                item_integ.setForeground(QColor("#C42B1C"))
            else:
                item_integ.setForeground(QColor("#797775"))
            self._table.setItem(r_idx, 8, item_integ)

            # 9: Remarks
            self._table.setItem(r_idx, 9, QTableWidgetItem(r_data["remarks"]))

        # Update Stat Cards
        self._card_total._val_label.setText(str(len(rows)))
        self._card_verified._val_label.setText(str(verified_cnt))
        self._card_pending._val_label.setText(str(pending_cnt))
        self._card_failed._val_label.setText(str(failed_cnt))

        # Update Section 2: Control Checks
        checks = data["control_checks"]
        self._checks_table.setRowCount(len(checks))
        for c_idx, c_data in enumerate(checks):
            item_cno = QTableWidgetItem(str(c_data["no"]))
            item_cno.setTextAlignment(Qt.AlignCenter)
            self._checks_table.setItem(c_idx, 0, item_cno)

            self._checks_table.setItem(c_idx, 1, QTableWidgetItem(c_data["check"]))

            res_str = c_data["result"]
            item_res = QTableWidgetItem(res_str)
            item_res.setTextAlignment(Qt.AlignCenter)
            if res_str == "Yes":
                item_res.setForeground(QColor("#107C10"))
            elif res_str == "No":
                item_res.setForeground(QColor("#C42B1C"))
            elif res_str == "Not Applicable":
                item_res.setForeground(QColor("#797775"))
            else:
                item_res.setForeground(QColor("#CA5010"))
            self._checks_table.setItem(c_idx, 2, item_res)

            self._checks_table.setItem(c_idx, 3, QTableWidgetItem(c_data["remarks"]))

    def _on_generate_clicked(self) -> None:
        target_date = self._selected_py_date()
        op_name = self._operator_edit.text().strip()
        repo_tag = self._repo_tag_edit.text().strip()
        chk_by = self._config.report_checked_by

        try:
            out_file = self._report_service.generate_daily_report(
                report_date=target_date,
                operator_name=op_name,
                checked_by=chk_by,
                repository_tag=repo_tag,
            )

            if "_latest" in out_file.name:
                InfoBar.warning(
                    title="Excel File Already Open",
                    content=f"Primary file was locked by Excel. Saved update to: {out_file.name}. Close Excel to allow overwriting.",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=6000,
                    parent=self,
                )
            else:
                InfoBar.success(
                    title="Report Generated Successfully",
                    content=f"Saved corporate checklist to: {out_file.name}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self,
                )
            # Try to open the file directly in Excel if possible
            if sys.platform == "win32":
                try:
                    os.startfile(str(out_file))
                except Exception:
                    pass
        except Exception as e:
            logger.exception("Report generation error: %s", e)
            InfoBar.error(
                title="Generation Failed",
                content=f"Error generating checklist: {e}",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=6000,
                parent=self,
            )

    def _on_open_folder_clicked(self) -> None:
        folder = self._report_service.reports_dir
        if sys.platform == "win32":
            try:
                os.startfile(str(folder))
            except Exception as e:
                logger.warning("Could not open reports folder: %s", e)

    def _on_config_clicked(self) -> None:
        dialog = ChecklistConfigDialog(self._config, self._report_service._db, self.window())
        if dialog.exec():
            self._signoff_chk_val.setText(self._config.report_checked_by)
            self._repo_tag_edit.setText(self._config.report_repository_tag)
            self._refresh_data()
            InfoBar.success(
                title="Configuration Saved",
                content="Checklist master systems and sign-off settings updated.",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500,
                parent=self,
            )
