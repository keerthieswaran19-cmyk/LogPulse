# LogPulse – Operations & Pipeline Guide

## 1. Setup & Environment

Ensure Python 3.9+ is available. Clone the repository and install dependencies:

```bash
cd D:\Yotta\LogPulse
pip install -r requirements.txt
```

Environment settings can be customized in `.env` (refer to `.env.example`).

---

## 2. Ingestion Pipeline Execution

The ingestion engine can be run directly via the CLI:

```bash
python -m src.pipeline.orchestrator
```

### Discovery & Processing Logic
- The orchestrator searches `data/raw/` for supported files (`.json`, `.jsonl`, `.csv`, `.log`, `.txt`).
- Computes SHA-256 hash for each file.
- Checks the `file_registry` table in `db/logpulse.db`. If a file has already been ingested with an identical checksum, it is skipped in `0.03s`.
- Parses valid records, extracts latency and request IDs, standardizes time and severity, validates fields, strips duplicates, and loads to SQLite.
- Quarantined records are written both to SQLite `quarantine` and exported as CSV files in `data/quarantine/`.

---

## 3. Synthetic Data Generation

LogPulse includes a generator capable of outputting 100,000+ records in seconds:

```bash
# Generate 100,000 records across mixed formats (JSON, CSV, Syslog)
python -m src.generator.synthetic_data --records 100000 --format mixed --output-dir data/raw

# Generate pure JSON
python -m src.generator.synthetic_data --records 50000 --format json --output-dir data/raw

# Generate pure CSV
python -m src.generator.synthetic_data --records 50000 --format csv --output-dir data/raw
```

### Anomaly Injection Controls
The generator automatically injects controlled anomalies:
- ~8% Error/Critical rates
- ~3% Duplicate records
- ~2% Malformed entries (unparseable dates, missing sources, invalid levels, corrupted chunks)

---

## 4. Testing & Validation

Run the Pytest suite:

```bash
python -m pytest tests -v
```

All 26 automated tests validate unit parsing, normalizers, validator rules, deduplication, schema setup, analytics queries, synthetic generator output, and end-to-end pipeline idempotency.
