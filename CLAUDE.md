# CLAUDE.md

Appointment management web app for a specialist clinic in Sydney. Built as a time-boxed pre-screening assessment, so keep it simple, readable and easy for a reviewer to run.

## Stack
- Backend: Python 3.11+, FastAPI, SQLModel, SQLite, pytest. Code lives in `backend/app`.
- Frontend: Next.js, TypeScript, Tailwind. Code lives in `frontend/`.
- Commands: `make setup`, `make seed`, `make backend`, `make frontend`, `make test`.

## Rules that must not change
- The id is the only identity. Names are never unique. Patients have a unique `mrn` and practitioners a unique `provider_number`. Always show people by their `label`.
- All booking rules live in `backend/app/rules.py` as pure functions that take `now` as an argument. Create and edit both go through them. Never duplicate a rule in the API or the frontend.
- No double booking for the practitioner or the patient. Touching edges are allowed. Cancelled appointments don't block a slot.
- Times are stored in UTC and shown in Australia/Sydney. All conversion goes through `backend/app/timezones.py`.
- Clinic hours: Monday to Friday, 08:00 to 18:00 Sydney time. Length 15 to 120 minutes. No bookings in the past.
- Cancelled is final and never deletes a record. Completed and No-show only after the start time.
- Natural-language booking never saves anything by itself and never guesses a person: if a name matches more than one record, list them all; if none match, say so.
- Only invented names in seed data. No real personal data. Never commit `.env` or secrets.

## How to work
- Work in phases and stop after each one with a summary and a "what to check" list. Commit each phase separately.
- Run `make test` before every commit. Add tests for every new rule.
- Ask instead of guessing. Prefer simple and correct over clever.
- Don't write the "How I used AI" section of the README. The author writes it.

## Progress
- Phase 1 (models, rules, seed) and the identity change: done.
- Phase 2 (rule tests, 79 passing on Python 3.11 and 3.14): done.
- Phase 3 (services, API including GET /api/clinic, API and concurrency tests, 109 passing): done.
- Backend additions for the frontend (error fields, allowed_actions, patient search and registration with duplicate check, clinic day info; 154 passing): done.
- Next: phase 4 (frontend), then 5 (optional natural-language booking), 6 (README).
