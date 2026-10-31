# LogPulse – Technical Design Decisions & Architecture Rationale

This document outlines the architectural and engineering decisions made during the design and implementation of LogPulse, contextualized for a professional Data Engineering recruitment solution.

---

## 1. Single Responsibility Modular Architecture

### Decision
Partition the codebase into single-responsibility packages under `src/`:
- `parser/`: Format detection and text-to-dict extraction only.
- `normalizer/`: Pure functional transformations (timestamps and severities).
- `validator/`: Schema validation rules and quarantine tagging.
- `dedup/`: Record hashing and duplicate suppression.
- `loader/`: Database table management, parameterized SQL upserts, and file registry.
- `analytics/`: Analytical SQL aggregations, percentiles, and SLA metrics.
- `pipeline/`: Orchestration, exponential backoff retries, and run tracking.
- `generator/`: High-throughput synthetic data generation.
- `utils/`: Structured logging, database context managers, and execution metrics.

### Rationale
- Decouples parsing from validation and database persistence, allowing each stage to be unit-tested in complete isolation.
- Matches standard enterprise data pipeline patterns (Extract → Transform/Normalize → Validate → Cleanse → Load).
- Enables new log formats or database targets to be introduced without touching existing normalizer or analytics logic.

---

## 2. Deterministic SHA-256 Record Hashing for Idempotency

### Decision
Primary keys in `log_events` are not auto-increment integers or random UUIDs. Instead, each log row derives its unique key deterministically:

$$\text{record\_hash} = \text{SHA-256}(\text{timestamp\_utc} \parallel \text{source} \parallel \text{message})$$

### Rationale
- **Deterministic Identity**: Identical events parsed from different files or re-ingested in recurring runs consistently produce the same 64-character hex hash.
- **Hardware-Level Idempotency**: Inserting records via `INSERT OR IGNORE INTO log_events ...` delegates deduplication to the SQLite B-tree unique index on `record_hash`.
- **Zero Collision Risk**: SHA-256 provides collision resistance far exceeding operational requirements for large-scale application telemetry.

---

## 3. Multi-Tier Idempotency & Duplicate Suppression

### Decision
Implement three complementary layers of duplicate prevention:

1. **File-Level (Checksum Fast-Path)**:
   - Before parsing, the orchestrator computes the file's SHA-256 checksum and queries `file_registry`.
   - If the file was previously processed with status `COMPLETED` and identical checksum, it is skipped instantly (`~0.03s`), avoiding redundant disk I/O and CPU parsing.
2. **Batch-Level (In-Memory Dedup)**:
   - Incoming records are deduplicated in memory using `df.drop_duplicates(subset=['record_hash'])`, reducing database write load.
3. **Database-Level (Cross-Batch Dedup)**:
   - Records are cross-checked against existing DB hashes and inserted using `INSERT OR IGNORE`.

---

## 4. Two-Tier Quarantine Pattern

### Decision
Invalid or malformed records do not fail the pipeline or get dropped silently. They are tagged with detailed `rejection_reason` strings and routed to:
1. The **`quarantine` table** in SQLite: Facilitates real-time querying, aggregation, and visibility in the Streamlit UI.
2. An **audit CSV file** (`data/quarantine/quarantine_<run_id>.csv`): Preserves unparsed or corrupted records on disk for dead-letter analysis.

### Rationale
- Production pipelines must be resilient to dirty data. A single corrupted log line must never halt batch ingestion of 100,000 valid events.
- Audit trails enable data source owners to inspect root causes (e.g., misconfigured logging libraries or date formats).

---

## 5. Technology Stack Selection

| Technology | Selection | Alternative Considered | Rationale |
|---|---|---|---|
| **Language** | Python 3.11 | Go / Scala | Rich ecosystem for data processing (`pandas`, `sqlite3`, `dateutil`), highly accessible for 0–3 YOE DE role. |
| **DataFrames** | Pandas 2.0+ | Polars / PySpark | Standard in DE challenges; zero JVM overhead; vectorized performance handles 100K records in seconds. |
| **Database** | SQLite (WAL mode) | PostgreSQL / MySQL | Self-contained, zero-configuration file database; supports standard SQL and index optimization without external daemon setup. |
| **Testing** | Pytest | Unittest | Modern fixtures, parameterized test runs, concise assertions, clean CLI reports. |
| **Visualization**| Streamlit | Dash / Grafana | Pure Python dashboarding; renders KPI cards, time-series, and percentile breakdowns directly from database queries. |

---

## 6. Timestamp & Severity Standardization

### Decision
- **Timestamps**: All valid timestamps (ISO-8601, BSD syslog `Jan 15 10:30:00`, epoch seconds, epoch milliseconds) are converted to canonical UTC ISO-8601 strings (`YYYY-MM-DDTHH:MM:SSZ` or `.fffZ`). Naive timestamps are interpreted as UTC.
- **Severities**: All non-standard aliases (`WARN`, `ERR`, `FATAL`, `TRACE`, RFC 5424 numerical priorities 0–7) map to five canonical levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
