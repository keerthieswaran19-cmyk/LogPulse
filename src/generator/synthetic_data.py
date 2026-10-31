"""Scalable synthetic data generator for application logs."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import random
import uuid
from typing import Dict, List, Optional

from src.utils.db_utils import PROJECT_ROOT, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

SERVICES = [
    "auth-service",
    "api-gateway",
    "payment-service",
    "user-service",
    "notification-service",
    "order-service",
    "inventory-service",
    "search-service",
]

MESSAGES = {
    "INFO": [
        "User authenticated successfully",
        "HTTP request processed 200 OK | latency={latency}ms",
        "Token issued for user session",
        "Order checkout initialized",
        "Notification dispatched via email",
        "Cache hit for key user_profile",
        "Search query executed successfully | latency={latency}ms",
        "Inventory reserved for order",
    ],
    "DEBUG": [
        "Connection pool acquired connection",
        "Payload serialized to JSON",
        "Redis ping latency={latency}ms",
        "Parsing request headers",
        "Evaluating feature flag dark_launch_v2",
    ],
    "WARNING": [
        "Slow database query detected | latency={latency}ms",
        "Cache miss for query key, reading from primary replica",
        "Rate limit threshold approaching 80%",
        "Token expiring in 5 minutes",
        "Retry attempt 1 for upstream service",
    ],
    "ERROR": [
        "Database connection failed: timeout after 5000ms | latency={latency}ms",
        "Payment gateway declined transaction: Insufficient funds",
        "Upstream HTTP 503 Service Unavailable",
        "JSON decode failure in webhook payload",
        "Failed to write record to replica",
    ],
    "CRITICAL": [
        "Deadlock detected in transactional database cluster",
        "Security alert: Multiple failed admin authentication attempts detected",
        "Out of memory error in worker process",
        "Primary storage disk capacity exceeded 98%",
    ],
}


class SyntheticLogGenerator:
    """Generates realistic application logs with configurable anomalies and formats."""

    def __init__(
        self,
        services: Optional[List[str]] = None,
        error_ratio: float = 0.08,
        duplicate_ratio: float = 0.03,
        malformed_ratio: float = 0.02,
        seed: Optional[int] = 42,
    ) -> None:
        self.services = services or SERVICES
        self.error_ratio = error_ratio
        self.duplicate_ratio = duplicate_ratio
        self.malformed_ratio = malformed_ratio
        if seed is not None:
            random.seed(seed)

    def generate_records(
        self,
        count: int = 100000,
        start_time: Optional[datetime] = None,
        duration_hours: int = 24,
    ) -> List[Dict]:
        """Generate a list of structured log dictionaries."""
        logger.info(f"Generating {count} synthetic log records...")
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(hours=duration_hours)

        records: List[Dict] = []
        time_step = (duration_hours * 3600) / max(count, 1)

        # Pre-generate duplicate candidates
        num_duplicates = int(count * self.duplicate_ratio)
        num_malformed = int(count * self.malformed_ratio)
        standard_count = count - num_duplicates - num_malformed

        for i in range(standard_count):
            curr_time = start_time + timedelta(seconds=i * time_step + random.uniform(-1, 1))

            # Decide severity
            is_err = random.random() < self.error_ratio
            if is_err:
                sev = random.choices(["ERROR", "CRITICAL"], weights=[0.85, 0.15])[0]
                latency = round(random.uniform(500, 3500), 2)
            else:
                sev = random.choices(["INFO", "DEBUG", "WARNING"], weights=[0.70, 0.15, 0.15])[0]
                latency = round(random.uniform(15, 450), 2)

            service = random.choice(self.services)
            msg_tmpl = random.choice(MESSAGES[sev])
            message = msg_tmpl.format(latency=latency)
            req_id = f"req-{uuid.uuid4().hex[:8]}"

            # Timestamp formats variety
            ts_choice = random.random()
            if ts_choice < 0.7:
                ts_str = curr_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            elif ts_choice < 0.85:
                ts_str = curr_time.strftime("%Y-%m-%d %H:%M:%S")
            elif ts_choice < 0.95:
                ts_str = curr_time.strftime("%b %d %H:%M:%S")
            else:
                ts_str = str(int(curr_time.timestamp() * 1000))

            records.append({
                "timestamp": ts_str,
                "severity": sev,
                "source": service,
                "message": message,
                "latency_ms": latency,
                "request_id": req_id,
            })

        # Inject deliberate duplicates
        if records and num_duplicates > 0:
            for _ in range(num_duplicates):
                duplicate_rec = dict(random.choice(records[:1000]))
                records.append(duplicate_rec)

        # Inject deliberate anomalies/malformed records
        for j in range(num_malformed):
            anomaly_type = random.choice([
                "invalid_timestamp",
                "missing_source",
                "invalid_severity",
                "empty_message",
                "corrupted_syntax",
            ])
            if anomaly_type == "invalid_timestamp":
                records.append({
                    "timestamp": "not-a-valid-date-format",
                    "severity": "INFO",
                    "source": random.choice(self.services),
                    "message": "Transaction failed with unparseable date",
                    "latency_ms": 120.0,
                    "request_id": f"req-err-{j}",
                })
            elif anomaly_type == "missing_source":
                records.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "WARNING",
                    "source": None,
                    "message": "Missing component service identifier",
                    "latency_ms": 80.0,
                    "request_id": f"req-err-{j}",
                })
            elif anomaly_type == "invalid_severity":
                records.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "UNKNOWN_CUSTOM_LEVEL",
                    "source": "auth-service",
                    "message": "Custom telemetry metric emitted",
                    "latency_ms": 45.0,
                    "request_id": f"req-err-{j}",
                })
            elif anomaly_type == "empty_message":
                records.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "INFO",
                    "source": "api-gateway",
                    "message": "",
                    "latency_ms": 30.0,
                    "request_id": f"req-err-{j}",
                })
            else:
                records.append({
                    "raw_corrupted_line": ":::CORRUPTED_STREAM_BYTE_CHUNK_9999:::",
                    "timestamp": None,
                    "severity": None,
                    "source": None,
                    "message": None,
                })

        random.shuffle(records)
        logger.info(
            f"Generated total {len(records)} records: "
            f"{standard_count} clean, {num_duplicates} duplicates, {num_malformed} malformed"
        )
        return records

    def write_to_file(self, records: List[Dict], output_path: str, fmt: str = "json") -> str:
        """Write records to file in JSON, CSV, or Syslog format."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        fmt = fmt.lower()
        if fmt == "json":
            with open(path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
        elif fmt == "csv":
            import pandas as pd
            df = pd.DataFrame(records)
            df.to_csv(path, index=False)
        else:  # syslog
            with open(path, "w", encoding="utf-8") as f:
                for r in records:
                    if "raw_corrupted_line" in r:
                        f.write(r["raw_corrupted_line"] + "\n")
                    else:
                        ts = r.get("timestamp") or "2024-01-15T12:00:00Z"
                        sev = r.get("severity") or "INFO"
                        src = r.get("source") or "unknown-service"
                        req = f"[{r['request_id']}] " if r.get("request_id") else ""
                        msg = r.get("message") or ""
                        f.write(f"{ts} {sev} {src} {req}{msg}\n")

        logger.info(f"Wrote {len(records)} records to {path.resolve()} ({fmt})")
        return str(path.resolve())


def main():
    parser = argparse.ArgumentParser(description="LogPulse Synthetic Log Generator")
    parser.add_argument("--records", type=int, default=100000, help="Number of records (default: 100000)")
    parser.add_argument("--output-dir", type=str, default="data/raw", help="Output directory")
    parser.add_argument("--format", type=str, choices=["json", "csv", "syslog", "mixed"], default="json")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir

    generator = SyntheticLogGenerator(seed=args.seed)

    if args.format == "mixed":
        # Split into 3 files of different formats
        part_count = args.records // 3
        r_json = generator.generate_records(count=part_count)
        generator.write_to_file(r_json, str(out_dir / "logs_part1.json"), fmt="json")

        r_csv = generator.generate_records(count=part_count)
        generator.write_to_file(r_csv, str(out_dir / "logs_part2.csv"), fmt="csv")

        r_syslog = generator.generate_records(count=args.records - (2 * part_count))
        generator.write_to_file(r_syslog, str(out_dir / "logs_part3.log"), fmt="syslog")
    else:
        ext = "json" if args.format == "json" else ("csv" if args.format == "csv" else "log")
        records = generator.generate_records(count=args.records)
        generator.write_to_file(records, str(out_dir / f"synthetic_logs_{args.records}.{ext}"), fmt=args.format)


if __name__ == "__main__":
    main()
