"""Automated tests for Streamlit dashboard startup and database auto-bootstrapping."""

from pathlib import Path
import pytest
import sqlite3

from dashboard.app import bootstrap_database
from src.analytics.metrics import AnalyticsEngine
from src.loader.db_loader import DBLoader
from src.utils.db_utils import get_connection


def test_fresh_database_initialization(temp_db_path):
    """Test that a brand new database path is safely initialized with all required tables."""
    # bootstrap_database initializes schema
    bootstrap_database(temp_db_path)

    with get_connection(temp_db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]

    assert "log_events" in table_names
    assert "quarantine" in table_names
    assert "file_registry" in table_names
    assert "pipeline_runs" in table_names


def test_automatic_sample_data_ingestion(temp_db_path):
    """Test that an empty database automatically ingests sample data on startup."""
    bootstrapped = bootstrap_database(temp_db_path)

    # Ingestion should succeed
    assert bootstrapped is True

    engine = AnalyticsEngine(temp_db_path)
    summary = engine.get_overall_summary()

    # Sample dataset has ~1,000 records (~935 valid after dedup/quarantine)
    assert summary["total_logs"] > 0
    assert summary["quarantined_count"] > 0

    # Analytics queries must succeed without error
    df_services = engine.get_error_rates_by_service()
    assert not df_services.empty


def test_existing_non_empty_database_preservation(temp_db_path):
    """Test that existing database records are preserved and not overwritten with sample data."""
    loader = DBLoader(temp_db_path)
    loader.init_db()

    run_id = "run-preservation-test"
    loader.save_pipeline_run({
        "run_id": run_id,
        "started_at": "2026-10-31T10:00:00Z",
        "completed_at": "2026-10-31T10:01:00Z",
        "status": "SUCCESS",
        "total_files": 1,
        "files_processed": 1,
        "total_records": 1,
        "records_loaded": 1,
        "records_quarantined": 0,
        "records_duplicated": 0,
        "duration_seconds": 1.0,
    })

    # Insert a single pre-existing record
    with get_connection(temp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO log_events (
                record_hash, timestamp_utc, severity, source, message,
                source_file, pipeline_run_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "existing_hash_123",
                "2026-10-31T10:00:00Z",
                "INFO",
                "custom-preexisting-service",
                "Pre-existing record",
                "custom.log",
                run_id,
                "2026-10-31T10:00:00Z",
            ),
        )

    # Call bootstrap on pre-populated database
    bootstrapped = bootstrap_database(temp_db_path)

    # Must NOT bootstrap or inject sample data
    assert bootstrapped is False

    with get_connection(temp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
        row = conn.execute("SELECT source FROM log_events").fetchone()

    assert count == 1
    assert row["source"] == "custom-preexisting-service"


def test_repeated_startup_without_duplicate_records(temp_db_path):
    """Test that repeated app launches and Streamlit reruns do not create duplicates."""
    # Launch 1: bootstraps empty DB
    b1 = bootstrap_database(temp_db_path)
    assert b1 is True

    with get_connection(temp_db_path) as conn:
        count_after_first = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]

    # Launch 2 (e.g. Streamlit rerun): sees existing records, skips bootstrap
    b2 = bootstrap_database(temp_db_path)
    assert b2 is False

    # Launch 3: skips bootstrap
    b3 = bootstrap_database(temp_db_path)
    assert b3 is False

    with get_connection(temp_db_path) as conn:
        count_after_reruns = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]

    # Exactly 0 duplicate rows inserted
    assert count_after_reruns == count_after_first


def test_missing_sample_directory_handling(temp_db_path, monkeypatch):
    """Test graceful handling when data/sample directory is missing."""
    import dashboard.app as app_mod

    # Point sample_dir to a non-existent path
    fake_root = Path("C:/non_existent_directory_for_test_12345")
    monkeypatch.setattr(app_mod, "PROJECT_ROOT", fake_root)

    bootstrapped = bootstrap_database(temp_db_path)

    # Handled safely without crash
    assert bootstrapped is False

    with get_connection(temp_db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
    assert count == 0
