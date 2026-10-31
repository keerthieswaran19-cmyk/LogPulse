"""Log parsing module for structured and semi-structured logs."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from src.parser.patterns import (
    CSV_EXPECTED_COLUMNS,
    JSON_FIELD_MAP,
    LATENCY_PATTERN,
    REQUEST_ID_PATTERN,
    SYSLOG_BSD_PATTERN,
    SYSLOG_ISO_PATTERN,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def extract_latency(text: str) -> Optional[float]:
    """Extract latency in milliseconds from a message string."""
    if not isinstance(text, str):
        return None
    match = LATENCY_PATTERN.search(text)
    if match:
        val = float(match.group("value"))
        unit = match.group("unit").lower()
        if unit == "s":
            return val * 1000.0
        return val
    return None


def extract_request_id(text: str) -> Optional[str]:
    """Extract request or trace ID from message or header."""
    if not isinstance(text, str):
        return None
    match = REQUEST_ID_PATTERN.search(text)
    if match:
        return match.group("bracket_id") or match.group("kv_id")
    return None


class LogParser:
    """Parses various application log formats into standardized record dictionaries."""

    def __init__(self) -> None:
        pass

    def detect_format(self, file_path: str) -> str:
        """Auto-detect format from file extension or content sniffing.

        Returns one of: 'json', 'csv', 'syslog'
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext in [".json", ".jsonl", ".ndjson"]:
            return "json"
        if ext in [".csv"]:
            return "csv"
        if ext in [".log", ".txt"]:
            # Content sniff first few non-empty lines
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    for _ in range(5):
                        line = f.readline()
                        if not line:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("{") and line.endswith("}"):
                            return "json"
                        if "," in line and any(col in line.lower() for col in ["timestamp", "severity", "level", "message"]):
                            return "csv"
            except Exception as e:
                logger.warning(f"Error sniffing file format for {file_path}: {e}")
            return "syslog"
        return "syslog"

    def parse_file(self, file_path: str) -> Tuple[pd.DataFrame, int]:
        """Parse an input log file into a DataFrame.

        Returns:
            Tuple of (DataFrame of parsed records, total raw lines count).
        """
        fmt = self.detect_format(file_path)
        logger.info(f"Parsing {file_path} with detected format: {fmt}")

        records: List[Dict[str, Any]] = []
        total_lines = 0

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if fmt == "json":
            records, total_lines = self._parse_json(file_path)
        elif fmt == "csv":
            records, total_lines = self._parse_csv(file_path)
        else:
            records, total_lines = self._parse_syslog(file_path)

        df = pd.DataFrame(records)
        source_filename = os.path.basename(file_path)
        if not df.empty:
            df["source_file"] = source_filename
        else:
            df = pd.DataFrame(
                columns=[
                    "timestamp",
                    "severity",
                    "source",
                    "message",
                    "latency_ms",
                    "request_id",
                    "raw_line",
                    "source_file",
                ]
            )

        logger.info(f"Parsed {len(df)} records from {total_lines} raw lines in {source_filename}")
        return df, total_lines

    def _parse_json(self, file_path: str) -> Tuple[List[Dict[str, Any]], int]:
        records: List[Dict[str, Any]] = []
        total_lines = 0
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                raw_line = line.strip()
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                    if not isinstance(data, dict):
                        records.append({
                            "raw_line": raw_line,
                            "parsing_error": "JSON is not an object",
                        })
                        continue

                    record: Dict[str, Any] = {"raw_line": raw_line}
                    for k, v in data.items():
                        canon_key = JSON_FIELD_MAP.get(k.lower(), k)
                        record[canon_key] = v

                    # Latency extraction fallback
                    if "latency_ms" in record:
                        try:
                            record["latency_ms"] = float(record["latency_ms"])
                        except (ValueError, TypeError):
                            record["latency_ms"] = None
                    elif "message" in record and isinstance(record["message"], str):
                        record["latency_ms"] = extract_latency(record["message"])

                    # Request ID extraction fallback
                    if "request_id" not in record and "message" in record and isinstance(record["message"], str):
                        record["request_id"] = extract_request_id(record["message"])

                    records.append(record)
                except Exception as e:
                    records.append({
                        "raw_line": raw_line,
                        "parsing_error": f"JSON decode error: {str(e)}",
                    })
        return records, total_lines

    def _parse_csv(self, file_path: str) -> Tuple[List[Dict[str, Any]], int]:
        records: List[Dict[str, Any]] = []
        total_lines = 0
        try:
            # First read raw lines count
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                total_lines = sum(1 for line in f if line.strip())

            df = pd.read_csv(file_path)
            # Normalize column names using JSON_FIELD_MAP aliases
            rename_map = {}
            for col in df.columns:
                c_clean = str(col).strip().lower()
                if c_clean in JSON_FIELD_MAP:
                    rename_map[col] = JSON_FIELD_MAP[c_clean]
            df = df.rename(columns=rename_map)

            for _, row in df.iterrows():
                row_dict = row.to_dict()
                raw_line = ",".join(f"{k}={v}" for k, v in row_dict.items() if pd.notna(v))
                row_dict["raw_line"] = raw_line

                if "latency_ms" in row_dict and pd.notna(row_dict["latency_ms"]):
                    try:
                        row_dict["latency_ms"] = float(row_dict["latency_ms"])
                    except (ValueError, TypeError):
                        row_dict["latency_ms"] = None
                elif "message" in row_dict and isinstance(row_dict["message"], str):
                    row_dict["latency_ms"] = extract_latency(row_dict["message"])

                if ("request_id" not in row_dict or pd.isna(row_dict.get("request_id"))) and "message" in row_dict:
                    if isinstance(row_dict["message"], str):
                        row_dict["request_id"] = extract_request_id(row_dict["message"])

                records.append(row_dict)
        except Exception as e:
            logger.error(f"Failed to read CSV file {file_path}: {e}")
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        records.append({
                            "raw_line": line.strip(),
                            "parsing_error": f"CSV parse failure: {str(e)}",
                        })
        return records, total_lines

    def _parse_syslog(self, file_path: str) -> Tuple[List[Dict[str, Any]], int]:
        records: List[Dict[str, Any]] = []
        total_lines = 0
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                raw_line = line.strip()
                if not raw_line:
                    continue

                # Try ISO pattern first, then BSD syslog pattern
                m = SYSLOG_ISO_PATTERN.match(raw_line)
                if not m:
                    m = SYSLOG_BSD_PATTERN.match(raw_line)

                if m:
                    d = m.groupdict()
                    record = {
                        "timestamp": d.get("timestamp"),
                        "severity": d.get("severity"),
                        "source": d.get("source"),
                        "message": d.get("message"),
                        "request_id": d.get("request_id"),
                        "raw_line": raw_line,
                    }
                    # Extract latency from message if present
                    record["latency_ms"] = extract_latency(record["message"])
                    if not record["request_id"]:
                        record["request_id"] = extract_request_id(record["message"])
                    records.append(record)
                else:
                    # Could not parse syslog structure
                    records.append({
                        "raw_line": raw_line,
                        "parsing_error": "Unmatched syslog format",
                    })
        return records, total_lines
