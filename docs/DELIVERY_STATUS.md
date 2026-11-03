# SUTRA backend verification record

Verification date: 2026-11-03 (local Windows workspace; Python 3.14.6; SQLite).

- Automated suite: `16 passed, 1 warning` using pytest.
- Local server: Uvicorn startup succeeded; mock client completed registration, heartbeat, experiment creation/start, step start/completion, duplicate event, deviation and review events, and malformed event rejection.
- Restart persistence: after stopping and restarting Uvicorn, health returned HTTP 200 and 104 previously persisted events were still retrievable from SQLite.
- HTTP benchmark: 100 events; observed 2.1196 s duration, 47.18 event requests/s, median HTTP latency 19.973 ms, P95 30.364 ms, process RSS 48,136,192 bytes. Combined ingestion/database path represents API request latency and is not an isolated SQL measurement.
- WebSocket: tests verified two dashboard clients, ready messages, ping/pong, device heartbeat fan-out and clean close. A standalone single-client broadcast round-trip harness is available at `scripts/benchmark_websocket.py`; latency has not yet been measured with it.
- Local status/GitHub: no Git repository is initialized in the workspace, so Git status, commit and remote publication have not been performed. No remote URL provided. Nothing was pushed. Before publishing, initialize repository `sutra-backend`, verify status and scan staged files for secrets; `.env` and database artifacts are ignored.
- Current development database `sutra.db` was created by smoke testing and is ignored by `.gitignore`.
