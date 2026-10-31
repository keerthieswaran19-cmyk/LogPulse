"""End-to-End integration tests for LogPulse pipeline."""

import os
from src.loader.db_loader import DBLoader
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.db_utils import get_connection


def test_pipeline_end_to_end(
    temp_db_path, sample_json_file, sample_csv_file, sample_syslog_file
):
    orchestrator = PipelineOrchestrator(db_path=temp_db_path)
    files = [sample_json_file, sample_csv_file, sample_syslog_file]

    # --- Run 1: Ingestion ---
    metrics1 = orchestrator.run(input_files=files)

    assert metrics1.status == "SUCCESS"
    assert metrics1.total_files == 3
    assert metrics1.files_processed == 3
    assert metrics1.records_loaded > 0
    assert metrics1.records_quarantined > 0

    with get_connection(temp_db_path) as conn:
        count_loaded1 = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
        count_quar1 = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
        runs_count = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]

    assert count_loaded1 == metrics1.records_loaded
    assert count_quar1 == metrics1.records_quarantined
    assert runs_count == 1

    # --- Run 2: Idempotent re-run on identical input files ---
    metrics2 = orchestrator.run(input_files=files)

    assert metrics2.status == "SUCCESS"
    assert metrics2.total_files == 3
    # All files should have been skipped via file registry check
    assert metrics2.records_loaded == 0

    with get_connection(temp_db_path) as conn:
        count_loaded2 = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
        count_quar2 = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]

    # Database state must be identical to Run 1
    assert count_loaded2 == count_loaded1
    assert count_quar2 == count_quar1
