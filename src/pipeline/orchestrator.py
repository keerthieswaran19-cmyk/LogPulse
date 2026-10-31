"""Pipeline orchestration module – end-to-end pipeline execution with retries and tracking."""

import os
from pathlib import Path
import time
from typing import List, Optional

from src.dedup.deduplicator import Deduplicator
from src.loader.db_loader import DBLoader, compute_file_hash
from src.parser.log_parser import LogParser
from src.utils.db_utils import PROJECT_ROOT, get_connection, load_config
from src.utils.logger import get_logger
from src.utils.metrics_tracker import PipelineMetrics
from src.validator.record_validator import RecordValidator

logger = get_logger(__name__)


class PipelineOrchestrator:
    """Coordinates log file discovery, parsing, normalization, validation, deduplication, and database ingestion."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        max_retries: int = 3,
        retry_backoff_base: float = 2.0,
    ) -> None:
        self.config = load_config()
        self.loader = DBLoader(db_path)
        self.parser = LogParser()
        self.validator = RecordValidator(
            allowed_severities=self.config.get("validation", {}).get("allowed_severities")
        )
        self.max_retries = max_retries or self.config.get("pipeline", {}).get("max_retries", 3)
        self.retry_backoff_base = retry_backoff_base or self.config.get("pipeline", {}).get(
            "retry_backoff_base", 2.0
        )

    def discover_files(self, raw_dir: Optional[str] = None) -> List[str]:
        """Find all eligible log files in the raw directory.

        Supports: .json, .jsonl, .ndjson, .csv, .log, .txt
        """
        target_dir = Path(raw_dir or (PROJECT_ROOT / self.config["directories"]["raw"]))
        if not target_dir.exists():
            logger.warning(f"Raw directory does not exist: {target_dir}")
            return []

        extensions = {".json", ".jsonl", ".ndjson", ".csv", ".log", ".txt"}
        files = []
        for p in sorted(target_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith("."):
                files.append(str(p.resolve()))

        logger.info(f"Discovered {len(files)} log files in {target_dir}")
        return files

    def process_file_with_retry(
        self, file_path: str, run_id: str, metrics: PipelineMetrics
    ) -> bool:
        """Process a single file with exponential backoff retry.

        Returns:
            True if processed or safely skipped, False if permanent failure.
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                self._process_single_file(file_path, run_id, metrics)
                return True
            except Exception as e:
                logger.error(
                    f"Attempt {attempt}/{self.max_retries} failed for {file_path}: {e}",
                    exc_info=True,
                )
                if attempt == self.max_retries:
                    # Mark as failed in registry
                    try:
                        f_hash = compute_file_hash(file_path)
                        self.loader.update_file_registry(
                            file_path=file_path,
                            file_hash=f_hash,
                            status="FAILED",
                            record_count=0,
                            loaded_count=0,
                            quarantined_count=0,
                            duplicate_count=0,
                            run_id=run_id,
                        )
                    except Exception as reg_err:
                        logger.error(f"Failed to record registry failure: {reg_err}")
                    return False
                wait_time = self.retry_backoff_base ** attempt
                logger.warning(f"Backing off for {wait_time:.1f}s before retrying {file_path}...")
                time.sleep(wait_time)
        return False

    def _process_single_file(
        self, file_path: str, run_id: str, metrics: PipelineMetrics
    ) -> None:
        """Core single-file pipeline stages execution."""
        file_hash = compute_file_hash(file_path)
        file_name = os.path.basename(file_path)

        # 1. Idempotency Check (File-level)
        if self.loader.is_file_processed(file_path, file_hash):
            logger.info(f"File {file_name} already processed with identical content hash. Skipping.")
            return

        logger.info(f"--- Processing {file_name} (Run: {run_id}) ---")

        # 2. Parse
        raw_df, total_lines = self.parser.parse_file(file_path)
        metrics.total_records += total_lines

        if raw_df.empty:
            logger.warning(f"File {file_name} contained no parsable records.")
            self.loader.update_file_registry(
                file_path=file_path,
                file_hash=file_hash,
                status="COMPLETED",
                record_count=0,
                loaded_count=0,
                quarantined_count=0,
                duplicate_count=0,
                run_id=run_id,
            )
            return

        # 3. Validate & Normalize
        valid_df, quar_df = self.validator.validate(raw_df)

        # 4. Quarantine Processing
        quar_count = 0
        if not quar_df.empty:
            quar_count = self.loader.load_quarantine(quar_df, run_id)
            metrics.records_quarantined += quar_count

        # 5. Deduplication
        loaded_count = 0
        dup_count = 0
        if not valid_df.empty:
            # Add hash
            valid_df = Deduplicator.add_record_hashes(valid_df)

            # In-batch dedup
            deduped_df, in_batch_dups = Deduplicator.deduplicate_batch(valid_df)
            dup_count += in_batch_dups

            # DB-level dedup check
            with get_connection(self.loader.db_path) as conn:
                new_records_df, db_dups = Deduplicator.filter_existing_db_records(
                    deduped_df, conn
                )
                dup_count += db_dups

            metrics.records_duplicated += dup_count

            # 6. Load to SQLite
            if not new_records_df.empty:
                loaded_count = self.loader.load_log_events(new_records_df, run_id)
                metrics.records_loaded += loaded_count

        # 7. Update File Registry
        self.loader.update_file_registry(
            file_path=file_path,
            file_hash=file_hash,
            status="COMPLETED",
            record_count=total_lines,
            loaded_count=loaded_count,
            quarantined_count=quar_count,
            duplicate_count=dup_count,
            run_id=run_id,
        )

    def run(self, input_files: Optional[List[str]] = None, raw_dir: Optional[str] = None) -> PipelineMetrics:
        """Run the end-to-end ingestion pipeline."""
        # Initialize schema
        self.loader.init_db()

        metrics = PipelineMetrics()
        metrics.start()

        # Save initial RUNNING state
        self.loader.save_pipeline_run(metrics.summary())

        # Determine target files
        files = input_files if input_files is not None else self.discover_files(raw_dir)
        metrics.total_files = len(files)

        if not files:
            logger.info("No files to process.")
            metrics.finish(status="SUCCESS")
            self.loader.save_pipeline_run(metrics.summary())
            return metrics

        for file_path in files:
            success = self.process_file_with_retry(file_path, metrics.run_id, metrics)
            if success:
                metrics.files_processed += 1

        metrics.finish()
        self.loader.save_pipeline_run(metrics.summary())
        return metrics


if __name__ == "__main__":
    orchestrator = PipelineOrchestrator()
    results = orchestrator.run()
    print("\n--- Pipeline Execution Summary ---")
    for k, v in results.summary().items():
        print(f"  {k:22}: {v}")
