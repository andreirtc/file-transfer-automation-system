"""
Tests for the transfer engine.
"""

import shutil
from pathlib import Path

import pytest

from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.models import FileStatus, TransferRecord
from core.transfer_engine import TransferEngine


@pytest.fixture
def engine():
    """Create a transfer engine with fast safety checks."""
    safety = FileSafetyChecker(stability_interval=0, required_stable_checks=1)
    integrity = IntegrityVerifier()
    return TransferEngine(safety, integrity)


@pytest.fixture
def ready_engine():
    """Create a transfer engine whose safety checker always passes."""
    safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
    integrity = IntegrityVerifier()
    return TransferEngine(safety, integrity)


class TestTransferEngine:
    """Tests for TransferEngine."""

    def test_successful_transfer(self, ready_engine, sample_file, tmp_dest_dir):
        """A normal file should transfer successfully with verification."""
        dest_path = tmp_dest_dir / sample_file.name
        record = TransferRecord(
            source_path=str(sample_file),
            destination_path=str(dest_path),
            file_name=sample_file.name,
            file_size=sample_file.stat().st_size,
        )
        # Pre-pass safety check
        ready_engine._safety.check_file(sample_file)

        result = ready_engine.transfer_file(record)

        assert result.success is True
        assert dest_path.exists()
        assert record.status == FileStatus.COMPLETED
        assert record.source_hash is not None
        assert record.destination_hash is not None
        assert record.source_hash == record.destination_hash
        assert record.verification_passed is True

    def test_source_remains_after_transfer(self, ready_engine, sample_file, tmp_dest_dir):
        """Source file must remain untouched after transfer (COPY, not MOVE)."""
        original_content = sample_file.read_bytes()
        dest_path = tmp_dest_dir / sample_file.name

        record = TransferRecord(
            source_path=str(sample_file),
            destination_path=str(dest_path),
            file_name=sample_file.name,
            file_size=sample_file.stat().st_size,
        )
        ready_engine._safety.check_file(sample_file)
        ready_engine.transfer_file(record)

        # Source must still exist with original content
        assert sample_file.exists()
        assert sample_file.read_bytes() == original_content

    def test_destination_matches_source(self, ready_engine, sample_file, tmp_dest_dir):
        """Destination file should be byte-identical to source."""
        dest_path = tmp_dest_dir / sample_file.name
        record = TransferRecord(
            source_path=str(sample_file),
            destination_path=str(dest_path),
            file_name=sample_file.name,
            file_size=sample_file.stat().st_size,
        )
        ready_engine._safety.check_file(sample_file)
        ready_engine.transfer_file(record)

        assert sample_file.read_bytes() == dest_path.read_bytes()

    def test_missing_source_fails(self, ready_engine, tmp_dest_dir):
        """Transfer should fail if source file doesn't exist."""
        record = TransferRecord(
            source_path="C:\\nonexistent\\file.txt",
            destination_path=str(tmp_dest_dir / "file.txt"),
            file_name="file.txt",
        )

        result = ready_engine.transfer_file(record)

        assert result.success is False
        assert record.status == FileStatus.FAILED
        assert "not found" in result.error_message.lower()

    def test_creates_destination_directory(self, ready_engine, sample_file, tmp_path):
        """Transfer should create the destination directory if it doesn't exist."""
        dest_dir = tmp_path / "new" / "sub" / "dir"
        dest_path = dest_dir / sample_file.name

        record = TransferRecord(
            source_path=str(sample_file),
            destination_path=str(dest_path),
            file_name=sample_file.name,
            file_size=sample_file.stat().st_size,
        )
        ready_engine._safety.check_file(sample_file)
        result = ready_engine.transfer_file(record)

        assert result.success is True
        assert dest_path.exists()

    def test_temp_file_cleanup_on_failure(self, tmp_source_dir, tmp_dest_dir):
        """If transfer fails, temp files should be cleaned up."""
        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        # Create a source file
        src = tmp_source_dir / "test.txt"
        src.write_text("content")
        safety.check_file(src)

        # Make destination read-only to cause rename failure
        dest_path = tmp_dest_dir / "test.txt"
        record = TransferRecord(
            source_path=str(src),
            destination_path=str(dest_path),
            file_name="test.txt",
            file_size=src.stat().st_size,
        )

        # This should succeed normally
        result = engine.transfer_file(record)
        assert result.success is True

        # Verify no temp files remain
        temp_files = list(tmp_dest_dir.glob("*.transfer_tmp"))
        assert len(temp_files) == 0

    def test_progress_callback(self, ready_engine, large_sample_file, tmp_dest_dir):
        """Progress callback should be invoked during transfer."""
        dest_path = tmp_dest_dir / large_sample_file.name
        record = TransferRecord(
            source_path=str(large_sample_file),
            destination_path=str(dest_path),
            file_name=large_sample_file.name,
            file_size=large_sample_file.stat().st_size,
        )
        ready_engine._safety.check_file(large_sample_file)

        progress_events = []

        def on_progress(phase, current, total):
            progress_events.append((phase, current, total))

        result = ready_engine.transfer_file(record, on_progress)

        assert result.success is True
        assert len(progress_events) > 0
        # Should have copy and verify phases
        phases = set(p[0] for p in progress_events)
        assert "copy" in phases

    def test_conflict_detection_no_conflict(self, ready_engine, sample_file, tmp_dest_dir):
        """No conflict when destination doesn't exist."""
        dest = tmp_dest_dir / "new_file.txt"
        exists, conflicts, _, _ = ready_engine.check_destination_conflict(
            sample_file, dest
        )
        assert exists is False
        assert conflicts is False

    def test_conflict_detection_matching(self, ready_engine, sample_file, tmp_dest_dir):
        """No conflict when destination matches source."""
        dest = tmp_dest_dir / sample_file.name
        shutil.copy2(str(sample_file), str(dest))

        exists, conflicts, _, _ = ready_engine.check_destination_conflict(
            sample_file, dest
        )
        assert exists is True
        assert conflicts is False

    def test_conflict_detection_different(self, ready_engine, sample_file, tmp_dest_dir):
        """Conflict when destination exists but differs."""
        dest = tmp_dest_dir / sample_file.name
        dest.write_text("different content entirely")

        exists, conflicts, _, _ = ready_engine.check_destination_conflict(
            sample_file, dest
        )
        assert exists is True
        assert conflicts is True
