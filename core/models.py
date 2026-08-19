"""
Data models and enumerations for the File Transfer Automation System.

Defines the core data structures used across all layers:
- FileStatus enum for transfer state machine
- TransferRecord for individual file transfer tracking
- TransferJob for source/destination job configuration
- StabilityCheck for file readiness monitoring
- VerificationResult for post-copy integrity checks
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileStatus(enum.Enum):
    """
    States in the file transfer lifecycle.

    State machine flow:
        DETECTED → PROCESSING → READY → QUEUED → TRANSFERRING → VERIFYING → COMPLETED
                                                                           → FAILED
                                                              → FAILED
                                              → FAILED
        Any state → SKIPPED (user decision or duplicate)
        FAILED → QUEUED (retry)
        READY/QUEUED → CONFLICT (destination differs)
    """
    DETECTED = "DETECTED"
    PROCESSING = "PROCESSING"
    WAITING_FOR_WINDOW = "WAITING_FOR_WINDOW"
    READY = "READY"
    QUEUED = "QUEUED"
    TRANSFERRING = "TRANSFERRING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CONFLICT = "CONFLICT"

    def is_terminal(self) -> bool:
        """Return True if this is a final state (no automatic transitions)."""
        return self in (
            FileStatus.COMPLETED,
            FileStatus.FAILED,
            FileStatus.SKIPPED,
        )

    def is_active(self) -> bool:
        """Return True if this state indicates active processing."""
        return self in (
            FileStatus.DETECTED,
            FileStatus.PROCESSING,
            FileStatus.WAITING_FOR_WINDOW,
            FileStatus.READY,
            FileStatus.QUEUED,
            FileStatus.TRANSFERRING,
            FileStatus.VERIFYING,
        )


@dataclass
class TransferRecord:
    """
    Tracks the state and history of a single file transfer.

    Each record represents one file's journey through the transfer pipeline.
    Records are persisted in SQLite for history and duplicate detection.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    file_name: str = ""
    source_path: str = ""
    destination_path: str = ""
    file_size: int = 0
    source_modified: Optional[float] = None
    source_hash: Optional[str] = None
    destination_hash: Optional[str] = None
    status: FileStatus = FileStatus.DETECTED
    detected_at: Optional[datetime] = None
    transfer_started: Optional[datetime] = None
    transfer_completed: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    verification_passed: Optional[bool] = None
    override_window: bool = False

    def __post_init__(self):
        if self.detected_at is None:
            self.detected_at = datetime.now()
        # Ensure status is always the enum, not a string
        if isinstance(self.status, str):
            self.status = FileStatus(self.status)

    @property
    def display_size(self) -> str:
        """Human-readable file size."""
        return format_file_size(self.file_size)

    @property
    def is_transferable(self) -> bool:
        """Whether this record is in a state that allows transfer."""
        return self.status in (FileStatus.READY, FileStatus.QUEUED)


@dataclass
class TransferJob:
    """
    Configuration for a one-way file transfer job.

    A job defines a source folder to monitor and a destination folder
    to copy files into. Multiple jobs can exist but operate independently.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    source_folder: str = ""
    destination_folder: str = ""
    enabled: bool = True
    auto_monitor: bool = True
    schedule_mode: str = "continuous"  # "continuous" or "window"
    window_start: str = "23:00"
    window_end: str = "06:00"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    @property
    def source_path(self) -> Path:
        return Path(self.source_folder)

    @property
    def destination_path(self) -> Path:
        return Path(self.destination_folder)

    def validate(self) -> list[str]:
        """
        Validate job configuration. Returns list of error messages.
        Empty list means valid.
        """
        errors = []
        if not self.name.strip():
            errors.append("Job name cannot be empty.")
        if not self.source_folder.strip():
            errors.append("Source folder cannot be empty.")
        if not self.destination_folder.strip():
            errors.append("Destination folder cannot be empty.")

        src = Path(self.source_folder)
        dst = Path(self.destination_folder)

        if self.source_folder and self.destination_folder:
            # Resolve to handle relative paths (avoid .resolve() on Windows network drives)
            try:
                resolved_src = src.absolute()
                resolved_dst = dst.absolute()
                if resolved_src == resolved_dst:
                    errors.append("Source and destination cannot be the same folder.")
                # Prevent nested paths (destination inside source or vice versa)
                try:
                    resolved_dst.relative_to(resolved_src)
                    errors.append("Destination cannot be inside the source folder.")
                except ValueError:
                    pass
                try:
                    resolved_src.relative_to(resolved_dst)
                    errors.append("Source cannot be inside the destination folder.")
                except ValueError:
                    pass
            except (OSError, ValueError):
                pass  # Path resolution failed; paths may not exist yet

        return errors


@dataclass
class StabilityCheck:
    """
    Tracks file stability measurements for readiness detection.

    The safety checker records file size and mtime at intervals.
    A file is considered stable when consecutive checks show no change.
    """
    file_path: str
    file_size: int = 0
    modified_time: float = 0.0
    last_check_time: Optional[datetime] = None
    stable_count: int = 0
    is_accessible: bool = False

    def reset(self, new_size: int, new_mtime: float):
        """Reset stability tracking when file changes."""
        self.file_size = new_size
        self.modified_time = new_mtime
        self.stable_count = 0
        self.last_check_time = datetime.now()

    def record_stable(self):
        """Record a stable check (no change detected)."""
        self.stable_count += 1
        self.last_check_time = datetime.now()


@dataclass
class VerificationResult:
    """Result of a post-transfer integrity verification."""
    success: bool
    source_hash: str = ""
    destination_hash: str = ""
    source_size: int = 0
    destination_size: int = 0
    source_exists: bool = True
    destination_exists: bool = True
    size_match: bool = True
    hash_match: bool = True
    error_message: str = ""


@dataclass
class TransferResult:
    """Result of a file transfer operation."""
    success: bool
    record: Optional[TransferRecord] = None
    verification: Optional[VerificationResult] = None
    error_message: str = ""
    was_conflict: bool = False


class ConflictResolution(enum.Enum):
    """User's choice when a destination conflict is detected."""
    OVERWRITE = "overwrite"
    SKIP = "skip"
    CANCEL = "cancel"


class SyncAction(enum.Enum):
    """User's choice when sync is requested with processing files."""
    TRANSFER_READY = "transfer_ready"
    WAIT_ALL = "wait_all"
    CANCEL = "cancel"


def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable size string."""
    if size_bytes < 0:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            if unit == "B":
                return f"{size_bytes} {unit}"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"
