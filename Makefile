# Convenience commands for macOS/Linux. The README lists the plain commands for Windows.
# Override the interpreter if needed, e.g. `make setup PYTHON=python3.12`.
PYTHON ?= python3
VENV := backend/.venv
BIN := $(VENV)/bin

.PHONY: setup backend-setup frontend-setup seed backend frontend test e2e screenshots

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

# Browser tests: start their own backend (port 8001, backend/e2e.db) and frontend (port 3001).
e2e:
	cd frontend && npx playwright install chromium && npx playwright test

# Re-take the README screenshots in docs/screenshots/.
screenshots:
	mkdir -p docs/screenshots
	cd frontend && npx playwright install chromium && SCREENSHOTS=1 npx playwright test
