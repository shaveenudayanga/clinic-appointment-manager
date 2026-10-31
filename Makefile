# Convenience commands for macOS/Linux. The README lists the plain commands for Windows.
# Override the interpreter if needed, e.g. `make setup PYTHON=python3.12`.
PYTHON ?= python3
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup backend-setup seed test

setup: backend-setup

backend-setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r backend/requirements.txt
	test -f backend/.env || cp backend/.env.example backend/.env

seed:
	cd backend && .venv/bin/python -m app.seed

test:
	cd backend && .venv/bin/pytest
