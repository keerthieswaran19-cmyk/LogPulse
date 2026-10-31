"""Deduplication module – hash-based duplicate detection and filtering."""

import hashlib
from typing import Optional, Set, Tuple
import pandas as pd
import sqlite3

from src.utils.logger import get_logger

logger = get_logger(__name__)


def compute_record_hash(timestamp_utc: str, source: str, message: str) -> str:
    """Compute deterministic SHA-256 record hash from core log identifiers.

    Args:
        timestamp_utc: Normalized timestamp string.
        source: Normalized service/component name.
        message: Log message string.

    Returns:
        64-character hexadecimal SHA-256 hash.
    """
    payload = f"{timestamp_utc}|{source}|{message}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class Deduplicator:
    """Handles in-batch and cross-database record deduplication."""

    @staticmethod
    def add_record_hashes(df: pd.DataFrame) -> pd.DataFrame:
        """Add 'record_hash' column to DataFrame based on core attributes."""
        if df.empty or "timestamp_utc" not in df.columns:
            df["record_hash"] = pd.Series(dtype="str")
            return df

        hashes = []
        for _, row in df.iterrows():
            ts = str(row.get("timestamp_utc", ""))
            src = str(row.get("source", ""))
            msg = str(row.get("message", ""))
            hashes.append(compute_record_hash(ts, src, msg))

        df["record_hash"] = hashes
        return df

    @classmethod
    def deduplicate_batch(cls, df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
        """Remove duplicate records within the current DataFrame batch.

        Keeps the first occurrence of each unique record_hash.

        Returns:
            Tuple of (deduplicated DataFrame, number of in-batch duplicates dropped).
        """
        if df.empty:
            return df, 0

        if "record_hash" not in df.columns:
            df = cls.add_record_hashes(df)

        initial_count = len(df)
        deduped_df = df.drop_duplicates(subset=["record_hash"], keep="first").copy()
        dropped_count = initial_count - len(deduped_df)

        if dropped_count > 0:
            logger.info(f"Dropped {dropped_count} in-batch duplicate records")

        return deduped_df, dropped_count

    @classmethod
    def filter_existing_db_records(
        cls, df: pd.DataFrame, conn: sqlite3.Connection
    ) -> Tuple[pd.DataFrame, int]:
        """Filter out records that already exist in the SQLite log_events table.

        Args:
            df: DataFrame containing a 'record_hash' column.
            conn: Active SQLite connection.

        Returns:
            Tuple of (DataFrame of new records only, count of existing DB duplicates skipped).
        """
        if df.empty or "record_hash" not in df.columns:
            return df, 0

        # Query existing hashes in chunks if large, or in a single pass
        hashes = df["record_hash"].tolist()
        existing_hashes: Set[str] = set()

        chunk_size = 500  # SQLite parameter limits
        for i in range(0, len(hashes), chunk_size):
            chunk = hashes[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(
                f"SELECT record_hash FROM log_events WHERE record_hash IN ({placeholders})",
                chunk,
            )
            existing_hashes.update(row[0] for row in cursor.fetchall())

        if not existing_hashes:
            return df, 0

        new_df = df[~df["record_hash"].isin(existing_hashes)].copy()
        db_duplicates = len(df) - len(new_df)

        if db_duplicates > 0:
            logger.info(f"Filtered out {db_duplicates} records that already exist in database")

        return new_df, db_duplicates
