# SUTRA Backend

**An independent event-ingestion and experiment backend for SUTRA (SIH26174).** Built with FastAPI, SQLAlchemy, SQLite, Pydantic, YAML protocols, and WebSockets.

This repository is designed to run on its own: no AI Vision Engine or dashboard checkout is required. The backend validates reported AI events and experiment order; it does **not** inspect video or independently verify visual evidence. Its five-step wet-lab flow is a mock demonstration, not an official BAS procedure.

## What this backend does

- Registers devices and receives heartbeats.
- Validates versioned event payloads and deduplicates deliveries by `event_id`.
- Persists experiments, protocol steps, telemetry, activity, deviations, system logs, and operator acknowledgements.
- Enforces step start/completion order and confidence thresholds; rejected transitions do not advance experiment state.
- Broadcasts dashboard-safe updates over `/ws/dashboard`; REST APIs can recover missed events.
- Provides independent mock clients, automated tests, and local performance scripts.

## Start here

### Requirements

- Python 3.10 or newer
- Windows PowerShell, macOS, or Linux

### Install and run (Windows PowerShell)

Run these commands from the repository root:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app
```

If PowerShell blocks virtual-environment activation, use the interpreter directly: `.venv\Scripts\python.exe -m pip install -r requirements.txt`, then `.venv\Scripts\python.exe -m app`. The host and port are read from `SUTRA_HOST` and `SUTRA_PORT`.

The server initializes the SQLAlchemy tables and loads the demo protocol at startup. Local SQLite data is stored in `sutra.db` (ignored by Git). `.env` is loaded automatically from the project root.

| Resource | URL |
|---|---|
| Health | `http://127.0.0.1:8000/health` |
| Interactive OpenAPI / Swagger UI | `http://127.0.0.1:8000/docs` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| Dashboard WebSocket | `ws://127.0.0.1:8000/ws/dashboard` |

### Connect from another laptop

Set `SUTRA_HOST=0.0.0.0`, allow the configured port through the host firewall, and connect clients to the backend machine's reachable LAN IP (for example, `http://<backend-ip>:8000`). A remote laptop must not use its own `localhost` to reach this server. Configure `SUTRA_CORS_ORIGINS` for the dashboard origin.

## Try it without the AI engine

Keep the server running, then open a second terminal at the project root:

```powershell
python tools/mock_ai_client.py
```

This registers a mock device, sends a heartbeat, creates and starts an experiment, sends step events, exercises duplicate delivery, creates deviation/review events, and submits an invalid event to demonstrate validation.

To simulate all five protocol steps in order:

```powershell
python tools/event_simulator.py
```

For a server on another host, add `--base-url http://<backend-ip>:8000` to either client.

## Event and dashboard contracts

All REST endpoints are versioned under `/api/v1`. The supported event types are `HEARTBEAT`, `STEP_STARTED`, `STEP_COMPLETED`, `DEVIATION_DETECTED`, `CAMERA_DISCONNECTED`, `CAMERA_RECONNECTED`, `NEEDS_REVIEW`, and `SYSTEM_STATUS`. Events use schema version `1.0`, timezone-aware timestamps, and confidence values from 0 to 1. Unknown fields and malformed event contracts are rejected.

See [docs/EVENT_CONTRACT.md](docs/EVENT_CONTRACT.md) for a complete payload example, error envelope, pagination format, token mode, WebSocket messages, and LAN setup guidance.

Key endpoints:

| Area | Routes |
|---|---|
| Health/status | `GET /health`, `GET /api/v1/system/status`, `GET /api/v1/system/metrics`, `GET /api/v1/system/logs` |
| Devices | `POST /api/v1/devices/register`, `POST /api/v1/devices/heartbeat`, `GET /api/v1/devices` |
| Events | `POST /api/v1/events`, `POST /api/v1/events/batch`, `GET /api/v1/events`, `GET /api/v1/events/{event_id}` |
| Experiments | `GET/POST /api/v1/experiments`, `GET /api/v1/experiments/current`, start/stop routes, experiment timeline |
| Protocols | `GET/POST /api/v1/protocols`, `GET /api/v1/protocols/{protocol_id}` |
| Deviations | `GET /api/v1/deviations`, `POST /api/v1/deviations/{deviation_id}/acknowledge` |

List APIs use `items`, `total`, `limit`, and `offset` for pagination. Duplicate event IDs return the original processing result without inserting a second event. Protocol-invalid events are recorded as rejected with an error and deviation; they do not update a step. WebSocket messages intentionally omit evidence and raw event payloads. Clients should reconnect and recover missed data through REST.

## Architecture and extension points

```text
HTTP / WebSocket clients
          │
          ▼
FastAPI routes and request schemas       app/main.py, app/schemas/
          │
          ├── device validation           app/core/auth.py
          ▼
Event ingestion and alert handling       app/services/
          │
          ├── protocol transition rules   modules/experiment_engine/
          ├── persisted protocol data      protocols/, experiment_protocols
          ▼
SQLAlchemy models and database            app/models/, app/database.py
          │
          └── dashboard event broadcast    app/websocket/
```

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI app, lifecycle, REST routes, request controls, WebSocket endpoint |
| `app/__main__.py` | Configurable local startup via `python -m app` |
| `app/config.py` | Environment-based settings |
| `app/database.py` | SQLAlchemy engine, sessions, schema initialization |
| `app/models/models.py` | Database tables, indexes, and uniqueness constraints |
| `app/schemas/schemas.py` | Request validation and event contract |
| `app/services/ingestion.py` | Idempotent event processing, protocol invocation, persistence, broadcasts |
| `modules/experiment_engine/engine.py` | Protocol transition and ordering rules |
| `protocols/demo_wetlab.yaml` | Configurable five-step mock protocol |
| `app/websocket/manager.py` | Multi-client WebSocket lifecycle and broadcast |
| `tests/` | API, protocol, persistence, and WebSocket checks |
| `tools/` | Independent mock event producers |
| `docs/` | Integration contract, benchmarking, and code-fixing guide |

For an approachable, step-by-step codebase walkthrough, see [docs/CODE_FIX_GUIDE.md](docs/CODE_FIX_GUIDE.md).

## Configuration and security

Copy `.env.example` to `.env` and set values in your shell/IDE before starting the server. `app/config.py` reads environment variables; copying the file alone does not load it automatically.

| Setting | Default | Purpose |
|---|---|---|
| `SUTRA_ENV` | `development` | Environment label |
| `SUTRA_DATABASE_URL` | `sqlite:///./sutra.db` | SQLAlchemy database URL |
| `SUTRA_HOST` / `SUTRA_PORT` | `127.0.0.1` / `8000` | Bind address and port |
| `SUTRA_CORS_ORIGINS` | localhost dashboard origins | Allowed browser origins |
| `SUTRA_DEV_AUTH` | `true` | Local development authentication mode |
| `SUTRA_MAX_REQUEST_BYTES` | `1048576` | Request size limit |
| `SUTRA_RATE_LIMIT_PER_MINUTE` | `120` | In-memory API request limit |
| `SUTRA_PROTOCOL_PATH` | `protocols/demo_wetlab.yaml` | Default protocol definition |

Startup also validates that the port is within 1–65535 and that request-size and rate-limit values are positive.

In development mode, device tokens are not required. For token mode set `SUTRA_DEV_AUTH=false`: registration returns a one-time token for the `X-Device-Token` header, and the backend stores only its hash. Never commit `.env`, live tokens, or database files. This is a local MVP, not a production security certification. A real network deployment also needs TLS, managed secrets, durable rate limiting, backup/restore procedures, and security review.

## Tests and performance checks

Run the automated suite from the repository root:

```powershell
python -m pytest -q
```

The tests use an isolated SQLite database. They cover health, registration/heartbeat, event validation and deduplication, experiment lifecycle, protocol order/confidence, deviations and acknowledgement, WebSockets, and persistence across database sessions.

With the server running, collect local observations:

```powershell
python scripts/benchmark.py --count 100
python scripts/benchmark_websocket.py --count 50
```

Previously observed on the development laptop: 100-event HTTP run measured 47.18 requests/s, median 19.973 ms and P95 30.364 ms; 50 single-client WebSocket round trips measured median 12.493 ms and P95 25.373 ms. These are sample local results, not capacity guarantees. The WebSocket measurement includes HTTP request, server broadcast, and client receive; no concurrent stress benchmark is claimed. See [docs/benchmarking.md](docs/benchmarking.md) for scope and interpretation.

## Database and migration path

The MVP uses portable SQLAlchemy models and creates tables on startup with `Base.metadata.create_all()`. This is convenient for local development but does not migrate existing tables when columns change. Back up important data before any schema change. Before team/production use, add and review Alembic migrations. In-memory SQLite URLs (`sqlite://` and `sqlite:///:memory:`) share one connection pool so app sessions see the same test database. To use PostgreSQL, configure a PostgreSQL SQLAlchemy URL and install a compatible driver; test migrations and connection-pool settings before deployment.

## Contributing / fixing a bug

1. Reproduce the issue and note the request, response, and expected behavior.
2. Add or update a focused regression test under `tests/`.
3. Make the smallest change in the layer responsible for the behavior.
4. Run `python -m pytest -q` and, when appropriate, the mock client.
5. Review `git diff` and `git status`; ensure `.env`, database files, and credentials are not staged.

The repository is published at [github.com/TeamSamay/phaltan-backend-](https://github.com/TeamSamay/phaltan-backend-).
