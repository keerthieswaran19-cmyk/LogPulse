"""Shared fixtures for LogPulse test suite."""

import os
from pathlib import Path
import tempfile
import pytest
import sqlite3

from src.loader.db_loader import DBLoader


@pytest.fixture
def temp_db_path():
    """Create a temporary SQLite database file and initialize schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    loader = DBLoader(db_path)
    loader.init_db()

    yield db_path

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except PermissionError:
            pass


@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for raw/quarantine files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_json_file(temp_data_dir):
    """Create a sample JSON log file with valid and invalid lines."""
    file_path = temp_data_dir / "sample.json"
    lines = [
        '{"timestamp": "2024-01-15T10:00:00Z", "level": "INFO", "service": "auth-service", "message": "User login success", "latency": 45}',
        '{"timestamp": "2024-01-15T10:05:00Z", "level": "ERR", "service": "payment-service", "message": "Card declined | latency=320ms", "request_id": "req-999"}',
        '{"timestamp": "invalid-time", "level": "WARN", "service": "api-gateway", "message": "Unparseable time"}',
        '{"corrupted_json": true',  # Malformed JSON
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return str(file_path)


@pytest.fixture
def sample_csv_file(temp_data_dir):
    """Create a sample CSV log file."""
    file_path = temp_data_dir / "sample.csv"
    content = """timestamp,severity,source,message,latency_ms,request_id
2024-01-15T11:00:00Z,INFO,user-service,User fetched,25.5,req-101
2024-01-15T11:05:00Z,CRITICAL,inventory-service,Stock out of sync,150.0,req-102
,INFO,auth-service,Missing timestamp,30.0,req-103
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(file_path)


@pytest.fixture
def sample_syslog_file(temp_data_dir):
    """Create a sample syslog-style log file."""
    file_path = temp_data_dir / "sample.log"
    lines = [
        "2024-01-15 12:00:00 INFO auth-service [req-201] Login success | latency=50ms",
        "2024-01-15 12:05:00 ERROR api-gateway [req-202] Connection timed out | latency=5000ms",
        "Jan 15 12:10:00 WARNING search-service Query took long",
        "Random unparseable garbage line without standard log tokens",
    ]
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return str(file_path)
