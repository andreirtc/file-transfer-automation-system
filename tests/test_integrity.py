"""
Tests for the integrity verification module.
"""

from pathlib import Path

import pytest

from core.integrity import IntegrityVerifier


class TestIntegrityVerifier:
    """Tests for IntegrityVerifier."""

    def test_hash_file_deterministic(self, sample_file):
        """Hashing the same file twice should produce the same result."""
        verifier = IntegrityVerifier()
        hash1 = verifier.hash_file(sample_file)
        hash2 = verifier.hash_file(sample_file)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest length

    def test_hash_different_files(self, tmp_source_dir):
        """Different files should produce different hashes."""
        verifier = IntegrityVerifier()
        f1 = tmp_source_dir / "file1.txt"
        f2 = tmp_source_dir / "file2.txt"
        f1.write_text("content A")
        f2.write_text("content B")

        hash1 = verifier.hash_file(f1)
        hash2 = verifier.hash_file(f2)
        assert hash1 != hash2

    def test_hash_file_with_progress(self, large_sample_file):
        """Progress callback should be called during hashing."""
        verifier = IntegrityVerifier()
        progress_calls = []

        def on_progress(bytes_read, total):
            progress_calls.append((bytes_read, total))

        verifier.hash_file(large_sample_file, on_progress)
        assert len(progress_calls) > 0
        # Last call should report complete
        assert progress_calls[-1][0] == progress_calls[-1][1]

    def test_compare_identical_files(self, sample_file, tmp_dest_dir):
        """Comparing identical files should return match=True."""
        verifier = IntegrityVerifier()
        dest = tmp_dest_dir / "sample_copy.txt"
        dest.write_text(sample_file.read_text())

        match, src_hash, dst_hash = verifier.compare_files(sample_file, dest)
        assert match is True
        assert src_hash == dst_hash

    def test_compare_different_files(self, tmp_source_dir, tmp_dest_dir):
        """Comparing different files should return match=False."""
        verifier = IntegrityVerifier()
        src = tmp_source_dir / "src.txt"
        dst = tmp_dest_dir / "dst.txt"
        src.write_text("source content")
        dst.write_text("different content")

        match, src_hash, dst_hash = verifier.compare_files(src, dst)
        assert match is False
        assert src_hash != dst_hash

    def test_verify_transfer_success(self, sample_file, tmp_dest_dir):
        """verify_transfer should succeed for matching files."""
        verifier = IntegrityVerifier()
        dest = tmp_dest_dir / sample_file.name
        dest.write_bytes(sample_file.read_bytes())

        result = verifier.verify_transfer(sample_file, dest)
        assert result.success is True
        assert result.size_match is True
        assert result.hash_match is True
        assert result.source_hash == result.destination_hash

    def test_verify_transfer_missing_dest(self, sample_file, tmp_dest_dir):
        """verify_transfer should fail if destination doesn't exist."""
        verifier = IntegrityVerifier()
        dest = tmp_dest_dir / "nonexistent.txt"

        result = verifier.verify_transfer(sample_file, dest)
        assert result.success is False
        assert result.destination_exists is False

    def test_verify_transfer_size_mismatch(self, sample_file, tmp_dest_dir):
        """verify_transfer should fail if sizes differ."""
        verifier = IntegrityVerifier()
        dest = tmp_dest_dir / sample_file.name
        dest.write_text("short")  # Different size

        result = verifier.verify_transfer(sample_file, dest)
        assert result.success is False
        assert result.size_match is False

    def test_verify_transfer_hash_mismatch(self, tmp_source_dir, tmp_dest_dir):
        """verify_transfer should fail if same size but different content."""
        verifier = IntegrityVerifier()
        src = tmp_source_dir / "test.bin"
        dst = tmp_dest_dir / "test.bin"
        # Same size, different content
        src.write_bytes(b"AAAAAAAAAA")
        dst.write_bytes(b"BBBBBBBBBB")

        result = verifier.verify_transfer(src, dst)
        assert result.success is False
        assert result.size_match is True
        assert result.hash_match is False

    def test_hash_large_file_chunked(self, large_sample_file):
        """Hashing a 1 MB file should work correctly with chunked reads."""
        verifier = IntegrityVerifier(chunk_size=4096)
        hash_val = verifier.hash_file(large_sample_file)
        assert len(hash_val) == 64

    def test_hash_empty_file(self, tmp_source_dir):
        """Hashing an empty file should work."""
        verifier = IntegrityVerifier()
        empty = tmp_source_dir / "empty.txt"
        empty.write_bytes(b"")
        hash_val = verifier.hash_file(empty)
        assert len(hash_val) == 64
