"""SQLite database connection helpers for LogPulse."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import yaml

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Project root directory (two levels up from this file)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_config() -> dict:
    """Load pipeline configuration from YAML file.

    Returns:
        Configuration dictionary.
    """
    config_path = PROJECT_ROOT / "config" / "pipeline_config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_db_path() -> str:
    """Get the SQLite database file path.

    Reads from environment variable LOGPULSE_DB_PATH or falls back
    to the config file. Creates the parent directory if it doesn't exist.

    Returns:
        Absolute path to the SQLite database file.
    """
    env_path = os.environ.get("LOGPULSE_DB_PATH")
    if env_path:
        db_path = Path(env_path)
    else:
        config = load_config()
        db_path = PROJECT_ROOT / config["database"]["path"]

    # Ensure the parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return str(db_path)


@contextmanager
def get_connection(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database connections.

    Enables WAL mode and foreign keys for better concurrency and integrity.

    Args:
        db_path: Optional path to the SQLite database. If None, uses default.

    Yields:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
