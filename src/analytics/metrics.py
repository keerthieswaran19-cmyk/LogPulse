"""Analytics module – error rates, latency percentiles, and aggregation queries."""

from typing import Any, Dict, Optional
import numpy as np
import pandas as pd

from src.utils.db_utils import get_connection, get_db_path
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsEngine:
    """Executes analytical aggregations and computes metrics over ingested log data."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or get_db_path()

    def get_overall_summary(self) -> Dict[str, Any]:
        """Compute high-level summary of all logs in the database."""
        with get_connection(self.db_path) as conn:
            total_logs = conn.execute("SELECT COUNT(*) FROM log_events").fetchone()[0]
            if total_logs == 0:
                return {
                    "total_logs": 0,
                    "error_count": 0,
                    "error_rate_pct": 0.0,
                    "avg_latency_ms": 0.0,
                    "p50_latency_ms": 0.0,
                    "p95_latency_ms": 0.0,
                    "p99_latency_ms": 0.0,
                    "quarantined_count": 0,
                }

            error_count = conn.execute(
                "SELECT COUNT(*) FROM log_events WHERE severity IN ('ERROR', 'CRITICAL')"
            ).fetchone()[0]

            quar_count = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]

            # Latency calculations
            df_lat = pd.read_sql_query(
                "SELECT latency_ms FROM log_events WHERE latency_ms IS NOT NULL", conn
            )

            if not df_lat.empty and len(df_lat) > 0:
                latencies = df_lat["latency_ms"].dropna()
                avg_lat = float(latencies.mean())
                p50 = float(np.percentile(latencies, 50))
                p95 = float(np.percentile(latencies, 95))
                p99 = float(np.percentile(latencies, 99))
            else:
                avg_lat = p50 = p95 = p99 = 0.0

            error_rate = (error_count / total_logs) * 100.0 if total_logs > 0 else 0.0

            return {
                "total_logs": total_logs,
                "error_count": error_count,
                "error_rate_pct": round(error_rate, 2),
                "avg_latency_ms": round(avg_lat, 2),
                "p50_latency_ms": round(p50, 2),
                "p95_latency_ms": round(p95, 2),
                "p99_latency_ms": round(p99, 2),
                "quarantined_count": quar_count,
            }

    def get_error_rates_by_service(self) -> pd.DataFrame:
        """Calculate total logs, error logs, and error rate percentage grouped by service."""
        query = """
        SELECT
            source AS service,
            COUNT(*) AS total_logs,
            SUM(CASE WHEN severity IN ('ERROR', 'CRITICAL') THEN 1 ELSE 0 END) AS error_logs,
            ROUND(
                CAST(SUM(CASE WHEN severity IN ('ERROR', 'CRITICAL') THEN 1 ELSE 0 END) AS REAL) * 100.0 / COUNT(*),
                2
            ) AS error_rate_pct
        FROM log_events
        GROUP BY source
        ORDER BY error_rate_pct DESC, total_logs DESC
        """
        with get_connection(self.db_path) as conn:
            return pd.read_sql_query(query, conn)

    def get_latency_by_service(self) -> pd.DataFrame:
        """Compute latency percentiles (p50, p95, p99, mean, max) per service."""
        query = "SELECT source AS service, latency_ms FROM log_events WHERE latency_ms IS NOT NULL"
        with get_connection(self.db_path) as conn:
            df = pd.read_sql_query(query, conn)

        if df.empty:
            return pd.DataFrame(
                columns=["service", "count", "mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"]
            )

        def calc_stats(group: pd.Series) -> pd.Series:
            arr = group.dropna().values
            if len(arr) == 0:
                return pd.Series({"count": 0, "mean_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "max_ms": 0})
            return pd.Series({
                "count": int(len(arr)),
                "mean_ms": round(float(np.mean(arr)), 2),
                "p50_ms": round(float(np.percentile(arr, 50)), 2),
                "p95_ms": round(float(np.percentile(arr, 95)), 2),
                "p99_ms": round(float(np.percentile(arr, 99)), 2),
                "max_ms": round(float(np.max(arr)), 2),
            })

        result = df.groupby("service")["latency_ms"].apply(calc_stats).unstack().reset_index()
        return result.sort_values(by="p95_ms", ascending=False)

    def get_severity_distribution(self) -> pd.DataFrame:
        """Count and percentage distribution of log records by severity."""
        query = """
        SELECT
            severity,
            COUNT(*) AS count,
            ROUND(CAST(COUNT(*) AS REAL) * 100.0 / (SELECT COUNT(*) FROM log_events), 2) AS percentage
        FROM log_events
        GROUP BY severity
        ORDER BY count DESC
        """
        with get_connection(self.db_path) as conn:
            return pd.read_sql_query(query, conn)

    def get_top_error_messages(self, limit: int = 10) -> pd.DataFrame:
        """Find the most frequently occurring error/critical messages."""
        query = """
        SELECT
            source AS service,
            message,
            COUNT(*) AS occurrences,
            MAX(timestamp_utc) AS last_seen
        FROM log_events
        WHERE severity IN ('ERROR', 'CRITICAL')
        GROUP BY source, message
        ORDER BY occurrences DESC
        LIMIT ?
        """
        with get_connection(self.db_path) as conn:
            return pd.read_sql_query(query, conn, params=(limit,))

    def get_volume_timeline(self, freq: str = "1h") -> pd.DataFrame:
        """Group log volume and errors over time for trend charts."""
        query = "SELECT timestamp_utc, severity, source FROM log_events"
        with get_connection(self.db_path) as conn:
            df = pd.read_sql_query(query, conn)

        if df.empty:
            return pd.DataFrame(columns=["dt", "total", "errors", "error_rate_pct"])

        # Robust ISO-8601 parsing supporting fractional seconds, trailing Z, and timezone offsets
        try:
            df["dt"] = pd.to_datetime(
                df["timestamp_utc"], format="ISO8601", utc=True, errors="coerce"
            )
        except Exception:
            df["dt"] = pd.to_datetime(
                df["timestamp_utc"], format="mixed", utc=True, errors="coerce"
            )

        # Safely drop any unparseable timestamps to prevent dashboard crash
        df = df.dropna(subset=["dt"]).copy()
        if df.empty:
            return pd.DataFrame(columns=["dt", "total", "errors", "error_rate_pct"])

        df["is_error"] = df["severity"].isin(["ERROR", "CRITICAL"]).astype(int)

        grouped = df.set_index("dt").resample(freq).agg(
            total=("severity", "count"),
            errors=("is_error", "sum")
        ).reset_index()

        grouped["error_rate_pct"] = (grouped["errors"] / grouped["total"].replace(0, 1)) * 100.0
        grouped["error_rate_pct"] = grouped["error_rate_pct"].round(2)
        return grouped

    def get_quarantine_reasons(self) -> pd.DataFrame:
        """Analyze quarantine rejection reasons and counts."""
        query = """
        SELECT
            rejection_reason,
            COUNT(*) AS count,
            ROUND(CAST(COUNT(*) AS REAL) * 100.0 / (SELECT COUNT(*) FROM quarantine), 2) AS percentage
        FROM quarantine
        GROUP BY rejection_reason
        ORDER BY count DESC
        """
        with get_connection(self.db_path) as conn:
            return pd.read_sql_query(query, conn)

    def get_pipeline_runs_history(self) -> pd.DataFrame:
        """Retrieve execution history for all pipeline runs."""
        query = """
        SELECT
            run_id,
            started_at,
            completed_at,
            status,
            total_files,
            files_processed,
            total_records,
            records_loaded,
            records_quarantined,
            records_duplicated,
            duration_seconds
        FROM pipeline_runs
        ORDER BY started_at DESC
        """
        with get_connection(self.db_path) as conn:
            return pd.read_sql_query(query, conn)
