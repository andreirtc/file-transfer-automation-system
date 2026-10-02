"""
File transfer engine for the File Transfer Automation System.

Handles the physical copy of files from source to destination using a
safe copy strategy:
1. Copy to a temporary filename (.filename.transfer_tmp)
2. Verify the copy via IntegrityVerifier
3. Atomically rename to the final filename
4. Clean up temp files on failure

This ensures the destination never contains a partial/corrupt file
under its real filename.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.models import (
    FileStatus,
    TransferRecord,
    TransferResult,
    VerificationResult,
)

logger = logging.getLogger("transfer")


class TransferEngine:
    """
    Copies files from source to destination with safety and verification.
    """

    def __init__(
        self,
        safety_checker: FileSafetyChecker,
        integrity_verifier: IntegrityVerifier,
        temp_prefix: str = ".",
        temp_suffix: str = ".transfer_tmp",
        config: Optional[Any] = None,
    ):
        self._safety = safety_checker
        self._integrity = integrity_verifier
        self._temp_prefix = temp_prefix
        self._temp_suffix = temp_suffix
        self._config = config

    def transfer_file(
        self,
        record: TransferRecord,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> TransferResult:
        """
        Execute a complete file transfer: safety → copy → verify → finalize.

        Args:
            record: The TransferRecord describing the file to transfer.
                    record.source_path and record.destination_path must be set.
            progress_callback: Optional (phase, current, total) callback.
                phase: "copy", "verify_source", "verify_destination"

        Returns:
            TransferResult with success status, verification details, and
            any error information.
        """
        source = Path(record.source_path)
        dest_dir = Path(record.destination_path).parent
        dest_final = Path(record.destination_path)

        # Build temp filename
        temp_name = f"{self._temp_prefix}{source.name}{self._temp_suffix}"
        dest_temp = dest_dir / temp_name

        result = TransferResult(success=False, record=record)
        original_progress = progress_callback
        def check_cancel():
            if cancel_check and cancel_check():
                raise InterruptedError("Transfer stopped by operator")
        def cancellable_progress(phase, current, total):
            check_cancel()
            if original_progress:
                original_progress(phase, current, total)
        if cancel_check:
            progress_callback = cancellable_progress

        try:
            check_cancel()
            # ---- Pre-flight checks ----
            result = self._preflight_checks(source, dest_dir, dest_final, record, progress_callback)
            if not result.success and result.error_message:
                return result

            # If preflight returned was_conflict, bubble that up
            if result.was_conflict:
                return result

            if record.status in (FileStatus.COMPLETED, FileStatus.SKIPPED):
                return result

            # ---- Final safety check ----
            if not self._safety.final_safety_check(source):
                record.status = FileStatus.PROCESSING
                result.error_message = (
                    "File failed final safety check — it may still be changing."
                )
                logger.warning("Transfer aborted: %s", result.error_message)
                return result

            result.success = False  # Preflight success is not transfer success.

            # ---- Mark as transferring ----
            record.status = FileStatus.TRANSFERRING
            record.transfer_started = datetime.now()

            # ---- Copy to temp file ----
            logger.info("Copying %s → %s", source.name, dest_temp.name)
            try:
                self._copy_with_progress(source, dest_temp, progress_callback)
            except InterruptedError:
                raise
            except OSError as e:
                self._cleanup_temp(dest_temp)
                record.status = FileStatus.FAILED
                result.error_message = f"Copy failed: {e}"
                record.error_message = result.error_message
                logger.error("Copy failed for %s: %s", source.name, e)
                return result

            # ---- Verify the temp copy ----
            record.status = FileStatus.VERIFYING
            logger.info("Verifying %s", source.name)

            verify_cb = None
            if progress_callback:
                verify_cb = lambda phase, cur, tot: progress_callback(
                    f"verify_{phase}", cur, tot
                )

            smart_mode = getattr(self._config, "smart_verification_enabled", True) if self._config else True
            verification = self._integrity.verify_transfer(
                source, dest_temp, verify_cb, smart_mode=smart_mode
            )
            check_cancel()
            result.verification = verification

            if not verification.success:
                self._cleanup_temp(dest_temp)
                record.status = FileStatus.FAILED
                result.error_message = (
                    f"Verification failed: {verification.error_message}"
                )
                record.error_message = result.error_message
                record.verification_passed = False
                logger.error(
                    "Verification failed for %s: %s",
                    source.name,
                    verification.error_message,
                )
                return result

            # ---- Finalize: rename temp → final ----
            try:
                os.replace(dest_temp, dest_final)
                try:
                    shutil.copystat(source, dest_final)
                except OSError:
                    pass
            except OSError as e:
                self._cleanup_temp(dest_temp)
                record.status = FileStatus.FAILED
                result.error_message = f"Rename to final path failed: {e}"
                record.error_message = result.error_message
                logger.error("Rename failed for %s: %s", source.name, e)
                return result

            # ---- Success ----
            record.status = FileStatus.COMPLETED
            record.transfer_completed = datetime.now()
            record.source_hash = verification.source_hash
            record.destination_hash = verification.destination_hash
            record.verification_passed = True
            record.error_message = None

            result.success = True
            result.error_message = ""

            logger.info(
                "Transfer completed: %s (hash=%s)",
                source.name,
                verification.source_hash[:16],
            )
            return result

        except InterruptedError as e:
            self._cleanup_temp(dest_temp)
            record.status = FileStatus.READY
            record.error_message = str(e)
            record.verification_passed = None
            result.success = False
            result.error_message = str(e)
            return result
        except Exception as e:
            # Catch-all for unexpected errors
            self._cleanup_temp(dest_temp)
            record.status = FileStatus.FAILED
            result.error_message = f"Unexpected error: {e}"
            record.error_message = result.error_message
            logger.exception("Unexpected transfer error for %s", source.name)
            return result

    def check_destination_conflict(
        self,
        source: str | Path,
        destination: str | Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> tuple[bool, bool, str, str]:
        """
        Check whether the destination file exists and if it conflicts.

        Returns:
            (exists, conflicts, source_hash, dest_hash)
            - exists: True if destination file exists
            - conflicts: True if destination exists but differs from source
            - source_hash: SHA-256 of source
            - dest_hash: SHA-256 of destination (empty if not exists)
        """
        source = Path(source)
        destination = Path(destination)

        if not destination.exists():
            return (False, False, "", "")

        # Destination exists — check if it matches
        try:
            match, src_hash, dst_hash = self._integrity.compare_files(
                source, destination, progress_callback
            )
            return (True, not match, src_hash, dst_hash)
        except InterruptedError:
            raise
        except OSError as e:
            logger.warning("Conflict check failed: %s", e)
            return (True, True, "", "")

    def _preflight_checks(
        self,
        source: Path,
        dest_dir: Path,
        dest_final: Path,
        record: TransferRecord,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> TransferResult:
        """Run pre-flight checks before copying."""
        result = TransferResult(success=False, record=record)

        # Source must exist
        if not source.exists():
            record.status = FileStatus.FAILED
            result.error_message = f"Source file not found: {source}"
            record.error_message = result.error_message
            return result

        # Source must be a file
        if not source.is_file():
            record.status = FileStatus.SKIPPED
            result.error_message = f"Source is not a file: {source}"
            record.error_message = result.error_message
            return result

        # Ensure destination directory exists
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            record.status = FileStatus.FAILED
            result.error_message = f"Cannot create destination directory: {e}"
            record.error_message = result.error_message
            return result

        # Validate paths are not the same
        try:
            if source.resolve() == dest_final.resolve():
                record.status = FileStatus.FAILED
                result.error_message = "Source and destination are the same file."
                record.error_message = result.error_message
                return result
        except OSError:
            pass

        if self._config and dest_final.exists() and not getattr(record, "overwrite_approved", False):
            exists, conflict, source_hash, dest_hash = self.check_destination_conflict(source, dest_final, progress_callback)
            if not conflict:
                record.status = FileStatus.COMPLETED
                record.transfer_completed = datetime.now()
                record.source_hash, record.destination_hash = source_hash, dest_hash
                record.verification_passed = True
                result.success = True
                result.destination_already_matched = True
                return result
            policy = self._config.overwrite_policy
            if policy == "skip":
                record.status = FileStatus.SKIPPED
                record.error_message = "Destination differs; skipped by overwrite policy"
                result.success = True
                return result
            if policy != "overwrite":
                record.status = FileStatus.CONFLICT
                record.error_message = "Destination differs; operator decision required"
                result.was_conflict = True
                return result

        # No errors — return success=True to indicate preflight passed
        result.success = True
        return result

    def _copy_with_progress(
        self,
        source: Path,
        destination: Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Copy a file with optional throttled progress reporting."""
        import time
        total_size = source.stat().st_size
        bytes_copied = 0
        # Use 16 MB chunks for large files (> 1 GB) for maximum sequential throughput; 1 MB otherwise
        chunk_size = max(self._integrity._chunk_size, 1024 * 1024 * 16 if total_size > 1024 * 1024 * 1024 else 1048576)
        last_callback_time = 0.0

        # Reuse a single buffer: allocating a new large bytes object on every
        # read can hold two chunks at once and multiply RAM across workers.
        buffer = bytearray(min(chunk_size, max(total_size, 1)))
        view = memoryview(buffer)
        with open(source, "rb", buffering=0) as src, open(destination, "wb") as dst:
            while True:
                read_size = src.readinto(buffer)
                if not read_size:
                    break
                dst.write(view[:read_size])
                bytes_copied += read_size
                if progress_callback:
                    now = time.time()
                    if bytes_copied == total_size or (now - last_callback_time) >= 0.1:
                        last_callback_time = now
                        progress_callback("copy", bytes_copied, total_size)

        # Preserve metadata (timestamps, permissions)
        shutil.copystat(str(source), str(destination))

    def _cleanup_temp(self, temp_path: Path) -> None:
        """Remove a temporary file, logging but not raising on failure."""
        try:
            if temp_path.exists():
                temp_path.unlink()
                logger.info("Cleaned up temp file: %s", temp_path.name)
        except OSError as e:
            logger.warning("Failed to clean up temp file %s: %s", temp_path.name, e)
