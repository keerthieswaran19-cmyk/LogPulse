"""Integration tests for AnalyticsEngine."""

import pandas as pd
from src.analytics.metrics import AnalyticsEngine
from src.loader.db_loader import DBLoader


def test_analytics_empty_db(temp_db_path):
    engine = AnalyticsEngine(temp_db_path)
    summary = engine.get_overall_summary()
    assert summary["total_logs"] == 0
    assert summary["error_rate_pct"] == 0.0

    df_services = engine.get_error_rates_by_service()
    assert df_services.empty

    df_lat = engine.get_latency_by_service()
    assert df_lat.empty


def test_analytics_with_data(temp_db_path):
    loader = DBLoader(temp_db_path)
    run_id = "run-metrics-test"

    loader.save_pipeline_run({
        "run_id": run_id,
        "started_at": "2024-01-15T10:00:00Z",
        "completed_at": "2024-01-15T10:01:00Z",
        "status": "SUCCESS",
        "total_files": 1,
        "files_processed": 1,
        "total_records": 4,
        "records_loaded": 4,
        "records_quarantined": 0,
        "records_duplicated": 0,
        "duration_seconds": 60.0,
    })

    df = pd.DataFrame([
        {
            "record_hash": "h1",
            "timestamp_utc": "2024-01-15T10:00:00Z",
            "severity": "INFO",
            "source": "auth-service",
            "message": "Auth ok",
            "latency_ms": 20.0,
            "request_id": "r1",
            "raw_line": "raw",
            "source_file": "f.log",
        },
        {
            "record_hash": "h2",
            "timestamp_utc": "2024-01-15T10:01:00Z",
            "severity": "ERROR",
            "source": "auth-service",
            "message": "Auth failed",
            "latency_ms": 50.0,
            "request_id": "r2",
            "raw_line": "raw",
            "source_file": "f.log",
        },
        {
            "record_hash": "h3",
            "timestamp_utc": "2024-01-15T10:02:00Z",
            "severity": "INFO",
            "source": "payment-service",
            "message": "Payment charged",
            "latency_ms": 100.0,
            "request_id": "r3",
            "raw_line": "raw",
            "source_file": "f.log",
        },
        {
            "record_hash": "h4",
            "timestamp_utc": "2024-01-15T10:03:00Z",
            "severity": "CRITICAL",
            "source": "payment-service",
            "message": "Database cluster deadlock",
            "latency_ms": 200.0,
            "request_id": "r4",
            "raw_line": "raw",
            "source_file": "f.log",
        },
    ])
    loader.load_log_events(df, run_id)

    engine = AnalyticsEngine(temp_db_path)
    summary = engine.get_overall_summary()

    assert summary["total_logs"] == 4
    assert summary["error_count"] == 2
    assert summary["error_rate_pct"] == 50.0
    assert summary["avg_latency_ms"] == 92.5

    df_services = engine.get_error_rates_by_service()
    assert len(df_services) == 2

    df_lat = engine.get_latency_by_service()
    assert len(df_lat) == 2
    assert "p95_ms" in df_lat.columns

    df_top_errors = engine.get_top_error_messages()
    assert len(df_top_errors) == 2
