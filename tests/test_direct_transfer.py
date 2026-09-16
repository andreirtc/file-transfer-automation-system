"""
Unit tests for Direct Raw 1:1 Stream Transfers, Smart Verification, and
Operational Batch Date / 'Tumatawid' Overnight Crossover Resolution.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from core.file_safety import FileSafetyChecker
from core.integrity import IntegrityVerifier
from core.models import FileStatus, TransferJob, TransferRecord
from core.transfer_engine import TransferEngine
from core.transfer_manager import JobController, TransferManager, TransferWorker
from services.configuration_service import ConfigurationService
from services.database_service import DatabaseService
from services.report_service import ReportService


class TestDirectTransferAndSmartVerification:
    """Test direct 1:1 raw file copying and smart multi-block verification."""

    def test_direct_copy_preserves_size_and_mtime(self, tmp_path):
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        src_file = source_dir / "ORCL_PROD_DUMP.dmp"
        content = b"ORACLE_HEADER_DATA_12345" + b"\x00" * 1024 * 1024
        src_file.write_bytes(content)

        target_mtime = 1789500000.0
        os.utime(src_file, (target_mtime, target_mtime))

        record = TransferRecord(
            file_name=src_file.name,
            source_path=str(src_file),
            destination_path=str(dest_dir / src_file.name),
            file_size=len(content),
            source_modified=target_mtime,
            status=FileStatus.READY,
        )

        safety = FileSafetyChecker(stability_interval=0, required_stable_checks=0)
        integrity = IntegrityVerifier()
        engine = TransferEngine(safety, integrity)

        result = engine.transfer_file(record)

        assert result.success is True
        dest_file = dest_dir / src_file.name
        assert dest_file.exists()
        assert dest_file.stat().st_size == len(content)
        assert abs(dest_file.stat().st_mtime - target_mtime) < 1.0

    def test_smart_verification_multi_block(self, tmp_path):
        verifier = IntegrityVerifier()

        f1 = tmp_path / "file1.dmp"
        f2 = tmp_path / "file2.dmp"
        data = b"HEAD" + b"\xAA" * (25 * 1024 * 1024 - 8) + b"TAIL"
        f1.write_bytes(data)
        f2.write_bytes(data)

        h1 = verifier.hash_blocks(f1)
        h2 = verifier.hash_blocks(f2)
        assert h1 == h2
        assert h1.startswith("smart_")
        assert len(h1) == 70

        match, h_src, h_dst = verifier.compare_files(f1, f2, smart_mode=True)
        assert match is True
        assert h_src == h_dst

        v_res = verifier.verify_transfer(f1, f2, smart_mode=True)
        assert v_res.success is True

        # Corrupt middle block
        with open(f2, "r+b") as f:
            f.seek(12 * 1024 * 1024)
            f.write(b"\xFF\xFF\xFF\xFF")

        match_corrupt, h_src_c, h_dst_c = verifier.compare_files(f1, f2, smart_mode=True)
        assert match_corrupt is False
        assert h_src_c != h_dst_c

        v_corrupt = verifier.verify_transfer(f1, f2, smart_mode=True)
        assert v_corrupt.success is False
        assert "mismatch" in (v_corrupt.error_message or "").lower()


class TestOperationalBatchDateAndTumatawid:
    """Test operational batch date resolution across midnight crossover ('tumatawid') windows."""

    def test_standard_evening_file_resolves_to_same_date(self):
        dt = datetime(2026, 9, 15, 23, 15, 0)
        batch = ReportService.resolve_operational_batch_date(dt, "18:00", "12:00")
        assert batch == "2026-09-15"

    def test_tumatawid_midnight_crossing_resolves_to_previous_date(self):
        dt_crossover = datetime(2026, 9, 16, 2, 30, 0)
        batch = ReportService.resolve_operational_batch_date(dt_crossover, "18:00", "12:00")
        assert batch == "2026-09-15"

    def test_morning_file_before_cutoff_resolves_to_previous_date(self):
        dt_morning = datetime(2026, 9, 16, 11, 59, 0)
        batch = ReportService.resolve_operational_batch_date(dt_morning, "18:00", "12:00")
        assert batch == "2026-09-15"

    def test_afternoon_file_after_cutoff_resolves_to_current_date(self):
        dt_afternoon = datetime(2026, 9, 16, 12, 1, 0)
        batch = ReportService.resolve_operational_batch_date(dt_afternoon, "18:00", "12:00")
        assert batch == "2026-09-16"

    def test_next_night_file_resolves_to_next_date(self):
        dt_night = datetime(2026, 9, 16, 23, 45, 0)
        batch = ReportService.resolve_operational_batch_date(dt_night, "18:00", "12:00")
        assert batch == "2026-09-16"

    def test_cycle_range_calculation(self):
        start_dt, end_dt = ReportService.get_cycle_range_for_date("2026-09-15", "18:00", "12:00")
        assert start_dt == datetime(2026, 9, 15, 18, 0, 0)
        assert end_dt == datetime(2026, 9, 16, 12, 0, 0)


class TestBacklogTargetBatchSync:
    """Test manual target batch filtering for backlog scenarios with mixed file dates in source."""

    def test_sync_filters_to_targeted_batch_and_captures_tumatawid(self, tmp_path):
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        source_dir.mkdir()
        dest_dir.mkdir()

        db_path = tmp_path / "test.db"
        db = DatabaseService(str(db_path))
        cfg_path = tmp_path / "config.json"
        config = ConfigurationService(str(cfg_path))
        config.set("transfer_mode", "direct")
        config.set("operational_cycle_start", "18:00")
        config.set("operational_cycle_end", "12:00")

        job = TransferJob(
            name="Oracle Backup",
            source_folder=str(source_dir),
            destination_folder=str(dest_dir),
            schedule_mode="continuous",
        )
        db.save_job(job)

        f1 = source_dir / "ORCL_20260915_2315.dmp"
        f1.write_bytes(b"DATA_1")
        dt1 = datetime(2026, 9, 15, 23, 15, 0).timestamp()
        os.utime(f1, (dt1, dt1))

        f2 = source_dir / "ORCL_20260916_0230.dmp"
        f2.write_bytes(b"DATA_2")
        dt2 = datetime(2026, 9, 16, 2, 30, 0).timestamp()
        os.utime(f2, (dt2, dt2))

        f3 = source_dir / "ORCL_20260916_2345.dmp"
        f3.write_bytes(b"DATA_3")
        dt3 = datetime(2026, 9, 16, 23, 45, 0).timestamp()
        os.utime(f3, (dt3, dt3))

        ctrl = JobController(job, config, db)

        ready, _ = ctrl.sync_now(target_batch_date="2026-09-15")

        ready_names = [r.file_name for r in ready]
        assert "ORCL_20260915_2315.dmp" in ready_names
        assert "ORCL_20260916_0230.dmp" in ready_names
        assert "ORCL_20260916_2345.dmp" not in ready_names

        for r in ready:
            assert r.batch_date == "2026-09-15"

        worker = TransferWorker(ready, ctrl._engine, db, config, job)
        worker.run()

        for r in ready:
            assert r.status == FileStatus.COMPLETED
            assert r.batch_date == "2026-09-15"
            dest_f = dest_dir / r.file_name
            assert dest_f.exists()

        batch_records = db.get_records_by_date("2026-09-15")
        batch_names = [br.file_name for br in batch_records]
        assert "ORCL_20260915_2315.dmp" in batch_names
        assert "ORCL_20260916_0230.dmp" in batch_names
        assert "ORCL_20260916_2345.dmp" not in batch_names
