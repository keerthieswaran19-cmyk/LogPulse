"""Unit tests for TimestampNormalizer and SeverityNormalizer."""

from datetime import datetime, timezone
from src.normalizer.severity_normalizer import SeverityNormalizer
from src.normalizer.timestamp_normalizer import TimestampNormalizer


def test_timestamp_normalizer_iso():
    iso_input = "2024-01-15T10:30:00Z"
    assert TimestampNormalizer.normalize(iso_input) == "2024-01-15T10:30:00Z"

    # Space separator ISO
    space_iso = "2024-01-15 10:30:00"
    assert TimestampNormalizer.normalize(space_iso) == "2024-01-15T10:30:00Z"


def test_timestamp_normalizer_epoch():
    # 1705314600 is 2024-01-15 10:30:00 UTC
    assert TimestampNormalizer.normalize(1705314600) == "2024-01-15T10:30:00Z"
    # Milliseconds
    assert TimestampNormalizer.normalize(1705314600000) == "2024-01-15T10:30:00Z"
    # String numeric
    assert TimestampNormalizer.normalize("1705314600") == "2024-01-15T10:30:00Z"


def test_timestamp_normalizer_datetime():
    dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    assert TimestampNormalizer.normalize(dt) == "2024-01-15T10:30:00Z"


def test_timestamp_normalizer_invalid():
    assert TimestampNormalizer.normalize(None) is None
    assert TimestampNormalizer.normalize("") is None
    assert TimestampNormalizer.normalize("not-a-valid-date") is None


def test_severity_normalizer():
    # Canonical
    assert SeverityNormalizer.normalize("INFO") == "INFO"
    assert SeverityNormalizer.normalize("ERROR") == "ERROR"
    assert SeverityNormalizer.normalize("CRITICAL") == "CRITICAL"

    # Common aliases
    assert SeverityNormalizer.normalize("warn") == "WARNING"
    assert SeverityNormalizer.normalize("ERR") == "ERROR"
    assert SeverityNormalizer.normalize("fatal") == "CRITICAL"
    assert SeverityNormalizer.normalize("trace") == "DEBUG"
    assert SeverityNormalizer.normalize("information") == "INFO"

    # Numeric RFC 5424
    assert SeverityNormalizer.normalize("3") == "ERROR"
    assert SeverityNormalizer.normalize("4") == "WARNING"

    # Invalid
    assert SeverityNormalizer.normalize("UNKNOWN_LEVEL") is None
    assert SeverityNormalizer.normalize("") is None
    assert SeverityNormalizer.normalize(None) is None
