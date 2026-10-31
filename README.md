# ⚡ LogPulse – Application Log Analytics Pipeline

LogPulse is an end-to-end, production-grade Python data engineering pipeline that ingests, parses, normalizes, validates, deduplicates, and loads structured and semi-structured application logs into SQLite, providing error-rate and latency analytics with an interactive Streamlit dashboard.

---

## 🏗️ Architecture & Data Flow

```
[Raw Logs: JSON / CSV / Syslog]
             │
             ▼
      [LogParser] ───────────── Auto-detects format, extracts fields, request IDs & latencies
             │
             ▼
   [RecordValidator] ────────── Schema checks, UTC normalization, canonical severity mapping
        │         │
(Valid) │         │ (Invalid)
        │         └───────────► [Quarantine Table & CSV Audit File]
        ▼
   [Deduplicator] ───────────── SHA-256 hash deduplication (in-batch & against DB)
        │
        ▼
    [DBLoader] ──────────────── Idempotent SQLite upserts (INSERT OR IGNORE)
        │
        ├─────────────────────► [SQLite log_events]
        ├─────────────────────► [File Registry (Idempotency Tracking)]
        └─────────────────────► [Pipeline Run Execution Metrics]
             │
             ▼
   [Analytics & Dashboard] ──── Error rates, P50/P95/P99 latency, Streamlit UI
```

---

## 🚀 Key Features

- **Multi-Format Parsing**: Automatically identifies and parses JSON, CSV, and Syslog format logs, extracting embedded request IDs and latency values.
- **Normalization Engine**: Converts arbitrary timestamp formats (ISO-8601, BSD syslog, Unix epoch seconds/milliseconds) to normalized UTC ISO strings; unifies severity levels to `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`.
- **Validation & Quarantine Routing**: Strict data quality checks isolate malformed or incomplete records into a dedicated `quarantine` table and CSV exports without halting the pipeline.
- **Idempotency & Deduplication**:
  - **File-level idempotency**: Checks file content SHA-256 in `file_registry` to skip redundant processing.
  - **Record-level deduplication**: SHA-256 hashes generated from core event fields prevent duplicate storage both in-batch and across runs.
  - **Database safety**: SQLite primary key on `record_hash` with `INSERT OR IGNORE`.
- **Fault Tolerance & Retries**: Per-file retry logic with exponential backoff for transient failures.
- **Scalable Synthetic Generator**: Capable of generating 100,000+ realistic log records with controlled anomaly and duplicate injection in seconds.
- **Analytics & Dashboard**: Interactive Streamlit UI featuring service error rates, P50/P95/P99 latency charts, quarantine inspector, and pipeline execution logs.

---

## 📁 Repository Structure

```
LogPulse/
├── config/
│   └── pipeline_config.yaml         # Configurable parameters (batch sizes, retries, thresholds)
├── dashboard/
│   └── app.py                       # Streamlit analytics dashboard
├── data/
│   ├── raw/                         # Inbound raw logs
│   ├── quarantine/                  # Quarantined records and audit CSVs
│   └── sample/                      # Sample datasets for quick demo
├── db/
│   └── logpulse.db                  # SQLite database (auto-created)
├── src/
│   ├── parser/                      # JSON, CSV, and Syslog parsers
│   ├── normalizer/                  # Timestamp and severity normalizers
│   ├── validator/                   # Data quality and quarantine router
│   ├── dedup/                       # SHA-256 deduplication
│   ├── loader/                      # SQLite table initialization and loaders
│   ├── analytics/                   # Analytics aggregations and percentiles
│   ├── pipeline/                    # Orchestrator with retries
│   ├── generator/                   # 100K+ synthetic log generator
│   └── utils/                       # Logging, DB context managers, metrics
├── tests/                           # Complete test suite (unit, integration, e2e)
├── Makefile                         # CLI shortcuts
├── requirements.txt                 # Dependencies
└── pyproject.toml                   # Project configuration
```

---

## 🛠️ Getting Started

### 1. Prerequisites & Installation

```bash
# Clone and navigate to project root
cd d:\Yotta\LogPulse

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Scalable Synthetic Data (100,000+ records)

Generate 100,000 synthetic log records across JSON, CSV, and Syslog formats with injected duplicates and anomalies:

```bash
python -m src.generator.synthetic_data --records 100000 --format mixed --output-dir data/raw
```

### 3. Run the Data Pipeline

Run the ingestion orchestrator to process all files in `data/raw`:

```bash
python -m src.pipeline.orchestrator
```

### 4. Run Automated Tests

Execute the comprehensive test suite:

```bash
python -m pytest tests -v
```

### 5. Launch the Analytics Dashboard

```bash
streamlit run dashboard/app.py
```

---

## 📊 Database Schema

- **`log_events`**: Main fact table containing normalized log records.
  - `record_hash` (TEXT, PRIMARY KEY): SHA-256(`timestamp_utc|source|message`)
  - `timestamp_utc` (TEXT), `severity` (TEXT), `source` (TEXT), `message` (TEXT)
  - `latency_ms` (REAL), `request_id` (TEXT), `source_file` (TEXT), `pipeline_run_id` (TEXT)
- **`quarantine`**: Stores rejected records with specific `rejection_reason`.
- **`file_registry`**: Ingestion ledger tracking processed file paths, SHA-256 hashes, status, and record counts for idempotency.
- **`pipeline_runs`**: High-level execution metrics (start/end time, counts loaded, quarantined, duplicates, wall-clock duration).
