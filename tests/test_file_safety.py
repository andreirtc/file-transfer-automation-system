"""
Tests for the file safety checker.
"""

import os
import threading
import time
from pathlib import Path

import pytest

from core.file_safety import FileSafetyChecker
from core.models import FileStatus


class TestFileSafetyChecker:
    """Tests for FileSafetyChecker."""

    def test_stable_file_becomes_ready(self, tmp_source_dir):
        """A file that doesn't change should become READY after enough checks."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "stable.txt"
        file_path.write_text("stable content")

        # First check — DETECTED → PROCESSING (starts tracking)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # Second check — still PROCESSING (1 stable, need 2)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # Third check — should be READY (2 consecutive stable checks)
        status = checker.check_file(file_path)
        assert status == FileStatus.READY

    def test_growing_file_stays_processing(self, tmp_source_dir):
        """A file that keeps changing should stay PROCESSING."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "growing.bin"

        # Write initial data
        file_path.write_bytes(b"x" * 100)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # Grow the file
        with open(file_path, "ab") as f:
            f.write(b"y" * 100)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # Grow again
        with open(file_path, "ab") as f:
            f.write(b"z" * 100)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

    def test_file_grows_then_stabilizes(self, tmp_source_dir):
        """A file that stops growing should eventually become READY."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "growing_then_stable.bin"

        # Write and grow
        file_path.write_bytes(b"x" * 100)
        checker.check_file(file_path)

        with open(file_path, "ab") as f:
            f.write(b"y" * 100)
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # Now stop writing — let it stabilize
        # After reset: 1st stable check → count=1
        status = checker.check_file(file_path)
        assert status == FileStatus.PROCESSING

        # 2nd stable check → count=2 → meets required_stable_checks=2
        status = checker.check_file(file_path)
        assert status == FileStatus.READY

    def test_nonexistent_file_returns_failed(self, tmp_source_dir):
        """Checking a non-existent file should return FAILED."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        status = checker.check_file(tmp_source_dir / "does_not_exist.txt")
        assert status == FileStatus.FAILED

    def test_directory_returns_skipped(self, tmp_source_dir):
        """Checking a directory should return SKIPPED."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        sub_dir = tmp_source_dir / "subdir"
        sub_dir.mkdir()
        status = checker.check_file(sub_dir)
        assert status == FileStatus.SKIPPED

    def test_final_safety_check_stable_file(self, tmp_source_dir):
        """Final safety check should pass for a stable, accessible file."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "final_check.txt"
        file_path.write_text("content")

        # Run through stability checks first
        checker.check_file(file_path)
        checker.check_file(file_path)
        checker.check_file(file_path)

        # Final check should pass
        assert checker.final_safety_check(file_path) is True

    def test_final_safety_check_missing_file(self, tmp_source_dir):
        """Final safety check should fail for a missing file."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        assert checker.final_safety_check(tmp_source_dir / "gone.txt") is False

    def test_final_safety_check_changed_file(self, tmp_source_dir):
        """Final safety check should fail if file changed after being declared ready."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "changing.txt"
        file_path.write_text("original")

        # Stabilize
        checker.check_file(file_path)
        checker.check_file(file_path)
        checker.check_file(file_path)

        # Modify the file
        time.sleep(0.05)
        file_path.write_text("modified!")

        # Final check should fail
        assert checker.final_safety_check(file_path) is False

    def test_get_all_processing(self, tmp_source_dir):
        """get_all_processing should return paths of files still being tracked."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=3)

        f1 = tmp_source_dir / "file1.txt"
        f2 = tmp_source_dir / "file2.txt"
        f1.write_text("a")
        f2.write_text("b")

        checker.check_file(f1)
        checker.check_file(f2)

        processing = checker.get_all_processing()
        assert str(f1) in processing
        assert str(f2) in processing

    def test_clear(self, tmp_source_dir):
        """clear() should remove all tracking data."""
        checker = FileSafetyChecker(stability_interval=0, required_stable_checks=2)
        file_path = tmp_source_dir / "tracked.txt"
        file_path.write_text("data")

        checker.check_file(file_path)
        assert len(checker.get_all_processing()) > 0

        checker.clear()
        assert len(checker.get_all_processing()) == 0
