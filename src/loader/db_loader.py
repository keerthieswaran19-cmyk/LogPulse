"""SQLite database loader module – schema initialization, upserts, and registry tracking."""

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd
import sqlite3

from src.utils.db_utils import get_connection, get_db_path, PROJECT_ROOT
from src.utils.logger import get_logger

logger = get_logger(__name__)


def compute_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of a file's content."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class DBLoader:
    """Manages SQLite schema creation, data loading, quarantine writes, and file registry."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or get_db_path()

    def init_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with get_connection(self.db_path) as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                total_files INTEGER DEFAULT 0,
                files_processed INTEGER DEFAULT 0,
                total_records INTEGER DEFAULT 0,
                records_loaded INTEGER DEFAULT 0,
                records_quarantined INTEGER DEFAULT 0,
                records_duplicated INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0.0
            );

            CREATE TABLE IF NOT EXISTS file_registry (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                status TEXT NOT NULL,
                record_count INTEGER DEFAULT 0,
                loaded_count INTEGER DEFAULT 0,
                quarantined_count INTEGER DEFAULT 0,
                duplicate_count INTEGER DEFAULT 0,
                pipeline_run_id TEXT,
                processed_at TEXT NOT NULL,
                FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS log_events (
                record_hash TEXT PRIMARY KEY,
                timestamp_utc TEXT NOT NULL,
                severity TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                latency_ms REAL,
                request_id TEXT,
                raw_line TEXT,
                source_file TEXT NOT NULL,
                pipeline_run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS quarantine (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_hash TEXT,
                raw_line TEXT,
                rejection_reason TEXT NOT NULL,
                source_file TEXT NOT NULL,
                pipeline_run_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (pipeline_run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE INDEX IF NOT EXISTS idx_log_events_timestamp ON log_events(timestamp_utc);
            CREATE INDEX IF NOT EXISTS idx_log_events_severity ON log_events(severity);
            CREATE INDEX IF NOT EXISTS idx_log_events_source ON log_events(source);
            CREATE INDEX IF NOT EXISTS idx_log_events_run_id ON log_events(pipeline_run_id);
            CREATE INDEX IF NOT EXISTS idx_quarantine_run_id ON quarantine(pipeline_run_id);
            """)
        logger.info(f"Database schema initialized successfully at {self.db_path}")

    def is_file_processed(self, file_path: str, file_hash: str) -> bool:
        """Check if file with matching hash has already been processed successfully."""
        with get_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT status FROM file_registry
                WHERE file_path = ? AND file_hash = ?
                """,
                (os.path.abspath(file_path), file_hash),
            )
            row = cursor.fetchone()
            if row and row["status"] == "COMPLETED":
                return True
            return False

    def load_log_events(self, df: pd.DataFrame, run_id: str) -> int:
        """Insert records into log_events using INSERT OR IGNORE.

        Returns:
            Number of rows actually inserted.
        """
        if df.empty:
            return 0

        now_utc = datetime.now(timezone.utc).isoformat()
        records_to_insert = []
        for _, row in df.iterrows():
            records_to_insert.append((
                str(row["record_hash"]),
                str(row["timestamp_utc"]),
                str(row["severity"]),
                str(row["source"]),
                str(row["message"]),
                float(row["latency_ms"]) if pd.notna(row.get("latency_ms")) and row.get("latency_ms") is not None else None,
                str(row["request_id"]) if pd.notna(row.get("request_id")) and row.get("request_id") is not None else None,
                str(row.get("raw_line", "")),
                str(row.get("source_file", "unknown")),
                run_id,
                now_utc,
            ))

        with get_connection(self.db_path) as conn:
            # We track change in total count
            cursor = conn.cursor()
            initial_count = cursor.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]

            cursor.executemany(
                """
                INSERT OR IGNORE INTO log_events (
                    record_hash, timestamp_utc, severity, source, message,
                    latency_ms, request_id, raw_line, source_file,
                    pipeline_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records_to_insert,
            )
            final_count = cursor.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
            inserted = final_count - initial_count

        logger.info(f"Inserted {inserted} records into log_events for run {run_id}")
        return inserted

    def load_quarantine(self, df: pd.DataFrame, run_id: str) -> int:
        """Insert invalid records into quarantine table and export to CSV file.

        Returns:
            Number of records quarantined.
        """
        if df.empty:
            return 0

        now_utc = datetime.now(timezone.utc).isoformat()
        records_to_insert = []

        for _, row in df.iterrows():
            raw_line = str(row.get("raw_line", ""))
            rejection_reason = str(row.get("rejection_reason", "Validation failed"))
            source_file = str(row.get("source_file", "unknown"))
            # Generate temporary hash for quarantine tracking
            rec_hash = hashlib.sha256(f"{raw_line}|{rejection_reason}".encode("utf-8")).hexdigest()

            records_to_insert.append((
                rec_hash,
                raw_line,
                rejection_reason,
                source_file,
                run_id,
                now_utc,
            ))

        with get_connection(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO quarantine (
                    record_hash, raw_line, rejection_reason, source_file,
                    pipeline_run_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                records_to_insert,
            )

        # Export to CSV for audit
        quar_dir = PROJECT_ROOT / "data" / "quarantine"
        quar_dir.mkdir(parents=True, exist_ok=True)
        csv_file = quar_dir / f"quarantine_{run_id[:8]}.csv"

        df_export = df.copy()
        df_export["pipeline_run_id"] = run_id
        df_export["quarantined_at"] = now_utc
        # Append or write
        write_header = not csv_file.exists()
        df_export.to_csv(csv_file, mode="a", index=False, header=write_header)

        logger.info(f"Loaded {len(records_to_insert)} records to quarantine (exported to {csv_file.name})")
        return len(records_to_insert)

    def update_file_registry(
        self,
        file_path: str,
        file_hash: str,
        status: str,
        record_count: int,
        loaded_count: int,
        quarantined_count: int,
        duplicate_count: int,
        run_id: str,
    ) -> None:
        """Record or update file processing status in the registry."""
        now_utc = datetime.now(timezone.utc).isoformat()
        abs_path = os.path.abspath(file_path)

        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO file_registry (
                    file_path, file_hash, status, record_count,
                    loaded_count, quarantined_count, duplicate_count,
                    pipeline_run_id, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    file_hash = excluded.file_hash,
                    status = excluded.status,
                    record_count = excluded.record_count,
                    loaded_count = excluded.loaded_count,
                    quarantined_count = excluded.quarantined_count,
                    duplicate_count = excluded.duplicate_count,
                    pipeline_run_id = excluded.pipeline_run_id,
                    processed_at = excluded.processed_at
                """,
                (
                    abs_path,
                    file_hash,
                    status,
                    record_count,
                    loaded_count,
                    quarantined_count,
                    duplicate_count,
                    run_id,
                    now_utc,
                ),
            )
        logger.info(f"Updated file_registry for {os.path.basename(file_path)}: status={status}")

    def save_pipeline_run(self, summary: dict) -> None:
        """Save or update pipeline run execution metrics in SQLite."""
        with get_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pipeline_runs (
                    run_id, started_at, completed_at, status,
                    total_files, files_processed, total_records,
                    records_loaded, records_quarantined, records_duplicated,
                    duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    status = excluded.status,
                    total_files = excluded.total_files,
                    files_processed = excluded.files_processed,
                    total_records = excluded.total_records,
                    records_loaded = excluded.records_loaded,
                    records_quarantined = excluded.records_quarantined,
                    records_duplicated = excluded.records_duplicated,
                    duration_seconds = excluded.duration_seconds
                """,
                (
                    summary["run_id"],
                    summary["started_at"],
                    summary["completed_at"],
                    summary["status"],
                    summary["total_files"],
                    summary["files_processed"],
                    summary["total_records"],
                    summary["records_loaded"],
                    summary["records_quarantined"],
                    summary["records_duplicated"],
                    summary["duration_seconds"],
                ),
            )
        logger.info(f"Saved pipeline run record {summary['run_id']} ({summary['status']})")
