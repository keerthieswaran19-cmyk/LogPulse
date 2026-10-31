"""Unit tests for Deduplicator and hash computation."""

import pandas as pd
from src.dedup.deduplicator import Deduplicator, compute_record_hash
from src.utils.db_utils import get_connection


def test_compute_record_hash_deterministic():
    h1 = compute_record_hash("2024-01-15T10:00:00Z", "auth-service", "User logged in")
    h2 = compute_record_hash("2024-01-15T10:00:00Z", "auth-service", "User logged in")
    h3 = compute_record_hash("2024-01-15T10:00:00Z", "payment-service", "User logged in")

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64  # SHA-256


def test_in_batch_deduplication():
    df = pd.DataFrame([
        {"timestamp_utc": "2024-01-15T10:00:00Z", "source": "auth-service", "message": "msg1"},
        {"timestamp_utc": "2024-01-15T10:00:00Z", "source": "auth-service", "message": "msg1"},  # duplicate
        {"timestamp_utc": "2024-01-15T10:00:00Z", "source": "auth-service", "message": "msg2"},
    ])
    deduped_df, dropped_count = Deduplicator.deduplicate_batch(df)
    assert dropped_count == 1
    assert len(deduped_df) == 2


def test_filter_existing_db_records(temp_db_path):
    from src.loader.db_loader import DBLoader
    loader = DBLoader(temp_db_path)
    run_id = "run-filter-test"
    loader.save_pipeline_run({
        "run_id": run_id,
        "started_at": "2024-01-15T10:00:00Z",
        "completed_at": None,
        "status": "RUNNING",
        "total_files": 1,
        "files_processed": 0,
        "total_records": 1,
        "records_loaded": 0,
        "records_quarantined": 0,
        "records_duplicated": 0,
        "duration_seconds": 0.0,
    })

    df1 = pd.DataFrame([
        {"timestamp_utc": "2024-01-15T10:00:00Z", "source": "auth-service", "message": "msg1"},
    ])
    df1 = Deduplicator.add_record_hashes(df1)

    # Insert record into DB
    with get_connection(temp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO log_events (
                record_hash, timestamp_utc, severity, source, message,
                source_file, pipeline_run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                df1.iloc[0]["record_hash"],
                df1.iloc[0]["timestamp_utc"],
                "INFO",
                df1.iloc[0]["source"],
                df1.iloc[0]["message"],
                "test.log",
                run_id,
                "2024-01-15T10:00:00Z",
            ),
        )

    # Now test filtering an incoming batch with the same record + 1 new record
    df2 = pd.DataFrame([
        {"timestamp_utc": "2024-01-15T10:00:00Z", "source": "auth-service", "message": "msg1"},  # already in DB
        {"timestamp_utc": "2024-01-15T10:05:00Z", "source": "auth-service", "message": "new msg"},
    ])
    df2 = Deduplicator.add_record_hashes(df2)

    with get_connection(temp_db_path) as conn:
        filtered_df, db_dups = Deduplicator.filter_existing_db_records(df2, conn)

    assert db_dups == 1
    assert len(filtered_df) == 1
    assert filtered_df.iloc[0]["message"] == "new msg"
