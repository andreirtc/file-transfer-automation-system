"""
Tests for batch zip compression feature and naming format.
"""

import os
import re
from pathlib import Path
import pytest
from datetime import datetime

from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_manager import TransferManager, TransferWorker
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

