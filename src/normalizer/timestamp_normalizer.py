"""Timestamp normalization module – standardizes diverse timestamp formats to UTC ISO-8601."""

from datetime import datetime, timezone
from typing import Any, Optional, Union
import dateutil.parser

from src.utils.logger import get_logger

logger = get_logger(__name__)


class TimestampNormalizer:
    """Normalizes raw timestamp representations into UTC ISO-8601 strings."""

    @staticmethod
    def normalize(ts_val: Any) -> Optional[str]:
        """Convert any supported timestamp representation to UTC ISO-8601 string.

        Supports:
            - ISO 8601 strings (e.g., '2024-01-15T10:30:45Z', '2024-01-15 10:30:45')
            - BSD syslog format (e.g., 'Jan 15 10:30:45')
            - Unix timestamps (numeric or string digits; seconds or milliseconds)
            - Datetime objects

        Returns:
            Normalized UTC string in 'YYYY-MM-DDTHH:MM:SSZ' (or with milliseconds),
            or None if parsing fails.
        """
        if ts_val is None:
            return None

        # If already datetime
        if isinstance(ts_val, datetime):
            dt = ts_val
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Handle numeric / epoch
        if isinstance(ts_val, (int, float)):
            try:
                # Milliseconds heuristic (> 10^11 is ms)
                if ts_val > 1e11:
                    dt = datetime.fromtimestamp(ts_val / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (OverflowError, OSError, ValueError):
                return None

        # String processing
        if not isinstance(ts_val, str):
            ts_str = str(ts_val).strip()
        else:
            ts_str = ts_val.strip()

        if not ts_str:
            return None

        # Check if string is purely numeric epoch
        if ts_str.isdigit() or (ts_str.replace(".", "", 1).isdigit() and ts_str.count(".") <= 1):
            try:
                val = float(ts_str)
                if val > 1e11:
                    dt = datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
                else:
                    dt = datetime.fromtimestamp(val, tz=timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except (OverflowError, OSError, ValueError):
                pass

        # Try dateutil parser
        try:
            dt = dateutil.parser.parse(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)

            # If BSD syslog format without year, default year might be current year
            # Ensure it formats cleanly
            if dt.microsecond > 0:
                return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
