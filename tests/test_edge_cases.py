from datetime import datetime, timedelta, timezone
from tests.conftest import create_running_experiment, event, register


def test_out_of_order_timestamp_persisted_as_rejected_deviation(test_client):
    register(test_client); create_running_experiment(test_client)
    t0 = datetime.now(timezone.utc)
    first = event(event_id="newer", event_type="HEARTBEAT", step_id=None,
                  timestamp=(t0 + timedelta(seconds=10)).isoformat())
    earlier = event(event_id="older", event_type="HEARTBEAT", step_id=None,
                    timestamp=t0.isoformat())
    assert test_client.post("/api/v1/events", json=first).json()["accepted"]
    result = test_client.post("/api/v1/events", json=earlier).json()
    assert not result["accepted"]
    assert "earlier than the latest" in result["processing_error"]
    assert test_client.get("/api/v1/deviations").json()["total"] == 1


def test_unknown_experiment_event_is_persisted_rejected(test_client):
    register(test_client)
    result = test_client.post("/api/v1/events", json=event(experiment_id="missing-exp", event_id="missing-event")).json()
    assert not result["accepted"]
    assert test_client.get("/api/v1/events/missing-event").json()["processing_status"] == "rejected"


def test_camera_and_system_status_events(test_client):
    register(test_client)
    for event_type in ("CAMERA_DISCONNECTED", "CAMERA_RECONNECTED", "SYSTEM_STATUS"):
        result = test_client.post("/api/v1/events", json=event(
            experiment_id=None, step_id=None, event_type=event_type, event_id=f"event-{event_type}"))
        assert result.status_code == 200 and result.json()["accepted"]
