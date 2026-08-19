"""
Transfer manager — the central multi-job orchestrator with Sequential Global Transfer Queue.

Coordinates:
- JobController: manages individual job background monitoring and file stability checking
- TransferManager: central multi-job registry with a Global FIFO Transfer Queue ensuring
  jobs transfer sequentially (one at a time) to prevent disk saturation, lock contention,
  and missed window end-time triggers
- TransferWorker: background QThread worker handling batch ZipCrypto compression and safe copy
- DatabaseService: persists transfer records and configurations
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
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


@dataclass
class JobBatchRequest:
    """A batch transfer request queued for sequential execution."""
    job_id: str
    records: list[TransferRecord]
    created_at: datetime = datetime.now()


class TransferWorker(QThread):
    """Background worker that executes batch compression and transfer for a single job."""

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

            # Format zip filename: YYYY-MM-DD_<window_start_or_time>.zip
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
                    logger.error("Source file missing: %s", src_path)
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

            for record in successful_records:
                self.transfer_progress.emit(record.id, "compressing", 10, 100)

            # Compress using isolated child process with native standard ZipCrypto encryption
            # Running in an isolated subprocess prevents Python GIL locking on the GUI thread
            cfg_data = {
                "src_paths": src_paths_for_zip,
                "prefixes": prefixes_for_zip,
                "zip_path": temp_zip_path,
                "password": password,
                "compression_level": 4,
            }

            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as f_cfg:
                json.dump(cfg_data, f_cfg)
                cfg_path = f_cfg.name

            try:
                creationflags = 0
                if sys.platform == "win32":
                    creationflags = subprocess.CREATE_NO_WINDOW

                if getattr(sys, "frozen", False):
                    worker_cmd = [sys.executable, "--compression-worker", cfg_path]
                    work_cwd = str(Path(sys.executable).parent)
                else:
                    worker_cmd = [sys.executable, "-u", "-m", "core.compression_worker", cfg_path]
                    work_cwd = str(Path(__file__).resolve().parent.parent)

                proc = subprocess.Popen(
                    worker_cmd,
                    creationflags=creationflags,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=work_cwd,
                    text=True,
                    bufsize=1,
                )
                total_files = len(src_paths_for_zip)
                while proc.poll() is None:
                    if self._cancel_requested:
                        proc.kill()
                        break
                    line = proc.stdout.readline()
                    if line:
                        line_str = line.strip()
                        if line_str.startswith("PROGRESS:"):
                            try:
                                count = int(line_str.split(":", 1)[1])
                                for r in successful_records:
                                    self.transfer_progress.emit(r.id, "compressing", count, total_files)
                            except (ValueError, IndexError):
                                pass
                    else:
                        self.msleep(50)

                stdout_rest, stderr = proc.communicate()
                if proc.returncode != 0 and not self._cancel_requested:
                    raise RuntimeError(f"Compression failed: {stderr}")
            finally:
                if os.path.exists(cfg_path):
                    try:
                        os.remove(cfg_path)
                    except OSError:
                        pass

            for record in successful_records:
                self.transfer_progress.emit(record.id, "compressing", total_files, total_files)

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

            last_emit_time = 0.0

            def progress_cb(phase: str, current: int, total: int) -> None:
                nonlocal last_emit_time
                now = time.time()
                if current == total or (now - last_emit_time) >= 0.1:
                    last_emit_time = now
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
    Background controller managing an individual transfer job's monitoring,
    file safety checking, and schedule detection.
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
    enqueue_requested = Signal(str, list)             # job_id, list[TransferRecord]

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
        self._last_window_executed_minute: Optional[str] = None

        # Periodic timers
        self._safety_timer = QTimer(self)
        self._safety_timer.timeout.connect(self._run_safety_checks)

        self._window_timer = QTimer(self)
        self._window_timer.timeout.connect(self._check_windows)
        self._window_timer.setInterval(2000)

        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._process_retries)
        self._retry_timer.setInterval(self._config.retry_delay * 1000)

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._run_auto_cleanup)
        self._cleanup_timer.setInterval(3600 * 1000)

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
        """Evaluate whether the current time is within the configured window."""
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
        """Start background directory monitoring."""
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
            self.log_message.emit(self.job.id, "ERROR", f"Cannot create source folder: {e}")
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
                logger.exception("Initial scan error for '%s': %s", self.job.name, e)

        threading.Thread(target=_start_and_scan, daemon=True).start()
        self.monitoring_changed.emit(self.job.id, True)
        self.log_message.emit(self.job.id, "INFO", f"Started monitoring '{self.job.name}'")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        if not self.is_monitoring:
            return

        if self._monitor:
            self._monitor.stop()
            self._monitor = None

        self._safety_timer.stop()
        self._retry_timer.stop()
        self._window_timer.stop()

        self.monitoring_changed.emit(self.job.id, False)
        self.log_message.emit(self.job.id, "INFO", f"Stopped monitoring '{self.job.name}'")

    def _on_file_detected(self, file_path: str) -> None:
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
        """Check pending files for lock release and stability in a background thread."""
        if getattr(self, "_is_checking_safety", False):
            return

        to_check = [
            r for r in list(self._active_records.values())
            if r.status in (FileStatus.DETECTED, FileStatus.PROCESSING)
        ]
        if not to_check:
            return

        self._is_checking_safety = True

        def _bg_safety():
            try:
                ready_files = []
                changed = []
                for record in to_check:
                    status = self._safety.check_file(record.source_path)
                    if status != record.status:
                        record.status = status
                        if status == FileStatus.READY:
                            if self.job.schedule_mode == "window" and not record.override_window:
                                record.status = FileStatus.WAITING_FOR_WINDOW
                            else:
                                ready_files.append(record)
                        changed.append(record)

                if changed:
                    self._db.save_records_batch(changed)
                    for record in changed:
                        self.file_status_changed.emit(self.job.id, record.id, record.status)

                if ready_files and self.is_monitoring and self.job.schedule_mode == "continuous":
                    self.enqueue_requested.emit(self.job.id, ready_files)

                self._emit_stats()
            finally:
                self._is_checking_safety = False

        threading.Thread(target=_bg_safety, daemon=True).start()

    def _check_windows(self) -> None:
        """
        Scheduled Window Trigger:
        At the configured window_end time, enqueue all waiting files into the
        Sequential Global Transfer Queue.
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

        if is_end_minute:
            waiting = [
                r for r in list(self._active_records.values())
                if r.status in (FileStatus.WAITING_FOR_WINDOW, FileStatus.READY, FileStatus.PROCESSING, FileStatus.DETECTED)
            ]

            db_records = self._db.get_active_records(self.job.id)
            for r in db_records:
                if r.source_path not in self._active_records:
                    self._active_records[r.source_path] = r
                if r.status in (FileStatus.WAITING_FOR_WINDOW, FileStatus.READY, FileStatus.PROCESSING, FileStatus.DETECTED) and r not in waiting:
                    waiting.append(r)

            if waiting and self._last_window_executed_minute != current_minute:
                self._last_window_executed_minute = current_minute
                logger.info("Window end reached (%s) for '%s'. Enqueueing %d files.",
                            self.job.window_end, self.job.name, len(waiting))
                self.log_message.emit(
                    self.job.id,
                    "INFO",
                    f"Window end reached ({self.job.window_end}). Enqueueing {len(waiting)} file(s) for transfer.",
                )
                for record in waiting:
                    record.status = FileStatus.READY
                    self.file_status_changed.emit(self.job.id, record.id, record.status)

                self._db.save_records_batch(waiting)
                self.enqueue_requested.emit(self.job.id, waiting)
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
        """Transfer ready files by requesting placement into the Central Transfer Queue."""
        ready = []
        for r in list(self._active_records.values()):
            if r.status in (FileStatus.READY, FileStatus.WAITING_FOR_WINDOW):
                if override or r.override_window or self.is_in_transfer_window:
                    r.override_window = True
                    r.status = FileStatus.READY
                    self._db.save_record(r)
                    ready.append(r)
                else:
                    r.status = FileStatus.WAITING_FOR_WINDOW
                    self._db.save_record(r)
                    self.file_status_changed.emit(self.job.id, r.id, r.status)

        if ready:
            self.enqueue_requested.emit(self.job.id, ready)
            return len(ready)
        return 0

    def force_start(self, record_id: str) -> None:
        record = self._find_record_by_id(record_id)
        if record and record.status in (FileStatus.PROCESSING, FileStatus.WAITING_FOR_WINDOW, FileStatus.READY):
            record.override_window = True
            record.status = FileStatus.READY
            self._db.save_record(record)
            self.file_status_changed.emit(self.job.id, record.id, record.status)
            self.enqueue_requested.emit(self.job.id, [record])

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
            self.log_message.emit(self.job.id, "INFO", f"Auto-cleanup removed {deleted} old source file(s)")

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
    Central Multi-Job Transfer Manager with Sequential Global Transfer Queue.

    - Monitors all enabled jobs concurrently.
    - Processes transfer batches sequentially (one job at a time in FIFO order)
      to eliminate disk thrashing, lock contention, and missed schedules.
    """

    file_detected = Signal(str, object)          # file_path, TransferRecord (for active workspace job)
    files_detected = Signal(list)                # list[TransferRecord] (for active workspace job)
    file_status_changed = Signal(str, object)    # record_id, FileStatus (for active workspace job)
    transfer_progress = Signal(str, str, int, int)  # record_id, phase, current, total
    transfer_completed = Signal(str, object)     # record_id, TransferResult (for active workspace job)
    stats_updated = Signal(dict)                 # {status: count} for active workspace job
    monitoring_changed = Signal(bool)            # is_monitoring for active workspace job
    conflict_detected = Signal(object)           # TransferRecord
    log_message = Signal(str, str)               # level, message

    # Multi-job live signals for Main Dashboard (emitted for all jobs in real-time)
    job_file_detected = Signal(str, str, object)       # job_id, file_path, TransferRecord
    job_file_status_changed = Signal(str, str, object) # job_id, record_id, FileStatus
    job_transfer_progress = Signal(str, str, int, int) # job_id, phase, current, total
    job_transfer_completed = Signal(str, str, object)  # job_id, record_id, TransferResult
    job_stats_updated = Signal(str, dict)              # job_id, stats dict
    job_status_changed = Signal(str, str)              # job_id, execution_state

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

        # Sequential Global Transfer Queue state
        self._transfer_queue: list[JobBatchRequest] = []
        self._active_transfer_job_id: Optional[str] = None
        self._active_worker: Optional[TransferWorker] = None

        self.reload_jobs()

    def reload_jobs(self) -> None:
        """Reload all jobs from database and synchronize controllers."""
        jobs = self._db.get_jobs()
        job_map = {j.id: j for j in jobs}

        for jid in list(self._controllers.keys()):
            if jid not in job_map:
                ctrl = self._controllers.pop(jid)
                ctrl.stop_monitoring()
                ctrl.deleteLater()

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
                ctrl.enqueue_requested.connect(self.enqueue_job_batch)
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
        return self._active_worker

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

    def get_job_execution_state(self, job_id: str) -> str:
        """
        Return the real-time execution state for a job card:
        'TRANSFERRING', 'QUEUED', 'IN_WINDOW', 'OUTSIDE_WINDOW', 'MONITORING', or 'IDLE'
        """
        if self._active_transfer_job_id == job_id:
            return "TRANSFERRING"
        if any(req.job_id == job_id for req in self._transfer_queue):
            return "QUEUED"
        ctrl = self._controllers.get(job_id)
        if not ctrl:
            return "IDLE"
        if ctrl.is_monitoring:
            if ctrl.job.schedule_mode == "window":
                return "IN_WINDOW" if ctrl.is_in_transfer_window else "OUTSIDE_WINDOW"
            return "MONITORING"
        return "IDLE"

    def set_job(self, job: TransferJob) -> None:
        self._current_job = job
        if job.id not in self._controllers:
            self.reload_jobs()
        self._emit_stats()

    def start_monitoring(self) -> None:
        if self._current_job and self._current_job.id in self._controllers:
            self._controllers[self._current_job.id].start_monitoring()

    def stop_monitoring(self) -> None:
        if self._current_job and self._current_job.id in self._controllers:
            self._controllers[self._current_job.id].stop_monitoring()

    def start_job_monitoring(self, job_id: str) -> None:
        ctrl = self._controllers.get(job_id)
        if ctrl:
            ctrl.start_monitoring()

    def stop_job_monitoring(self, job_id: str) -> None:
        ctrl = self._controllers.get(job_id)
        if ctrl:
            ctrl.stop_monitoring()

    def start_all_monitoring(self) -> None:
        for ctrl in self._controllers.values():
            if ctrl.job.enabled:
                ctrl.start_monitoring()

    def stop_all_monitoring(self) -> None:
        for ctrl in self._controllers.values():
            ctrl.stop_monitoring()

    def sync_now(self) -> tuple[list[TransferRecord], list[TransferRecord]]:
        if self._current_job and self._current_job.id in self._controllers:
            return self._controllers[self._current_job.id].sync_now()
        return [], []

    def sync_job(self, job_id: str) -> tuple[list[TransferRecord], list[TransferRecord]]:
        ctrl = self._controllers.get(job_id)
        if ctrl:
            return ctrl.sync_now()
        return [], []

    def transfer_ready_files(self, job_id: Optional[str] = None, override: bool = False) -> int:
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
                    self.enqueue_job_batch(ctrl.job.id, [rec])
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
    # Sequential Global Transfer Queue Dispatcher
    # ──────────────────────────────────────────────

    def enqueue_job_batch(self, job_id: str, records: list[TransferRecord]) -> None:
        """Enqueue a batch of records for sequential processing."""
        ctrl = self.get_controller(job_id)
        if not ctrl or not records:
            return

        for record in records:
            record.status = FileStatus.QUEUED
            self._db.save_record(record)
            ctrl.file_status_changed.emit(job_id, record.id, record.status)

        # Check if job is already in queue
        existing = next((req for req in self._transfer_queue if req.job_id == job_id), None)
        if existing:
            # Merge records into existing request
            existing_ids = {r.id for r in existing.records}
            for r in records:
                if r.id not in existing_ids:
                    existing.records.append(r)
        else:
            self._transfer_queue.append(JobBatchRequest(job_id=job_id, records=records))

        ctrl._emit_stats()

        # Emit updated execution states for all jobs
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

        # If no job is currently transferring, dispatch immediately
        if self._active_worker is None:
            self._dispatch_next_batch()

    def _dispatch_next_batch(self) -> None:
        """Dispatch the next job batch in the FIFO queue."""
        if not self._transfer_queue:
            self._active_transfer_job_id = None
            self._active_worker = None
            for jid in list(self._controllers.keys()):
                self.job_status_changed.emit(jid, self.get_job_execution_state(jid))
            return

        request = self._transfer_queue.pop(0)
        ctrl = self.get_controller(request.job_id)
        if not ctrl or not request.records:
            self._dispatch_next_batch()
            return

        self._active_transfer_job_id = request.job_id
        logger.info("Sequential Queue: Starting batch transfer for job '%s' (%d records)",
                    ctrl.job.name, len(request.records))
        self.log_message.emit("INFO", f"Starting transfer for '{ctrl.job.name}' ({len(request.records)} files)")

        # Notify UI of updated statuses across all jobs
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

        self._active_worker = TransferWorker(
            records=request.records,
            engine=ctrl._engine,
            db=self._db,
            config=self._config,
            job=ctrl.job,
            parent=self,
        )
        self._active_worker.transfer_started.connect(
            lambda rid, jid=ctrl.job.id: self._on_worker_transfer_started(jid, rid)
        )
        self._active_worker.transfer_progress.connect(
            lambda rid, ph, c, t, jid=ctrl.job.id: self._on_worker_progress(jid, rid, ph, c, t)
        )
        self._active_worker.transfer_completed.connect(
            lambda rid, res, jid=ctrl.job.id: self._on_worker_transfer_completed(jid, rid, res)
        )
        self._active_worker.finished.connect(
            lambda jid=ctrl.job.id: self._on_worker_all_done(jid)
        )
        self._active_worker.start()

    def _on_worker_progress(self, job_id: str, record_id: str, phase: str, cur: int, tot: int) -> None:
        ctrl = self.get_controller(job_id)
        if ctrl:
            ctrl.transfer_progress.emit(job_id, record_id, phase, cur, tot)
        self.job_transfer_progress.emit(job_id, phase, cur, tot)
        if self._current_job and self._current_job.id == job_id:
            self.transfer_progress.emit(record_id, phase, cur, tot)

    def _on_worker_transfer_started(self, job_id: str, record_id: str) -> None:
        ctrl = self.get_controller(job_id)
        if ctrl:
            ctrl.file_status_changed.emit(job_id, record_id, FileStatus.TRANSFERRING)
            self.job_status_changed.emit(job_id, "TRANSFERRING")

    def _on_worker_transfer_completed(self, job_id: str, record_id: str, result: TransferResult) -> None:
        ctrl = self.get_controller(job_id)
        if ctrl:
            record = ctrl._find_record_by_id(record_id)
            if record:
                self._db.save_record(record)
                ctrl.transfer_completed.emit(job_id, record_id, result)
            ctrl._emit_stats()

    def _on_worker_all_done(self, job_id: str) -> None:
        ctrl = self.get_controller(job_id)
        if ctrl:
            completed_paths = [
                path for path, r in ctrl._active_records.items()
                if r.status in (FileStatus.COMPLETED, FileStatus.SKIPPED)
            ]
            for path in completed_paths:
                del ctrl._active_records[path]
            ctrl._emit_stats()

        self._active_transfer_job_id = None
        self._active_worker = None

        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

        # Automatically process the next queued job batch in line
        self._dispatch_next_batch()

    # ──────────────────────────────────────────────
    # Controller Signal Forwarding
    # ──────────────────────────────────────────────

    def _on_ctrl_file_detected(self, job_id: str, file_path: str, record: TransferRecord) -> None:
        self.job_file_detected.emit(job_id, file_path, record)
        if self._current_job and self._current_job.id == job_id:
            self.file_detected.emit(file_path, record)

    def _on_ctrl_files_detected(self, job_id: str, records: list) -> None:
        for r in records:
            self.job_file_detected.emit(job_id, r.source_path, r)
        if self._current_job and self._current_job.id == job_id:
            self.files_detected.emit(records)

    def _on_ctrl_file_status_changed(self, job_id: str, record_id: str, status: FileStatus) -> None:
        self.job_file_status_changed.emit(job_id, record_id, status)
        if self._current_job and self._current_job.id == job_id:
            self.file_status_changed.emit(record_id, status)

    def _on_ctrl_transfer_progress(self, job_id: str, record_id: str, phase: str, cur: int, tot: int) -> None:
        if self._current_job and self._current_job.id == job_id:
            self.transfer_progress.emit(record_id, phase, cur, tot)

    def _on_ctrl_transfer_completed(self, job_id: str, record_id: str, result: TransferResult) -> None:
        self.job_transfer_completed.emit(job_id, record_id, result)
        if self._current_job and self._current_job.id == job_id:
            self.transfer_completed.emit(record_id, result)

    def _on_ctrl_stats_updated(self, job_id: str, stats: dict) -> None:
        self.job_stats_updated.emit(job_id, stats)
        if self._current_job and self._current_job.id == job_id:
            self.stats_updated.emit(stats)

    def _on_ctrl_monitoring_changed(self, job_id: str, is_monitoring: bool) -> None:
        self.job_status_changed.emit(job_id, self.get_job_execution_state(job_id))
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
            self.job_stats_updated.emit(self._current_job.id, stats)

    def shutdown(self) -> None:
        self.stop_all_monitoring()
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.cancel()
