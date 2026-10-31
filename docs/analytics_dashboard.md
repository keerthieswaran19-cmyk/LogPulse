# LogPulse – Analytics & Dashboard Reference

## Overview

The LogPulse Streamlit dashboard (`dashboard/app.py`) provides real-time visibility into pipeline throughput, application error rates, service latency distributions, data quality quarantine records, and execution lineage.

---

## Launching the Dashboard

```bash
streamlit run dashboard/app.py
```

The application will bind locally (typically at `http://localhost:8501`).

---

## Dashboard Capabilities

### 1. Executive KPIs
- **Total Logs Loaded**: Cumulative count of processed, deduplicated, and stored records.
- **Total Errors**: Count of logs classified under `ERROR` or `CRITICAL`.
- **Overall Error Rate (%)**: Percentage of error logs across all services.
- **Average Latency**: Mean latency extracted across log messages.
- **Quarantined Count**: Total malformed records safely isolated from analytics.

### 2. Tab 1: Volume & Trends
- **Log Volume & Error Trends**: Time-series charts visualizing log throughput vs error spikes over configurable intervals (1h, 30m, 15m).
- **Severity Breakdown**: Distribution table and bar chart across `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.

### 3. Tab 2: Service Analytics
- **Service Error Rates**: Table and bar chart ranking services by highest error percentages.
- **Top Error Messages**: Frequency analysis of the most recurring error signatures, identifying top offenders and when they were last seen.

### 4. Tab 3: Latency Profiling
- **Service Percentiles**: Comprehensive SLA tracking displaying `count`, `mean_ms`, `p50_ms`, `p95_ms`, `p99_ms`, and `max_ms` per microservice.
- **Percentile Comparison**: Multi-metric bar charts highlighting latency degradation.

### 5. Tab 4: Quarantine Inspector
- **Rejection Breakdown**: Classification of quarantine causes (e.g., `Missing required field: timestamp`, `Unrecognized severity`, `JSON decode failure`).
- **Audit Viewer**: Raw log view of the last 50 quarantined records for root cause analysis.

### 6. Tab 5: Pipeline Execution Runs
- **Run History**: Table of previous batch runs displaying `status`, `total_files`, `records_loaded`, `records_quarantined`, `records_duplicated`, and `duration_seconds`.
