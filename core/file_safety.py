"""
File safety checker for the File Transfer Automation System.

Determines whether a file is safe to copy by verifying it is no longer
being written, modified, or locked. Uses a multi-check strategy:

1. Size stability: file size must remain unchanged for N consecutive checks.
2. Modification time stability: mtime must stop changing.
3. File accessibility: file must be openable without lock conflicts.
4. Final pre-copy check: re-verified immediately before the copy begins.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models import FileStatus, StabilityCheck

logger = logging.getLogger("transfer")


class FileSafetyChecker:
    """
    Determines whether files are safe (complete and not actively written)
    before allowing them to enter the transfer queue.
    """

    def __init__(
        self,
        stability_interval: int = 5,
        required_stable_checks: int = 2,
    ):
        """
        Args:
            stability_interval: Seconds between stability checks.
            required_stable_checks: Consecutive stable checks required
                to declare a file READY.
        """
        self._stability_interval = stability_interval
        self._required_stable_checks = required_stable_checks
        # Tracks ongoing stability measurements per file path
        self._checks: dict[str, StabilityCheck] = {}

    @property
    def stability_interval(self) -> int:
        return self._stability_interval

    def get_check(self, file_path: str) -> Optional[StabilityCheck]:
        """Return the current stability check for a file, if any."""
        return self._checks.get(file_path)

    def remove_check(self, file_path: str) -> None:
        """Remove stability tracking for a file."""
        self._checks.pop(file_path, None)

    def check_file(self, file_path: str | Path) -> FileStatus:
        """
        Perform a stability check on a file.

        Returns:
            FileStatus.READY if the file passes all safety checks.
            FileStatus.PROCESSING if the file is still changing or locked.
            FileStatus.FAILED if the file cannot be accessed at all.
        """
        path = Path(file_path)
        path_key = str(path)

        # ---- Step 1: Basic existence check ----
        if not path.exists():
            logger.warning("Safety check: file does not exist: %s", path.name)
            self.remove_check(path_key)
            return FileStatus.FAILED

        if path.is_dir():
            # We only transfer files, not directories
            self.remove_check(path_key)
            return FileStatus.SKIPPED

        # ---- Step 2: Read current file metadata ----
        try:
            stat = path.stat()
            current_size = stat.st_size
            current_mtime = stat.st_mtime
        except OSError as e:
            logger.warning("Safety check: cannot stat %s: %s", path.name, e)
            return FileStatus.PROCESSING

        # ---- Step 3: Compare against previous check ----
        check = self._checks.get(path_key)

        if check is None:
            # First time seeing this file — start tracking
            check = StabilityCheck(
                file_path=path_key,
                file_size=current_size,
                modified_time=current_mtime,
                last_check_time=datetime.now(),
                stable_count=0,
            )
            self._checks[path_key] = check
            logger.info(
                "Safety check: started tracking %s (size=%d)",
                path.name,
                current_size,
            )
            return FileStatus.PROCESSING

        # Has the file changed since last check?
        if current_size != check.file_size or current_mtime != check.modified_time:
            # File changed — reset stability counter
            check.reset(current_size, current_mtime)
            logger.info(
                "Safety check: %s still changing (size=%d, mtime=%.2f)",
                path.name,
                current_size,
                current_mtime,
            )
            return FileStatus.PROCESSING

        # ---- Step 4: Check time elapsed since last check ----
        now = datetime.now()
        if check.last_check_time:
            elapsed = (now - check.last_check_time).total_seconds()
            if elapsed < self._stability_interval:
                # Not enough time has passed for a meaningful check
                return FileStatus.PROCESSING

        # File unchanged — increment stability counter
        check.record_stable()

        # ---- Step 5: Check file accessibility ----
        accessible = self._check_file_accessible(path)
        check.is_accessible = accessible

        if not accessible:
            logger.info("Safety check: %s is locked or inaccessible", path.name)
            # Reset stability since we can't confirm it's truly ready
            check.stable_count = max(0, check.stable_count - 1)
            return FileStatus.PROCESSING

        # ---- Step 6: Enough stable checks? ----
        if check.stable_count >= self._required_stable_checks:
            logger.info(
                "Safety check: %s is READY (%d stable checks, accessible)",
                path.name,
                check.stable_count,
            )
            return FileStatus.READY

        logger.info(
            "Safety check: %s stable check %d/%d",
            path.name,
            check.stable_count,
            self._required_stable_checks,
        )
        return FileStatus.PROCESSING

    def final_safety_check(self, file_path: str | Path) -> bool:
        """
        Perform a final safety verification immediately before copying.

        This is a point-in-time check — it does NOT rely on previous
        stability history. Even if a file was previously READY, this
        re-checks that the file hasn't changed since.

        Returns True if the file is safe to copy RIGHT NOW.
        """
        path = Path(file_path)

        if not path.exists():
            logger.warning("Final safety check: file gone: %s", path.name)
            return False

        # Check current metadata
        try:
            stat = path.stat()
        except OSError as e:
            logger.warning("Final safety check: cannot stat %s: %s", path.name, e)
            return False

        # Verify file hasn't changed from what we previously tracked
        path_key = str(path)
        check = self._checks.get(path_key)
        if check:
            if stat.st_size != check.file_size or stat.st_mtime != check.modified_time:
                logger.warning(
                    "Final safety check: %s changed since declared READY!", path.name
                )
                # Reset tracking
                check.reset(stat.st_size, stat.st_mtime)
                return False

        # Verify accessibility
        if not self._check_file_accessible(path):
            logger.warning("Final safety check: %s is locked", path.name)
            return False

        return True

    @staticmethod
    def _check_file_accessible(path: Path) -> bool:
        """
        Test whether the file can be opened for reading.

        On Windows, a file actively being written by another process
        may raise PermissionError when opened. This heuristic catches
        many (but not all) cases of files still being written.
        """
        try:
            # Try to open with shared read access
            fd = os.open(str(path), os.O_RDONLY)
            os.close(fd)
            return True
        except (OSError, PermissionError):
            return False

    def get_all_processing(self) -> list[str]:
        """Return paths of all files currently being tracked as processing."""
        result = []
        for path_key, check in self._checks.items():
            if check.stable_count < self._required_stable_checks:
                result.append(path_key)
        return result

    def clear(self) -> None:
        """Clear all stability tracking data."""
        self._checks.clear()
