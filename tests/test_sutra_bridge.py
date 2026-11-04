import uuid
from starlette.testclient import TestClient
from app.main import app


def test_sutra_telemetry_events_bridge():
    with TestClient(app) as client:
        test_uid = uuid.uuid4().hex[:8]
        exp_id = f"EXP-{test_uid}"
        evt_id = f"sutra-bridge-{test_uid}"

        # Pre-registered ai-device-01 should work out of the box
        # Create and start demo experiment
        client.post("/api/v1/experiments", json={"experiment_id": exp_id, "name": "Demo Wetlab Protocol"})
        client.post(f"/api/v1/experiments/{exp_id}/start")

        # Payload matching sutra-ai-engine's exact TelemetryEvent.model_dump()
        payload = {
            "schema_version": "1.0",
            "event_id": evt_id,
            "source": "sutra-ai-engine",
            "device_id": "ai-device-01",
            "experiment_id": exp_id,
            "timestamp": "2026-11-04T01:10:00Z",
            "event_type": "STEP_STARTED",
            "step_id": "STEP_01",
            "step_name": "Rack Extraction",
            "status": "STARTED",
            "confidence": 0.92,
            "evidence": {"method": "kinematic_pose_tracking"},
            "rack_coordinates": {
                "x": 0.42,
                "y": 0.68,
                "calibration_status": "CALIBRATED"
            },
            "requires_review": False
        }

        # Post to /api/v1/telemetry/events (Sutra AI Engine's target URL)
        resp = client.post("/api/v1/telemetry/events", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["acknowledged"] is True
        assert data["event_id"] == evt_id
        assert data["accepted"] is True

        # Test duplicate event handling
        resp_dup = client.post("/api/v1/telemetry/events", json=payload)
        assert resp_dup.status_code == 200
        assert resp_dup.json()["is_duplicate"] is True

        # Test GET /api/v1/telemetry/events
        get_resp = client.get("/api/v1/telemetry/events?limit=10")
        assert get_resp.status_code == 200
        assert get_resp.json()["count"] >= 1
