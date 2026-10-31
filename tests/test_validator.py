"""Unit tests for RecordValidator and quarantine routing."""

import pandas as pd
from src.validator.record_validator import RecordValidator


def test_validator_valid_record():
    validator = RecordValidator()
    df = pd.DataFrame([
        {
            "timestamp": "2024-01-15T10:00:00Z",
            "severity": "INFO",
            "source": "auth-service",
            "message": "User logged in",
            "latency_ms": 45.0,
            "raw_line": "raw",
            "source_file": "app.log",
        }
    ])
    valid_df, quar_df = validator.validate(df)
    assert len(valid_df) == 1
    assert len(quar_df) == 0
    assert valid_df.iloc[0]["severity"] == "INFO"
    assert valid_df.iloc[0]["source"] == "auth-service"


def test_validator_missing_fields_quarantine():
    validator = RecordValidator()
    df = pd.DataFrame([
        {
            # Missing timestamp
            "timestamp": None,
            "severity": "INFO",
            "source": "auth-service",
            "message": "Missing ts",
            "raw_line": "raw1",
        },
        {
            # Missing source
            "timestamp": "2024-01-15T10:00:00Z",
            "severity": "INFO",
            "source": "",
            "message": "Missing source",
            "raw_line": "raw2",
        },
        {
            # Invalid severity
            "timestamp": "2024-01-15T10:00:00Z",
            "severity": "UNKNOWN",
            "source": "auth-service",
            "message": "Bad sev",
            "raw_line": "raw3",
        },
        {
            # Empty message
            "timestamp": "2024-01-15T10:00:00Z",
            "severity": "INFO",
            "source": "auth-service",
            "message": "   ",
            "raw_line": "raw4",
        },
    ])
    valid_df, quar_df = validator.validate(df)
    assert len(valid_df) == 0
    assert len(quar_df) == 4
    assert any("timestamp" in r for r in quar_df["rejection_reason"])
    assert any("source" in r for r in quar_df["rejection_reason"])
    assert any("severity" in r for r in quar_df["rejection_reason"])
    assert any("message" in r for r in quar_df["rejection_reason"])


def test_validator_parsing_error_passthrough():
    validator = RecordValidator()
    df = pd.DataFrame([
        {
            "raw_line": "corrupted",
            "parsing_error": "JSON decode error",
            "source_file": "bad.json",
        }
    ])
    valid_df, quar_df = validator.validate(df)
    assert len(valid_df) == 0
    assert len(quar_df) == 1
    assert "JSON decode error" in quar_df.iloc[0]["rejection_reason"]
