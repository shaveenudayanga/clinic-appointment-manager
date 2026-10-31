# Convenience commands for macOS/Linux. The README lists the plain commands for Windows.
# Override the interpreter if needed, e.g. `make setup PYTHON=python3.12`.
PYTHON ?= python3
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup backend-setup frontend-setup seed backend frontend test

setup: backend-setup frontend-setup

backend-setup:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -r backend/requirements.txt
	test -f backend/.env || cp backend/.env.example backend/.env

frontend-setup:
	cd frontend && npm install

seed:
	cd backend && .venv/bin/python -m app.seed

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest
