"""Dedicated edge-case and resilience tests for LogPulse pipeline.

Covers:
- Retry handling with exponential backoff
- Partial file failure recovery
- Interrupted processing and retry recovery
- Late and out-of-order timestamps
- Schema variations and column aliases
- Empty files and empty batches
- Repeated same-input reruns
"""

from unittest.mock import patch, MagicMock
import os
from pathlib import Path
import pandas as pd
import pytest

from src.parser.log_parser import LogParser
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.db_utils import get_connection
from src.utils.metrics_tracker import PipelineMetrics
from src.analytics.metrics import AnalyticsEngine


def test_retry_handling_transient_failure(temp_db_path, temp_data_dir):
    """Test that transient file errors trigger retry with backoff and succeed."""
    file_path = temp_data_dir / "transient.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "auth-service", "message": "OK"}\n')

    orchestrator = PipelineOrchestrator(db_path=temp_db_path, max_retries=3, retry_backoff_base=1.1)
    metrics = PipelineMetrics()
    metrics.start()
    orchestrator.loader.save_pipeline_run(metrics.summary())

    attempts = {"count": 0}
    original_process = orchestrator._process_single_file

    def mock_process(path, run_id, met):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise IOError("Simulated transient I/O disk lock")
        return original_process(path, run_id, met)

    with patch.object(orchestrator, "_process_single_file", side_effect=mock_process):
        success = orchestrator.process_file_with_retry(str(file_path), metrics.run_id, metrics)

    assert success is True
    assert attempts["count"] == 2  # Succeeded on 2nd attempt
    assert metrics.records_loaded == 1


def test_partial_file_failure(temp_db_path, temp_data_dir):
    """Test that if one file permanently fails, others still succeed and run status is PARTIAL."""
    good_file = temp_data_dir / "good.json"
    bad_file = temp_data_dir / "unreadable.json"

    with open(good_file, "w", encoding="utf-8") as f:
        f.write('{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "user-service", "message": "Success"}\n')

    with open(bad_file, "w", encoding="utf-8") as f:
        f.write('{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "user-service", "message": "Bad"}\n')

    orchestrator = PipelineOrchestrator(db_path=temp_db_path, max_retries=2, retry_backoff_base=1.0)

    # Force bad_file to raise fatal error during processing
    original_process = orchestrator._process_single_file

    def mock_process(path, run_id, metrics):
        if "unreadable.json" in path:
            raise PermissionError("Access denied to file")
        return original_process(path, run_id, metrics)

    with patch.object(orchestrator, "_process_single_file", side_effect=mock_process):
        metrics = orchestrator.run(input_files=[str(good_file), str(bad_file)])

    assert metrics.status == "PARTIAL"
    assert metrics.files_processed == 1
    assert metrics.total_files == 2
    assert metrics.records_loaded == 1

    # Check file registry statuses
    with get_connection(temp_db_path) as conn:
        statuses = dict(conn.execute("SELECT file_path, status FROM file_registry").fetchall())

    good_key = [k for k in statuses if "good.json" in k][0]
    bad_key = [k for k in statuses if "unreadable.json" in k][0]

    assert statuses[good_key] == "COMPLETED"
    assert statuses[bad_key] == "FAILED"


def test_interrupted_file_recovery_reprocess(temp_db_path, temp_data_dir):
    """Test recovery of a previously failed file when re-run after resolving the issue."""
    file_path = temp_data_dir / "retry_after_fix.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "api-gateway", "message": "Recovered"}\n')

    orchestrator = PipelineOrchestrator(db_path=temp_db_path, max_retries=1)

    # Step 1: Simulate failure
    with patch.object(orchestrator, "_process_single_file", side_effect=RuntimeError("Transient error")):
        metrics1 = orchestrator.run(input_files=[str(file_path)])
    assert metrics1.status == "FAILED"

    # Step 2: Rerun without failure
    metrics2 = orchestrator.run(input_files=[str(file_path)])
    assert metrics2.status == "SUCCESS"
    assert metrics2.records_loaded == 1

    with get_connection(temp_db_path) as conn:
        row = conn.execute("SELECT status, loaded_count FROM file_registry").fetchone()
        assert row["status"] == "COMPLETED"
        assert row["loaded_count"] == 1


def test_late_and_out_of_order_timestamps(temp_db_path, temp_data_dir):
    """Test handling events arriving out of chronological order with diverse time windows."""
    file_path = temp_data_dir / "out_of_order.json"
    records = [
        '{"timestamp": "2024-01-15T14:00:00Z", "level": "INFO", "service": "auth-service", "message": "Hour 14 event"}',
        '{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "auth-service", "message": "Hour 10 event"}',
        '{"timestamp": "2024-01-15T12:00:00Z", "level": "INFO", "service": "auth-service", "message": "Hour 12 event"}',
        '{"timestamp": "2024-01-15T08:00:00Z", "level": "ERROR", "service": "auth-service", "message": "Hour 8 event"}',
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(records) + "\n")

    orchestrator = PipelineOrchestrator(db_path=temp_db_path)
    metrics = orchestrator.run(input_files=[str(file_path)])
    assert metrics.records_loaded == 4

    # Analytics timeline should order events correctly
    engine = AnalyticsEngine(temp_db_path)
    timeline = engine.get_volume_timeline(freq="1h")

    assert not timeline.empty
    # Earliest bucket should correspond to 08:00 and contain the error
    assert timeline.iloc[0]["errors"] >= 1


def test_schema_variations_and_aliases(temp_db_path, temp_data_dir):
    """Test handling of various field aliases (@timestamp, log_level, app, msg, trace_id)."""
    file_path = temp_data_dir / "aliased_schema.json"
    lines = [
        '{"@timestamp": "2024-01-15T10:00:00Z", "log_level": "WARNING", "app": "search-svc", "msg": "Custom alias log", "trace_id": "tr-123"}',
        '{"time": "2024-01-15T10:05:00Z", "level": "CRITICAL", "component": "cache-svc", "body": "Memory high", "correlation_id": "corr-456"}',
        '{"ts": 1705314600000, "priority": "err", "service_name": "db-svc", "text": "Deadlock found"}',
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    orchestrator = PipelineOrchestrator(db_path=temp_db_path)
    metrics = orchestrator.run(input_files=[str(file_path)])

    assert metrics.records_loaded == 3
    assert metrics.records_quarantined == 0

    with get_connection(temp_db_path) as conn:
        rows = conn.execute("SELECT severity, source, message, request_id FROM log_events ORDER BY timestamp_utc").fetchall()

    assert rows[0]["severity"] == "WARNING"
    assert rows[0]["source"] == "search-svc"
    assert rows[0]["request_id"] == "tr-123"

    assert rows[1]["severity"] == "CRITICAL"
    assert rows[1]["source"] == "cache-svc"
    assert rows[1]["request_id"] == "corr-456"

    assert rows[2]["severity"] == "ERROR"
    assert rows[2]["source"] == "db-svc"


def test_empty_files_and_empty_batches(temp_db_path, temp_data_dir):
    """Test that zero-byte files or empty lines files are handled cleanly without error."""
    empty_file = temp_data_dir / "empty.log"
    empty_file.touch()

    whitespace_file = temp_data_dir / "whitespace.json"
    with open(whitespace_file, "w", encoding="utf-8") as f:
        f.write("\n\n   \n\n")

    orchestrator = PipelineOrchestrator(db_path=temp_db_path)
    metrics = orchestrator.run(input_files=[str(empty_file), str(whitespace_file)])

    assert metrics.status == "SUCCESS"
    assert metrics.files_processed == 2
    assert metrics.records_loaded == 0
    assert metrics.records_quarantined == 0

    with get_connection(temp_db_path) as conn:
        statuses = conn.execute("SELECT status, record_count FROM file_registry").fetchall()
        for s in statuses:
            assert s["status"] == "COMPLETED"
            assert s["record_count"] == 0


def test_repeated_same_input_reruns(temp_db_path, temp_data_dir):
    """Test that running the exact same file 3 times in succession creates 0 duplicate rows."""
    file_path = temp_data_dir / "rerun_test.json"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write('{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "auth-service", "message": "User session"}\n')

    orchestrator = PipelineOrchestrator(db_path=temp_db_path)

    # Run 1
    m1 = orchestrator.run(input_files=[str(file_path)])
    assert m1.records_loaded == 1

    # Run 2
    m2 = orchestrator.run(input_files=[str(file_path)])
    assert m2.records_loaded == 0

    # Run 3
    m3 = orchestrator.run(input_files=[str(file_path)])
    assert m3.records_loaded == 0

    with get_connection(temp_db_path) as conn:
        total_rows = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
        assert total_rows == 1
