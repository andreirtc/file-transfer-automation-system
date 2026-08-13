"""
Database service for the File Transfer Automation System.

Provides persistent SQLite storage for:
- Transfer jobs (source/destination configurations)
- Transfer records (file transfer history and status)

Thread-safe via connection-per-call pattern. Each public method opens
and closes its own connection so the service can be called from any thread.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models import FileStatus, TransferJob, TransferRecord

logger = logging.getLogger("app")

# ISO 8601 format for datetime serialization in SQLite
_DT_FMT = "%Y-%m-%d %H:%M:%S.%f"


class DatabaseService:
    """
    SQLite persistence layer for transfer jobs and records.

    All public methods are self-contained (open → work → close) so they
    can safely be called from any thread without external locking.
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = (
                Path(__file__).resolve().parent.parent
                / "database"
                / "transfer_history.db"
            )
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ──────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection."""
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        """Create tables if they do not exist."""
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS transfer_jobs (
                    id            TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    source_folder TEXT NOT NULL,
                    destination_folder TEXT NOT NULL,
                    enabled       INTEGER NOT NULL DEFAULT 1,
                    auto_monitor  INTEGER NOT NULL DEFAULT 1,
                    schedule_mode TEXT NOT NULL DEFAULT 'continuous',
                    window_start  TEXT NOT NULL DEFAULT '23:00',
                    window_end    TEXT NOT NULL DEFAULT '06:00',
                    created_at    TEXT
                );

                CREATE TABLE IF NOT EXISTS transfer_records (
                    id                TEXT PRIMARY KEY,
                    job_id            TEXT NOT NULL,
                    file_name         TEXT NOT NULL,
                    source_path       TEXT NOT NULL,
                    destination_path  TEXT NOT NULL DEFAULT '',
                    file_size         INTEGER NOT NULL DEFAULT 0,
                    source_modified   REAL,
                    source_hash       TEXT,
                    destination_hash  TEXT,
                    status            TEXT NOT NULL DEFAULT 'DETECTED',
                    detected_at       TEXT,
                    transfer_started  TEXT,
                    transfer_completed TEXT,
                    error_message     TEXT,
                    retry_count       INTEGER NOT NULL DEFAULT 0,
                    verification_passed INTEGER,
                    override_window   INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (job_id) REFERENCES transfer_jobs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_records_job
                    ON transfer_records(job_id);
                CREATE INDEX IF NOT EXISTS idx_records_source
                    ON transfer_records(source_path);
                CREATE INDEX IF NOT EXISTS idx_records_status
                    ON transfer_records(status);
                """
            )
            conn.commit()
            
            # Simple migration for existing tables
            try:
                conn.execute("ALTER TABLE transfer_jobs ADD COLUMN schedule_mode TEXT NOT NULL DEFAULT 'continuous'")
                conn.execute("ALTER TABLE transfer_jobs ADD COLUMN window_start TEXT NOT NULL DEFAULT '23:00'")
                conn.execute("ALTER TABLE transfer_jobs ADD COLUMN window_end TEXT NOT NULL DEFAULT '06:00'")
            except sqlite3.OperationalError:
                pass  # Columns likely already exist
                
            try:
                conn.execute("ALTER TABLE transfer_records ADD COLUMN override_window INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            logger.info("Database schema initialized at %s", self._db_path)
        finally:
            conn.close()

    @staticmethod
    def _dt_to_str(dt: Optional[datetime]) -> Optional[str]:
        return dt.strftime(_DT_FMT) if dt else None

    @staticmethod
    def _str_to_dt(s: Optional[str]) -> Optional[datetime]:
        if s:
            try:
                return datetime.strptime(s, _DT_FMT)
            except ValueError:
                return None
        return None

    # ──────────────────────────────────────────────
    # Transfer Jobs
    # ──────────────────────────────────────────────

    def save_job(self, job: TransferJob) -> None:
        """Insert or replace a transfer job."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO transfer_jobs
                    (id, name, source_folder, destination_folder,
                     enabled, auto_monitor, schedule_mode, window_start, window_end, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.name,
                    job.source_folder,
                    job.destination_folder,
                    int(job.enabled),
                    int(job.auto_monitor),
                    job.schedule_mode,
                    job.window_start,
                    job.window_end,
                    self._dt_to_str(job.created_at),
                ),
            )
            conn.commit()
            logger.info("Saved job '%s' (id=%s)", job.name, job.id)
        finally:
            conn.close()

    def get_jobs(self) -> list[TransferJob]:
        """Return all transfer jobs."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM transfer_jobs ORDER BY name").fetchall()
            return [self._row_to_job(r) for r in rows]
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[TransferJob]:
        """Return a single job by ID, or None."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM transfer_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return self._row_to_job(row) if row else None
        finally:
            conn.close()

    def delete_job(self, job_id: str) -> None:
        """Delete a job and all its records."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM transfer_records WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM transfer_jobs WHERE id = ?", (job_id,))
            conn.commit()
            logger.info("Deleted job id=%s and its records", job_id)
        finally:
            conn.close()

    def _row_to_job(self, row: sqlite3.Row) -> TransferJob:
        return TransferJob(
            id=row["id"],
            name=row["name"],
            source_folder=row["source_folder"],
            destination_folder=row["destination_folder"],
            enabled=bool(row["enabled"]),
            auto_monitor=bool(row["auto_monitor"]),
            schedule_mode=row["schedule_mode"],
            window_start=row["window_start"],
            window_end=row["window_end"],
            created_at=self._str_to_dt(row["created_at"]),
        )

    # ──────────────────────────────────────────────
    # Transfer Records
    # ──────────────────────────────────────────────

    def save_record(self, record: TransferRecord) -> None:
        """Insert or replace a transfer record."""
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO transfer_records
                    (id, job_id, file_name, source_path, destination_path,
                     file_size, source_modified, source_hash, destination_hash,
                     status, detected_at, transfer_started, transfer_completed,
                    error_message, retry_count, verification_passed, override_window)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.job_id,
                    record.file_name,
                    record.source_path,
                    record.destination_path,
                    record.file_size,
                    record.source_modified,
                    record.source_hash,
                    record.destination_hash,
                    record.status.value,
                    self._dt_to_str(record.detected_at),
                    self._dt_to_str(record.transfer_started),
                    self._dt_to_str(record.transfer_completed),
                    record.error_message,
                    record.retry_count,
                    (
                        int(record.verification_passed)
                        if record.verification_passed is not None
                        else None
                    ),
                    int(record.override_window),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_records_by_job(
        self,
        job_id: str,
        status: Optional[FileStatus] = None,
        limit: int = 500,
    ) -> list[TransferRecord]:
        """Return transfer records for a job, optionally filtered by status."""
        conn = self._connect()
        try:
            if status:
                rows = conn.execute(
                    """SELECT * FROM transfer_records
                       WHERE job_id = ? AND status = ?
                       ORDER BY detected_at DESC LIMIT ?""",
                    (job_id, status.value, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM transfer_records
                       WHERE job_id = ?
                       ORDER BY detected_at DESC LIMIT ?""",
                    (job_id, limit),
                ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_record_by_source(
        self, job_id: str, source_path: str
    ) -> Optional[TransferRecord]:
        """Return the most recent record for a source path within a job."""
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM transfer_records
                   WHERE job_id = ? AND source_path = ?
                   ORDER BY detected_at DESC LIMIT 1""",
                (job_id, source_path),
            ).fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def check_already_transferred(
        self, job_id: str, source_path: str, file_size: int, source_modified: float
    ) -> Optional[TransferRecord]:
        """
        Check if a file has already been successfully transferred.

        Matches on source_path + file_size + source_modified to detect
        exact duplicates. Returns the matching record, or None.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                """SELECT * FROM transfer_records
                   WHERE job_id = ? AND source_path = ?
                     AND file_size = ? AND source_modified = ?
                     AND status = 'COMPLETED'
                   ORDER BY transfer_completed DESC LIMIT 1""",
                (job_id, source_path, file_size, source_modified),
            ).fetchone()
            return self._row_to_record(row) if row else None
        finally:
            conn.close()

    def get_cleanup_candidates(self, job_id: str, days: int) -> list[TransferRecord]:
        """
        Return COMPLETED transfer records older than the specified number of days.
        Used by the auto-cleanup worker to delete original source files.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM transfer_records
                   WHERE job_id = ? AND status = 'COMPLETED'
                     AND (julianday('now') - julianday(transfer_completed)) >= ?
                   ORDER BY transfer_completed ASC""",
                (job_id, days),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_active_records(self, job_id: str) -> list[TransferRecord]:
        """Return all records in non-terminal states for a job."""
        conn = self._connect()
        try:
            active_states = [s.value for s in FileStatus if s.is_active()]
            placeholders = ",".join("?" for _ in active_states)
            rows = conn.execute(
                f"""SELECT * FROM transfer_records
                    WHERE job_id = ? AND status IN ({placeholders})
                    ORDER BY detected_at ASC""",
                (job_id, *active_states),
            ).fetchall()
            return [self._row_to_record(r) for r in rows]
        finally:
            conn.close()

    def get_statistics(self, job_id: str) -> dict[str, int]:
        """Return counts of records by status for a job."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT status, COUNT(*) as cnt
                   FROM transfer_records
                   WHERE job_id = ?
                   GROUP BY status""",
                (job_id,),
            ).fetchall()
            stats = {s.value: 0 for s in FileStatus}
            for row in rows:
                stats[row["status"]] = row["cnt"]
            return stats
        finally:
            conn.close()

    def clear_stale_states(self, job_id: str) -> int:
        """
        Reset records stuck in transient states (e.g., after a crash).

        TRANSFERRING/VERIFYING → QUEUED (will be retried)
        DETECTED/PROCESSING → cleared (will be re-detected by monitor)
        """
        conn = self._connect()
        try:
            # Records stuck in transfer → re-queue
            cursor = conn.execute(
                """UPDATE transfer_records
                   SET status = 'QUEUED', error_message = 'Reset after restart'
                   WHERE job_id = ? AND status IN ('TRANSFERRING', 'VERIFYING')""",
                (job_id,),
            )
            requeued = cursor.rowcount

            # Records in detection phase → remove (will be re-detected)
            cursor2 = conn.execute(
                """DELETE FROM transfer_records
                   WHERE job_id = ? AND status IN ('DETECTED', 'PROCESSING')""",
                (job_id,),
            )
            cleared = cursor2.rowcount

            conn.commit()
            if requeued or cleared:
                logger.info(
                    "Stale state cleanup: %d re-queued, %d cleared", requeued, cleared
                )
            return requeued + cleared
        finally:
            conn.close()

    def _row_to_record(self, row: sqlite3.Row) -> TransferRecord:
        verification = row["verification_passed"]
        return TransferRecord(
            id=row["id"],
            job_id=row["job_id"],
            file_name=row["file_name"],
            source_path=row["source_path"],
            destination_path=row["destination_path"],
            file_size=row["file_size"],
            source_modified=row["source_modified"],
            source_hash=row["source_hash"],
            destination_hash=row["destination_hash"],
            status=FileStatus(row["status"]),
            detected_at=self._str_to_dt(row["detected_at"]),
            transfer_started=self._str_to_dt(row["transfer_started"]),
            transfer_completed=self._str_to_dt(row["transfer_completed"]),
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            verification_passed=bool(verification) if verification is not None else None,
            override_window=bool(row["override_window"]),
        )
