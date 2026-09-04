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


def format_deletion_message(file_names: list[str], folder_name: str, is_dir_deleted: bool = False) -> str:
    """Format human-friendly deletion messages for files and folders."""
    f_label = f"folder '{folder_name}'" if folder_name else "source folder"
    if is_dir_deleted:
        if file_names:
            return f"Folder '{folder_name}' and its {len(file_names)} file(s) were deleted; removed from queue."
        return f"Folder '{folder_name}' was deleted; removed from queue."

    count = len(file_names)
    if count == 0:
        return f"Files were deleted from {f_label}."
    if count == 1:
        return f"File '{file_names[0]}' was deleted from {f_label}."
    if count == 2:
        return f"Files '{file_names[0]}' and '{file_names[1]}' were deleted from {f_label}."
    if count <= 5:
        all_but_last = ", ".join(f"'{f}'" for f in file_names[:-1])
        return f"Files {all_but_last}, and '{file_names[-1]}' were deleted from {f_label}."

    first_three = ", ".join(f"'{f}'" for f in file_names[:3])
    remaining = count - 3
    return f"Files {first_three}, and {remaining} others were deleted from {f_label}."


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
    worker_event = Signal(str, str)                 # job_id, message
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
        self._current_proc: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._current_proc:
            try:
                self._current_proc.kill()
            except Exception:
                pass

    def run(self) -> None:
        if not self._records:
            self.all_done.emit()
            return

        if self._config.batch_compression_enabled and len(self._records) > 0:
            self._run_batch_compression()
        else:
            self._run_direct_transfers()

    def _run_direct_transfers(self) -> None:
        threads = max(1, min(128, self._config.transfer_threads))
        if threads == 1 or len(self._records) <= 1:
            for record in self._records:
                if self._cancel_requested:
                    break

                self.transfer_started.emit(record.id)

                def make_cb(rid: str):
                    return lambda p, c, t: self.transfer_progress.emit(rid, p, c, t)

                result = self._engine.transfer_file(record, make_cb(record.id))
                self._db.save_record(record)
                self.transfer_completed.emit(record.id, result)
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                def _do_transfer(record: TransferRecord):
                    if self._cancel_requested:
                        return
                    self.transfer_started.emit(record.id)
                    last_emit = [0.0]
                    def throttled_cb(p: str, c: int, t: int):
                        now_t = time.time()
                        if c >= t or (now_t - last_emit[0]) >= 0.1:
                            last_emit[0] = now_t
                            self.transfer_progress.emit(record.id, p, c, t)

                    result = self._engine.transfer_file(record, throttled_cb)
                    self._db.save_record(record)
                    self.transfer_completed.emit(record.id, result)

                futures = [executor.submit(_do_transfer, r) for r in self._records]
                concurrent.futures.wait(futures)

        self.all_done.emit()

    def _run_batch_compression(self) -> None:
        temp_zip_path = None
        try:
            if self._records:
                self.transfer_started.emit(self._records[0].id)

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

            if job and job.destination_folder:
                dest_dir = Path(job.destination_folder)
            else:
                dest_dir = Path(self._records[0].destination_path).parent

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.error("Cannot create destination folder %s: %s", dest_dir, e)

            target_path = dest_dir / temp_zip_name
            counter = 1
            while target_path.exists():
                temp_zip_name = f"{base_zip_name}_{counter}.zip"
                target_path = dest_dir / temp_zip_name
                counter += 1

            unique_tag = f"{job.id[:8] if job else 'job'}_{uuid.uuid4().hex[:8]}"
            # Place temp zip in dest_dir to support huge datasets (>10GB) without C: drive exhaustion
            try:
                test_tmp = dest_dir / f".tmp_test_{unique_tag}"
                test_tmp.touch()
                test_tmp.unlink()
                temp_dir = str(dest_dir)
            except OSError:
                temp_dir = tempfile.gettempdir()

            temp_zip_path = os.path.join(temp_dir, f".tmp_batch_{unique_tag}_{temp_zip_name}")

            if self._cancel_requested:
                self.all_done.emit()
                return

            candidates = list(self._records)
            successful_records = []
            compress_success = False
            max_compress_attempts = 3

            for attempt in range(max_compress_attempts):
                if self._cancel_requested:
                    break

                successful_records = []
                src_paths_for_zip = []
                prefixes_for_zip = []
                skipped_before = []

                for record in candidates:
                    src_path = Path(record.source_path)
                    if not src_path.exists():
                        logger.info("Source file missing/deleted: %s", src_path)
                        record.status = FileStatus.SKIPPED
                        record.error_message = "Source file deleted before transfer"
                        self._db.save_record(record)
                        self.transfer_completed.emit(
                            record.id, TransferResult(success=True, record=record, error_message="Source file deleted before transfer")
                        )
                        skipped_before.append(record)
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

                if skipped_before and self._job:
                    del_names = [r.file_name for r in skipped_before]
                    parent_name = Path(skipped_before[0].source_path).parent.name
                    del_msg = format_deletion_message(del_names, parent_name)
                    if successful_records:
                        msg = f"{del_msg} Excluded from archive; compressing remaining {len(successful_records)} file(s)..."
                    else:
                        msg = f"{del_msg} All files were deleted; transfer cancelled."
                    self.worker_event.emit(self._job.id, msg)

                if not successful_records or self._cancel_requested:
                    break

                if os.path.exists(temp_zip_path):
                    try:
                        os.remove(temp_zip_path)
                    except OSError:
                        pass

                total_bytes = sum(r.file_size for r in successful_records)
                for record in successful_records:
                    self.transfer_progress.emit(record.id, "compressing", 0, max(1, total_bytes))

                cfg_data = {
                    "src_paths": src_paths_for_zip,
                    "prefixes": prefixes_for_zip,
                    "zip_path": temp_zip_path,
                    "password": password,
                    "compression_level": 1,
                    "total_bytes": total_bytes,
                }

                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8") as f_cfg:
                    json.dump(cfg_data, f_cfg)
                    cfg_path = f_cfg.name

                proc = None
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
                    self._current_proc = proc
                    total_files = len(src_paths_for_zip)
                    last_emit_time = 0.0
                    last_disk_check = time.time()
                    mid_deletion_detected = False

                    while proc.poll() is None:
                        if self._cancel_requested:
                            proc.kill()
                            break

                        now = time.time()
                        # Real-time mid-compression deletion check (every 1.5s)
                        if (now - last_disk_check) >= 1.5:
                            last_disk_check = now
                            for r in successful_records:
                                if not os.path.exists(r.source_path):
                                    time.sleep(0.02)
                                    if not os.path.exists(r.source_path):
                                        mid_deletion_detected = True
                                        logger.info("File deleted mid-compression: %s", r.source_path)
                                        break
                            if mid_deletion_detected:
                                proc.kill()
                                break

                        line = proc.stdout.readline()
                        if line:
                            line_str = line.strip()
                            if line_str.startswith("PROGRESS_BYTES:"):
                                try:
                                    parts = line_str.split(":")
                                    cur_bytes = int(parts[1])
                                    tot_bytes = int(parts[2])
                                    if tot_bytes > 0 and (cur_bytes == tot_bytes or (now - last_emit_time) >= 0.08):
                                        last_emit_time = now
                                        self.transfer_progress.emit(successful_records[0].id, "compressing", cur_bytes, tot_bytes)
                                except (ValueError, IndexError):
                                    pass
                            elif line_str.startswith("PROGRESS:"):
                                try:
                                    count = int(line_str.split(":", 1)[1])
                                    if count == total_files or (now - last_emit_time) >= 0.1:
                                        last_emit_time = now
                                        self.transfer_progress.emit(successful_records[0].id, "compressing", count, total_files)
                                except (ValueError, IndexError):
                                    pass
                        else:
                            self.msleep(15)

                    stdout_rest, stderr = proc.communicate()
                    if self._cancel_requested:
                        break

                    # Verify that all source files STILL exist on disk (none were deleted before/during compression)
                    deleted_records = []
                    still_existing = []
                    for r in successful_records:
                        if not os.path.exists(r.source_path):
                            r.status = FileStatus.SKIPPED
                            r.error_message = "Source file deleted during transfer"
                            self._db.save_record(r)
                            self.transfer_completed.emit(
                                r.id, TransferResult(success=True, record=r, error_message="Source file deleted during transfer")
                            )
                            deleted_records.append(r)
                        else:
                            still_existing.append(r)

                    if deleted_records:
                        # Temporary zip contains deleted file(s) — destroy it and re-compress without them
                        if temp_zip_path and os.path.exists(temp_zip_path):
                            try:
                                os.remove(temp_zip_path)
                            except OSError:
                                pass

                        del_names = [r.file_name for r in deleted_records]
                        parent_name = Path(deleted_records[0].source_path).parent.name
                        del_msg = format_deletion_message(del_names, parent_name)
                        if self._job:
                            if still_existing:
                                event_msg = f"{del_msg} Discarded partial archive; automatically restarting with remaining {len(still_existing)} file(s)..."
                            else:
                                event_msg = f"{del_msg} All files were deleted; transfer cancelled."
                            self.worker_event.emit(self._job.id, event_msg)

                        if still_existing:
                            candidates = still_existing
                            continue  # Automatically re-compress remaining valid files!
                        else:
                            break

                    if proc.returncode == 0 and os.path.exists(temp_zip_path):
                        compress_success = True
                        successful_records = still_existing
                        break
                    else:
                        if temp_zip_path and os.path.exists(temp_zip_path):
                            try:
                                os.remove(temp_zip_path)
                            except OSError:
                                pass
                        raise RuntimeError(f"Compression failed: {stderr}")
                finally:
                    if os.path.exists(cfg_path):
                        try:
                            os.remove(cfg_path)
                        except OSError:
                            pass

            if self._cancel_requested or not compress_success or not successful_records or not os.path.exists(temp_zip_path):
                if temp_zip_path and os.path.exists(temp_zip_path):
                    try:
                        os.remove(temp_zip_path)
                    except OSError:
                        pass
                self.all_done.emit()
                return

            for record in successful_records:
                self.transfer_progress.emit(record.id, "compressing", total_files, total_files)

            valid_records = successful_records
            first_record = valid_records[0]

            # Instantaneous finalization of the completed archive into target_path
            try:
                if target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass

                if temp_dir == str(dest_dir):
                    os.replace(temp_zip_path, str(target_path))
                else:
                    shutil.move(temp_zip_path, str(target_path))

                final_stat = target_path.stat()
                now_dt = datetime.now()

                result = TransferResult(success=True, record=first_record)
                for record in valid_records:
                    record.status = FileStatus.COMPLETED
                    record.destination_path = str(target_path)
                    record.transfer_completed = now_dt
                    record.verification_passed = True
                self._db.save_records_batch(valid_records)
                for record in valid_records:
                    self.transfer_completed.emit(record.id, result)
            except OSError as e:
                result = TransferResult(success=False, record=first_record, error_message=f"Finalizing archive failed: {e}")
                for record in valid_records:
                    record.status = FileStatus.FAILED
                    record.error_message = result.error_message
                self._db.save_records_batch(valid_records)
                for record in valid_records:
                    self.transfer_completed.emit(record.id, result)

        finally:
            self._current_proc = None
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
    job_event = Signal(str, str)                      # job_id, message

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

        self._retry_timer = QTimer(self)
        self._retry_timer.timeout.connect(self._process_retries)
        self._retry_timer.setInterval(self._config.retry_delay * 1000)

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._run_auto_cleanup)
        self._cleanup_timer.setInterval(3600 * 1000)

        self._load_active_records()

    def _load_active_records(self) -> None:
        active = self._db.get_active_records(self.job.id)
        to_save = []
        for record in active:
            if self.job.schedule_mode == "window" and record.status in (FileStatus.QUEUED, FileStatus.TRANSFERRING, FileStatus.VERIFYING):
                record.status = FileStatus.WAITING_FOR_WINDOW
                to_save.append(record)
            elif self.job.schedule_mode == "continuous" and record.status in (FileStatus.TRANSFERRING, FileStatus.VERIFYING):
                record.status = FileStatus.READY
                to_save.append(record)
            self._active_records[record.source_path] = record
        if to_save:
            self._db.save_records_batch(to_save)

    @property
    def is_monitoring(self) -> bool:
        return self._monitor is not None and self._monitor.is_running

    @property
    def is_in_transfer_window(self) -> bool:
        """Evaluate whether the current time and day are within the configured window."""
        if self.job.schedule_mode != "window":
            return True
        try:
            # Day of week check
            day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            today_code = day_names[datetime.now().weekday()]
            active_days = self.job.days_of_week or day_names
            if today_code not in active_days:
                return False

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

        use_polling = self._config.network_drive_mode or self.job.source_folder.startswith(("\\\\", "//"))
        self._monitor = FileMonitor(
            source_folder=self.job.source_folder,
            on_file_detected=self._on_file_detected,
            on_file_deleted=self._on_file_deleted,
            on_dir_deleted=self._on_dir_deleted,
            reconciliation_interval=recon_interval,
            temp_suffix=self._config.temp_file_suffix,
            use_polling=use_polling,
        )
        self._monitor.start()

        def _start_and_scan():
            try:
                # Ensure active records in memory includes any active records saved in DB
                db_recs = self._db.get_active_records(self.job.id)
                to_save_start = []
                for r in db_recs:
                    if self.job.schedule_mode == "window" and r.status in (FileStatus.QUEUED, FileStatus.TRANSFERRING, FileStatus.VERIFYING):
                        r.status = FileStatus.WAITING_FOR_WINDOW
                        to_save_start.append(r)
                    elif self.job.schedule_mode == "continuous" and r.status in (FileStatus.TRANSFERRING, FileStatus.VERIFYING):
                        r.status = FileStatus.READY
                        to_save_start.append(r)
                    if r.source_path not in self._active_records:
                        self._active_records[r.source_path] = r
                if to_save_start:
                    self._db.save_records_batch(to_save_start)

                # Check for files deleted while paused / stopped (verify source folder is accessible first)
                if not os.path.exists(self.job.source_folder):
                    logger.warning("Source folder '%s' temporarily unreachable, skipping deletion check", self.job.source_folder)
                    return

                deleted_records = []
                for path_str, rec in list(self._active_records.items()):
                    if rec.status not in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                        if not os.path.exists(path_str):
                            time.sleep(0.05)
                            if not os.path.exists(path_str):
                                deleted_records.append(rec)

                if deleted_records:
                    by_folder: dict[str, list[TransferRecord]] = {}
                    for rec in deleted_records:
                        self._active_records.pop(rec.source_path, None)
                        rec.status = FileStatus.SKIPPED
                        rec.error_message = "Source file deleted before transfer"
                        by_folder.setdefault(Path(rec.source_path).parent.name, []).append(rec)

                    self._db.save_records_batch(deleted_records)
                    for rec in deleted_records:
                        self.file_status_changed.emit(self.job.id, rec.id, rec.status)

                    for parent_folder, recs in by_folder.items():
                        f_names = [r.file_name for r in recs]
                        parent_path = Path(recs[0].source_path).parent
                        msg = format_deletion_message(f_names, parent_folder, is_dir_deleted=not parent_path.exists())
                        self.job_event.emit(self.job.id, msg)

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

        self.monitoring_changed.emit(self.job.id, False)
        self.log_message.emit(self.job.id, "INFO", f"Stopped monitoring '{self.job.name}'")

    def _on_dir_deleted(self, dir_path: str) -> None:
        """Real-time handler for directory deletion events from watchdog."""
        # Guard against phantom events on network shares: verify directory actually does not exist
        if os.path.exists(dir_path):
            return
        time.sleep(0.05)
        if os.path.exists(dir_path):
            return

        # Never treat root source folder as deleted if it exists
        if os.path.normpath(dir_path) == os.path.normpath(self.job.source_folder):
            if os.path.exists(self.job.source_folder):
                return

        dir_norm = os.path.normpath(dir_path)
        matching_paths = []
        for p_str in list(self._active_records.keys()):
            p_norm = os.path.normpath(p_str)
            if p_norm.startswith(dir_norm + os.sep) or p_norm == dir_norm:
                matching_paths.append(p_str)

        deleted_recs = []
        for p_str in matching_paths:
            rec = self._active_records.pop(p_str, None)
            if rec and rec.status not in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                rec.status = FileStatus.SKIPPED
                rec.error_message = f"Parent folder '{Path(dir_path).name}' deleted before transfer"
                deleted_recs.append(rec)

        if not deleted_recs:
            return

        self._db.save_records_batch(deleted_recs)
        for r in deleted_recs:
            self.file_status_changed.emit(self.job.id, r.id, r.status)

        folder_name = Path(dir_path).name
        file_names = [r.file_name for r in deleted_recs]
        msg = format_deletion_message(file_names, folder_name, is_dir_deleted=True)
        self.job_event.emit(self.job.id, msg)
        self._emit_stats()

    def _on_file_deleted(self, file_path: str) -> None:
        """Real-time handler for file deletion events from watchdog."""
        # Guard against phantom events on network shares: verify file actually does not exist
        if os.path.exists(file_path):
            return

        rec = self._active_records.pop(file_path, None)
        if rec and rec.status not in (FileStatus.COMPLETED, FileStatus.SKIPPED):
            rec.status = FileStatus.SKIPPED
            rec.error_message = "Source file deleted before transfer"
            self._db.save_record(rec)
            self.file_status_changed.emit(self.job.id, rec.id, rec.status)
            parent_name = Path(file_path).parent.name
            msg = format_deletion_message([rec.file_name], parent_name)
            self.job_event.emit(self.job.id, msg)
            self._emit_stats()

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
        """Check pending files for lock release, stability, and deletions in a background thread."""
        if getattr(self, "_is_checking_safety", False):
            return

        to_check = [
            r for r in list(self._active_records.values())
            if r.status in (FileStatus.DETECTED, FileStatus.PROCESSING, FileStatus.WAITING_FOR_WINDOW, FileStatus.READY)
        ]
        if not to_check:
            return

        self._is_checking_safety = True

        def _bg_safety():
            try:
                # Guard against temporary network/SMB share disconnections
                if not os.path.exists(self.job.source_folder):
                    return

                # Check if any active records have been deleted from disk
                deleted_records = []
                for record in list(to_check):
                    if not os.path.exists(record.source_path):
                        time.sleep(0.05)
                        if not os.path.exists(record.source_path):
                            deleted_records.append(record)
                            if record in to_check:
                                to_check.remove(record)

                if deleted_records:
                    by_folder: dict[str, list[TransferRecord]] = {}
                    for rec in deleted_records:
                        self._active_records.pop(rec.source_path, None)
                        rec.status = FileStatus.SKIPPED
                        rec.error_message = "Source file deleted before transfer"
                        by_folder.setdefault(Path(rec.source_path).parent.name, []).append(rec)

                    self._db.save_records_batch(deleted_records)
                    for rec in deleted_records:
                        self.file_status_changed.emit(self.job.id, rec.id, rec.status)

                    for parent_folder, recs in by_folder.items():
                        f_names = [r.file_name for r in recs]
                        parent_path = Path(recs[0].source_path).parent
                        msg = format_deletion_message(f_names, parent_folder, is_dir_deleted=not parent_path.exists())
                        self.job_event.emit(self.job.id, msg)

                    self._emit_stats()

                # Only files that are still being written (DETECTED or PROCESSING) need stability checks
                stability_candidates = [
                    r for r in to_check
                    if r.status in (FileStatus.DETECTED, FileStatus.PROCESSING)
                ]

                if not stability_candidates:
                    return

                ready_files = []
                changed = []
                for record in stability_candidates:
                    if not Path(record.source_path).exists():
                        continue
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

        # Check Active Days
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        today_code = day_names[now.weekday()]
        active_days = self.job.days_of_week or day_names
        if today_code not in active_days:
            return

        try:
            end_time_base = datetime.strptime(self.job.window_end, "%H:%M").time()
        except (ValueError, AttributeError):
            return

        current_minute = now.strftime("%Y-%m-%d_%H:%M")
        is_end_minute = (now_time.hour == end_time_base.hour and now_time.minute == end_time_base.minute)

        if is_end_minute:
            if self._last_window_executed_minute == current_minute:
                return
            self._last_window_executed_minute = current_minute

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

            if waiting:
                logger.info("Window end reached (%s) for '%s'. Enqueueing %d files.",
                            self.job.window_end, self.job.name, len(waiting))
                self.log_message.emit(
                    self.job.id,
                    "INFO",
                    f"Window end reached ({self.job.window_end}). Enqueueing {len(waiting)} file(s) for transfer.",
                )
                for record in waiting:
                    record.status = FileStatus.READY

                self._db.save_records_batch(waiting)
                self.enqueue_requested.emit(self.job.id, waiting)
                self._emit_stats()

    def sync_now(self) -> tuple[list[TransferRecord], list[TransferRecord]]:
        """Manual sync scan for this job — immediately discovers and triggers transfer."""
        if not self._monitor:
            recon_interval = self._config.reconciliation_interval
            use_polling = self._config.network_drive_mode or self.job.source_folder.startswith(("\\\\", "//"))
            self._monitor = FileMonitor(
                source_folder=self.job.source_folder,
                on_file_detected=self._on_file_detected,
                on_file_deleted=self._on_file_deleted,
                on_dir_deleted=self._on_dir_deleted,
                reconciliation_interval=recon_interval,
                temp_suffix=self._config.temp_file_suffix,
                use_polling=use_polling,
            )

        self._monitor.update_known_files()
        found_files = self._monitor.scan_folder()

        batch_new = []
        for fpath in found_files:
            try:
                p = Path(fpath)
                if not p.exists() or p.is_dir():
                    continue
                fsize = p.stat().st_size
                mtime = p.stat().st_mtime
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
                    status=FileStatus.READY,
                    override_window=True,
                )
                self._active_records[fpath] = rec
                batch_new.append(rec)

        if batch_new:
            self._db.save_records_batch(batch_new)

        deleted_in_sync = []
        ready: list[TransferRecord] = []
        for rec in list(self._active_records.values()):
            if not Path(rec.source_path).exists():
                rec.status = FileStatus.SKIPPED
                rec.error_message = "Source file deleted before transfer"
                deleted_in_sync.append(rec)
                self._active_records.pop(rec.source_path, None)
                continue

            # Recover any non-finished file (including interrupted TRANSFERRING, QUEUED, or FAILED)
            if rec.status not in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                rec.override_window = True
                rec.status = FileStatus.READY
                ready.append(rec)

        if deleted_in_sync:
            self._db.save_records_batch(deleted_in_sync)
            for r in deleted_in_sync:
                self.file_status_changed.emit(self.job.id, r.id, r.status)
            by_folder: dict[str, list[TransferRecord]] = {}
            for rec in deleted_in_sync:
                by_folder.setdefault(Path(rec.source_path).parent.name, []).append(rec)
            for parent_folder, recs in by_folder.items():
                f_names = [r.file_name for r in recs]
                parent_path = Path(recs[0].source_path).parent
                msg = format_deletion_message(f_names, parent_folder, is_dir_deleted=not parent_path.exists())
                self.job_event.emit(self.job.id, msg)

        if ready:
            self._db.save_records_batch(ready)
            for r in ready:
                self.file_status_changed.emit(self.job.id, r.id, r.status)
            self.enqueue_requested.emit(self.job.id, ready)
            self._emit_stats()

        return ready, []

    def reset_job(self) -> None:
        """Reset all active state, safety checks, and history for this job."""
        self.stop_monitoring()
        self._safety.clear()
        self._active_records.clear()
        self._db.clear_job_history(self.job.id)
        self._emit_stats()
        self.job_event.emit(self.job.id, "Job reset and ready.")

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
        active_bytes = sum(
            r.file_size for r in self._active_records.values()
            if r.status != FileStatus.SKIPPED and r.file_size
        )
        if active_bytes > stats.get("TOTAL_SOURCE_BYTES", 0):
            stats["TOTAL_SOURCE_BYTES"] = active_bytes
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
    job_event = Signal(str, str)                       # job_id, message
    _batch_dispatch_requested = Signal()               # Internal thread-safe dispatch trigger

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

        # Worker pool & Queue state
        self._transfer_queue: list[JobBatchRequest] = []
        self._active_workers: dict[str, TransferWorker] = {}
        self._preparing_jobs: set[str] = set()
        self._batch_dispatch_requested.connect(self._dispatch_next_batch)

        # Master window evaluation timer across all jobs (evaluates in strict alphabetical order)
        self._master_window_timer = QTimer(self)
        self._master_window_timer.timeout.connect(self._check_all_windows)
        self._master_window_timer.setInterval(1000)
        self._master_window_timer.start()

        self.reload_jobs()

    def _check_all_windows(self) -> None:
        """Centrally evaluate scheduled windows across all controllers in strict alphabetical order."""
        now = datetime.now()
        current_minute = now.strftime("%Y-%m-%d_%H:%M")
        now_time = now.time()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        today_code = day_names[now.weekday()]

        triggered_ctrls: list[JobController] = []
        for ctrl in sorted(self._controllers.values(), key=lambda c: c.job.name.lower()):
            if not ctrl.is_monitoring or ctrl.job.schedule_mode != "window":
                continue
            active_days = ctrl.job.days_of_week or day_names
            if today_code not in active_days:
                continue
            try:
                end_time = datetime.strptime(ctrl.job.window_end, "%H:%M").time()
            except (ValueError, AttributeError):
                continue
            if now_time.hour == end_time.hour and now_time.minute == end_time.minute:
                if ctrl._last_window_executed_minute != current_minute:
                    ctrl._last_window_executed_minute = current_minute
                    triggered_ctrls.append(ctrl)

        if not triggered_ctrls:
            return

        # Mark all triggered jobs as preparing/queued immediately so UI displays active status rather than reverting to waiting
        for ctrl in triggered_ctrls:
            self._preparing_jobs.add(ctrl.job.id)
            self.job_status_changed.emit(ctrl.job.id, "QUEUED")

        # Execute entire window gathering and dispatch in background so main GUI thread NEVER hitches
        threading.Thread(
            target=self._bg_process_window_triggers,
            args=(triggered_ctrls,),
            daemon=True,
        ).start()

    def _bg_process_window_triggers(self, triggered_ctrls: list[JobController]) -> None:
        """Gather records and enqueue for all window-triggered jobs in strict alphabetical order."""
        logger.info(
            "Window end reached for %d job(s) in strict alphabetical order: %s",
            len(triggered_ctrls),
            ", ".join(c.job.name for c in triggered_ctrls),
        )

        import concurrent.futures

        def _scan_job(ctrl: JobController) -> tuple[JobController, list[TransferRecord]]:
            try:
                # Include all non-terminal and queued files for transfer
                waiting = [
                    r for r in list(ctrl._active_records.values())
                    if r.status in (
                        FileStatus.WAITING_FOR_WINDOW,
                        FileStatus.READY,
                        FileStatus.PROCESSING,
                        FileStatus.DETECTED,
                        FileStatus.QUEUED,
                    )
                ]

                db_records = self._db.get_active_records(ctrl.job.id)
                for r in db_records:
                    if r.source_path not in ctrl._active_records:
                        ctrl._active_records[r.source_path] = r
                    if r.status in (
                        FileStatus.WAITING_FOR_WINDOW,
                        FileStatus.READY,
                        FileStatus.PROCESSING,
                        FileStatus.DETECTED,
                        FileStatus.QUEUED,
                    ) and r not in waiting:
                        waiting.append(r)

                if ctrl._monitor:
                    try:
                        existing_files = ctrl._monitor.scan_folder()
                        for fpath in existing_files:
                            try:
                                p = Path(fpath)
                                if not p.exists() or p.is_dir():
                                    continue
                                fsize = p.stat().st_size
                                mtime = p.stat().st_mtime
                            except OSError:
                                continue

                            if self._db.check_already_transferred(ctrl.job.id, fpath, fsize, mtime):
                                continue

                            existing_rec = ctrl._active_records.get(fpath)
                            if existing_rec:
                                if existing_rec not in waiting and not existing_rec.status.is_terminal():
                                    waiting.append(existing_rec)
                            else:
                                rec = TransferRecord(
                                    job_id=ctrl.job.id,
                                    file_name=Path(fpath).name,
                                    source_path=fpath,
                                    destination_path=str(Path(ctrl.job.destination_folder) / Path(fpath).name),
                                    file_size=fsize,
                                    source_modified=mtime,
                                    status=FileStatus.READY,
                                )
                                ctrl._active_records[fpath] = rec
                                waiting.append(rec)
                    except Exception as e:
                        logger.warning("Scan error during window trigger for '%s': %s", ctrl.job.name, e)

                return ctrl, waiting
            except Exception as e:
                logger.exception("Error preparing window trigger for job '%s': %s", ctrl.job.name, e)
                return ctrl, []

        try:
            max_scan_workers = min(len(triggered_ctrls), 8)
            if max_scan_workers > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_scan_workers) as executor:
                    scanned_results = list(executor.map(_scan_job, triggered_ctrls))
            else:
                scanned_results = [_scan_job(c) for c in triggered_ctrls]

            # Sort strictly alphabetically by Job Name so they are queued and started in A->Z order
            scanned_results.sort(key=lambda item: item[0].job.name.lower())

            for ctrl, waiting in scanned_results:
                if waiting:
                    logger.info("Window end reached (%s) for '%s'. Enqueueing %d files.",
                                ctrl.job.window_end, ctrl.job.name, len(waiting))
                    ctrl.log_message.emit(
                        ctrl.job.id,
                        "INFO",
                        f"Window end reached ({ctrl.job.window_end}). Enqueueing {len(waiting)} file(s) for transfer.",
                    )
                    for record in waiting:
                        record.status = FileStatus.READY

                    self._db.save_records_batch(waiting)
                    # Enqueue with auto_dispatch=False so all jobs are loaded into queue before simultaneous pool dispatch
                    self.enqueue_job_batch(ctrl.job.id, waiting, auto_dispatch=False)
                    ctrl._emit_stats()

            # Trigger batch dispatch check across all newly queued jobs so all concurrent workers start together
            self._batch_dispatch_requested.emit()
        finally:
            for c in triggered_ctrls:
                self._preparing_jobs.discard(c.job.id)
            for jid in list(self._controllers.keys()):
                self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

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
                ctrl = self._controllers[job.id]
                old_job = ctrl.job
                ctrl.job = job
                if (old_job.window_end != job.window_end or
                    old_job.window_start != job.window_start or
                    old_job.schedule_mode != job.schedule_mode or
                    old_job.days_of_week != job.days_of_week):
                    ctrl._last_window_executed_minute = None
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
                ctrl.job_event.connect(self._on_ctrl_job_event)
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
        if self._current_job:
            return self._active_workers.get(self._current_job.id)
        return next(iter(self._active_workers.values()), None)

    @property
    def _active_worker(self) -> Optional[TransferWorker]:
        return next(iter(self._active_workers.values()), None)

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
        if job_id in self._active_workers:
            return "TRANSFERRING"
        if job_id in self._preparing_jobs or any(req.job_id == job_id for req in self._transfer_queue):
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
            # Cleanly reset any interrupted active transfers so Sync Now / Resume picks them up
            to_reset = []
            for rec in ctrl._active_records.values():
                if rec.status in (FileStatus.TRANSFERRING, FileStatus.QUEUED):
                    rec.status = FileStatus.WAITING_FOR_WINDOW if ctrl.job.schedule_mode == "window" else FileStatus.READY
                    to_reset.append(rec)
            if to_reset:
                self._db.save_records_batch(to_reset)
                for r in to_reset:
                    ctrl.file_status_changed.emit(job_id, r.id, r.status)
                ctrl._emit_stats()

        if job_id in self._active_workers:
            worker = self._active_workers.get(job_id)
            if worker and worker.isRunning():
                worker.cancel()
        self._preparing_jobs.discard(job_id)
        self._transfer_queue = [req for req in self._transfer_queue if req.job_id != job_id]
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

    def start_all_monitoring(self) -> None:
        for ctrl in self._controllers.values():
            if ctrl.job.enabled:
                ctrl.start_monitoring()

    def stop_all_monitoring(self) -> None:
        for ctrl in self._controllers.values():
            ctrl.stop_monitoring()
            to_reset = []
            for rec in ctrl._active_records.values():
                if rec.status in (FileStatus.TRANSFERRING, FileStatus.QUEUED):
                    rec.status = FileStatus.WAITING_FOR_WINDOW if ctrl.job.schedule_mode == "window" else FileStatus.READY
                    to_reset.append(rec)
            if to_reset:
                self._db.save_records_batch(to_reset)
                for r in to_reset:
                    ctrl.file_status_changed.emit(ctrl.job.id, r.id, r.status)
                ctrl._emit_stats()

        for worker in list(self._active_workers.values()):
            if worker and worker.isRunning():
                worker.cancel()
        self._preparing_jobs.clear()
        self._transfer_queue.clear()
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

    def reset_job(self, job_id: str) -> None:
        """Reset an individual job's state and history."""
        if job_id in self._active_workers:
            worker = self._active_workers.get(job_id)
            if worker and worker.isRunning():
                worker.cancel()
        self._transfer_queue = [req for req in self._transfer_queue if req.job_id != job_id]
        ctrl = self._controllers.get(job_id)
        if ctrl:
            ctrl.reset_job()
        self.job_status_changed.emit(job_id, self.get_job_execution_state(job_id))

    def reset_all_jobs(self) -> None:
        """Reset all jobs and database history."""
        self.stop_all_monitoring()
        for jid in list(self._controllers.keys()):
            self.reset_job(jid)

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
    # Concurrency & Worker Pool Dispatcher
    # ──────────────────────────────────────────────

    def enqueue_job_batch(self, job_id: str, records: list[TransferRecord], auto_dispatch: bool = True) -> None:
        """Enqueue a batch of records for processing."""
        ctrl = self.get_controller(job_id)
        if not ctrl or not records:
            return

        for record in records:
            record.status = FileStatus.QUEUED
        self._db.save_records_batch(records)

        # Emit file_status_changed once to notify UI without flooding event loop
        if records:
            ctrl.file_status_changed.emit(job_id, records[0].id, records[0].status)

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

        # Always sort queue alphabetically by Job Name so they execute in order
        def _get_job_name(req: JobBatchRequest) -> str:
            c = self.get_controller(req.job_id)
            return c.job.name.lower() if c else ""

        self._transfer_queue.sort(key=_get_job_name)

        ctrl._emit_stats()

        # Emit updated execution states for all jobs
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

        if auto_dispatch:
            self._dispatch_next_batch()

    def _dispatch_next_batch(self) -> None:
        """Dispatch queued job batches up to max_concurrent_transfers."""
        max_workers = self._config.max_concurrent_transfers

        while self._transfer_queue:
            if max_workers > 0 and len(self._active_workers) >= max_workers:
                break

            req_idx = next((i for i, r in enumerate(self._transfer_queue) if r.job_id not in self._active_workers), None)
            if req_idx is None:
                break

            request = self._transfer_queue.pop(req_idx)
            ctrl = self.get_controller(request.job_id)
            if not ctrl or not request.records:
                continue

            logger.info("Worker Pool: Starting batch transfer for job '%s' (%d records)",
                        ctrl.job.name, len(request.records))
            self.log_message.emit("INFO", f"Starting transfer for '{ctrl.job.name}' ({len(request.records)} files)")
            msg = f"Transfer started ({len(request.records)} files)"
            self.job_event.emit(request.job_id, msg)

            worker = TransferWorker(
                records=request.records,
                engine=ctrl._engine,
                db=self._db,
                config=self._config,
                job=ctrl.job,
                parent=self,
            )
            self._active_workers[request.job_id] = worker
            worker.transfer_started.connect(
                lambda rid, jid=ctrl.job.id: self._on_worker_transfer_started(jid, rid)
            )
            worker.transfer_progress.connect(
                lambda rid, ph, c, t, jid=ctrl.job.id: self._on_worker_progress(jid, rid, ph, c, t)
            )
            worker.transfer_completed.connect(
                lambda rid, res, jid=ctrl.job.id: self._on_worker_transfer_completed(jid, rid, res)
            )
            worker.finished.connect(
                lambda jid=ctrl.job.id: self._on_worker_all_done(jid)
            )
            worker.worker_event.connect(
                lambda jid, msg: self._on_worker_event(jid, msg)
            )
            worker.start()

        # Notify UI of updated statuses across all jobs
        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

    def _on_worker_event(self, job_id: str, message: str) -> None:
        ctrl = self.get_controller(job_id)
        if ctrl:
            ctrl.job_event.emit(job_id, message)
            ctrl.log_message.emit(job_id, "INFO", message)
        self.job_event.emit(job_id, message)

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
                if result.record:
                    record.status = result.record.status
                    record.error_message = result.record.error_message
                    record.transfer_completed = result.record.transfer_completed
                    record.source_hash = result.record.source_hash
                    record.destination_hash = result.record.destination_hash
                ctrl.transfer_completed.emit(job_id, record_id, result)

    def _on_worker_all_done(self, job_id: str) -> None:
        worker = self._active_workers.pop(job_id, None)
        ctrl = self.get_controller(job_id)
        if ctrl:
            completed_paths = [
                path for path, r in ctrl._active_records.items()
                if r.status in (FileStatus.COMPLETED, FileStatus.SKIPPED)
            ]
            for path in completed_paths:
                ctrl._active_records.pop(path, None)

            if worker and worker._cancel_requested:
                msg = f"Transfer stopped for '{ctrl.job.name}' (partial archive destroyed)"
            elif any(r.status == FileStatus.FAILED for r in ctrl._active_records.values()):
                msg = f"Transfer aborted for '{ctrl.job.name}' (errors detected)"
            elif completed_paths:
                msg = f"Batch transfer completed for '{ctrl.job.name}'"
            else:
                msg = f"Transfer stopped for '{ctrl.job.name}'"

            self.job_event.emit(job_id, msg)
            ctrl._emit_stats()

        for jid in list(self._controllers.keys()):
            self.job_status_changed.emit(jid, self.get_job_execution_state(jid))

        # Automatically process the next queued job batch in pool
        self._dispatch_next_batch()

        # Auto-generate corporate daily report if enabled and all batch transfers are done
        if not self._active_workers and not self._transfer_queue:
            if self._config.report_auto_generate:
                import threading

                def _bg_generate_report():
                    try:
                        from services.report_service import ReportService
                        report_svc = ReportService(self._config, self._db)
                        out_file = report_svc.generate_daily_report(datetime.now().date())
                        if "_latest" in out_file.name:
                            self.log_message.emit(
                                "WARNING",
                                f"Daily report auto-saved as '{out_file.name}' (primary file is currently locked open in Microsoft Excel)."
                            )
                        else:
                            self.log_message.emit(
                                "INFO",
                                f"Daily backup checklist auto-updated: '{out_file.name}'"
                            )
                    except Exception as e:
                        logger.warning("Automatic daily report generation failed: %s", e)
                        self.log_message.emit("WARNING", f"Daily report auto-update failed: {e}")

                threading.Thread(target=_bg_generate_report, name="AutoReportGenerator", daemon=True).start()

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

    def _on_ctrl_job_event(self, job_id: str, message: str) -> None:
        self.job_event.emit(job_id, message)

    def _emit_stats(self) -> None:
        if self._current_job:
            stats = self._db.get_statistics(self._current_job.id)
            self.stats_updated.emit(stats)
            self.job_stats_updated.emit(self._current_job.id, stats)

    def shutdown(self) -> None:
        self.stop_all_monitoring()
        for worker in list(self._active_workers.values()):
            if worker and worker.isRunning():
                worker.cancel()
