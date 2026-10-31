"""Centralized logging configuration for LogPulse."""

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a consistent format.

    Args:
        level: Logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_format = "%(asctime)s | %(name)-30s | %(levelname)-8s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.addHandler(handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger, ensuring logging is configured.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logging.Logger instance.
    """
    setup_logging()
    return logging.getLogger(name)
