# LogPulse – Architecture Design & Engineering Rationale

## 1. Single Responsibility Principle (SRP)
The codebase divides pipeline stages into discrete, decoupled packages under `src/`:
- `parser`: Raw bytes/text extraction only
- `normalizer`: Format translation (temporal & levels)
- `validator`: Integrity rules & quarantine routing
- `dedup`: Hashing & uniqueness filtering
- `loader`: Persistence & schema ownership
- `analytics`: Metric queries & aggregations
- `pipeline`: Orchestration, fault-handling & retry loops

This clean modularity allowed 26 independent unit and integration tests to achieve full test coverage without mocking the entire system.

---

## 2. Cryptographic Record Hashing (`SHA-256`)
Instead of assigning arbitrary auto-increment IDs or random UUIDs as primary keys, each log record derives its identity deterministically:

$$\text{record\_hash} = \text{SHA-256}(\text{timestamp\_utc} \parallel \text{source} \parallel \text{message})$$

### Advantages:
- Enables `INSERT OR IGNORE` in SQLite for hardware-level deduplication.
- Safe across distributed workers or multi-pass runs.
- Does not change when the file is re-ingested.

---

## 3. Two-Tier Quarantine Strategy
When data quality validation fails, records are not silently dropped or allowed to crash the pipeline:
1. **SQLite `quarantine` table**: Allows instant queryability from the Streamlit UI.
2. **Audit CSV files (`data/quarantine/quarantine_<run_id>.csv`)**: Preserved on disk for downstream dead-letter queue replaying or human inspection.

---

## 4. File-Level and Record-Level Idempotency
- **Fast-path (File Checksum)**: If a 100,000-line file with unchanged SHA-256 checksum is rerun, the pipeline verifies `file_registry` and exits in `<0.05` seconds.
- **Granular-path (Record Hash)**: If an existing file receives append operations, previously ingested lines are skipped while novel lines are inserted.

---

## 5. Technology Stack Selection
- **Python 3.11 + Pandas**: High performance, vectorized data manipulation.
- **SQLite with WAL**: Zero-setup, embedded relational DB offering ACID guarantees and transaction isolation.
- **Pytest**: Industry standard test framework.
- **Streamlit**: Python-native analytical UI requiring zero JavaScript tooling.
