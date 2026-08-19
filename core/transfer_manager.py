"""
Transfer manager — the central multi-job orchestrator for the File Transfer Automation System.

Coordinates all components:
- JobController: manages a single job's background monitor, safety checker, and schedule
- TransferManager: central multi-job registry orchestrating all active jobs concurrently
- TransferWorker: background QThread worker handling batch compression (ZipCrypto) and safe transfer
- DatabaseService: persists transfer history and job configs
- ConfigurationService: provides global settings

All enabled jobs run concurrently in the background regardless of active UI navigation.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

import pyminizip

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
    """Background worker that processes the transfer queue."""

    transfer_started = Signal(str)                  # record_id
    transfer_progress = Signal(str, str, int, int)  # record_id, phase, current, total
    transfer_completed = Signal(str, object)        # record_id, TransferResult
    all_done = Signal()

    def __init__(
        self,
        records: list[TransferRecord],
        engine: TransferEngine,
        db: DatabaseService,
        config: ConfigurationService,
        job: Optional[TransferJob] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._records = records
        self._engine = engine
        self._db = db
        self._config = config
        self._job = job
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        if not self._records:
            self.all_done.emit()
            return

        if self._config.batch_compression_enabled and len(self._records) > 0:
            self._run_batch_compression()
        else:
            self._run_individual_transfers()

    def _run_individual_transfers(self) -> None:
        for record in self._records:
            if self._cancel_requested:
                break

            self.transfer_started.emit(record.id)

            def make_cb(rid: str):
                return lambda p, c, t: self.transfer_progress.emit(rid, p, c, t)

            result = self._engine.transfer_file(record, make_cb(record.id))
            self._db.save_record(record)
            self.transfer_completed.emit(record.id, result)

        self.all_done.emit()

    def _run_batch_compression(self) -> None:
        temp_zip_path = None
        try:
            for record in self._records:
                self.transfer_started.emit(record.id)

            password = self._config.zip_password if self._config.zip_password else None

            job = self._job
            source_folder = job.source_folder if job else None

            # Format zip filename: YYYY-MM-DD_<time>.zip
            date_str = datetime.now().strftime("%Y-%m-%d")
            if job and job.schedule_mode == "window" and job.window_start:
                clean_ws = job.window_start.replace(":", "").strip()
                if len(clean_ws) == 4:
                    time_str = clean_ws + "00"
                elif len(clean_ws) == 6:
                    time_str = clean_ws
                else:
                    time_str = datetime.now().strftime("%H%M%S")
            else:
                time_str = datetime.now().strftime("%H%M%S")

            base_zip_name = f"{date_str}_{time_str}"
            temp_zip_name = f"{base_zip_name}.zip"

            temp_dir = tempfile.gettempdir()
            temp_zip_path = os.path.join(temp_dir, f"batch_transfer_{temp_zip_name}")

            if self._cancel_requested:
                self.all_done.emit()
                return

            if job and job.destination_folder:
                dest_dir = Path(job.destination_folder)
            else:
                dest_dir = Path(self._records[0].destination_path).parent

            target_path = dest_dir / temp_zip_name
            counter = 1
            while target_path.exists():
                temp_zip_name = f"{base_zip_name}_{counter}.zip"
                target_path = dest_dir / temp_zip_name
                counter += 1

            successful_records = []
            src_paths_for_zip = []
            prefixes_for_zip = []

            for record in self._records:
                if self._cancel_requested:
                    break
                src_path = Path(record.source_path)
                if not src_path.exists():
                    logger.error(f"Source file missing: {src_path}")
                    record.status = FileStatus.FAILED
                    record.error_message = "Source file missing"
                    self._db.save_record(record)
                    self.transfer_completed.emit(
                        record.id, TransferResult(success=False, record=record, error_message="Source file missing")
                    )
                    continue

                if source_folder:
                    try:
                        rel_dir = str(
                            src_path.relative_to(Path(source_folder)).parent
                        ).replace("\\", "/")
                        if rel_dir == ".":
                            rel_dir = ""
                    except ValueError:
                        rel_dir = ""
                else:
                    rel_dir = ""

                src_paths_for_zip.append(str(src_path.resolve()))
                prefixes_for_zip.append(rel_dir)
                successful_records.append(record)

            if self._cancel_requested or not successful_records:
                if temp_zip_path and os.path.exists(temp_zip_path):
                    try:
                        os.remove(temp_zip_path)
                    except OSError:
                        pass
                self.all_done.emit()
                return

            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass

            # Create standard ZipCrypto encrypted ZIP
            pyminizip.compress_multiple(
                src_paths_for_zip,
                prefixes_for_zip,
                temp_zip_path,
                password,
                4,
            )

            for record in successful_records:
                self.transfer_progress.emit(record.id, "compressing", 100, 100)

            valid_records = successful_records
            first_record = valid_records[0]

            zip_record = TransferRecord(
                id=str(uuid.uuid4()),
                job_id=first_record.job_id,
                file_name=temp_zip_name,
                source_path=temp_zip_path,
                destination_path=str(target_path),
                file_size=Path(temp_zip_path).stat().st_size,
                source_modified=Path(temp_zip_path).stat().st_mtime,
                status=FileStatus.QUEUED,
            )

            def progress_cb(phase: str, current: int, total: int) -> None:
                for r in valid_records:
                    self.transfer_progress.emit(r.id, phase, current, total)

            result = self._engine.transfer_file(zip_record, progress_cb)

            for record in valid_records:
                if result.success:
                    record.status = FileStatus.COMPLETED
                    record.destination_path = str(target_path)
                    record.transfer_completed = zip_record.transfer_completed
                    record.source_hash = zip_record.source_hash
                    record.destination_hash = zip_record.destination_hash
                    record.verification_passed = True
                else:
                    record.status = FileStatus.FAILED
                    record.error_message = f"Batch transfer failed: {result.error_message}"

                self._db.save_record(record)
                self.transfer_completed.emit(record.id, result)

        finally:
            if temp_zip_path and os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass
            self.all_done.emit()


class JobController(QObject):
    """
    Background controller managing an individual transfer job's pipeline:
    monitoring, file safety checks, schedule checking, and queue dispatching.
    """

    file_detected = Signal(str, str, object)          # job_id, file_path, TransferRecord
    files_detected = Signal(str, list)                # job_id, list[TransferRecord]
    file_status_changed = Signal(str, str, object)    # job_id, record_id, FileStatus
    transfer_progress = Signal(str, str, str, int, int)  # job_id, record_id, phase, current, total
    transfer_completed = Signal(str, str, object)     # job_id, record_id, TransferResult
    stats_updated = Signal(str, dict)                 # job_id, {status: count}
    monitoring_changed = Signal(str, bool)            # job_id, is_monitoring
    conflict_detected = Signal(str, object)           # job_id, TransferRecord
    log_message = Signal(str, str, str)               # job_id, level, message

    def __init__(
        self,
        job: TransferJob,
        config: ConfigurationService,
        db: DatabaseService,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.job = job
        self._config = config
        self._db = db

        self._safety = FileSafetyChecker(
            stability_interval=config.stability_check_interval,
            required_stable_checks=config.required_stable_checks,
        )
        self._integrity = IntegrityVerifier(
            chunk_size=config.hash_chunk_size,
        )
        self._engine = TransferEngine(
            self._safety,
            self._integrity,
            temp_prefix=config.temp_file_prefix,
            temp_suffix=config.temp_file_suffix,
        )

        self._monitor: Optional[FileMonitor] = None
        self._active_records: dict[str, TransferRecord] = {}
        self._worker: Optional[TransferWorker] = None
        self._is_transferring = False
        self._last_window_executed_minute: Optional[str] = None

        # Safety timer
        self._safety_timer = QTimer(self)
        self._safety_timer.timeout.connect(self._run_safety_checks)

        # Window check timer (runs every 3 seconds)
        self._window_timer = QTimer(self)
        self._window_timer.timeout.connect(self._check_windows)
        self._window_timer.setInterval(3000)

        # Retry timer
        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._process_retries)
        self._retry_timer.setInterval(self._config.retry_delay * 1000)

        # Cleanup timer
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._run_auto_cleanup)
        self._cleanup_timer.setInterval(3600 * 1000)

        # Load active records from DB
        self._load_active_records()

    def _load_active_records(self) -> None:
        active = self._db.get_active_records(self.job.id)
        for record in active:
            self._active_records[record.source_path] = record

    @property
    def is_monitoring(self) -> bool:
        return self._monitor is not None and self._monitor.is_running

    @property
    def is_in_transfer_window(self) -> bool:
        """Check if current time is within the allowed transfer window."""
        if self.job.schedule_mode != "window":
            return True
        try:
            now = datetime.now().time()
            start_time = datetime.strptime(self.job.window_start, "%H:%M").time()
            end_time_base = datetime.strptime(self.job.window_end, "%H:%M").time()
            end_time = end_time_base.replace(second=59, microsecond=999999)
            if start_time <= end_time:
                return start_time <= now <= end_time
            else:
                return now >= start_time or now <= end_time
        except (ValueError, AttributeError):
            return True

    def start_monitoring(self) -> None:
        """Start monitoring source folder for this job."""
        if self.is_monitoring:
            return

        interval_ms = self._config.stability_check_interval * 1000
        self._safety_timer.start(interval_ms)
        self._retry_timer.start()
        self._window_timer.start()
        self._cleanup_timer.start()

        recon_interval = self._config.reconciliation_interval
        if self._config.network_drive_mode:
            recon_interval = min(recon_interval, 10)

        try:
            src = Path(self.job.source_folder)
            src.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.log_message.emit(self.job.id, "error", f"Cannot create source folder: {e}")
            return

        self._monitor = FileMonitor(
            source_folder=self.job.source_folder,
            on_file_detected=self._on_file_detected,
            reconciliation_interval=recon_interval,
            temp_suffix=self._config.temp_file_suffix,
        )
        self._monitor.start()

        def _start_and_scan():
            try:
                self._monitor.update_known_files()
                existing_files = self._monitor.scan_folder()

                if existing_files:
                    batch_records = []
                    for fpath in existing_files:
                        try:
                            fsize = Path(fpath).stat().st_size
                            mtime = Path(fpath).stat().st_mtime
                        except OSError:
                            continue

                        if self._db.check_already_transferred(self.job.id, fpath, fsize, mtime):
                            continue
                        if fpath in self._active_records:
                            continue

                        status = FileStatus.DETECTED
                        if self.job.schedule_mode == "window":
                            status = FileStatus.WAITING_FOR_WINDOW

                        rec = TransferRecord(
                            job_id=self.job.id,
                            file_name=Path(fpath).name,
                            source_path=fpath,
                            destination_path=str(Path(self.job.destination_folder) / Path(fpath).name),
                            file_size=fsize,
                            source_modified=mtime,
                            status=status,
                        )
                        self._active_records[fpath] = rec
                        batch_records.append(rec)

                    if batch_records:
                        self._db.save_records_batch(batch_records)
                        self.files_detected.emit(self.job.id, batch_records)
                        self._emit_stats()

            except Exception as e:
                logger.exception("Initial scan error for job %s: %s", self.job.name, e)

        threading.Thread(target=_start_and_scan, daemon=True).start()
        self.monitoring_changed.emit(self.job.id, True)
        self.log_message.emit(self.job.id, "info", f"Started monitoring '{self.job.name}'")

    def stop_monitoring(self) -> None:
        """Stop background monitoring for this job."""
        if not self.is_monitoring:
            return

        if self._monitor:
            self._monitor.stop()
            self._monitor = None

        self._safety_timer.stop()
        self._retry_timer.stop()
        self._window_timer.stop()

        if self._worker and self._worker.isRunning():
            self._worker.cancel()

        self.monitoring_changed.emit(self.job.id, False)
        self.log_message.emit(self.job.id, "info", f"Stopped monitoring '{self.job.name}'")

    def _on_file_detected(self, file_path: str) -> None:
        """Handle new file event from FileMonitor."""
        try:
            p = Path(file_path)
            if not p.exists() or p.is_dir():
                return
            file_size = p.stat().st_size
            source_modified = p.stat().st_mtime
        except OSError:
            return

        if self._db.check_already_transferred(self.job.id, file_path, file_size, source_modified):
            return

        if file_path in self._active_records:
            rec = self._active_records[file_path]
            if rec.status in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                return
            rec.file_size = file_size
            rec.source_modified = source_modified
        else:
            status = FileStatus.DETECTED
            if self.job.schedule_mode == "window":
                status = FileStatus.WAITING_FOR_WINDOW

            rec = TransferRecord(
                job_id=self.job.id,
                file_name=Path(file_path).name,
                source_path=file_path,
                destination_path=str(Path(self.job.destination_folder) / Path(file_path).name),
                file_size=file_size,
                source_modified=source_modified,
                status=status,
            )
            self._active_records[file_path] = rec

        self._db.save_record(rec)
        self.file_detected.emit(self.job.id, file_path, rec)
        self._emit_stats()

    def _run_safety_checks(self) -> None:
        """Periodically check pending files for lock release & stability."""
        to_check = [
            r for r in list(self._active_records.values())
            if r.status in (FileStatus.DETECTED, FileStatus.PROCESSING)
        ]
        if not to_check:
            return

        ready_files = []
        for record in to_check:
            status = self._safety.check_file(record.source_path)
            if status != record.status:
                record.status = status
                if status == FileStatus.READY:
                    if self.job.schedule_mode == "window" and not record.override_window:
                        record.status = FileStatus.WAITING_FOR_WINDOW
                    else:
                        ready_files.append(record)

                self._db.save_record(record)
                self.file_status_changed.emit(self.job.id, record.id, record.status)

        if ready_files and self.is_monitoring and self.job.schedule_mode == "continuous":
            self._queue_files(ready_files)

        self._emit_stats()

    def _check_windows(self) -> None:
        """
        Scheduled Transfer Execution:
        At the configured window_end time, execute the batch transfer of all accumulated files!
        """
        if self.job.schedule_mode != "window":
            return

        now = datetime.now()
        now_time = now.time()

        try:
            end_time_base = datetime.strptime(self.job.window_end, "%H:%M").time()
        except (ValueError, AttributeError):
            return

        current_minute = now.strftime("%Y-%m-%d_%H:%M")
        is_end_minute = (now_time.hour == end_time_base.hour and now_time.minute == end_time_base.minute)

        if is_end_minute and self._last_window_executed_minute != current_minute:
            self._last_window_executed_minute = current_minute

            # Gather all waiting files
            waiting = [
                r for r in list(self._active_records.values())
                if r.status in (FileStatus.WAITING_FOR_WINDOW, FileStatus.READY, FileStatus.PROCESSING, FileStatus.DETECTED)
            ]

            # Also check DB for any waiting records
            db_records = self._db.get_active_records(self.job.id)
            for r in db_records:
                if r.source_path not in self._active_records:
                    self._active_records[r.source_path] = r
                    waiting.append(r)

            if waiting:
                logger.info("Window end reached (%s) for '%s'. Executing batch transfer for %d files.",
                            self.job.window_end, self.job.name, len(waiting))
                self.log_message.emit(
                    self.job.id,
                    "info",
                    f"Window end reached ({self.job.window_end}). Executing batch transfer for {len(waiting)} file(s)...",
                )
                for record in waiting:
                    record.status = FileStatus.READY
                    self.file_status_changed.emit(self.job.id, record.id, record.status)

                self._db.save_records_batch(waiting)
                self._queue_files(waiting)
                self._emit_stats()

    def sync_now(self) -> tuple[list[TransferRecord], list[TransferRecord]]:
        """Manual sync scan for this job."""
        if not self._monitor:
            recon_interval = self._config.reconciliation_interval
            self._monitor = FileMonitor(
                source_folder=self.job.source_folder,
                on_file_detected=self._on_file_detected,
                reconciliation_interval=recon_interval,
                temp_suffix=self._config.temp_file_suffix,
            )

        self._monitor.update_known_files()
        found_files = self._monitor.scan_folder()

        for fpath in found_files:
            try:
                fsize = Path(fpath).stat().st_size
                mtime = Path(fpath).stat().st_mtime
            except OSError:
                continue

            if self._db.check_already_transferred(self.job.id, fpath, fsize, mtime):
                continue

            if fpath not in self._active_records:
                rec = TransferRecord(
                    job_id=self.job.id,
                    file_name=Path(fpath).name,
                    source_path=fpath,
                    destination_path=str(Path(self.job.destination_folder) / Path(fpath).name),
                    file_size=fsize,
                    source_modified=mtime,
                    status=FileStatus.DETECTED,
                )
                self._active_records[fpath] = rec
                self._db.save_record(rec)

        # Run safety check on all detected files
        ready: list[TransferRecord] = []
        processing: list[TransferRecord] = []

        for rec in list(self._active_records.values()):
            if rec.status in (FileStatus.DETECTED, FileStatus.PROCESSING, FileStatus.WAITING_FOR_WINDOW):
                st = self._safety.check_file(rec.source_path)
                rec.status = st
                self._db.save_record(rec)
                if st == FileStatus.READY:
                    ready.append(rec)
                elif st == FileStatus.PROCESSING:
                    processing.append(rec)

        self._emit_stats()
        return ready, processing

    def transfer_ready_files(self, override: bool = False) -> int:
        """Transfer all currently ready files for this job."""
        ready = []
        for r in list(self._active_records.values()):
            if r.status in (FileStatus.READY, FileStatus.WAITING_FOR_WINDOW):
                if override or r.override_window:
                    r.override_window = True
                    r.status = FileStatus.READY
                    self._db.save_record(r)
                    ready.append(r)
                elif self.is_in_transfer_window:
                    r.status = FileStatus.READY
                    self._db.save_record(r)
                    ready.append(r)
                else:
                    r.status = FileStatus.WAITING_FOR_WINDOW
                    self._db.save_record(r)
                    self.file_status_changed.emit(self.job.id, r.id, r.status)

        return self._queue_files(ready)

    def force_start(self, record_id: str) -> None:
        record = self._find_record_by_id(record_id)
        if record and record.status in (FileStatus.PROCESSING, FileStatus.WAITING_FOR_WINDOW, FileStatus.READY):
            record.override_window = True
            record.status = FileStatus.READY
            self._db.save_record(record)
            self.file_status_changed.emit(self.job.id, record.id, record.status)
            self._queue_file(record)

    def _queue_file(self, record: TransferRecord, auto_start: bool = True) -> bool:
        if not self.is_in_transfer_window and not record.override_window:
            record.status = FileStatus.WAITING_FOR_WINDOW
            self._db.save_record(record)
            self.file_status_changed.emit(self.job.id, record.id, record.status)
            self._emit_stats()
            return False

        record.status = FileStatus.QUEUED
        self._db.save_record(record)
        self.file_status_changed.emit(self.job.id, record.id, record.status)
        self._emit_stats()

        if auto_start and not self._is_transferring:
            self._start_transfer_batch()
        return True

    def _queue_files(self, records: list[TransferRecord]) -> int:
        queued_count = 0
        for record in records:
            if self._queue_file(record, auto_start=False):
                queued_count += 1
        if queued_count > 0 and not self._is_transferring:
            self._start_transfer_batch()
        return queued_count

    def _start_transfer_batch(self) -> None:
        if self._is_transferring:
            return

        queued = [
            r for r in list(self._active_records.values())
            if r.status == FileStatus.QUEUED
        ]
        if not queued:
            return

        self._is_transferring = True
        self._worker = TransferWorker(
            records=queued,
            engine=self._engine,
            db=self._db,
            config=self._config,
            job=self.job,
            parent=self,
        )
        self._worker.transfer_started.connect(self._on_transfer_started)
        self._worker.transfer_progress.connect(self._on_transfer_progress)
        self._worker.transfer_completed.connect(self._on_transfer_completed)
        self._worker.all_done.connect(self._on_all_transfers_done)
        self._worker.start()

    def _on_transfer_started(self, record_id: str) -> None:
        record = self._find_record_by_id(record_id)
        if record:
            self.file_status_changed.emit(self.job.id, record_id, FileStatus.TRANSFERRING)

    def _on_transfer_progress(self, record_id: str, phase: str, cur: int, tot: int) -> None:
        self.transfer_progress.emit(self.job.id, record_id, phase, cur, tot)

    def _on_transfer_completed(self, record_id: str, result: TransferResult) -> None:
        record = self._find_record_by_id(record_id)
        if record:
            self._db.save_record(record)
            self.transfer_completed.emit(self.job.id, record_id, result)
        self._emit_stats()

    def _on_all_transfers_done(self) -> None:
        self._is_transferring = False
        self._worker = None

        # Clean active completed records from in-memory dictionary
        completed_paths = [
            path for path, r in self._active_records.items()
            if r.status in (FileStatus.COMPLETED, FileStatus.SKIPPED)
        ]
        for path in completed_paths:
            del self._active_records[path]

        self._emit_stats()

    def _process_retries(self) -> None:
        failed = [
            r for r in list(self._active_records.values())
            if r.status == FileStatus.FAILED and r.retry_count < self._config.max_retries
        ]
        for record in failed:
            record.retry_count += 1
            record.status = FileStatus.DETECTED
            self._db.save_record(record)
            self.file_status_changed.emit(self.job.id, record.id, record.status)
        if failed:
            self._emit_stats()

    def _run_auto_cleanup(self) -> None:
        if not self._config.auto_cleanup_days or self._config.auto_cleanup_days <= 0:
            return
        candidates = self._db.get_cleanup_candidates(self.job.id, self._config.auto_cleanup_days)
        deleted = 0
        for record in candidates:
            sp = Path(record.source_path)
            dp = Path(record.destination_path)
            if sp.exists() and dp.exists():
                try:
                    sp.unlink()
                    deleted += 1
                except OSError:
                    pass
        if deleted > 0:
            self.log_message.emit(self.job.id, "info", f"Auto-cleanup deleted {deleted} old source file(s)")

    def _find_record_by_id(self, record_id: str) -> Optional[TransferRecord]:
        for r in self._active_records.values():
            if r.id == record_id:
                return r
        return self._db.get_record_by_id(record_id)

    def _emit_stats(self) -> None:
        stats = self._db.get_statistics(self.job.id)
        self.stats_updated.emit(self.job.id, stats)


class TransferManager(QObject):
    """
    Central Multi-Job Transfer Manager.

    Coordinates all configured transfer jobs concurrently, allowing each
    job to monitor, safety-check, and execute transfers independently in the background.
    """

    # Global signals forwarded to GUI
    file_detected = Signal(str, object)          # file_path, TransferRecord
    files_detected = Signal(list)                # list[TransferRecord]
    file_status_changed = Signal(str, object)    # record_id, FileStatus
    transfer_progress = Signal(str, str, int, int)  # record_id, phase, current, total
    transfer_completed = Signal(str, object)     # record_id, TransferResult
    stats_updated = Signal(dict)                 # {status: count} for active job
    monitoring_changed = Signal(bool)            # is_monitoring for active job
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
        self._controllers: dict[str, JobController] = {}
        self._current_job: Optional[TransferJob] = None

        self.reload_jobs()

    def reload_jobs(self) -> None:
        """Reload all jobs from database and synchronize job controllers."""
        jobs = self._db.get_jobs()
        job_map = {j.id: j for j in jobs}

        # Stop and remove controllers for deleted jobs
        for jid in list(self._controllers.keys()):
            if jid not in job_map:
                ctrl = self._controllers.pop(jid)
                ctrl.stop_monitoring()
                ctrl.deleteLater()

        # Add or update controllers for existing jobs
        for job in jobs:
            if job.id in self._controllers:
                self._controllers[job.id].job = job
            else:
                ctrl = JobController(job, self._config, self._db, self)
                ctrl.file_detected.connect(self._on_ctrl_file_detected)
                ctrl.files_detected.connect(self._on_ctrl_files_detected)
                ctrl.file_status_changed.connect(self._on_ctrl_file_status_changed)
                ctrl.transfer_progress.connect(self._on_ctrl_transfer_progress)
                ctrl.transfer_completed.connect(self._on_ctrl_transfer_completed)
                ctrl.stats_updated.connect(self._on_ctrl_stats_updated)
                ctrl.monitoring_changed.connect(self._on_ctrl_monitoring_changed)
                ctrl.conflict_detected.connect(self._on_ctrl_conflict_detected)
                ctrl.log_message.connect(self._on_ctrl_log_message)
                self._controllers[job.id] = ctrl

    def get_controller(self, job_id: str) -> Optional[JobController]:
        return self._controllers.get(job_id)

    @property
    def current_job(self) -> Optional[TransferJob]:
        return self._current_job

    @property
    def is_monitoring(self) -> bool:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id].is_monitoring
        return False

    @property
    def active_records(self) -> dict[str, TransferRecord]:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id]._active_records
        return {}

    @property
    def _active_records(self) -> dict[str, TransferRecord]:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id]._active_records
        return {}

    @property
    def _worker(self) -> Optional[TransferWorker]:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id]._worker
        return None

    @property
    def is_in_transfer_window(self) -> bool:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id].is_in_transfer_window
        return True

    def is_job_monitoring(self, job_id: str) -> bool:
        ctrl = self._controllers.get(job_id)
        return ctrl.is_monitoring if ctrl else False

    def is_job_in_window(self, job_id: str) -> bool:
        ctrl = self._controllers.get(job_id)
        return ctrl.is_in_transfer_window if ctrl else True

    def set_job(self, job: TransferJob) -> None:
        """Set the active workspace job."""
        self._current_job = job
        if job.id not in self._controllers:
            self.reload_jobs()
        self._emit_stats()

    def start_monitoring(self) -> None:
        """Start monitoring the active workspace job."""
        if self._current_job and self._current_job.id in self._controllers:
            self._controllers[self._current_job.id].start_monitoring()

    def stop_monitoring(self) -> None:
        """Stop monitoring the active workspace job."""
        if self._current_job and self._current_job.id in self._controllers:
            self._controllers[self._current_job.id].stop_monitoring()

    def start_job_monitoring(self, job_id: str) -> None:
        """Start background monitoring for a specific job."""
        ctrl = self._controllers.get(job_id)
        if ctrl:
            ctrl.start_monitoring()

    def stop_job_monitoring(self, job_id: str) -> None:
        """Stop background monitoring for a specific job."""
        ctrl = self._controllers.get(job_id)
        if ctrl:
            ctrl.stop_monitoring()

    def start_all_monitoring(self) -> None:
        """Start background monitoring for all configured jobs."""
        for ctrl in self._controllers.values():
            if ctrl.job.enabled:
                ctrl.start_monitoring()

    def stop_all_monitoring(self) -> None:
        """Stop background monitoring for all jobs."""
        for ctrl in self._controllers.values():
            ctrl.stop_monitoring()

    def sync_now(self) -> tuple[list[TransferRecord], list[TransferRecord]]:
        """Manual sync for the active workspace job."""
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id].sync_now()
        return [], []

    def sync_job(self, job_id: str) -> tuple[list[TransferRecord], list[TransferRecord]]:
        """Manual sync for a specific job."""
        ctrl = self._controllers.get(job_id)
        if ctrl:
            return ctrl.sync_now()
        return [], []

    def transfer_ready_files(self, job_id: Optional[str] = None, override: bool = False) -> int:
        """Transfer ready files for specified or active job."""
        jid = job_id or (self._current_job.id if self._current_job else None)
        if jid and jid in self._controllers:
            return self._controllers[jid].transfer_ready_files(override=override)
        return 0

    def force_start(self, record_id: str) -> None:
        for ctrl in self._controllers.values():
            if ctrl._find_record_by_id(record_id):
                ctrl.force_start(record_id)
                break

    def resolve_conflict(self, record_id: str, resolution: ConflictResolution) -> None:
        for ctrl in self._controllers.values():
            rec = ctrl._find_record_by_id(record_id)
            if rec:
                if resolution == ConflictResolution.OVERWRITE:
                    rec.status = FileStatus.QUEUED
                    rec.error_message = None
                    self._db.save_record(rec)
                    ctrl.file_status_changed.emit(ctrl.job.id, rec.id, rec.status)
                    ctrl._queue_file(rec)
                elif resolution == ConflictResolution.SKIP:
                    rec.status = FileStatus.SKIPPED
                    rec.error_message = "Skipped by user"
                    self._db.save_record(rec)
                    ctrl.file_status_changed.emit(ctrl.job.id, rec.id, rec.status)
                ctrl._emit_stats()
                break

    def get_all_records(self, job_id: Optional[str] = None) -> list[TransferRecord]:
        jid = job_id or (self._current_job.id if self._current_job else None)
        if jid:
            ctrl = self._controllers.get(jid)
            if ctrl:
                return list(ctrl._active_records.values())
            return self._db.get_active_records(jid)
        return []

    def get_history(self, job_id: Optional[str] = None, limit: int = 100) -> list[TransferRecord]:
        jid = job_id or (self._current_job.id if self._current_job else None)
        if jid:
            return self._db.get_records_by_job(jid, limit=limit)
        return []

    def _find_record_by_id(self, record_id: str) -> Optional[TransferRecord]:
        for ctrl in self._controllers.values():
            rec = ctrl._find_record_by_id(record_id)
            if rec:
                return rec
        return self._db.get_record_by_id(record_id)

    # ──────────────────────────────────────────────
    # Controller Signal Forwarding
    # ──────────────────────────────────────────────

    def _on_ctrl_file_detected(self, job_id: str, file_path: str, record: TransferRecord) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.file_detected.emit(file_path, record)

    def _on_ctrl_files_detected(self, job_id: str, records: list) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.files_detected.emit(records)

    def _on_ctrl_file_status_changed(self, job_id: str, record_id: str, status: FileStatus) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.file_status_changed.emit(record_id, status)

    def _on_ctrl_transfer_progress(self, job_id: str, record_id: str, phase: str, cur: int, tot: int) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.transfer_progress.emit(record_id, phase, cur, tot)

    def _on_ctrl_transfer_completed(self, job_id: str, record_id: str, result: TransferResult) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.transfer_completed.emit(record_id, result)

    def _on_ctrl_stats_updated(self, job_id: str, stats: dict) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.stats_updated.emit(stats)

    def _on_ctrl_monitoring_changed(self, job_id: str, is_monitoring: bool) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.monitoring_changed.emit(is_monitoring)

    def _on_ctrl_conflict_detected(self, job_id: str, record: TransferRecord) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.conflict_detected.emit(record)

    def _on_ctrl_log_message(self, job_id: str, level: str, message: str) -> None:
        self.log_message.emit(level, message)

    def _emit_stats(self) -> None:
        if self._current_job:
            stats = self._db.get_statistics(self._current_job.id)
            self.stats_updated.emit(stats)

    def shutdown(self) -> None:
        """Stop all monitoring and workers."""
        self.stop_all_monitoring()
