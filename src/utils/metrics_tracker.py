"""Pipeline execution metrics tracker for LogPulse."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class PipelineMetrics:
    """Tracks execution metrics for a single pipeline run.

    Attributes:
        run_id: Unique identifier for this pipeline run.
        started_at: ISO-8601 UTC timestamp when the run started.
        completed_at: ISO-8601 UTC timestamp when the run completed.
        status: Current status (RUNNING, SUCCESS, PARTIAL, FAILED).
        total_files: Number of files discovered for processing.
        files_processed: Number of files successfully processed.
        total_records: Total records parsed across all files.
        records_loaded: Records successfully inserted into the database.
        records_quarantined: Records rejected and sent to quarantine.
        records_duplicated: Duplicate records skipped.
        duration_seconds: Wall-clock duration of the pipeline run.
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    status: str = "RUNNING"
    total_files: int = 0
    files_processed: int = 0
    total_records: int = 0
    records_loaded: int = 0
    records_quarantined: int = 0
    records_duplicated: int = 0
    duration_seconds: float = 0.0

    _start_time: float = field(default=0.0, repr=False)

    def start(self) -> None:
        """Mark the pipeline run as started."""
        self._start_time = time.time()
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.status = "RUNNING"
        logger.info(f"Pipeline run {self.run_id} started at {self.started_at}")

    def finish(self, status: str = None) -> None:
        """Mark the pipeline run as completed.

        Args:
            status: Final status. If None, auto-determined from file counts.
        """
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.duration_seconds = round(time.time() - self._start_time, 3)

        if status:
            self.status = status
        elif self.files_processed == 0 and self.total_files > 0:
            self.status = "FAILED"
        elif self.files_processed < self.total_files:
            self.status = "PARTIAL"
        else:
            self.status = "SUCCESS"

        logger.info(
            f"Pipeline run {self.run_id} finished: status={self.status}, "
            f"files={self.files_processed}/{self.total_files}, "
            f"loaded={self.records_loaded}, quarantined={self.records_quarantined}, "
            f"duplicates={self.records_duplicated}, duration={self.duration_seconds}s"
        )

    def summary(self) -> dict:
        """Return a dictionary summary of the pipeline run metrics.

        Returns:
            Dictionary with all metric fields.
        """
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "total_files": self.total_files,
            "files_processed": self.files_processed,
            "total_records": self.total_records,
            "records_loaded": self.records_loaded,
            "records_quarantined": self.records_quarantined,
            "records_duplicated": self.records_duplicated,
            "duration_seconds": self.duration_seconds,
        }
