import uuid
import pytest
from starlette.testclient import TestClient
from app.main import app
from app.database_mongo import mongo_manager


def test_mongo_stats_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/mongo/stats")
        assert response.status_code == 200
        data = response.json()
        assert "connected" in data
        if data["connected"]:
            assert "counts" in data
            assert "telemetry_events" in data["counts"]


def test_mongo_events_query():
    with TestClient(app) as client:
        test_uid = uuid.uuid4().hex[:8]
        dev_id = f"m-dev-{test_uid}"
        exp_id = f"m-exp-{test_uid}"
        evt_id = f"m-evt-{test_uid}"

        # Register device and create experiment
        reg_res = client.post("/api/v1/devices/register", json={"device_id": dev_id})
        assert reg_res.status_code == 200

        exp_res = client.post("/api/v1/experiments", json={"experiment_id": exp_id, "name": "Mongo Exp"})
        assert exp_res.status_code == 201

        start_res = client.post(f"/api/v1/experiments/{exp_id}/start")
        assert start_res.status_code == 200

        # Ingest an event
        event_payload = {
            "schema_version": "1.0",
            "event_id": evt_id,
            "source": "sutra-ai-engine",
            "device_id": dev_id,
            "experiment_id": exp_id,
            "timestamp": "2026-11-04T01:00:00Z",
            "event_type": "STEP_STARTED",
            "step_id": "STEP_01",
            "confidence": 0.95,
            "evidence": {"note": "testing mongo storage"},
            "rack_coordinates": {"x": 0.5, "y": 0.5, "calibration_status": "CALIBRATED"}
        }
        ingest_res = client.post("/api/v1/events", json=event_payload)
        assert ingest_res.status_code == 200

        # Query via MongoDB API
        if mongo_manager.is_connected:
            mongo_res = client.get(f"/api/v1/mongo/events?experiment_id={exp_id}")
            assert mongo_res.status_code == 200
            m_data = mongo_res.json()
            assert m_data["total"] >= 1
            found = any(e["event_id"] == evt_id for e in m_data["items"])
            assert found
