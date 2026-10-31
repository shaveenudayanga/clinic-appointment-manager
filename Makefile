# Convenience commands for macOS/Linux. The README lists the plain commands for Windows.
# Override the interpreter if needed, e.g. `make setup PYTHON=python3.12`.
PYTHON ?= python3
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup backend-setup seed backend test

setup: backend-setup

backend-setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r backend/requirements.txt
	test -f backend/.env || cp backend/.env.example backend/.env

seed:
	cd backend && .venv/bin/python -m app.seed

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

test:
	cd backend && .venv/bin/pytest
