"""Regex patterns and format definitions for log parsing."""

import re

# ---------------------------------------------------------------------------
# Syslog-style log pattern
# Example: 2024-01-15 10:30:45 ERROR auth-service [req-abc123] Login failed | latency=250ms
# Example: Jan 15 10:30:45 WARNING api-gateway Request timeout
# ---------------------------------------------------------------------------

# ISO-style timestamp at the start
SYSLOG_ISO_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<severity>[A-Z]+)\s+"
    r"(?P<source>[\w._-]+)\s+"
    r"(?:\[(?P<request_id>[\w._-]+)\]\s+)?"
    r"(?P<message>.+)"
)

# BSD syslog-style (Mon DD HH:MM:SS)
SYSLOG_BSD_PATTERN = re.compile(
    r"^(?P<timestamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<severity>[A-Z]+)\s+"
    r"(?P<source>[\w._-]+)\s+"
    r"(?:\[(?P<request_id>[\w._-]+)\]\s+)?"
    r"(?P<message>.+)"
)

# ---------------------------------------------------------------------------
# Latency extraction pattern
# Matches: latency=250ms, latency=1.5s, response_time=100ms, duration=2000ms
# ---------------------------------------------------------------------------

LATENCY_PATTERN = re.compile(
    r"(?:latency|response_time|duration)\s*=\s*(?P<value>[\d.]+)\s*(?P<unit>ms|s)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Request ID extraction pattern (if not captured by syslog pattern)
# Matches: [req-abc123], request_id=abc123, trace_id=xyz789
# ---------------------------------------------------------------------------

REQUEST_ID_PATTERN = re.compile(
    r"(?:\[(?P<bracket_id>req-[\w._-]+)\]|(?:request_id|trace_id)\s*=\s*(?P<kv_id>[\w._-]+))",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Severity alias mapping
# Maps common aliases to the canonical set: DEBUG, INFO, WARNING, ERROR, CRITICAL
# ---------------------------------------------------------------------------

SEVERITY_MAP = {
    # Canonical (identity mappings)
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
    # Common aliases
    "WARN": "WARNING",
    "ERR": "ERROR",
    "FATAL": "CRITICAL",
    "TRACE": "DEBUG",
    "VERBOSE": "DEBUG",
    "NOTICE": "INFO",
    "INFORMATION": "INFO",
    "INFORMATIONAL": "INFO",
    "EMERGENCY": "CRITICAL",
    "EMERG": "CRITICAL",
    "ALERT": "CRITICAL",
    "SEVERE": "CRITICAL",
    "PANIC": "CRITICAL",
}

# Canonical severity levels (ordered by severity)
CANONICAL_SEVERITIES = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# ---------------------------------------------------------------------------
# JSON log expected field names (with common aliases)
# ---------------------------------------------------------------------------

# Maps various JSON field names to our canonical field names
JSON_FIELD_MAP = {
    # Timestamp fields
    "timestamp": "timestamp",
    "time": "timestamp",
    "ts": "timestamp",
    "datetime": "timestamp",
    "date": "timestamp",
    "@timestamp": "timestamp",
    "event_time": "timestamp",
    # Severity fields
    "severity": "severity",
    "level": "severity",
    "log_level": "severity",
    "loglevel": "severity",
    "priority": "severity",
    # Source fields
    "source": "source",
    "service": "source",
    "service_name": "source",
    "app": "source",
    "application": "source",
    "component": "source",
    "logger": "source",
    "host": "source",
    # Message fields
    "message": "message",
    "msg": "message",
    "text": "message",
    "log": "message",
    "body": "message",
    "description": "message",
    # Request ID fields
    "request_id": "request_id",
    "trace_id": "request_id",
    "correlation_id": "request_id",
    "req_id": "request_id",
    "span_id": "request_id",
    # Latency fields
    "latency": "latency_ms",
    "latency_ms": "latency_ms",
    "response_time": "latency_ms",
    "duration": "latency_ms",
    "duration_ms": "latency_ms",
    "elapsed": "latency_ms",
    "elapsed_ms": "latency_ms",
}

# CSV expected column orders (common patterns)
CSV_EXPECTED_COLUMNS = [
    "timestamp", "severity", "source", "message",
    "request_id", "latency_ms",
]
