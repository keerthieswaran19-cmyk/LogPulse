"""Integration tests for DBLoader."""

import pandas as pd
from src.loader.db_loader import DBLoader
from src.utils.db_utils import get_connection


def test_db_init(temp_db_path):
    loader = DBLoader(temp_db_path)
    loader.init_db()

    with get_connection(temp_db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

    assert "log_events" in table_names
    assert "quarantine" in table_names
    assert "file_registry" in table_names
    assert "pipeline_runs" in table_names


def test_load_log_events_idempotency(temp_db_path):
    loader = DBLoader(temp_db_path)
    run_id = "test-run-1"

    # Make run entry first for FK
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

    df = pd.DataFrame([
        {
            "record_hash": "hash_abc_123",
            "timestamp_utc": "2024-01-15T10:00:00Z",
            "severity": "INFO",
            "source": "auth-service",
            "message": "User login",
            "latency_ms": 25.0,
            "request_id": "req-1",
            "raw_line": "raw",
            "source_file": "app.log",
        }
    ])

    # First load
    inserted = loader.load_log_events(df, run_id)
    assert inserted == 1

    # Second load with identical hash should insert 0 rows (idempotent)
    inserted_again = loader.load_log_events(df, run_id)
    assert inserted_again == 0


def test_load_quarantine(temp_db_path):
    loader = DBLoader(temp_db_path)
    run_id = "test-run-quar"

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

    df = pd.DataFrame([
        {
            "raw_line": "bad log line",
            "rejection_reason": "Missing timestamp",
            "source_file": "bad.log",
        }
    ])

    quarantined = loader.load_quarantine(df, run_id)
    assert quarantined == 1

    with get_connection(temp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
        assert count == 1


def test_file_registry(temp_db_path):
    loader = DBLoader(temp_db_path)
    run_id = "test-run-reg"

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

    file_path = "test_file.log"
    file_hash = "dummy_file_hash_999"

    assert not loader.is_file_processed(file_path, file_hash)

    loader.update_file_registry(
        file_path=file_path,
        file_hash=file_hash,
        status="COMPLETED",
        record_count=100,
        loaded_count=95,
        quarantined_count=5,
        duplicate_count=0,
        run_id=run_id,
    )

    assert loader.is_file_processed(file_path, file_hash)
