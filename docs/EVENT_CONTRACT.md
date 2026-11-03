# SUTRA event and integration contract

REST API version: `/api/v1`; OpenAPI UI: `/docs`; JSON schema: `/openapi.json`.

## Event payload (schema 1.0)

```json
{
  "schema_version": "1.0",
  "event_id": "unique-id",
  "source": "sutra-ai-engine",
  "device_id": "ai-device-01",
  "experiment_id": "experiment-001",
  "timestamp": "2026-01-01T10:00:00Z",
  "event_type": "STEP_COMPLETED",
  "step_id": "STEP_03",
  "step_name": "Reagent Aspiration",
  "status": "COMPLETED",
  "confidence": 0.91,
  "evidence": {},
  "rack_coordinates": {"x": 0.45, "y": 0.62},
  "requires_review": false
}
```

Supported types: `HEARTBEAT`, `STEP_STARTED`, `STEP_COMPLETED`, `DEVIATION_DETECTED`, `CAMERA_DISCONNECTED`, `CAMERA_RECONNECTED`, `NEEDS_REVIEW`, `SYSTEM_STATUS`. Timestamps require timezone. Confidence is in [0,1]. Extra event fields are rejected. `event_id` is the idempotency key. Protocol-invalid events are persisted as rejected with an error and create deviation records; malformed schema bodies return 422.

## Errors and pagination

Errors use `{ "error": { "code": "...", "message": "..." } }`.
Paginated collections return `{ "items": [], "total": 0, "limit": 50, "offset": 0 }`.

## Authentication

Local development defaults to `SUTRA_DEV_AUTH=true`; registered devices can post events and heartbeat without a token. For token mode set `SUTRA_DEV_AUTH=false`: registration returns a one-time `device_token`, which must be sent in `X-Device-Token`. Only the SHA-256 token hash is stored. Use TLS and an external secrets mechanism for real deployments; this MVP is not production-security-certified.

## WebSocket `/ws/dashboard`

Connect and receive `connection.ready`, then JSON messages such as `event.new`, `alert`, `experiment.status`, `device.heartbeat`, and `deviation.acknowledged`. Client text `ping` or `heartbeat` receives `pong`. WebSocket messages intentionally omit evidence/raw event payload. Reconnect and recover gaps via `GET /api/v1/events?offset=...` or experiment timeline.

## Networking

Default bind is 127.0.0.1:8000. Set `SUTRA_HOST=0.0.0.0` to accept LAN traffic and configure a reachable address and `SUTRA_CORS_ORIGINS` for the dashboard; clients on another laptop must use the backend laptop's network IP, not their own localhost. OpenAPI may be opened at `http://<backend-host>:8000/docs`.
