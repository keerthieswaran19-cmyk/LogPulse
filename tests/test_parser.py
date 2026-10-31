"""Unit tests for LogParser and patterns."""

from src.parser.log_parser import LogParser, extract_latency, extract_request_id


def test_extract_latency():
    assert extract_latency("Request completed in latency=150ms") == 150.0
    assert extract_latency("duration=2.5s to finish") == 2500.0
    assert extract_latency("response_time=45ms") == 45.0
    assert extract_latency("No latency here") is None


def test_extract_request_id():
    assert extract_request_id("[req-abc12345] Authenticated") == "req-abc12345"
    assert extract_request_id("Error trace_id=trace-999 occurred") == "trace-999"
    assert extract_request_id("No id present") is None


def test_parse_json(sample_json_file):
    parser = LogParser()
    df, total_lines = parser.parse_file(sample_json_file)
    assert total_lines == 4
    assert len(df) == 4
    # Check field aliasing (level -> severity, service -> source)
    assert "severity" in df.columns
    assert "source" in df.columns
    # Check malformed JSON handling
    malformed = df[df["parsing_error"].notna()]
    assert len(malformed) == 1


def test_parse_csv(sample_csv_file):
    parser = LogParser()
    df, total_lines = parser.parse_file(sample_csv_file)
    assert total_lines == 4  # 1 header + 3 data lines
    assert len(df) == 3
    assert "timestamp" in df.columns
    assert "source" in df.columns


def test_parse_syslog(sample_syslog_file):
    parser = LogParser()
    df, total_lines = parser.parse_file(sample_syslog_file)
    assert total_lines == 4
    assert len(df) == 4
    valid_rows = df[df["source"].notna()]
    assert len(valid_rows) >= 3
    assert df.loc[0, "request_id"] == "req-201"
    assert df.loc[0, "latency_ms"] == 50.0
