"""
Transfer manager — the central orchestrator for the File Transfer Automation System.

Coordinates all components:
- FileMonitor: detects new files
- FileSafetyChecker: verifies files are safe to copy
- TransferEngine: performs the actual copy + verification
- DatabaseService: persists transfer history
- ConfigurationService: provides settings

Runs background processing via QThread workers to keep the GUI responsive.
Emits Qt signals for all state changes so the GUI can update.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from core.file_monitor import FileMonitor
from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.models import (
    ConflictResolution,
    FileStatus,
    SyncAction,
    TransferJob,
    TransferRecord,
    TransferResult,
)
from core.transfer_engine import TransferEngine
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService

logger = logging.getLogger("app")
transfer_logger = logging.getLogger("transfer")
error_logger = logging.getLogger("error")


class TransferWorker(QThread):
    """Background worker that processes the transfer queue one file at a time."""

    transfer_started = Signal(str)          # record_id
    transfer_progress = Signal(str, str, int, int)  # record_id, phase, current, total
    transfer_completed = Signal(str, object)  # record_id, TransferResult
    all_done = Signal()

    def __init__(
        self,
        records: list[TransferRecord],
        engine: TransferEngine,
        db: DatabaseService,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._records = records
        self._engine = engine
        self._db = db
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        for record in self._records:
            if self._cancel_requested:
                break

            self.transfer_started.emit(record.id)

            def progress_cb(phase: str, current: int, total: int) -> None:
                self.transfer_progress.emit(record.id, phase, current, total)

            result = self._engine.transfer_file(record, progress_cb)

            # Persist the updated record
            self._db.save_record(record)
            self.transfer_completed.emit(record.id, result)

        self.all_done.emit()


class TransferManager(QObject):
    """
    Central orchestrator for file transfer operations.

    Manages the full lifecycle: detect → safety check → queue →
    transfer → verify → persist. Emits signals for GUI updates.
    """

    # Signals for GUI binding
    file_detected = Signal(str, object)          # file_path, TransferRecord
    file_status_changed = Signal(str, object)    # record_id, FileStatus
    transfer_progress = Signal(str, str, int, int)  # record_id, phase, current, total
    transfer_completed = Signal(str, object)     # record_id, TransferResult
    stats_updated = Signal(dict)                 # {status: count}
    monitoring_changed = Signal(bool)            # is_monitoring
    conflict_detected = Signal(object)           # TransferRecord
    log_message = Signal(str, str)               # level, message

    def __init__(
        self,
        config: ConfigurationService,
        db: DatabaseService,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._config = config
        self._db = db

        # Core components
        self._safety = FileSafetyChecker(
            stability_interval=config.stability_check_interval,
            required_stable_checks=config.required_stable_checks,
        )
        self._integrity = IntegrityVerifier(
            algorithm=config.hash_algorithm,
            chunk_size=config.hash_chunk_size,
        )
        self._engine = TransferEngine(
            safety_checker=self._safety,
            integrity_verifier=self._integrity,
            temp_prefix=config.temp_file_prefix,
            temp_suffix=config.temp_file_suffix,
        )

        # State
        self._current_job: Optional[TransferJob] = None
        self._monitor: Optional[FileMonitor] = None
        self._active_records: dict[str, TransferRecord] = {}  # source_path → record
        self._worker: Optional[TransferWorker] = None
        self._is_transferring = False

        # Safety check timer — periodically re-checks PROCESSING files
        self._safety_timer = QTimer(self)
        self._safety_timer.timeout.connect(self._run_safety_checks)

        # Window check timer - checks if waiting files can be queued
        self._window_timer = QTimer(self)
        self._window_timer.timeout.connect(self._check_windows)
        self._window_timer.setInterval(60000) # 1 minute

        # Retry timer
        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._process_retries)
        self._retry_timer.setInterval(self._config.retry_delay * 1000)

        # Cleanup timer (runs every hour)
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._run_auto_cleanup)
        self._cleanup_timer.setInterval(3600 * 1000)  # 1 hour

    # ──────────────────────────────────────────────
    # Job management
    # ──────────────────────────────────────────────

    @property
    def current_job(self) -> Optional[TransferJob]:
        return self._current_job

    @property
    def is_monitoring(self) -> bool:
        return self._monitor is not None and self._monitor.is_running

    @property
    def is_transferring(self) -> bool:
        return self._is_transferring

    @property
    def active_records(self) -> dict[str, TransferRecord]:
        return dict(self._active_records)

    def set_job(self, job: TransferJob) -> None:
        """Set the active transfer job. Stops any existing monitoring."""
        if self.is_monitoring:
            self.stop_monitoring()

        self._current_job = job
        self._active_records.clear()
        self._safety.clear()

        # Clean up stale states from previous runs
        self._db.clear_stale_states(job.id)

        # Load any active records from the database
        active = self._db.get_active_records(job.id)
        for record in active:
            self._active_records[record.source_path] = record

        logger.info("Job set: '%s'", job.name)
        self._emit_stats()

    # ──────────────────────────────────────────────
    # Monitoring
    # ──────────────────────────────────────────────

    def start_monitoring(self) -> None:
        """Start monitoring the current job's source folder."""
        if not self._current_job:
            logger.warning("Cannot start monitoring: no job set")
            return

        if self.is_monitoring:
            logger.warning("Already monitoring")
            return

        job = self._current_job

        # Ensure source folder exists
        source = Path(job.source_folder)
        if not source.exists():
            try:
                source.mkdir(parents=True, exist_ok=True)
                logger.info("Created source folder: %s", source)
            except OSError as e:
                error_logger.error("Cannot create source folder: %s", e)
                self.log_message.emit("error", f"Cannot create source folder: {e}")
                return

        recon_interval = self._config.reconciliation_interval
        if self._config.network_drive_mode:
            recon_interval = min(recon_interval, 10)  # fast polling for networks
            logger.info("Network Drive Mode enabled: forcing fast reconciliation (every %ss)", recon_interval)

        self._monitor = FileMonitor(
            source_folder=job.source_folder,
            on_file_detected=self._on_file_detected,
            reconciliation_interval=recon_interval,
            temp_suffix=self._config.temp_file_suffix,
        )
        self._monitor.start()

        # Start the safety check timer
        interval_ms = self._config.stability_check_interval * 1000
        self._safety_timer.start(interval_ms)
        self._retry_timer.start()
        self._window_timer.start()

        # Initial scan to pick up existing files
        self._monitor.update_known_files()
        existing_files = self._monitor.scan_folder()
        for file_path in existing_files:
            self._on_file_detected(file_path)

        self.monitoring_changed.emit(True)
        logger.info("Monitoring started for '%s'", job.name)
        self.log_message.emit("info", "Monitoring started")

        if self._config.auto_cleanup_enabled:
            self._cleanup_timer.start()
            self._run_auto_cleanup()  # Run immediately on start

    def stop_monitoring(self) -> None:
        """Stop monitoring."""
        if self._monitor:
            self._monitor.stop()
            self._monitor = None

        self._safety_timer.stop()
        self._retry_timer.stop()
        self._cleanup_timer.stop()
        self._window_timer.stop()

        self.monitoring_changed.emit(False)
        logger.info("Monitoring stopped")
        self.log_message.emit("info", "Monitoring stopped")

    # ──────────────────────────────────────────────
    # File detection
    # ──────────────────────────────────────────────

    def _on_file_detected(self, file_path: str) -> None:
        """Called when a new or modified file is detected."""
        if not self._current_job:
            return

        source_path = str(Path(file_path))
        job = self._current_job

        # Check if we're already tracking this file
        if source_path in self._active_records:
            existing = self._active_records[source_path]
            if existing.status in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                # Check if source has changed since last transfer
                try:
                    stat = Path(source_path).stat()
                    prev = self._db.check_already_transferred(
                        job.id, source_path, stat.st_size, stat.st_mtime
                    )
                    if prev:
                        # Same file, already transferred — skip
                        return
                    # File changed — treat as new version
                    logger.info("Modified version detected: %s", Path(source_path).name)
                except OSError:
                    return
            elif existing.status.is_active():
                # Already being processed — don't create a duplicate
                return

        # Check if this file was already successfully transferred
        file_size = 0
        source_modified = 0.0
        initial_status = FileStatus.DETECTED
        
        try:
            stat = Path(source_path).stat()
            file_size = stat.st_size
            source_modified = stat.st_mtime
            prev = self._db.check_already_transferred(
                job.id, source_path, file_size, source_modified
            )
            if prev:
                logger.info("Already transferred: %s", Path(source_path).name)
                return
        except OSError as e:
            logger.warning("Cannot stat file %s (likely locked by Windows): %s", source_path, e)
            # Proceed anyway so UI shows the file in processing state,
            # wait for it to be accessible via safety checks.
            initial_status = FileStatus.PROCESSING

        # Create a new transfer record
        file_path_obj = Path(source_path)
        
        # Use Timestamped folder structure: Destination/YYYY-MM-DD_HHMMSS/filename.ext
        timestamp_folder = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        dest_path = str(Path(job.destination_folder) / timestamp_folder / file_path_obj.name)

        record = TransferRecord(
            job_id=job.id,
            file_name=file_path_obj.name,
            source_path=source_path,
            destination_path=dest_path,
            file_size=file_size,
            source_modified=source_modified,
            status=initial_status,
        )

        self._active_records[source_path] = record
        self._db.save_record(record)

        self.file_detected.emit(source_path, record)
        self._emit_stats()

        transfer_logger.info("File detected: %s (%s)", record.file_name, record.display_size)
        self.log_message.emit("info", f"File detected: {record.file_name}")

        # Immediately run a safety check if it's not locked, otherwise wait
        if initial_status != FileStatus.PROCESSING:
            self._check_file_safety(record)

    # ──────────────────────────────────────────────
    # Safety checks
    # ──────────────────────────────────────────────

    def _run_safety_checks(self) -> None:
        """Periodic safety check for all DETECTED/PROCESSING files."""
        for source_path, record in list(self._active_records.items()):
            if record.status in (FileStatus.DETECTED, FileStatus.PROCESSING):
                self._check_file_safety(record)

    def _check_file_safety(self, record: TransferRecord) -> None:
        """Run a safety check on a single file and update its state."""
        status = self._safety.check_file(record.source_path)

        if status == record.status:
            return  # No change

        old_status = record.status
        record.status = status

        if status == FileStatus.READY:
            # Check transfer window logic
            if not self._is_in_transfer_window(record) and not record.override_window:
                record.status = FileStatus.WAITING_FOR_WINDOW
                transfer_logger.info("File waiting for window: %s", record.file_name)
                self.log_message.emit("info", f"Waiting for window: {record.file_name}")
            else:
                transfer_logger.info("File ready: %s", record.file_name)
                self.log_message.emit("info", f"File ready: {record.file_name}")

                # Auto-transfer if monitoring is active
                if self.is_monitoring and self._current_job and self._current_job.auto_monitor:
                    self._queue_file(record)

        elif status == FileStatus.PROCESSING:
            if old_status == FileStatus.DETECTED:
                record.status = FileStatus.PROCESSING

        elif status == FileStatus.FAILED:
            record.error_message = "File no longer accessible"
            self._db.save_record(record)

        self.file_status_changed.emit(record.id, record.status)
        self._db.save_record(record)
        self._emit_stats()

    def _queue_file(self, record: TransferRecord) -> None:
        """Move a READY file into the transfer queue."""
        # Check for destination conflict first
        exists, conflicts, src_hash, dst_hash = self._engine.check_destination_conflict(
            record.source_path, record.destination_path
        )

        if exists and not conflicts:
            # Destination matches source — already synchronized
            record.status = FileStatus.COMPLETED
            record.source_hash = src_hash
            record.destination_hash = dst_hash
            record.verification_passed = True
            record.transfer_completed = datetime.now()
            self._db.save_record(record)
            self.file_status_changed.emit(record.id, record.status)
            transfer_logger.info("Already synchronized: %s", record.file_name)
            self.log_message.emit("info", f"Already synchronized: {record.file_name}")
            self._emit_stats()
            return

        if exists and conflicts:
            policy = self._config.overwrite_policy
            if policy == "ask":
                record.status = FileStatus.CONFLICT
                self._db.save_record(record)
                self.file_status_changed.emit(record.id, record.status)
                self.conflict_detected.emit(record)
                self._emit_stats()
                return
            elif policy == "skip":
                record.status = FileStatus.SKIPPED
                record.error_message = "Destination conflict — skipped by policy"
                self._db.save_record(record)
                self.file_status_changed.emit(record.id, record.status)
                self._emit_stats()
                return
            # policy == "overwrite" — continue to queue

        record.status = FileStatus.QUEUED
        self._db.save_record(record)
        self.file_status_changed.emit(record.id, record.status)
        self._emit_stats()

        # Auto-start transfer if not already transferring
        if not self._is_transferring:
            self._start_transfer_batch()

    # ──────────────────────────────────────────────
    # Transfer execution
    # ──────────────────────────────────────────────

    def _start_transfer_batch(self) -> None:
        """Start transferring all QUEUED files."""
        if self._is_transferring:
            return

        queued = [
            r for r in self._active_records.values()
            if r.status == FileStatus.QUEUED
        ]
        if not queued:
            return

        self._is_transferring = True

        self._worker = TransferWorker(queued, self._engine, self._db, self)
        self._worker.transfer_started.connect(self._on_transfer_started)
        self._worker.transfer_progress.connect(self._on_transfer_progress)
        self._worker.transfer_completed.connect(self._on_transfer_completed)
        self._worker.all_done.connect(self._on_all_transfers_done)
        self._worker.start()

    def _on_transfer_started(self, record_id: str) -> None:
        record = self._find_record_by_id(record_id)
        if record:
            self.file_status_changed.emit(record_id, FileStatus.TRANSFERRING)
            self.log_message.emit("info", f"Transferring: {record.file_name}")

    def _on_transfer_progress(
        self, record_id: str, phase: str, current: int, total: int
    ) -> None:
        self.transfer_progress.emit(record_id, phase, current, total)

    def _on_transfer_completed(self, record_id: str, result: TransferResult) -> None:
        record = self._find_record_by_id(record_id)
        if not record:
            return

        self.file_status_changed.emit(record_id, record.status)
        self.transfer_completed.emit(record_id, result)
        self._emit_stats()

        if result.success:
            transfer_logger.info("Transfer completed: %s", record.file_name)
            self.log_message.emit("info", f"Completed: {record.file_name}")
            # Clean up safety tracking
            self._safety.remove_check(record.source_path)
        else:
            error_msg = result.error_message or "Unknown error"
            error_logger.error(
                "Transfer failed: %s — %s", record.file_name, error_msg
            )
            self.log_message.emit(
                "error", f"Failed: {record.file_name} — {error_msg}"
            )

            # Schedule retry if under max retries
            if record.retry_count < self._config.max_retries:
                record.retry_count += 1
                record.status = FileStatus.QUEUED
                record.error_message = (
                    f"{error_msg} (retry {record.retry_count}/{self._config.max_retries})"
                )
                self._db.save_record(record)
                self.file_status_changed.emit(record_id, record.status)
                self.log_message.emit(
                    "warning",
                    f"Will retry: {record.file_name} "
                    f"(attempt {record.retry_count}/{self._config.max_retries})",
                )

    def _on_all_transfers_done(self) -> None:
        self._is_transferring = False
        self._emit_stats()

        # Check if more files were queued while transferring
        queued = [
            r for r in self._active_records.values()
            if r.status == FileStatus.QUEUED
        ]
        if queued:
            self._start_transfer_batch()

    def _process_retries(self) -> None:
        """Re-queue failed files that have retries remaining."""
        if not self._current_job:
            return
        # Retries are handled in _on_transfer_completed
        # This timer just triggers a new batch if retries were queued
        if not self._is_transferring:
            queued = [
                r for r in self._active_records.values()
                if r.status == FileStatus.QUEUED
            ]
            if queued:
                self._start_transfer_batch()

    # ──────────────────────────────────────────────
    # Manual sync
    # ──────────────────────────────────────────────

    def sync_now(self) -> tuple[list[TransferRecord], list[TransferRecord]]:
        """
        Perform a manual synchronization scan.

        Returns:
            (ready_files, processing_files) — lists of TransferRecords
            that are ready to transfer and still processing.
        """
        if not self._current_job:
            return [], []

        job = self._current_job

        # Scan the source folder
        if self._monitor:
            files = self._monitor.scan_folder()
        else:
            source = Path(job.source_folder)
            if not source.exists():
                return [], []
            files = [
                str(f) for f in source.iterdir()
                if f.is_file()
                and not f.name.startswith(".")
                and not f.name.endswith(self._config.temp_file_suffix)
            ]

        # Process each file
        for file_path in files:
            self._on_file_detected(file_path)

        # Force safety checks
        self._run_safety_checks()

        # Categorize results
        ready = []
        processing = []
        for record in self._active_records.values():
            if record.status == FileStatus.READY:
                ready.append(record)
            elif record.status in (FileStatus.DETECTED, FileStatus.PROCESSING, FileStatus.WAITING_FOR_WINDOW):
                processing.append(record)

        return ready, processing

    def transfer_ready_files(self) -> int:
        """Queue all READY files for transfer. Returns count queued."""
        count = 0
        for record in list(self._active_records.values()):
            if record.status == FileStatus.READY:
                self._queue_file(record)
                count += 1
        return count

    def resolve_conflict(
        self, record_id: str, resolution: ConflictResolution
    ) -> None:
        """Handle a user's conflict resolution decision."""
        record = self._find_record_by_id(record_id)
        if not record:
            return

        if resolution == ConflictResolution.OVERWRITE:
            record.status = FileStatus.QUEUED
            self._db.save_record(record)
            self.file_status_changed.emit(record_id, record.status)
            if not self._is_transferring:
                self._start_transfer_batch()
        elif resolution == ConflictResolution.SKIP:
            record.status = FileStatus.SKIPPED
            record.error_message = "Skipped by user (destination conflict)"
            self._db.save_record(record)
            self.file_status_changed.emit(record_id, record.status)
        else:  # CANCEL
            record.status = FileStatus.READY
            self._db.save_record(record)
            self.file_status_changed.emit(record_id, record.status)

        self._emit_stats()

    def force_start(self, record_id: str) -> None:
        """Manually override transfer window and start immediately."""
        record = self._find_record_by_id(record_id)
        if not record:
            return
            
        record.override_window = True
        if record.status == FileStatus.WAITING_FOR_WINDOW:
            record.status = FileStatus.READY
            self._db.save_record(record)
            self.file_status_changed.emit(record_id, record.status)
            self._queue_file(record)
            self._emit_stats()

    # ──────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────

    def _find_record_by_id(self, record_id: str) -> Optional[TransferRecord]:
        """Find a record by ID in the active records."""
        for record in self._active_records.values():
            if record.id == record_id:
                return record
        return None

    def _emit_stats(self) -> None:
        """Emit updated statistics."""
        stats = {}
        for status in FileStatus:
            stats[status.value] = 0
        for record in self._active_records.values():
            stats[record.status.value] = stats.get(record.status.value, 0) + 1
        self.stats_updated.emit(stats)

    def get_all_records(self) -> list[TransferRecord]:
        """Return all active records."""
        return list(self._active_records.values())

    def get_history(self, limit: int = 500) -> list[TransferRecord]:
        """Return transfer history from the database."""
        if self._current_job:
            return self._db.get_records_by_job(self._current_job.id, limit=limit)
        return []

    def shutdown(self) -> None:
        """Clean shutdown — stop monitoring and cancel transfers."""
        self.stop_monitoring()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        logger.info("Transfer manager shut down")

    # ──────────────────────────────────────────────
    # Auto-Cleanup
    # ──────────────────────────────────────────────

    def _run_auto_cleanup(self) -> None:
        """Runs the auto-cleanup job to delete old transferred source files on Mondays."""
        if not self._config.auto_cleanup_enabled or not self._current_job:
            return

        # Check if it's Monday (0 = Monday, 6 = Sunday)
        if datetime.now().weekday() != 0:
            return

        logger.info("Running Monday auto-cleanup...")
        self.log_message.emit("info", "Starting weekly source cleanup...")

        # Find candidates older than 7 days
        candidates = self._db.get_cleanup_candidates(self._current_job.id, days=7)
        deleted_count = 0

        for record in candidates:
            source_path = Path(record.source_path)
            dest_path = Path(record.destination_path)

            if not source_path.exists():
                continue

            # Ensure it actually exists at the destination before deleting the source
            if dest_path.exists() and dest_path.stat().st_size == record.file_size:
                try:
                    source_path.unlink()
                    deleted_count += 1
                    logger.info("Auto-cleanup deleted source file: %s", source_path)
                except OSError as e:
                    logger.error("Failed to delete source file during cleanup %s: %s", source_path, e)

        if deleted_count > 0:
            self.log_message.emit("info", f"Auto-cleanup removed {deleted_count} old file(s).")

    # ──────────────────────────────────────────────
    # Windows & Scheduling
    # ──────────────────────────────────────────────
    def _is_in_transfer_window(self, record: TransferRecord) -> bool:
        """Check if current time is within the allowed transfer window."""
        if not self._current_job or self._current_job.schedule_mode != "window":
            return True
            
        try:
            now = datetime.now().time()
            start_time = datetime.strptime(self._current_job.window_start, "%H:%M").time()
            end_time = datetime.strptime(self._current_job.window_end, "%H:%M").time()
            
            if start_time <= end_time:
                return start_time <= now <= end_time
            else:
                # Crosses midnight
                return now >= start_time or now <= end_time
        except ValueError:
            return True # Fallback if time format is wrong
            
    def _check_windows(self) -> None:
        """Transition WAITING_FOR_WINDOW files to READY if window opened."""
        if not self._current_job:
            return
            
        now_in_window = self._is_in_transfer_window(None) # record argument not used for job config
        if not now_in_window:
            return
            
        queued_count = 0
        for record in list(self._active_records.values()):
            if record.status == FileStatus.WAITING_FOR_WINDOW:
                record.status = FileStatus.READY
                self._db.save_record(record)
                self.file_status_changed.emit(record.id, record.status)
                
                if self.is_monitoring and self._current_job.auto_monitor:
                    self._queue_file(record)
                    queued_count += 1
                    
        if queued_count > 0:
            self._emit_stats()


