# LogPulse – Architecture & Technical Design

## 1. Executive Summary

LogPulse is an enterprise-grade log ingestion, processing, and analytical pipeline. Designed to handle diverse log formats emitted by distributed microservices, LogPulse standardizes temporal and severity attributes, guarantees exactly-once processing via cryptographic hashing, routes invalid records into quarantine, and populates an analytical data warehouse.

---

## 2. Architecture Overview

```mermaid
flowchart TD
    subgraph Ingestion ["1. Discovery & Ingestion"]
        A["Inbound Raw Logs\n(JSON, CSV, Syslog)"] --> B["File Registry Check\n(Content SHA-256)"]
    end

    subgraph Processing ["2. Core ETL Pipeline"]
        B -->|New or Modified| C["Log Parser\n(Multi-format Auto-detect)"]
        B -->|Already Processed| SKIP["Idempotent Skip"]
        C --> D["Timestamp & Severity Normalizer\n(UTC ISO-8601 & Canonical Levels)"]
        D --> E{"Record Validator"}
        E -->|Valid| F["Deduplicator\n(SHA-256 Hash Computation)"]
        E -->|Invalid| G["Quarantine Manager\n(DB Table + Audit CSV)"]
        F --> H["In-batch & Cross-DB Dedup Filter"]
    end

    subgraph Storage ["3. Data Storage (SQLite)"]
        H --> I[("log_events\n(INSERT OR IGNORE)")]
        G --> J[("quarantine")]
        H --> K[("file_registry")]
        H --> L[("pipeline_runs")]
    end

    subgraph Analytics ["4. Consumption Layer"]
        I --> M["Analytics Engine\n(Percentiles & Error Rates)"]
        M --> N["Streamlit Dashboard\n(5 Interactive Tabs)"]
    end
```

---

## 3. Database Schema Design

The storage layer utilizes SQLite with Write-Ahead Logging (WAL) and enforced foreign key constraints.

```mermaid
erDiagram
    pipeline_runs ||--o{ log_events : "tracks lineage"
    pipeline_runs ||--o{ quarantine : "isolates errors"
    file_registry ||--o{ log_events : "source file"
    file_registry ||--o{ quarantine : "source file"

    log_events {
        TEXT record_hash PK "SHA-256(timestamp_utc|source|message)"
        TEXT timestamp_utc "ISO-8601 UTC timestamp"
        TEXT severity "Canonical level: DEBUG|INFO|WARNING|ERROR|CRITICAL"
        TEXT source "Service or application name"
        TEXT message "Normalized message body"
        REAL latency_ms "Extracted request latency (nullable)"
        TEXT request_id "Extracted trace or correlation ID (nullable)"
        TEXT raw_line "Original unparsed log record"
        TEXT source_file "Source filename"
        TEXT pipeline_run_id FK "Lineage to pipeline_runs"
        TEXT created_at "Ingestion timestamp"
    }

    quarantine {
        INTEGER id PK "Auto-increment ID"
        TEXT record_hash "Cryptographic hash of invalid record"
        TEXT raw_line "Original corrupted log line"
        TEXT rejection_reason "Validation error description"
        TEXT source_file "Source filename"
        TEXT pipeline_run_id FK "Lineage to pipeline_runs"
        TEXT created_at "Quarantine timestamp"
    }

    file_registry {
        TEXT file_path PK "Absolute path of processed file"
        TEXT file_hash "SHA-256 checksum of file contents"
        TEXT status "COMPLETED | FAILED | IN_PROGRESS"
        INTEGER record_count "Total records in file"
        INTEGER loaded_count "Successfully loaded records"
        INTEGER quarantined_count "Quarantined records"
        INTEGER duplicate_count "Duplicates skipped"
        TEXT pipeline_run_id FK "Lineage to pipeline_runs"
        TEXT processed_at "Timestamp of processing"
    }

    pipeline_runs {
        TEXT run_id PK "UUIDv4 identifier"
        TEXT started_at "UTC start time"
        TEXT completed_at "UTC completion time"
        TEXT status "SUCCESS | PARTIAL | FAILED | RUNNING"
        INTEGER total_files "Discovered files count"
        INTEGER files_processed "Successfully completed files"
        INTEGER total_records "Total parsed records"
        INTEGER records_loaded "Records loaded into log_events"
        INTEGER records_quarantined "Records quarantined"
        INTEGER records_duplicated "Duplicates skipped"
        REAL duration_seconds "Wall-clock run duration"
    }
```

---

## 4. Key Design Decisions

1. **Deterministic Record Hashing (`SHA-256`)**:
   - `record_hash = sha256(f"{timestamp_utc}|{source}|{message}")`
   - Serves as the primary key of `log_events`.
   - Guarantees natural idempotency without requiring distributed lock managers or synthetic primary keys.

2. **Multi-Layer Idempotency**:
   - **File-Level**: Checksum inspection in `file_registry` prevents redundant processing of untouched files.
   - **Batch-Level**: Drops intra-file duplicate logs in memory before DB interaction.
   - **Storage-Level**: `INSERT OR IGNORE` acts as the safety net against race conditions or overlapping batches.

3. **Data Quality & Quarantine Routing**:
   - Malformed records do not abort the pipeline.
   - Invalid records are enriched with granular `rejection_reason` metadata and routed to the `quarantine` table and CSV audit logs.

4. **Zero-Overhead Local Stack**:
   - Standard Python, Pandas, SQLite, and Streamlit deliver 3,000+ records/second on local developer workstations without complex external infrastructure setup.
