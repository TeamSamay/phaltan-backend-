from starlette.testclient import TestClient
from app.main import app
from app.services.process_manager import process_manager


def test_engine_process_status_and_control():
    with TestClient(app) as client:
        # Check initial status
        resp = client.get("/api/v1/engine/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_running" in data
        assert "status" in data
        assert "recent_logs" in data

        # Check logs endpoint
        logs_resp = client.get("/api/v1/engine/logs?limit=50")
        assert logs_resp.status_code == 200
        assert "lines" in logs_resp.json()

        # Check runs endpoint
        runs_resp = client.get("/api/v1/engine/runs")
        assert runs_resp.status_code == 200
        assert "runs" in runs_resp.json()

        # Stop when already stopped should be safe
        stop_resp = client.post("/api/v1/engine/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["success"] is True
