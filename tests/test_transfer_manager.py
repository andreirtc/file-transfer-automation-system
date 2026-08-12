"""
Integration tests for the transfer manager.

These tests verify the full pipeline: detect → safety → transfer → verify → persist.
They run without a GUI (no QApplication required for the manager itself).
"""

import shutil
import time
from pathlib import Path

import pytest

from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_engine import TransferEngine
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService


class TestTransferManagerIntegration:
    """
    Integration tests that exercise the core pipeline without the GUI.
    These test the engine + safety + integrity + database together.
    """

    def test_full_pipeline_new_file(self, tmp_source_dir, tmp_dest_dir, test_db, config):
        """New file should go through the full pipeline to COMPLETED."""
        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        # Create a file
        src = tmp_source_dir / "report.pdf"
        src.write_text("PDF content here")
        safety.check_file(src)

        # Create a job
        job = TransferJob(
            name="Test",
            source_folder=str(tmp_source_dir),
            destination_folder=str(tmp_dest_dir),
        )
        test_db.save_job(job)

        # Create a record
        dest_path = tmp_dest_dir / src.name
        record = TransferRecord(
            job_id=job.id,
            file_name=src.name,
            source_path=str(src),
            destination_path=str(dest_path),
            file_size=src.stat().st_size,
            source_modified=src.stat().st_mtime,
            status=FileStatus.READY,
        )

        # Transfer
        result = engine.transfer_file(record)

        assert result.success is True
        assert record.status == FileStatus.COMPLETED
        assert dest_path.exists()
        assert src.exists()  # Source must remain
        assert src.read_text() == dest_path.read_text()

        # Persist
        test_db.save_record(record)

        # Verify it's recorded
        stored = test_db.get_record_by_source(job.id, str(src))
        assert stored is not None
        assert stored.status == FileStatus.COMPLETED

    def test_duplicate_detection(self, tmp_source_dir, tmp_dest_dir, test_db):
        """Already-transferred file should be detected as duplicate."""
        job = TransferJob(
            name="Dup Test",
            source_folder=str(tmp_source_dir),
            destination_folder=str(tmp_dest_dir),
        )
        test_db.save_job(job)

        src = tmp_source_dir / "data.csv"
        src.write_text("col1,col2\na,b")

        # Record a successful transfer
        record = TransferRecord(
            job_id=job.id,
            file_name=src.name,
            source_path=str(src),
            destination_path=str(tmp_dest_dir / src.name),
            file_size=src.stat().st_size,
            source_modified=src.stat().st_mtime,
            status=FileStatus.COMPLETED,
        )
        test_db.save_record(record)

        # Check duplicate
        found = test_db.check_already_transferred(
            job.id, str(src), src.stat().st_size, src.stat().st_mtime
        )
        assert found is not None

    def test_modified_file_recognized(self, tmp_source_dir, tmp_dest_dir, test_db):
        """Modified source file should be recognized as a new version."""
        job = TransferJob(
            name="Mod Test",
            source_folder=str(tmp_source_dir),
            destination_folder=str(tmp_dest_dir),
        )
        test_db.save_job(job)

        src = tmp_source_dir / "config.ini"
        src.write_text("version=1")
        original_mtime = src.stat().st_mtime

        # Record original transfer
        record = TransferRecord(
            job_id=job.id,
            file_name=src.name,
            source_path=str(src),
            file_size=src.stat().st_size,
            source_modified=original_mtime,
            status=FileStatus.COMPLETED,
        )
        test_db.save_record(record)

        # Modify the file
        time.sleep(0.05)
        src.write_text("version=2")
        new_mtime = src.stat().st_mtime

        # Should NOT match the previous transfer
        found = test_db.check_already_transferred(
            job.id, str(src), src.stat().st_size, new_mtime
        )
        assert found is None  # Not a duplicate — should be re-transferred

    def test_conflict_detection(self, tmp_source_dir, tmp_dest_dir):
        """Destination conflict should be detected when files differ."""
        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        src = tmp_source_dir / "conflict.txt"
        dst = tmp_dest_dir / "conflict.txt"
        src.write_text("source version")
        dst.write_text("different version in destination")

        exists, conflicts, _, _ = engine.check_destination_conflict(src, dst)
        assert exists is True
        assert conflicts is True

    def test_matching_destination_no_conflict(self, tmp_source_dir, tmp_dest_dir):
        """Matching destination should not be flagged as conflict."""
        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        src = tmp_source_dir / "same.txt"
        dst = tmp_dest_dir / "same.txt"
        content = "identical content"
        src.write_text(content)
        dst.write_text(content)

        exists, conflicts, _, _ = engine.check_destination_conflict(src, dst)
        assert exists is True
        assert conflicts is False

    def test_transfer_failure_does_not_crash(self, tmp_dest_dir):
        """Transfer of a missing file should fail gracefully."""
        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        record = TransferRecord(
            file_name="missing.txt",
            source_path="C:\\nonexistent\\missing.txt",
            destination_path=str(tmp_dest_dir / "missing.txt"),
        )

        result = engine.transfer_file(record)
        assert result.success is False
        assert record.status == FileStatus.FAILED
        # No exception raised — graceful failure
