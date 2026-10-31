# ⚡ LogPulse – Application Log Analytics Pipeline

LogPulse is a modular, fully working Python data engineering pipeline that ingests, parses, normalizes, validates, deduplicates, and loads structured and semi-structured application logs into SQLite, generating error-rate and latency analytics with an interactive Streamlit dashboard.

Built as a submission for the YottaFlex AI Data Engineering recruitment challenge.

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
     [DBLoader] ─────────────── Idempotent SQLite inserts using INSERT OR IGNORE
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
- **Normalization Engine**: Converts arbitrary timestamp formats (ISO-8601, BSD syslog, Unix epoch seconds/milliseconds) to normalized UTC ISO-8601 strings; standardizes severity levels to canonical `{DEBUG, INFO, WARNING, ERROR, CRITICAL}`.
- **Validation & Quarantine Routing**: Enforces required schema fields; isolates invalid or corrupted records into a dedicated `quarantine` table and CSV exports without stopping pipeline execution.
- **Idempotency & Deduplication**:
  - **File-level idempotency**: Checks file content SHA-256 in `file_registry` to skip already-processed files in milliseconds.
  - **Record-level deduplication**: Deterministic SHA-256 hashes generated from core event fields prevent duplicate storage both in-batch and across runs.
  - **Database-level safety**: Enforces uniqueness via SQLite primary key on `record_hash` with idempotent SQLite inserts using `INSERT OR IGNORE`.
- **Fault Tolerance & Retries**: Per-file retry logic with exponential backoff for transient failures; records partial-run statuses when individual files fail.
- **Scalable Synthetic Generator**: Generates 100,000+ realistic log records with controlled anomaly and duplicate injection in seconds.
- **Analytics & Dashboard**: Interactive Streamlit UI featuring service error rates, P50/P95/P99 latency distributions, quarantine inspector, and pipeline execution logs.

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

## 🛠️ Environment Setup

### 1. Clone Repository and Navigate to Root

```bash
git clone https://github.com/keerthieswaran19-cmyk/LogPulse.git
```

```bash
cd LogPulse
```

### 2. Create and Activate a Virtual Environment

#### On Windows (PowerShell):

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
```

*(Or in Windows Command Prompt: `.venv\Scripts\activate.bat`)*

#### On Linux / macOS:

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🎬 End-to-End Demo Instructions

Follow these three steps to run a complete demonstration:

### Step 1: Generate Input Data

You can either use the pre-built sample dataset in `data/sample/`, or generate a full 100,000+ synthetic log workload across mixed formats:

```bash
python -m src.generator.synthetic_data --records 100000 --format mixed --output-dir data/raw
```

*(To run a quick 1,000-record demo instead, pass `--records 1000`)*

### Step 2: Run the Ingestion Pipeline

Execute the orchestrator to discover, validate, deduplicate, and ingest logs:

```bash
python -m src.pipeline.orchestrator
```

### Step 3: Launch the Analytics Dashboard

Start the Streamlit dashboard in your browser:

```bash
streamlit run dashboard/app.py
```

The dashboard will open at `http://localhost:8501`, displaying live KPI cards, error rates by service, P50/P95/P99 latency percentiles, quarantine logs, and pipeline execution history.

---

## 🧪 Automated Testing

LogPulse includes 40 automated tests covering parser format detection, normalizers, schema validation, quarantine routing, deduplication, SQLite loader idempotency, analytics queries, dashboard auto-bootstrapping, and edge cases (retries, partial failures, out-of-order timestamps, schema aliases, empty files, and repeated reruns).

Run the full test suite with verbose output:

```bash
python -m pytest tests -v
```

---

## 📊 Verified Pipeline Execution & Reconciliation

The pipeline was verified on a synthetic dataset of **100,001 raw lines** across JSON, CSV, and Syslog formats. Below are the verified metrics recorded in `pipeline_runs` and `file_registry`:

### Execution Summary Metrics

| Metric | Verified Result | Details |
|---|---|---|
| **Raw Lines Processed** | `100,001` | 33,333 JSON + 33,334 CSV (incl. header) + 33,334 Syslog |
| **Successfully Loaded** | `93,340` | Inserted into `log_events` |
| **Quarantined Records** | `3,400` | Diverted to `quarantine` table & audit CSV |
| **Duplicates Filtered** | `3,260` | 3,065 in-batch duplicates + 195 cross-DB duplicates |
| **Wall-Clock Duration** | `33.2s` | ~3,000 records/second throughput |
| **Run Status** | `SUCCESS` | All 3 files processed without fatal errors |

### Record Reconciliation Formula

```text
Loaded (93,340) + Quarantined (3,400) + Duplicates (3,260) = 100,000 data records + 1 CSV header = 100,001 raw lines
```

### Idempotent Rerun Verification

Re-running the pipeline on the identical raw files completed in **0.035 seconds**:
- SHA-256 file checksum matched `COMPLETED` entry in `file_registry`.
- Files were safely skipped.
- Exactly **0 duplicate rows** were inserted into `log_events`.

---

## 🗄️ Database Schema & Record Hashing

SQLite tables are configured with WAL (Write-Ahead Logging) and enforced foreign keys:

- **`log_events`**: Main fact table containing normalized log records.
  - `record_hash` (`TEXT PRIMARY KEY`): Deterministic hash computed strictly via `SHA-256(timestamp_utc + "|" + source + "|" + message)` (as implemented in [`src/dedup/deduplicator.py`](src/dedup/deduplicator.py)).
  - `timestamp_utc` (`TEXT`), `severity` (`TEXT`), `source` (`TEXT`), `message` (`TEXT`)
  - `latency_ms` (`REAL`, nullable), `request_id` (`TEXT`, nullable), `raw_line` (`TEXT`), `source_file` (`TEXT`), `pipeline_run_id` (`TEXT`), `created_at` (`TEXT`)
- **`quarantine`**: Stores rejected records with explicit `rejection_reason` and original `raw_line`.
- **`file_registry`**: Ingestion ledger tracking processed file paths, SHA-256 content hashes, status, and record counts for file-level idempotency.
- **`pipeline_runs`**: Execution metrics auditing run duration, record counts, and status (`SUCCESS`, `PARTIAL`, `FAILED`, `RUNNING`).
