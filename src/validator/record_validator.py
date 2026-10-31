"""Record validation module – schema checks and quarantine routing."""

from typing import List, Optional, Tuple
import pandas as pd

from src.normalizer.severity_normalizer import SeverityNormalizer
from src.normalizer.timestamp_normalizer import TimestampNormalizer
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RecordValidator:
    """Validates log records, normalizes fields, and segregates valid and quarantined records."""

    def __init__(self, allowed_severities: Optional[List[str]] = None) -> None:
        self.allowed_severities = allowed_severities or [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Validate records in DataFrame.

        Performs:
            - Timestamp normalization and validation
            - Severity normalization and validation
            - Non-empty checks for source and message
            - Checks for parsing errors

        Returns:
            Tuple of (valid_df, quarantine_df)
        """
        if df.empty:
            valid_cols = [
                "timestamp_utc",
                "severity",
                "source",
                "message",
                "latency_ms",
                "request_id",
                "raw_line",
                "source_file",
            ]
            quar_cols = [
                "raw_line",
                "rejection_reason",
                "source_file",
            ]
            return pd.DataFrame(columns=valid_cols), pd.DataFrame(columns=quar_cols)

        valid_records = []
        quarantine_records = []

        for _, row in df.iterrows():
            raw_line = str(row.get("raw_line", "") or "").strip()
            source_file = str(row.get("source_file", "unknown"))

            # Check if upstream parser flagged an error
            if "parsing_error" in row and pd.notna(row["parsing_error"]):
                quarantine_records.append({
                    "raw_line": raw_line,
                    "rejection_reason": f"Parsing Error: {row['parsing_error']}",
                    "source_file": source_file,
                })
                continue

            reasons = []

            # 1. Timestamp validation & normalization
            raw_ts = row.get("timestamp")
            if pd.isna(raw_ts) or raw_ts is None or str(raw_ts).strip() == "":
                reasons.append("Missing required field: timestamp")
                norm_ts = None
            else:
                norm_ts = TimestampNormalizer.normalize(raw_ts)
                if norm_ts is None:
                    reasons.append(f"Invalid timestamp format: '{raw_ts}'")

            # 2. Severity validation & normalization
            raw_sev = row.get("severity")
            if pd.isna(raw_sev) or raw_sev is None or str(raw_sev).strip() == "":
                reasons.append("Missing required field: severity")
                norm_sev = None
            else:
                norm_sev = SeverityNormalizer.normalize(raw_sev)
                if norm_sev is None or norm_sev not in self.allowed_severities:
                    reasons.append(f"Unrecognized or disallowed severity: '{raw_sev}'")

            # 3. Source validation
            source = row.get("source")
            if pd.isna(source) or source is None or str(source).strip() == "":
                reasons.append("Missing required field: source")
                clean_source = None
            else:
                clean_source = str(source).strip()

            # 4. Message validation
            message = row.get("message")
            if pd.isna(message) or message is None or str(message).strip() == "":
                reasons.append("Missing required field: message")
                clean_msg = None
            else:
                clean_msg = str(message).strip()

            # Latency handling
            raw_lat = row.get("latency_ms")
            latency_ms = None
            if pd.notna(raw_lat) and raw_lat is not None:
                try:
                    latency_ms = float(raw_lat)
                except (ValueError, TypeError):
                    latency_ms = None

            # Request ID handling
            raw_req = row.get("request_id")
            request_id = None
            if pd.notna(raw_req) and raw_req is not None:
                request_id = str(raw_req).strip() or None

            if reasons:
                quarantine_records.append({
                    "raw_line": raw_line or f"{raw_ts} | {raw_sev} | {source} | {message}",
                    "rejection_reason": "; ".join(reasons),
                    "source_file": source_file,
                })
            else:
                valid_records.append({
                    "timestamp_utc": norm_ts,
                    "severity": norm_sev,
                    "source": clean_source,
                    "message": clean_msg,
                    "latency_ms": latency_ms,
                    "request_id": request_id,
                    "raw_line": raw_line or f"{norm_ts} {norm_sev} {clean_source} {clean_msg}",
                    "source_file": source_file,
                })

        valid_df = pd.DataFrame(valid_records)
        quar_df = pd.DataFrame(quarantine_records)

        logger.info(
            f"Validation complete: {len(valid_df)} valid records, "
            f"{len(quar_df)} quarantined records"
        )
        return valid_df, quar_df
