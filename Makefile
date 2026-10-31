# Makefile for LogPulse

PYTHON = python
PIP = $(PYTHON) -m pip
PYTEST = $(PYTHON) -m pytest
STREAMLIT = $(PYTHON) -m streamlit

.PHONY: help install generate ingest test dashboard clean

help:
	@echo "Available commands:"
	@echo "  make install     Install project dependencies"
	@echo "  make generate    Generate 100,000 synthetic log records into data/raw"
	@echo "  make ingest      Run the end-to-end ingestion pipeline"
	@echo "  make test        Execute automated test suite with pytest"
	@echo "  make dashboard   Launch the Streamlit analytics dashboard"
	@echo "  make clean       Remove temporary databases and generated quarantine files"

install:
	$(PIP) install -r requirements.txt

generate:
	$(PYTHON) -m src.generator.synthetic_data --records 100000 --format mixed --output-dir data/raw

ingest:
	$(PYTHON) -m src.pipeline.orchestrator

test:
	$(PYTEST) tests -v

dashboard:
	$(STREAMLIT) run dashboard/app.py

clean:
	rm -rf db/logpulse.db data/quarantine/*.csv .pytest_cache __pycache__
