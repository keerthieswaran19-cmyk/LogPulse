# LogPulse – AI Prompt & Engineering History

This document details how AI assistance was integrated into the engineering lifecycle of the **LogPulse** project for the YottaFlex AI Data Engineering challenge. It outlines the collaborative paradigm between AI generation and developer-led verification, architectural decisions, prompt summaries, debugging workflows, and testing validation.

---

## 1. Engineering Paradigm & Overview

The LogPulse pipeline was built using an advanced pair-programming workflow:
- **AI Coding Assistant**: Accelerated boilerplate scaffolding, algorithm implementations, regular expressions, test synthesis, and analytical SQL queries.
- **Developer Authority**: Directed architecture, defined quality criteria, enforced single-responsibility boundaries, executed live regression tests, and reviewed all generated artifacts for data engineering correctness.

---

## 2. AI-Assisted Architecture & Project Planning

### Prompt Summary (Phase 1 – Discovery & Scaffolding)
> *The developer provided the recruitment challenge specification and instructed the AI to inspect the empty repository, propose a professional project architecture, define table schemas and relationships, design idempotency and quarantine mechanisms, outline test scenarios, and wait for approval before coding.*

### AI Suggestions vs. Developer Decisions
- **AI Proposal**: Proposed a modular package structure under `src/` (`parser`, `normalizer`, `validator`, `dedup`, `loader`, `analytics`, `pipeline`, `generator`, `utils`), along with SQLite WAL mode and four relational tables (`log_events`, `quarantine`, `file_registry`, `pipeline_runs`).
- **Developer Review**: Approved the single-responsibility modular structure. Specifically required that idempotency rely on a deterministic SHA-256 record hash as the primary key rather than artificial auto-increment keys, ensuring natural deduplication via SQLite's B-tree index.

---

## 3. Core Pipeline Implementation & Prompt Summaries

### A. Parsing & Normalization
- **Summary**: Prompted to build a resilient parser supporting JSON, CSV, and Syslog logs with automatic format detection, latency extraction (`latency=250ms`, `duration=1.5s`), and request ID correlation.
- **Implementation**: Normalized timestamps from heterogeneous representations (ISO-8601, BSD syslog `Jan 15 10:30:00`, epoch seconds/milliseconds) to canonical UTC ISO-8601 strings. Standardized disparate severity aliases (`WARN`, `ERR`, `FATAL`, RFC 5424 levels 0–7) into `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`.

### B. Validation & Quarantine Routing
- **Summary**: Prompted to enforce schema integrity without allowing malformed rows to crash the pipeline.
- **Implementation**: `RecordValidator` tags failed records with descriptive `rejection_reason` metadata (e.g., `Missing required field: timestamp`, `Unrecognized severity`). Quarantined records are persisted to the SQLite `quarantine` table and exported to `data/quarantine/quarantine_<run_id>.csv` for dead-letter analysis.

### C. Multi-Tier Deduplication & SQLite Loader
- **Summary**: Prompted to guarantee safe, idempotent reruns across batch-level, file-level, and database-level boundaries.
- **Implementation**:
  1. *File-Level*: Checksums in `file_registry` skip unchanged files in `<0.05s`.
  2. *Batch-Level*: In-memory hash deduplication drops intra-batch duplicates.
  3. *Database-Level*: Parameterized `INSERT OR IGNORE INTO log_events` serves as the final safety net.

### D. Analytics Engine & Streamlit Dashboard
- **Summary**: Prompted to compute service-level error rates, SLA latency percentiles (P50, P95, P99), timeline trends, and render them in a 5-tab Streamlit dashboard.
- **Implementation**: Implemented vectorized NumPy/Pandas percentile calculations and parameterized SQL aggregations in `src/analytics/metrics.py`, rendered in `dashboard/app.py`.

---

## 4. Debugging Mixed Timestamp Formats

### Problem Encountered
When executing `get_volume_timeline()` in Pandas on a 93,340-record database containing mixed timestamp precisions (some rows with microsecond precision `2026-10-31T06:08:56.589441Z` and others without `2026-10-31T06:08:56Z`), Pandas raised:
```text
ValueError: time data "2026-10-31T06:08:56.589441Z" doesn't match format "%Y-%m-%dT%H:%M:%S%z"
```

### AI Assistance & Technical Solution
1. **Diagnosis**: Identified that Pandas' C-based `strptime` parser inferred a rigid format from the initial rows and rejected subsequent microsecond variations.
2. **Fix Implemented**:
   - Specified `format="ISO8601"` explicitly with `utc=True` and `errors="coerce"`.
   - Added fallback to `format="mixed"` for maximum cross-version compatibility.
   - Added safe null filtering (`df.dropna(subset=["dt"])`) so invalid timestamps are safely coerced to `NaT` rather than crashing the dashboard.
3. **Verification**: Successfully processed the entire 93,340-record dataset in **0.42 seconds** and confirmed with dedicated regression tests.

---

## 5. Test Creation & Edge-Case Resilience

### Prompt Summary
> *The developer requested dedicated automated tests for retry handling, partial file failures, interrupted processing, late/out-of-order timestamps, schema variations, empty batches, and repeated same-input reruns.*

### Test Suite Evolution
- **Initial Suite (26 tests)**: Unit tests for parsers, normalizers, validator, deduplicator, loader, and end-to-end integration.
- **Edge-Case Suite (+7 tests in `tests/test_edge_cases.py`)**:
  - `test_retry_handling_transient_failure`: Simulates transient I/O lock; verifies exponential backoff retry.
  - `test_partial_file_failure`: Verifies `status='PARTIAL'` when one file permanently fails while others succeed.
  - `test_interrupted_file_recovery_reprocess`: Verifies recovery of previously `FAILED` files upon rerun.
  - `test_late_and_out_of_order_timestamps`: Confirms chronological ordering across scrambled time windows.
  - `test_schema_variations_and_aliases`: Tests disparate keys (`@timestamp`, `log_level`, `app`, `msg`, `trace_id`).
  - `test_empty_files_and_empty_batches`: Verifies zero-byte files exit cleanly with 0 records loaded.
  - `test_repeated_same_input_reruns`: Verifies 3 consecutive reruns yield zero duplicate records.
- **Dashboard & Regression Suite (+7 tests)**: Added mixed-timestamp regression tests and startup auto-bootstrapping tests in `tests/test_dashboard_startup.py`.
- **Final Result**: **40 automated tests passing cleanly in ~8 seconds** (verified via pytest).

---

## 6. Streamlit Community Cloud Readiness & Auto-Bootstrapping

### Problem Encountered
Because `db/logpulse.db` (60 MB) is excluded from Git via `.gitignore`, a fresh clone on Streamlit Community Cloud (`share.streamlit.io`) starts with no database file. Accessing the dashboard would immediately fail with `sqlite3.OperationalError: no such table: log_events`.

### AI Assistance & Solution
- Developed `bootstrap_database()` in `dashboard/app.py`:
  1. Calls `DBLoader.init_db()` to create all 4 tables if missing.
  2. Queries `SELECT COUNT(*) FROM log_events`.
  3. If empty (cloud container), automatically discovers and ingests the git-tracked sample logs in `data/sample/` (`1,001` records processed in `~0.39s`).
  4. If non-empty (local environment with 93K records), skips ingestion completely, leaving existing data untouched.
  5. Idempotent across Streamlit page reruns and user interactions.

---

## 7. Developer Review & Verification Responsibilities

Every line of AI-generated code was subjected to hands-on developer verification:

1. **Mathematical Record Reconciliation**:
   $$\text{Loaded (93,340)} + \text{Quarantined (3,400)} + \text{Duplicates (3,260)} = 100,000 \text{ data records} + 1 \text{ header} = 100,001 \text{ raw lines}$$
   Reconciled table counters against file lines to guarantee zero uncounted or dropped records.
2. **Git & Security Audits**:
   - Manually inspected `git status --ignored` and `git diff --cached --name-only` to verify that `logpulse.db`, `.env` secrets, and generated raw files were never committed.
   - Replaced fragile LaTeX math expressions in documentation with universal inline code expressions for GitHub markdown rendering.
3. **Environment & Cross-Platform Testing**:
   - Fixed Windows batch script execution (`run_tests.bat`) by resolving directory anchoring (`cd /d "%~dp0"`) and removing cmd parser conflicts.

---

## 8. Limitations of AI Suggestions & How They Were Validated

| Scenario / Limitation | AI-Generated Suggestion | Problem Identified by Developer | Corrective Action Taken |
|---|---|---|---|
| **Foreign Key in Test Mock** | AI mocked single-file processing in a unit test without creating a `pipeline_runs` parent record. | Pytest failed with `sqlite3.IntegrityError: FOREIGN KEY constraint failed`. | Added explicit parent run initialization in test fixture before invoking child loaders. |
| **CSV Line Counting** | AI asserted `total_lines == 3` on a CSV file with 3 data rows. | `total_lines` reads raw lines including the CSV header, so actual count was 4. | Corrected assertion to account for header line count (`4 raw lines = 1 header + 3 data`). |
| **Windows Batch Execution** | AI used `setlocal enabledelayedexpansion` and omitted `cd /d "%~dp0"`. | Double-clicking the `.bat` file in Windows Explorer executed from the wrong directory and closed immediately. | Added directory anchoring and simplified error checks, verified with interactive execution. |
| **Pandas Mixed ISO Parsing** | AI initially used standard `pd.to_datetime(s, utc=True)`. | Raised `ValueError` on mixed microsecond timestamps in real database runs. | Replaced with `format="ISO8601"`, `utc=True`, `errors="coerce"` and fallback handling. |

---

### Conclusion
AI tooling acted as an effective engineering accelerator, reducing boilerplate time by ~70%. However, project correctness, schema integrity, idempotency guarantees, and test reliability were achieved through rigorous human validation, SQL reconciliation, and automated pytest execution.
