"""
Job configuration dialog for the File Transfer Automation System.

Allows the user to create or edit a transfer job by specifying
the job name, source folder, destination folder, and options.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import TransferJob


class JobDialog(QDialog):
    """Dialog for creating or editing a transfer job."""

    def __init__(
        self,
        job: Optional[TransferJob] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._job = job or TransferJob()
        self._is_new = job is None

        self.setWindowTitle("Add Transfer Job" if self._is_new else "Edit Transfer Job")
        self.setMinimumWidth(550)

        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Job name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Local Test Transfer")
        form.addRow("Job Name:", self._name_edit)

        # Source folder
        source_layout = QHBoxLayout()
        self._source_edit = QLineEdit()
        self._source_edit.setPlaceholderText("Source folder path")
        source_layout.addWidget(self._source_edit)
        btn_source = QPushButton("Browse...")
        btn_source.clicked.connect(self._browse_source)
        source_layout.addWidget(btn_source)
        form.addRow("Source Folder:", source_layout)

        # Destination folder
        dest_layout = QHBoxLayout()
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Destination folder path")
        dest_layout.addWidget(self._dest_edit)
        btn_dest = QPushButton("Browse...")
        btn_dest.clicked.connect(self._browse_dest)
        dest_layout.addWidget(btn_dest)
        form.addRow("Destination Folder:", dest_layout)

        # Enabled
        self._enabled_check = QCheckBox("Enabled")
        form.addRow("", self._enabled_check)

        # Auto monitor
        self._auto_monitor_check = QCheckBox("Automatic Monitoring")
        form.addRow("", self._auto_monitor_check)

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

    def _on_save(self):
        """Validate and save the job."""
        self._job.name = self._name_edit.text().strip()
        self._job.source_folder = self._source_edit.text().strip()
        self._job.destination_folder = self._dest_edit.text().strip()
        self._job.enabled = self._enabled_check.isChecked()
        self._job.auto_monitor = self._auto_monitor_check.isChecked()

        errors = self._job.validate()
        if errors:
            QMessageBox.warning(
                self,
                "Validation Error",
                "\n".join(errors),
            )
            return

        self.accept()

    @property
    def job(self) -> TransferJob:
        return self._job
