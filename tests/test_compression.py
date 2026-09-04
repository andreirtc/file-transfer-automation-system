"""
Tests for batch zip compression feature and naming format.
"""

import os
import re
import time
from pathlib import Path
import pytest
from datetime import datetime

from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_manager import TransferManager, TransferWorker, JobBatchRequest
from core.transfer_engine import TransferEngine
from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService


def test_batch_compression_creates_zip(tmp_source_dir, tmp_dest_dir, test_db, config):
    """Test that the worker creates an AES-encrypted zip file when batch compression is enabled."""
    
    # Enable batch compression and set password
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "testpassword123")
    
    # Create two source files
    src1 = tmp_source_dir / "file1.txt"
    src1.write_text("Hello World 1")
    
    src2 = tmp_source_dir / "file2.txt"
    src2.write_text("Hello World 2")
    
    # Create job
    job = TransferJob(
        name="Zip Test",
        source_folder=str(tmp_source_dir),
        destination_folder=str(tmp_dest_dir),
    )
    test_db.save_job(job)
    
    dest_path1 = tmp_dest_dir / "file1.txt"
    record1 = TransferRecord(
        job_id=job.id,
        file_name=src1.name,
        source_path=str(src1),
        destination_path=str(dest_path1),
        file_size=src1.stat().st_size,
        source_modified=src1.stat().st_mtime,
        status=FileStatus.QUEUED,
    )
    
    dest_path2 = tmp_dest_dir / "file2.txt"
    record2 = TransferRecord(
        job_id=job.id,
        file_name=src2.name,
        source_path=str(src2),
        destination_path=str(dest_path2),
        file_size=src2.stat().st_size,
        source_modified=src2.stat().st_mtime,
        status=FileStatus.QUEUED,
    )
    
    records = [record1, record2]
    for r in records:
        test_db.save_record(r)
        
    safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
    integrity = IntegrityVerifier()
    engine = TransferEngine(safety, integrity)
    
    worker = TransferWorker(records, engine, test_db, config)
    worker.run()
    
    # After run, both records should be COMPLETED and their destination path should be the .zip
    assert record1.status == FileStatus.COMPLETED
    assert record2.status == FileStatus.COMPLETED
    
    # Check that destination paths end with .zip
    assert record1.destination_path.endswith(".zip")
    assert record2.destination_path.endswith(".zip")
    assert record1.destination_path == record2.destination_path
    
    # Verify the zip file name matches YYYY-MM-DD_HHMMSS.zip pattern
    zip_path = Path(record1.destination_path)
    assert zip_path.exists()
    assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}(\_\d+)?\.zip$", zip_path.name)
    
    # Try reading the zip file with pyzipper module (AES support)
    import pyzipper
    with pyzipper.AESZipFile(zip_path, 'r') as zf:
        file1_path = "file1.txt"
        file2_path = "file2.txt"
        
        assert file1_path in zf.namelist()
        assert file2_path in zf.namelist()
        
        # Verify content
        zf.setpassword(b"testpassword123")
        assert zf.read(file1_path).decode("utf-8") == "Hello World 1"
        assert zf.read(file2_path).decode("utf-8") == "Hello World 2"


def test_batch_compression_includes_all_ready_files(tmp_source_dir, tmp_dest_dir, test_db, config):
    """Test that multiple files queued simultaneously are all included in a single batch zip."""
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "secret456")
    
    job = TransferJob(
        name="Multi Zip Test",
        source_folder=str(tmp_source_dir),
        destination_folder=str(tmp_dest_dir),
    )
    test_db.save_job(job)
    
    # Create 5 source files
    files = []
    for i in range(5):
        f = tmp_source_dir / f"doc_{i}.txt"
        f.write_text(f"Content of document {i}")
        files.append(f)
        
    records = []
    for f in files:
        rec = TransferRecord(
            job_id=job.id,
            file_name=f.name,
            source_path=str(f),
            destination_path=str(tmp_dest_dir / f.name),
            file_size=f.stat().st_size,
            source_modified=f.stat().st_mtime,
            status=FileStatus.READY,
        )
        records.append(rec)
        test_db.save_record(rec)
        
    manager = TransferManager(config, test_db)
    manager.set_job(job)
    for r in records:
        manager._active_records[r.source_path] = r
        
    # Trigger transfer_ready_files
    queued_count = manager.transfer_ready_files()
    assert queued_count == 5
    
    # Wait for background worker to complete
    if manager._worker:
        manager._worker.wait(10000)
        
    # Check all records are completed
    for r in records:
        assert r.status == FileStatus.COMPLETED
        assert r.destination_path.endswith(".zip")
        
    # Verify the zip contains ALL 5 files
    zip_path = Path(records[0].destination_path)
    assert zip_path.exists()
    assert re.match(r"^\d{4}-\d{2}-\d{2}_\d{6}(\_\d+)?\.zip$", zip_path.name)
    
    import pyzipper
    with pyzipper.AESZipFile(zip_path, 'r') as zf:
        zf.setpassword(b"secret456")
        namelist = zf.namelist()
        assert len(namelist) == 5
        for i in range(5):
            assert f"doc_{i}.txt" in namelist
            assert zf.read(f"doc_{i}.txt").decode("utf-8") == f"Content of document {i}"


def test_transfer_window_holds_files_outside_window(tmp_source_dir, tmp_dest_dir, test_db, config):
    """Test that transfer window holds files in WAITING_FOR_WINDOW when outside the window."""
    # Set a window that is definitely not active right now
    now_hour = datetime.now().hour
    # Pick a 1-hour window far from now
    start_hour = (now_hour + 6) % 24
    end_hour = (now_hour + 7) % 24
    
    job = TransferJob(
        name="Window Test",
        source_folder=str(tmp_source_dir),
        destination_folder=str(tmp_dest_dir),
        schedule_mode="window",
        window_start=f"{start_hour:02d}:00",
        window_end=f"{end_hour:02d}:00",
    )
    test_db.save_job(job)
    
    src1 = tmp_source_dir / "win_file.txt"
    src1.write_text("Window test file")
    
    record = TransferRecord(
        job_id=job.id,
        file_name=src1.name,
        source_path=str(src1),
        destination_path=str(tmp_dest_dir / src1.name),
        file_size=src1.stat().st_size,
        source_modified=src1.stat().st_mtime,
        status=FileStatus.READY,
    )
    test_db.save_record(record)
    
    manager = TransferManager(config, test_db)
    manager.set_job(job)
    manager._active_records[record.source_path] = record
    
    assert not manager.is_in_transfer_window
    
    # Try to queue/transfer
    queued_count = manager.transfer_ready_files()
    assert queued_count == 0
    assert record.status == FileStatus.WAITING_FOR_WINDOW
    
    # Now set override_window = True
    record.override_window = True
    record.status = FileStatus.READY
    test_db.save_record(record)
    
    queued_count = manager.transfer_ready_files()
    assert queued_count == 1
    assert record.status in (FileStatus.QUEUED, FileStatus.TRANSFERRING, FileStatus.COMPLETED)
    
    if manager._worker:
        manager._worker.wait(10000)
    assert record.status == FileStatus.COMPLETED


def test_batch_compression_uses_window_start_in_filename(tmp_source_dir, tmp_dest_dir, test_db, config):
    """Test that batch compression uses the configured window_start time in the zip filename."""
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "winpass123")

    job = TransferJob(
        name="Window Zip Name Test",
        source_folder=str(tmp_source_dir),
        destination_folder=str(tmp_dest_dir),
        schedule_mode="window",
        window_start="14:30",
        window_end="18:00",
    )
    test_db.save_job(job)

    src = tmp_source_dir / "sample.txt"
    src.write_text("Window sample file")

    record = TransferRecord(
        job_id=job.id,
        file_name=src.name,
        source_path=str(src),
        destination_path=str(tmp_dest_dir / src.name),
        file_size=src.stat().st_size,
        source_modified=src.stat().st_mtime,
        status=FileStatus.READY,
        override_window=True,
    )
    test_db.save_record(record)

    manager = TransferManager(config, test_db)
    manager.set_job(job)
    manager._active_records[record.source_path] = record

    manager.transfer_ready_files()
    if manager._worker:
        manager._worker.wait(10000)

    assert record.status == FileStatus.COMPLETED
    zip_path = Path(record.destination_path)
    assert zip_path.exists()
    
    # Filename should contain "_143000.zip"
    today_str = datetime.now().strftime("%Y-%m-%d")
    assert zip_path.name.startswith(f"{today_str}_143000")
    assert zip_path.name.endswith(".zip")


def test_window_end_batch_transfer_execution(tmp_source_dir, tmp_dest_dir, test_db, config):
    """Test that reaching window_end automatically triggers batch compression and transfer of waiting files."""
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "winpass123")

    now = datetime.now()
    now_str = now.strftime("%H:%M")
    start_str = (now.replace(hour=(now.hour - 1) % 24)).strftime("%H:%M")

    job = TransferJob(
        name="Window End Trigger Test",
        source_folder=str(tmp_source_dir),
        destination_folder=str(tmp_dest_dir),
        schedule_mode="window",
        window_start=start_str,
        window_end=now_str,
    )
    test_db.save_job(job)

    src = tmp_source_dir / "waiting_item.txt"
    src.write_text("Item waiting for window end")

    record = TransferRecord(
        job_id=job.id,
        file_name=src.name,
        source_path=str(src),
        destination_path=str(tmp_dest_dir / src.name),
        file_size=src.stat().st_size,
        source_modified=src.stat().st_mtime,
        status=FileStatus.WAITING_FOR_WINDOW,
    )
    test_db.save_record(record)

    manager = TransferManager(config, test_db)
    manager.set_job(job)
    manager._active_records[record.source_path] = record

    ctrl = manager.get_controller(job.id)
    assert ctrl is not None

    # Trigger window check (simulates timer tick at window_end)
    ctrl._check_windows()

    if manager._worker:
        manager._worker.wait(10000)

    assert record.status == FileStatus.COMPLETED
    assert Path(record.destination_path).exists()


def test_sequential_global_transfer_queue_execution(tmp_path, test_db, config, qapp):
    """Test that multiple jobs queued simultaneously execute one by one in sequential FIFO order."""
    import time
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "winpass123")

    # Create 3 jobs
    jobs = []
    records = []
    for name in ("Easy", "Medium", "Hard"):
        src_dir = tmp_path / f"{name.lower()}_src"
        dst_dir = tmp_path / f"{name.lower()}_dst"
        src_dir.mkdir(parents=True, exist_ok=True)
        dst_dir.mkdir(parents=True, exist_ok=True)

        job = TransferJob(
            name=f"{name} Job",
            source_folder=str(src_dir),
            destination_folder=str(dst_dir),
            schedule_mode="continuous",
        )
        test_db.save_job(job)
        jobs.append(job)

        src_file = src_dir / f"{name.lower()}_file.txt"
        src_file.write_text(f"Content for {name}")

        rec = TransferRecord(
            job_id=job.id,
            file_name=src_file.name,
            source_path=str(src_file),
            destination_path=str(dst_dir / src_file.name),
            file_size=src_file.stat().st_size,
            source_modified=src_file.stat().st_mtime,
            status=FileStatus.READY,
        )
        test_db.save_record(rec)
        records.append(rec)

    manager = TransferManager(config, test_db)
    assert len(manager._controllers) == 3

    # Enqueue all 3 jobs into the sequential transfer queue
    for job, rec in zip(jobs, records):
        ctrl = manager.get_controller(job.id)
        ctrl._active_records[rec.source_path] = rec
        manager.enqueue_job_batch(job.id, [rec])

    # Wait for the sequential worker queue to drain completely
    for _ in range(100):
        qapp.processEvents()
        if manager._active_worker and manager._active_worker.isRunning():
            manager._active_worker.wait(100)
        qapp.processEvents()
        if not manager._active_worker and not manager._transfer_queue:
            break
        time.sleep(0.05)

    # Verify all 3 jobs completed successfully
    for rec in records:
        updated = test_db.get_record_by_id(rec.id)
        assert updated is not None
        assert updated.status == FileStatus.COMPLETED
        assert Path(updated.destination_path).exists()


def test_main_dashboard_progress_bar_updates(qapp, tmp_path, test_db, config):
    """Test that MainDashboardWidget and JobOverviewCard display and update progress bars smoothly."""
    from gui.main_dashboard import MainDashboardWidget, JobOverviewCard

    job = TransferJob(
        name="Progress Test Job",
        source_folder=str(tmp_path / "src"),
        destination_folder=str(tmp_path / "dst"),
        schedule_mode="continuous",
    )
    test_db.save_job(job)

    dashboard = MainDashboardWidget()
    dashboard.set_jobs([job], {job.id: {"COMPLETED": 0, "DETECTED": 2}}, {job.id: "TRANSFERRING"})

    assert job.id in dashboard._job_cards
    card: JobOverviewCard = dashboard._job_cards[job.id]

    # Progress bar should be visible during transferring
    assert not card._progress_container.isHidden()

    # Update progress
    dashboard.update_job_progress(job.id, "copy", 50, 100)
    assert card._progress_bar.value() == 50
    assert card._progress_percent.text() == "50%"

    # When transitioning to IDLE/COMPLETED, progress container hides
    card.update_status("IDLE")
    assert card._progress_container.isHidden()


def test_days_of_week_window_evaluation(tmp_path, test_db, config):
    """Test that day-of-week schedule filters active transfer windows properly."""
    from datetime import datetime
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_code = day_names[datetime.now().weekday()]
    
    # Pick a day that is NOT today
    other_days = [d for d in day_names if d != today_code]
    other_day = other_days[0]

    # Job scheduled only on other_day
    job_inactive = TransferJob(
        name="Inactive Day Job",
        source_folder=str(tmp_path / "src1"),
        destination_folder=str(tmp_path / "dst1"),
        schedule_mode="window",
        window_start="00:00",
        window_end="23:59",
        days_of_week=[other_day],
    )
    test_db.save_job(job_inactive)

    manager = TransferManager(config, test_db)
    ctrl_inactive = manager.get_controller(job_inactive.id)
    assert ctrl_inactive is not None
    assert not ctrl_inactive.is_in_transfer_window

    # Job scheduled on today
    job_active = TransferJob(
        name="Active Day Job",
        source_folder=str(tmp_path / "src2"),
        destination_folder=str(tmp_path / "dst2"),
        schedule_mode="window",
        window_start="00:00",
        window_end="23:59",
        days_of_week=[today_code],
    )
    test_db.save_job(job_active)
    manager.reload_jobs()
    ctrl_active = manager.get_controller(job_active.id)
    assert ctrl_active is not None
    assert ctrl_active.is_in_transfer_window


def test_pause_resume_deleted_source_file_handling(tmp_path, test_db, config, qapp):
    """Test that source files deleted while paused are cleanly marked SKIPPED and removed from active records."""
    src_dir = tmp_path / "del_src"
    dst_dir = tmp_path / "del_dst"
    src_dir.mkdir(parents=True, exist_ok=True)
    dst_dir.mkdir(parents=True, exist_ok=True)

    job = TransferJob(
        name="Delete Handling Job",
        source_folder=str(src_dir),
        destination_folder=str(dst_dir),
        schedule_mode="continuous",
    )
    test_db.save_job(job)

    src_file = src_dir / "will_be_deleted.txt"
    src_file.write_text("Temporary contents")

    rec = TransferRecord(
        job_id=job.id,
        file_name=src_file.name,
        source_path=str(src_file),
        destination_path=str(dst_dir / src_file.name),
        file_size=src_file.stat().st_size,
        source_modified=src_file.stat().st_mtime,
        status=FileStatus.PROCESSING,
    )
    test_db.save_record(rec)

    manager = TransferManager(config, test_db)
    ctrl = manager.get_controller(job.id)
    ctrl._active_records[rec.source_path] = rec

    # Delete the source file on disk
    src_file.unlink()
    assert not src_file.exists()

    # Trigger safety check
    ctrl._run_safety_checks()
    time.sleep(0.2)
    qapp.processEvents()

    # Record should be marked SKIPPED and purged from active records
    assert rec.source_path not in ctrl._active_records
    updated_rec = test_db.get_record_by_id(rec.id)
    assert updated_rec.status == FileStatus.SKIPPED
    assert "deleted" in updated_rec.error_message.lower()


def test_concurrent_worker_pool_dispatch(tmp_path, test_db, config, qapp):
    """Test that max_concurrent_transfers=2 allows two jobs to transfer simultaneously."""
    config.set("max_concurrent_transfers", 2)
    config.set("batch_compression_enabled", True)

    jobs = []
    records = []
    for i in range(2):
        src = tmp_path / f"pool_src_{i}"
        dst = tmp_path / f"pool_dst_{i}"
        src.mkdir(parents=True, exist_ok=True)
        dst.mkdir(parents=True, exist_ok=True)
        job = TransferJob(name=f"Pool Job {i}", source_folder=str(src), destination_folder=str(dst))
        test_db.save_job(job)
        jobs.append(job)

        f = src / f"file_{i}.dat"
        f.write_text(f"Data {i}")
        r = TransferRecord(job_id=job.id, file_name=f.name, source_path=str(f), destination_path=str(dst / f.name), file_size=f.stat().st_size, source_modified=f.stat().st_mtime, status=FileStatus.READY)
        test_db.save_record(r)
        records.append(r)

    manager = TransferManager(config, test_db)
    for job, r in zip(jobs, records):
        ctrl = manager.get_controller(job.id)
        ctrl._active_records[r.source_path] = r
        manager.enqueue_job_batch(job.id, [r])

    # Drain queue
    for _ in range(50):
        qapp.processEvents()
        if len(manager._active_workers) == 0 and len(manager._transfer_queue) == 0:
            break
        time.sleep(0.05)

    for r in records:
        rec = test_db.get_record_by_id(r.id)
        assert rec.status == FileStatus.COMPLETED


def test_job_reset_clears_records_and_history(tmp_path, test_db, config, qapp):
    """Test that resetting a job clears active records and database history."""
    src = tmp_path / "reset_src"
    dst = tmp_path / "reset_dst"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    job = TransferJob(name="Reset Test Job", source_folder=str(src), destination_folder=str(dst))
    test_db.save_job(job)

    f = src / "file1.txt"
    f.write_text("Test content")
    r = TransferRecord(
        job_id=job.id, file_name=f.name, source_path=str(f),
        destination_path=str(dst / f.name), file_size=f.stat().st_size,
        source_modified=f.stat().st_mtime, status=FileStatus.COMPLETED
    )
    test_db.save_record(r)

    manager = TransferManager(config, test_db)
    ctrl = manager.get_controller(job.id)
    ctrl._active_records[r.source_path] = r

    assert len(test_db.get_records_by_job(job.id)) == 1
    assert len(ctrl._active_records) == 1

    # Reset job
    manager.reset_job(job.id)

    assert len(ctrl._active_records) == 0
    assert len(test_db.get_records_by_job(job.id)) == 0


def test_sync_now_forces_immediate_transfer_outside_window(tmp_path, test_db, config, qapp):
    """Test that Sync Now immediately transfers ready files even when outside scheduled window."""
    config.set("batch_compression_enabled", False)
    config.set("stability_check_interval", 0)
    config.set("required_stable_checks", 1)

    src = tmp_path / "sync_src"
    dst = tmp_path / "sync_dst"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    job = TransferJob(
        name="Sync Window Job",
        source_folder=str(src),
        destination_folder=str(dst),
        schedule_mode="window",
        window_start="01:00",
        window_end="02:00",
    )
    test_db.save_job(job)

    f = src / "sync_file.txt"
    f.write_text("Data for sync")

    manager = TransferManager(config, test_db)
    ctrl = manager.get_controller(job.id)

    # First sync tracks the file
    ctrl.sync_now()
    # Second sync marks it stable (READY) and transfers immediately
    ctrl.sync_now()

    # Drain queue
    for _ in range(50):
        qapp.processEvents()
        if len(manager._active_workers) == 0 and len(manager._transfer_queue) == 0:
            break
        time.sleep(0.05)

    assert (dst / "sync_file.txt").exists()
    recs = test_db.get_records_by_job(job.id)
    assert len(recs) == 1
    assert recs[0].status == FileStatus.COMPLETED


def test_batch_compression_retries_remaining_when_file_deleted_during_transfer(tmp_path, test_db, config, qapp):
    """Verify that deleting a file right before/during compression skips the missing file and transfers the rest."""
    config.set("batch_compression_enabled", True)
    config.set("zip_password", "SecretPass123")

    src = tmp_path / "retry_src"
    dst = tmp_path / "retry_dst"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    job = TransferJob(
        name="Retry Deletion Job",
        source_folder=str(src),
        destination_folder=str(dst),
        schedule_mode="continuous",
    )
    test_db.save_job(job)

    f1 = src / "keep_me.txt"
    f2 = src / "delete_me.txt"
    f1.write_text("Valid file content")
    f2.write_text("Will be deleted")

    rec1 = TransferRecord(
        job_id=job.id,
        file_name="keep_me.txt",
        source_path=str(f1),
        destination_path=str(dst / "keep_me.txt"),
        file_size=f1.stat().st_size,
        status=FileStatus.READY,
    )
    rec2 = TransferRecord(
        job_id=job.id,
        file_name="delete_me.txt",
        source_path=str(f2),
        destination_path=str(dst / "delete_me.txt"),
        file_size=f2.stat().st_size,
        status=FileStatus.READY,
    )
    test_db.save_records_batch([rec1, rec2])

    # Delete f2 from disk before worker runs
    f2.unlink()

    manager = TransferManager(config, test_db)
    manager.enqueue_job_batch(job.id, [rec1, rec2])

    # Wait for completion
    for _ in range(50):
        qapp.processEvents()
        if len(manager._active_workers) == 0 and len(manager._transfer_queue) == 0:
            break
        time.sleep(0.05)

    # Verify a zip archive was created at destination
    zip_files = list(dst.glob("*.zip"))
    assert len(zip_files) == 1

    # Verify records state: keep_me is COMPLETED, delete_me is SKIPPED
    recs = {r.file_name: r for r in test_db.get_records_by_job(job.id)}
    assert recs["keep_me.txt"].status == FileStatus.COMPLETED
    assert recs["delete_me.txt"].status == FileStatus.SKIPPED


def test_strict_alphabetical_job_dispatch_order(tmp_path, test_db, config, qapp):
    """Verify that jobs are dispatched in strict alphabetical order (001, 002 before 003, 004)."""
    config.set("max_concurrent_transfers", 2)
    config.set("batch_compression_enabled", False)

    job_names = ["004 Job", "001 Job", "003 Job", "002 Job"]
    created_jobs = []
    for name in job_names:
        src = tmp_path / f"src_{name.replace(' ', '_')}"
        dst = tmp_path / f"dst_{name.replace(' ', '_')}"
        src.mkdir(parents=True, exist_ok=True)
        dst.mkdir(parents=True, exist_ok=True)
        j = TransferJob(name=name, source_folder=str(src), destination_folder=str(dst), enabled=True)
        test_db.save_job(j)
        created_jobs.append(j)

    manager = TransferManager(config, test_db)

    # Pause worker dispatch temporarily to inspect queue order
    for j in created_jobs:
        rec = TransferRecord(
            job_id=j.id,
            file_name="sample.txt",
            source_path=str(Path(j.source_folder) / "sample.txt"),
            destination_path=str(Path(j.destination_folder) / "sample.txt"),
            file_size=100,
            status=FileStatus.READY,
        )
        test_db.save_record(rec)
        manager._transfer_queue.append(JobBatchRequest(job_id=j.id, records=[rec]))

    # Sort queue as enqueue_job_batch does
    def _get_job_name(req: JobBatchRequest) -> str:
        c = manager.get_controller(req.job_id)
        return c.job.name.lower() if c else ""

    manager._transfer_queue.sort(key=_get_job_name)

    # Verify queue has sorted: 001, 002, 003, 004
    queue_names = [_get_job_name(r) for r in manager._transfer_queue]
    assert queue_names == ["001 job", "002 job", "003 job", "004 job"]


def test_format_deletion_message():
    """Verify human-friendly deletion messages for single file, multiple files, and folders."""
    from core.transfer_manager import format_deletion_message

    # Single file
    msg1 = format_deletion_message(["file1.txt"], "Documents")
    assert "File 'file1.txt' was deleted from folder 'Documents'" in msg1

    # Two files
    msg2 = format_deletion_message(["f1.txt", "f2.txt"], "Docs")
    assert "Files 'f1.txt' and 'f2.txt' were deleted from folder 'Docs'" in msg2

    # Multiple files (3)
    msg3 = format_deletion_message(["a.txt", "b.txt", "c.txt"], "Reports")
    assert "Files 'a.txt', 'b.txt', and 'c.txt' were deleted from folder 'Reports'" in msg3

    # Folder deletion
    msg_dir = format_deletion_message(["f1.txt", "f2.txt"], "SubFolder", is_dir_deleted=True)
    assert "Folder 'SubFolder' and its 2 file(s) were deleted; removed from queue" in msg_dir


def test_folder_deletion_marks_nested_files_skipped(tmp_path, test_db, config, qapp):
    """Verify deleting an entire folder immediately marks all nested records as SKIPPED and logs event."""
    from core.transfer_manager import TransferManager

    src = tmp_path / "src_folder_test"
    dst = tmp_path / "dst_folder_test"
    sub = src / "Projects"
    sub.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    f1 = sub / "doc1.pdf"
    f2 = sub / "doc2.pdf"
    f1.write_text("content 1")
    f2.write_text("content 2")

    job = TransferJob(name="Folder Deletion Job", source_folder=str(src), destination_folder=str(dst), enabled=True)
    test_db.save_job(job)

    manager = TransferManager(config, test_db)
    ctrl = manager.get_controller(job.id)

    events_logged = []
    ctrl.job_event.connect(lambda jid, msg: events_logged.append(msg))

    ctrl.sync_now()
    assert len(ctrl._active_records) == 2

    # Delete folder from disk and notify
    import shutil
    shutil.rmtree(sub)
    while os.path.exists(str(sub)):
        time.sleep(0.01)
    ctrl._on_dir_deleted(str(sub))

    # Records inside folder should now be SKIPPED and removed from active records
    assert len(ctrl._active_records) == 0
    db_recs = test_db.get_active_records(job.id)
    for r in db_recs:
        assert r.status == FileStatus.SKIPPED

    assert any("Projects" in msg and "deleted" in msg for msg in events_logged)


def test_pause_and_sync_now_recovers_interrupted_files(tmp_path, test_db, config, qapp):
    """Verify pausing mid-transfer cleans records and Sync Now picks up existing files while skipping deleted."""
    from core.transfer_manager import TransferManager

    config.set("batch_compression_enabled", False)
    src = tmp_path / "src_recov"
    dst = tmp_path / "dst_recov"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)

    f1 = src / "file1.txt"
    f2 = src / "file2.txt"
    f1.write_text("data 1")
    f2.write_text("data 2")

    job = TransferJob(name="Recovery Job", source_folder=str(src), destination_folder=str(dst), schedule_mode="window", window_start="01:00", window_end="02:00")
    test_db.save_job(job)

    manager = TransferManager(config, test_db)
    ctrl = manager.get_controller(job.id)

    r1 = TransferRecord(
        job_id=job.id,
        file_name="file1.txt",
        source_path=str(f1),
        destination_path=str(dst / "file1.txt"),
        file_size=6,
        status=FileStatus.TRANSFERRING,
    )
    r2 = TransferRecord(
        job_id=job.id,
        file_name="file2.txt",
        source_path=str(f2),
        destination_path=str(dst / "file2.txt"),
        file_size=6,
        status=FileStatus.TRANSFERRING,
    )
    ctrl._active_records[str(f1)] = r1
    ctrl._active_records[str(f2)] = r2
    test_db.save_records_batch([r1, r2])

    # User stops / pauses monitoring
    manager.stop_job_monitoring(job.id)
    # Statuses should reset cleanly to WAITING_FOR_WINDOW
    for r in ctrl._active_records.values():
        assert r.status == FileStatus.WAITING_FOR_WINDOW

    # User deletes f2 on disk
    f2.unlink()

    # User hits Sync Now
    ready, _ = ctrl.sync_now()

    # Only file1 should be ready and enqueued, file2 marked skipped
    ready_names = [r.file_name for r in ready]
    assert "file1.txt" in ready_names
    assert "file2.txt" not in ready_names

    f2_rec = next((r for r in test_db.get_records_by_job(job.id) if r.file_name == "file2.txt"), None)
    assert f2_rec is not None
    assert f2_rec.status == FileStatus.SKIPPED


def test_main_dashboard_reset_card_and_reset_all_cards(qapp):
    """Test that reset_card and reset_all_cards reset all metrics without AttributeError."""
    from gui.main_dashboard import JobOverviewCard, MainDashboardWidget

    job1 = TransferJob(name="Job 1", source_folder="C:/src1", destination_folder="C:/dst1")
    job2 = TransferJob(name="Job 2", source_folder="C:/src2", destination_folder="C:/dst2")

    dashboard = MainDashboardWidget()
    dashboard.set_jobs([job1, job2])

    # Trigger reset_card on single card
    card = dashboard._job_cards[job1.id]
    card.reset_card()
    assert card._pill_completed.val_label.text() == "0"
    assert card._pill_size.val_label.text() == "0 B"
    assert card._status_badge.text() == "IDLE / STOPPED"

    # Trigger reset_all_cards on dashboard
    dashboard.reset_all_cards()
    for c in dashboard._job_cards.values():
        assert c._pill_completed.val_label.text() == "0"
        assert c._pill_size.val_label.text() == "0 B"
        assert c._status_badge.text() == "IDLE / STOPPED"


def test_main_dashboard_source_folder_size_display(qapp, tmp_path):
    """Test that source folder size is properly computed, formatted and displayed on the card."""
    from gui.main_dashboard import JobOverviewCard, MainDashboardWidget

    # Create dummy source directory with files
    src_dir = tmp_path / "src_folder"
    src_dir.mkdir()
    f1 = src_dir / "data1.bin"
    f1.write_bytes(b"A" * 1048576)  # 1 MB
    f2 = src_dir / "data2.bin"
    f2.write_bytes(b"B" * 2097152)  # 2 MB

    job = TransferJob(name="Size Job", source_folder=str(src_dir), destination_folder=str(tmp_path / "dst"))

    dashboard = MainDashboardWidget()
    dashboard.set_jobs([job])

    card = dashboard._job_cards[job.id]
    # Check update_counts with TOTAL_SOURCE_BYTES
    stats = {
        "DETECTED": 2,
        "PROCESSING": 0,
        "WAITING_FOR_WINDOW": 2,
        "COMPLETED": 0,
        "FAILED": 0,
        "TOTAL_SOURCE_BYTES": 3145728,  # 3 MB
    }
    card.update_counts(stats)
    assert card._pill_size.val_label.text() == "3.0 MB"

    # Check reset_card
    card.reset_card()
    assert card._pill_size.val_label.text() == "0 B"


def test_mid_compression_deletion_emits_event_and_restarts_cleanly(tmp_path, test_db, config, qapp):
    """Verify that if a file is deleted during compression, worker_event is emitted, partial zip discarded, and clean zip created."""
    from core.transfer_manager import TransferWorker
    from core.file_safety import FileSafetyChecker
    from core.integrity import IntegrityVerifier
    from core.transfer_engine import TransferEngine
    import pyzipper

    config.set("batch_compression_enabled", True)
    config.set("zip_password", "")

    src_dir = tmp_path / "mid_del_src"
    dst_dir = tmp_path / "mid_del_dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    f1 = src_dir / "keep.txt"
    f2 = src_dir / "delete_me.txt"
    f1.write_text("surviving content")
    f2.write_text("doomed content")

    job = TransferJob(name="MidDelJob", source_folder=str(src_dir), destination_folder=str(dst_dir))
    test_db.save_job(job)

    r1 = TransferRecord(
        job_id=job.id,
        file_name=f1.name,
        source_path=str(f1),
        destination_path=str(dst_dir / f1.name),
        file_size=f1.stat().st_size,
        source_modified=f1.stat().st_mtime,
        status=FileStatus.QUEUED,
    )
    r2 = TransferRecord(
        job_id=job.id,
        file_name=f2.name,
        source_path=str(f2),
        destination_path=str(dst_dir / f2.name),
        file_size=f2.stat().st_size,
        source_modified=f2.stat().st_mtime,
        status=FileStatus.QUEUED,
    )
    test_db.save_record(r1)
    test_db.save_record(r2)

    # Delete f2 from disk before worker finishes compression
    f2.unlink()

    safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
    integrity = IntegrityVerifier()
    engine = TransferEngine(safety, integrity)

    events_captured = []
    worker = TransferWorker([r1, r2], engine, test_db, config, job=job)
    worker.worker_event.connect(lambda jid, msg: events_captured.append(msg))
    worker.run()

    # Worker event must have been emitted announcing the deletion and restart
    assert any("delete_me.txt" in e for e in events_captured)
    assert any("restarting" in e.lower() or "remaining" in e.lower() for e in events_captured)

    # r1 must be COMPLETED and r2 must be SKIPPED
    assert r1.status == FileStatus.COMPLETED
    assert r2.status == FileStatus.SKIPPED

    # Resulting zip must contain keep.txt and NOT delete_me.txt
    zip_path = Path(r1.destination_path)
    assert zip_path.exists()
    with pyzipper.AESZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "keep.txt" in names
        assert "delete_me.txt" not in names


def test_synchronized_window_triggers_strict_alphabetical_order(tmp_path, test_db, config, qapp):
    """Verify that when multiple jobs hit window_end at the same minute, they are all queued and dispatched in strict alphabetical order."""
    from datetime import datetime
    import time
    from core.transfer_manager import TransferManager

    config.set("batch_compression_enabled", True)
    config.set("max_concurrent_transfers", 1)  # Strictly 1 at a time to check exact dispatch sequence

    now_str = datetime.now().strftime("%H:%M")
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today_code = day_names[datetime.now().weekday()]

    # Create 3 jobs out of alphabetical order
    names = ["003", "001", "002"]
    jobs = []
    for name in names:
        src = tmp_path / f"src_{name}"
        dst = tmp_path / f"dst_{name}"
        src.mkdir()
        dst.mkdir()
        (src / f"file_{name}.txt").write_text(f"content {name}")
        j = TransferJob(
            name=name,
            source_folder=str(src),
            destination_folder=str(dst),
            schedule_mode="window",
            window_start="00:00",
            window_end=now_str,
            days_of_week=[today_code],
            enabled=True,
        )
        test_db.save_job(j)
        jobs.append(j)

    manager = TransferManager(config, test_db)
    for j in jobs:
        manager.start_job_monitoring(j.id)

    # Let monitor initial scan finish
    time.sleep(0.2)
    qapp.processEvents()

    # Call _check_all_windows to trigger the window
    manager._check_all_windows()

    # Wait briefly for background thread to gather and enqueue
    time.sleep(0.5)
    qapp.processEvents()

    # Jobs in queue or active must be ordered: 001, 002, 003!
    # With max_concurrent_transfers = 1:
    # Active worker must be '001'!
    assert len(manager._active_workers) == 1
    active_job_id = list(manager._active_workers.keys())[0]
    active_ctrl = manager.get_controller(active_job_id)
    assert active_ctrl.job.name == "001"

    # And remaining queue must have '002', then '003'!
    assert len(manager._transfer_queue) == 2
    c1 = manager.get_controller(manager._transfer_queue[0].job_id)
    c2 = manager.get_controller(manager._transfer_queue[1].job_id)
    assert c1.job.name == "002"
    assert c2.job.name == "003"

    # Cleanup
    for j in jobs:
        manager.stop_job_monitoring(j.id)
    for w in list(manager._active_workers.values()):
        w.cancel()
        w.wait(2000)


def test_activity_feed_deduplication(qapp):
    """Verify that rapid duplicate events are suppressed and upgraded cleanly."""
    from gui.main_dashboard import MainDashboardWidget

    dash = MainDashboardWidget()
    dash.add_activity_event("INFO", "Folder 'Reports' and 2 files deleted", "System")
    assert dash._activity_table.rowCount() == 1
    assert dash._activity_table.item(0, 1).text() == "System"

    # Adding exact same message right after with real job name should NOT add a 2nd row, but upgrade job name!
    dash.add_activity_event("INFO", "Folder 'Reports' and 2 files deleted", "Job 001")
    assert dash._activity_table.rowCount() == 1
    assert dash._activity_table.item(0, 1).text() == "Job 001"

    # Adding a different message should add a new row
    dash.add_activity_event("INFO", "Different message", "Job 001")
    assert dash._activity_table.rowCount() == 2


def test_file_monitor_stop_non_blocking(tmp_path):
    """Verify that FileMonitor.stop() returns immediately without blocking calling thread."""
    from core.file_monitor import FileMonitor

    src = tmp_path / "src_test_stop"
    src.mkdir(parents=True, exist_ok=True)

    monitor = FileMonitor(
        source_folder=src,
        on_file_detected=lambda f: None,
        use_polling=True,
        reconciliation_interval=1,
    )
    monitor.start()
    assert monitor.is_running is True

    start_t = time.time()
    monitor.stop()
    elapsed = time.time() - start_t

    # Stopping must take under 100 milliseconds
    assert elapsed < 0.1
    assert monitor.is_running is False








