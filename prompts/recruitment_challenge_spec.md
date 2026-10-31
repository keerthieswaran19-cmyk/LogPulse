# LogPulse – Recruitment Challenge Specification

## Project Name
**LogPulse – Application Log Analytics Pipeline**

## Context
Data Engineering recruitment challenge for YottaFlex AI.

## Candidate Profile Level
0–3 years of Data Engineering experience. Emphasis placed on correctness, data quality, test automation, idempotency, and clear documentation over excessive complexity.

---

## Core Requirements & Deliverables

1. **Structured & Semi-Structured Parsing**:
   - Parse JSON, CSV, and Syslog format logs.
   - Extract timestamps, severity levels, microservice sources, message bodies, request/correlation IDs, and request response times (latency).

2. **Normalization**:
   - Standardize all timestamps into UTC ISO-8601 strings (`YYYY-MM-DDTHH:MM:SSZ`).
   - Map diverse log severity aliases (`WARN`, `ERR`, `FATAL`, syslog numeric codes) to canonical levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

3. **Data Quality & Quarantine**:
   - Validate mandatory schema fields (`timestamp`, `severity`, `source`, `message`).
   - Segregate malformed or invalid records into a dedicated `quarantine` table and audit CSV export with explicit rejection reasons.

4. **Idempotency & Deduplication**:
   - Compute deterministic SHA-256 hash for each record: `sha256(timestamp_utc|source|message)`.
   - Prevent duplicate storage within batches and across recurring executions.
   - Support safe, repeated pipeline reruns via file content SHA-256 checks in `file_registry`.

5. **Analytics & Metrics**:
   - Error-rate analytics per service and across time windows.
   - Latency distribution metrics (P50, P95, P99, mean, max).
   - Execution metrics for pipeline runs (runtime, records parsed, loaded, quarantined, duplicates).

6. **Scalable Synthetic Generator**:
   - Scalable generator producing 100,000+ realistic records across JSON, CSV, and Syslog.
   - Controlled anomaly and duplicate injection for pipeline stress testing.

7. **Interactive Dashboard**:
   - Streamlit analytics UI providing KPI cards, trend charts, percentile tables, quarantine inspection, and run history.

8. **Test Automation & Quality**:
   - Automated Pytest test suite testing all units, loader integrations, analytics queries, and end-to-end idempotency.
