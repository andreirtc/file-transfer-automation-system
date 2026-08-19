"""
File integrity verification for the File Transfer Automation System.

Provides chunked SHA-256 hashing and post-transfer verification.
Files are read in configurable chunks (default 64 KB) so even
multi-gigabyte files never load entirely into RAM.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable, Optional

from core.models import VerificationResult

logger = logging.getLogger("transfer")


class IntegrityVerifier:
    """
    Performs SHA-256 integrity verification on files.

    All hashing is chunked to remain memory-safe for large files.
    """

    def __init__(
        self,
        algorithm: str = "sha256",
        chunk_size: int = 1048576,
    ):
        self._algorithm = algorithm
        self._chunk_size = chunk_size

    def hash_file(
        self,
        file_path: str | Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Calculate the hash of a file using chunked reading.

        Args:
            file_path: Path to the file to hash.
            progress_callback: Optional (bytes_read, total_bytes) callback.

        Returns:
            Hex digest string.

        Raises:
            FileNotFoundError: If the file does not exist.
            OSError: If the file cannot be read.
        """
        import time
        path = Path(file_path)
        total_size = path.stat().st_size
        bytes_read = 0
        last_callback_time = 0.0

        h = hashlib.new(self._algorithm)

        with open(path, "rb") as f:
            while True:
                chunk = f.read(self._chunk_size)
                if not chunk:
                    break
                h.update(chunk)
                bytes_read += len(chunk)
                if progress_callback:
                    now = time.time()
                    if bytes_read == total_size or (now - last_callback_time) >= 0.1:
                        last_callback_time = now
                        progress_callback(bytes_read, total_size)

        return h.hexdigest()

    def compare_files(
        self,
        source: str | Path,
        destination: str | Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> tuple[bool, str, str]:
        """
        Compare two files by their hashes.

        Args:
            source: Path to the source file.
            destination: Path to the destination file.
            progress_callback: Optional (phase, bytes_read, total) callback.
                phase is "source" or "destination".

        Returns:
            (match: bool, source_hash: str, dest_hash: str)
        """
        src_cb = None
        dst_cb = None
        if progress_callback:
            src_cb = lambda br, total: progress_callback("source", br, total)
            dst_cb = lambda br, total: progress_callback("destination", br, total)

        source_hash = self.hash_file(source, src_cb)
        dest_hash = self.hash_file(destination, dst_cb)

        return (source_hash == dest_hash, source_hash, dest_hash)

    def verify_transfer(
        self,
        source: str | Path,
        destination: str | Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> VerificationResult:
        """
        Perform full post-transfer verification.

        Checks:
        1. Source still exists
        2. Destination exists
        3. File sizes match
        4. SHA-256 hashes match

        Returns a VerificationResult with detailed information.
        """
        source = Path(source)
        destination = Path(destination)

        result = VerificationResult(success=False)

        # Check source exists
        if not source.exists():
            result.source_exists = False
            result.error_message = f"Source file no longer exists: {source.name}"
            logger.error("Verification failed: %s", result.error_message)
            return result

        # Check destination exists
        if not destination.exists():
            result.destination_exists = False
            result.error_message = f"Destination file not found: {destination.name}"
            logger.error("Verification failed: %s", result.error_message)
            return result

        # Check file sizes
        try:
            result.source_size = source.stat().st_size
            result.destination_size = destination.stat().st_size
        except OSError as e:
            result.error_message = f"Cannot read file sizes: {e}"
            logger.error("Verification failed: %s", result.error_message)
            return result

        result.size_match = result.source_size == result.destination_size
        if not result.size_match:
            result.error_message = (
                f"Size mismatch: source={result.source_size}, "
                f"destination={result.destination_size}"
            )
            logger.error("Verification failed: %s", result.error_message)
            return result

        # Compare hashes
        try:
            match, src_hash, dst_hash = self.compare_files(
                source, destination, progress_callback
            )
            result.source_hash = src_hash
            result.destination_hash = dst_hash
            result.hash_match = match
        except OSError as e:
            result.error_message = f"Hash computation failed: {e}"
            logger.error("Verification failed: %s", result.error_message)
            return result

        if not result.hash_match:
            result.error_message = (
                f"Hash mismatch: source={result.source_hash[:16]}..., "
                f"destination={result.destination_hash[:16]}..."
            )
            logger.error("Verification failed: %s", result.error_message)
            return result

        # All checks passed
        result.success = True
        logger.info(
            "Verification passed for %s (hash=%s)",
            source.name,
            result.source_hash[:16],
        )
        return result
