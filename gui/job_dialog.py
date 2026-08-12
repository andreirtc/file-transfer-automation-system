"""
Job configuration dialog for the File Transfer Automation System.

Allows the user to create or edit a transfer job by specifying
the job name, source folder, destination folder, and options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    MessageBoxBase,
    LineEdit,
    PushButton,
    SwitchButton,
    MessageBox,
    SubtitleLabel,
    BodyLabel
)

from core.models import TransferJob


class JobDialog(MessageBoxBase):
    """Dialog for creating or editing a transfer job."""

    def __init__(
        self,
        job: Optional[TransferJob] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._job = job or TransferJob()
        self._is_new = job is None

        title = "Add Transfer Job" if self._is_new else "Edit Transfer Job"
        self.titleLabel = SubtitleLabel(title, self)
        
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")
        self.widget.setMinimumWidth(550)

        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        # Add title
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)

        form = QFormLayout()

        # Job name
        self._name_edit = LineEdit(self)
        self._name_edit.setPlaceholderText("e.g., Local Test Transfer")
        form.addRow(BodyLabel("Job Name:", self), self._name_edit)

        # Source folder
        source_layout = QHBoxLayout()
        self._source_edit = LineEdit(self)
        self._source_edit.setPlaceholderText("Source folder path")
        source_layout.addWidget(self._source_edit)
        btn_source = PushButton("Browse...", self)
        btn_source.clicked.connect(self._browse_source)
        source_layout.addWidget(btn_source)
        form.addRow(BodyLabel("Source Folder:", self), source_layout)

        # Destination folder
        dest_layout = QHBoxLayout()
        self._dest_edit = LineEdit(self)
        self._dest_edit.setPlaceholderText("Destination folder path")
        dest_layout.addWidget(self._dest_edit)
        btn_dest = PushButton("Browse...", self)
        btn_dest.clicked.connect(self._browse_dest)
        dest_layout.addWidget(btn_dest)
        form.addRow(BodyLabel("Destination Folder:", self), dest_layout)

        # Enabled
        self._enabled_check = SwitchButton("Enabled", self)
        self._enabled_check.setOnText("Enabled")
        self._enabled_check.setOffText("Disabled")
        form.addRow(BodyLabel("", self), self._enabled_check)

        # Auto monitor
        self._auto_monitor_check = SwitchButton("Auto Monitor", self)
        self._auto_monitor_check.setOnText("Yes")
        self._auto_monitor_check.setOffText("No")
        form.addRow(BodyLabel("Automatic Monitoring:", self), self._auto_monitor_check)

        self.viewLayout.addLayout(form)

    def _populate(self):
        """Fill fields from the existing job."""
        self._name_edit.setText(self._job.name)
        self._source_edit.setText(self._job.source_folder)
        self._dest_edit.setText(self._job.destination_folder)
        self._enabled_check.setChecked(self._job.enabled)
        self._auto_monitor_check.setChecked(self._job.auto_monitor)

    def _browse_source(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Source Folder", self._source_edit.text()
        )
        if folder:
            self._source_edit.setText(folder)

    def _browse_dest(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Destination Folder", self._dest_edit.text()
        )
        if folder:
            self._dest_edit.setText(folder)
            
    def validate(self) -> bool:
        """Validate and save the job. Called when yesButton is clicked."""
        self._job.name = self._name_edit.text().strip()
        self._job.source_folder = self._source_edit.text().strip()
        self._job.destination_folder = self._dest_edit.text().strip()
        self._job.enabled = self._enabled_check.isChecked()
        self._job.auto_monitor = self._auto_monitor_check.isChecked()

        errors = self._job.validate()
        if errors:
            msg = MessageBox(
                "Validation Error",
                "\n".join(errors),
                self.window()
            )
            msg.exec()
            return False

        return True

    @property
    def job(self) -> TransferJob:
        return self._job
