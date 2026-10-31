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
- The README has no "How I used AI" section; the author decided to leave it out. Don't add one.

## Progress
- Phase 1 (models, rules, seed) and the identity change: done.
- Phase 2 (rule tests, 79 passing on Python 3.11 and 3.14): done.
- Phase 3 (services, API including GET /api/clinic, API and concurrency tests, 109 passing): done.
- Backend additions for the frontend (error fields, allowed_actions, patient search and registration with duplicate check, clinic day info; 154 passing): done.
- Phase 4 (Next.js appointment book: day grid, booking panel, patient search/registration with duplicate warning; checked in headless Chrome): done.
- After phase 4: only Booked appointments can be cancelled; body hydration warning from browser extensions suppressed; Playwright suite (`make e2e`, 3 flows, own servers on ports 8001/3001 and `backend/e2e.db`); README screenshots in `docs/screenshots/` (`make screenshots`). 161 backend tests passing.
- Phase 5 (natural-language booking with Gemini `gemini-3.5-flash-lite` via the Interactions API, `store=false`; only the sentence and date context are sent; names matched in the backend, ambiguous/unknown names listed for the user; never saves; see `docs/ai-booking.md`; 192 backend tests passing on 3.11 and 3.14): done. Checked against the real Gemini API on 1 Nov 2026 (dates, ambiguous/unknown names, prompt injection, full UI flow).
- Dates people read are shown in words ("DOB 3 Jan 1998", "Mon 2 Nov 2026" next to date pickers); the API stays ISO. 195 backend tests, 3 e2e flows.
- Phase 6 (README for a reviewer, screenshots in `docs/screenshots/`): done. All phases complete.
