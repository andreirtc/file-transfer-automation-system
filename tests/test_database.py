"""
Tests for the database service.
"""

from datetime import datetime
from pathlib import Path

import pytest

from core.models import FileStatus, TransferJob, TransferRecord
from services.database_service import DatabaseService


class TestDatabaseService:
    """Tests for DatabaseService."""

    def test_create_and_retrieve_job(self, test_db):
        """Should save and retrieve a transfer job."""
        job = TransferJob(
            name="Test Job",
            source_folder="C:\\source",
            destination_folder="C:\\dest",
        )
        test_db.save_job(job)

        jobs = test_db.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "Test Job"
        assert jobs[0].source_folder == "C:\\source"
        assert jobs[0].id == job.id

    def test_update_job(self, test_db):
        """Should update an existing job."""
        job = TransferJob(name="Original", source_folder="C:\\a", destination_folder="C:\\b")
        test_db.save_job(job)

        job.name = "Updated"
        test_db.save_job(job)

        retrieved = test_db.get_job(job.id)
        assert retrieved.name == "Updated"

    def test_delete_job(self, test_db):
        """Should delete a job and its records."""
        job = TransferJob(name="To Delete", source_folder="C:\\a", destination_folder="C:\\b")
        test_db.save_job(job)

        record = TransferRecord(
            job_id=job.id,
            file_name="test.txt",
            source_path="C:\\a\\test.txt",
        )
        test_db.save_record(record)

        test_db.delete_job(job.id)

        assert test_db.get_job(job.id) is None
        assert len(test_db.get_records_by_job(job.id)) == 0

    def test_save_and_retrieve_record(self, test_db):
        """Should save and retrieve a transfer record."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        record = TransferRecord(
            job_id=job.id,
            file_name="report.pdf",
            source_path="C:\\s\\report.pdf",
            destination_path="C:\\d\\report.pdf",
            file_size=1024,
            source_modified=1000000.0,
            status=FileStatus.COMPLETED,
            source_hash="abc123",
            destination_hash="abc123",
            verification_passed=True,
        )
        test_db.save_record(record)

        records = test_db.get_records_by_job(job.id)
        assert len(records) == 1
        assert records[0].file_name == "report.pdf"
        assert records[0].status == FileStatus.COMPLETED
        assert records[0].verification_passed is True

    def test_check_already_transferred(self, test_db):
        """Should detect an already-transferred file."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        record = TransferRecord(
            job_id=job.id,
            file_name="file.txt",
            source_path="C:\\s\\file.txt",
            file_size=500,
            source_modified=12345.0,
            status=FileStatus.COMPLETED,
        )
        test_db.save_record(record)

        # Same file, same size, same mtime → should find it
        found = test_db.check_already_transferred(
            job.id, "C:\\s\\file.txt", 500, 12345.0
        )
        assert found is not None
        assert found.id == record.id

    def test_modified_file_not_matched(self, test_db):
        """A modified file (different mtime) should not match previous transfer."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        record = TransferRecord(
            job_id=job.id,
            file_name="file.txt",
            source_path="C:\\s\\file.txt",
            file_size=500,
            source_modified=12345.0,
            status=FileStatus.COMPLETED,
        )
        test_db.save_record(record)

        # Same path but different mtime → should NOT match
        found = test_db.check_already_transferred(
            job.id, "C:\\s\\file.txt", 500, 99999.0
        )
        assert found is None

    def test_different_size_not_matched(self, test_db):
        """A file with different size should not match."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        record = TransferRecord(
            job_id=job.id,
            file_name="file.txt",
            source_path="C:\\s\\file.txt",
            file_size=500,
            source_modified=12345.0,
            status=FileStatus.COMPLETED,
        )
        test_db.save_record(record)

        found = test_db.check_already_transferred(
            job.id, "C:\\s\\file.txt", 999, 12345.0
        )
        assert found is None

    def test_get_statistics(self, test_db):
        """Should return correct counts by status."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        for i, status in enumerate([
            FileStatus.COMPLETED,
            FileStatus.COMPLETED,
            FileStatus.COMPLETED,
            FileStatus.FAILED,
            FileStatus.PROCESSING,
        ]):
            r = TransferRecord(
                job_id=job.id,
                file_name=f"file{i}.txt",
                source_path=f"C:\\s\\file{i}.txt",
                status=status,
            )
            test_db.save_record(r)

        stats = test_db.get_statistics(job.id)
        assert stats["COMPLETED"] == 3
        assert stats["FAILED"] == 1
        assert stats["PROCESSING"] == 1

    def test_clear_stale_states(self, test_db):
        """Should reset TRANSFERRING records to QUEUED on restart."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        r = TransferRecord(
            job_id=job.id,
            file_name="stuck.txt",
            source_path="C:\\s\\stuck.txt",
            status=FileStatus.TRANSFERRING,
        )
        test_db.save_record(r)

        cleared = test_db.clear_stale_states(job.id)
        assert cleared == 1

        records = test_db.get_records_by_job(job.id)
        assert records[0].status == FileStatus.QUEUED

    def test_persistence_across_connections(self, tmp_path):
        """Data should persist across separate DatabaseService instances."""
        db_path = tmp_path / "persist_test.db"

        # First connection — write data
        db1 = DatabaseService(db_path)
        job = TransferJob(name="Persist", source_folder="C:\\s", destination_folder="C:\\d")
        db1.save_job(job)
        record = TransferRecord(
            job_id=job.id,
            file_name="persist.txt",
            source_path="C:\\s\\persist.txt",
            status=FileStatus.COMPLETED,
        )
        db1.save_record(record)

        # Second connection — read data
        db2 = DatabaseService(db_path)
        jobs = db2.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "Persist"

        records = db2.get_records_by_job(job.id)
        assert len(records) == 1
        assert records[0].file_name == "persist.txt"
        assert records[0].status == FileStatus.COMPLETED

    def test_get_active_records(self, test_db):
        """Should return only non-terminal records."""
        job = TransferJob(name="J", source_folder="C:\\s", destination_folder="C:\\d")
        test_db.save_job(job)

        for status in [FileStatus.PROCESSING, FileStatus.READY, FileStatus.COMPLETED]:
            r = TransferRecord(
                job_id=job.id,
                file_name=f"{status.value}.txt",
                source_path=f"C:\\s\\{status.value}.txt",
                status=status,
            )
            test_db.save_record(r)

        active = test_db.get_active_records(job.id)
        statuses = [r.status for r in active]
        assert FileStatus.PROCESSING in statuses
        assert FileStatus.READY in statuses
        assert FileStatus.COMPLETED not in statuses
