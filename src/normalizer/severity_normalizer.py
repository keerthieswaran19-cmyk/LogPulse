"""Severity normalization module – standardizes severity aliases to canonical levels."""

from typing import Any, Optional

from src.parser.patterns import CANONICAL_SEVERITIES, SEVERITY_MAP
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SeverityNormalizer:
    """Normalizes raw severity strings to canonical uppercase levels."""

    @staticmethod
    def normalize(level_val: Any) -> Optional[str]:
        """Convert a severity level to one of: DEBUG, INFO, WARNING, ERROR, CRITICAL.

        Args:
            level_val: Raw severity value (e.g. 'WARN', 'err', 'critical', 'fatal').

        Returns:
            Canonical severity string or None if unrecognized / empty.
        """
        if level_val is None:
            return None

        clean_str = str(level_val).strip().upper()
        if not clean_str:
            return None

        # Check map
        if clean_str in SEVERITY_MAP:
            return SEVERITY_MAP[clean_str]

        # Numeric syslog facility / severity mapping (RFC 5424)
        numeric_map = {
            "0": "CRITICAL",  # Emergency
            "1": "CRITICAL",  # Alert
            "2": "CRITICAL",  # Critical
            "3": "ERROR",     # Error
            "4": "WARNING",   # Warning
            "5": "INFO",      # Notice
            "6": "INFO",      # Informational
            "7": "DEBUG",     # Debug
        }
        if clean_str in numeric_map:
            return numeric_map[clean_str]

        return None
