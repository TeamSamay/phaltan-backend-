# SUTRA Backend

Independent local backend and experiment engine for SUTRA (SIH26174). This repository does not require the AI Vision Engine and does not include a React dashboard. AI-related events are simulated; the backend validates reported evidence and protocol order, it does not analyze video. The five-step wet-lab flow is a mock demonstration, not an official BAS protocol.

## Requirements and setup

Python 3.10+ is required. From the project root:

1. Create and activate a virtual environment (`py -3 -m venv .venv`, then `.venv\\Scripts\\Activate.ps1` on Windows).
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and adjust settings if needed. Environment variables are read directly by the app; load `.env` in your shell or IDE.
4. Start with `uvicorn app.main:app --host 127.0.0.1 --port 8000`.

The app initializes SQLAlchemy tables and seeds `demo-wetlab` protocol on startup. SQLite file is `sutra.db`; it is git-ignored. PostgreSQL migration path: set `SUTRA_DATABASE_URL` to a PostgreSQL SQLAlchemy URL and install the matching driver; schema is portable SQLAlchemy, although this MVP uses `create_all` rather than Alembic migrations.

Default API: `http://127.0.0.1:8000`. Interactive OpenAPI docs: `/docs`; OpenAPI JSON: `/openapi.json`; health: `/health`.

## Independent mock tools

With backend running, use `python tools/mock_ai_client.py` to register a mock device, heartbeat, create/start a run, send step events, duplicate delivery, deviation and review events, and test malformed schema rejection. `python tools/event_simulator.py` sends the full five-step flow. Both accept `--base-url` to target the backend over LAN. For LAN use, bind `SUTRA_HOST=0.0.0.0`, open the appropriate firewall port, and use the backend machine's reachable IP from other devices.

## API scope

See `docs/EVENT_CONTRACT.md` and generated OpenAPI docs for all devices, events, experiments, protocols, timeline, deviations, system, and WebSocket contracts. Collections use offset pagination. Event deduplication is keyed by `event_id`; API validation errors use a consistent `error` envelope. Protocol violations are saved with `processing_status=rejected` and a deviation, not applied as state transitions.

## Security and reliability notes

Development auth is intentionally enabled by default for local MVP (`SUTRA_DEV_AUTH=true`). In token mode each device uses the returned `X-Device-Token`; never commit tokens or `.env`. CORS, payload size and in-memory per-client rate limits are configurable. This is not a security certification or production deployment recipe. For a network deployment, use TLS/reverse proxy, a managed secret store, persistent rate limiting, backup strategy and database migrations.

## Tests

Run `pytest -q`. Tests use an isolated temporary SQLite database. To check code diagnostics in VS Code, select a Python 3.10+ environment with requirements installed.

## Local performance measurements

With the server running, run `python scripts/benchmark.py --count 100` for event/API throughput and memory, and `python scripts/benchmark_websocket.py --count 50` for WebSocket broadcast round-trip. Record results with host and database details; these local checks are not production capacity guarantees.

## Structure

- `app/`: FastAPI endpoints, SQLAlchemy persistence, schemas, auth, ingestion, alert and WebSocket services.
- `modules/experiment_engine/`: protocol parsing and deterministic transition validation.
- `protocols/`: versioned YAML demo protocol.
- `tools/`: independent mock producer and complete event simulator.
- `tests/`: API, persistence and engine tests.
- `docs/`: dashboard and AI event integration contract.

## GitHub

Initialize a separate repository named `sutra-backend` when ready. Review `git status`, scan staged files for secrets, run tests and inspect ignored `.env`/database files before pushing. No remote or push is configured by this task; get approval before publishing.
