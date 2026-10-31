"""Unit tests for synthetic data generator."""

from pathlib import Path
from src.generator.synthetic_data import SyntheticLogGenerator


def test_synthetic_generator_counts():
    gen = SyntheticLogGenerator(seed=123)
    records = gen.generate_records(count=500)
    assert len(records) == 500


def test_synthetic_generator_anomalies_present():
    gen = SyntheticLogGenerator(error_ratio=0.2, malformed_ratio=0.1, seed=42)
    records = gen.generate_records(count=100)

    # Some records should have missing / invalid fields
    has_anomaly = any(
        r.get("timestamp") == "not-a-valid-date-format"
        or r.get("source") is None
        or r.get("severity") == "UNKNOWN_CUSTOM_LEVEL"
        or "raw_corrupted_line" in r
        for r in records
    )
    assert has_anomaly


def test_synthetic_generator_write_files(temp_data_dir):
    gen = SyntheticLogGenerator(seed=42)
    records = gen.generate_records(count=50)

    json_path = temp_data_dir / "gen.json"
    csv_path = temp_data_dir / "gen.csv"
    log_path = temp_data_dir / "gen.log"

    gen.write_to_file(records, str(json_path), fmt="json")
    gen.write_to_file(records, str(csv_path), fmt="csv")
    gen.write_to_file(records, str(log_path), fmt="syslog")

    assert json_path.exists()
    assert csv_path.exists()
    assert log_path.exists()
