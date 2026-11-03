from tests.conftest import create_running_experiment, event, register


def test_health_and_system_status(test_client):
    assert test_client.get("/health").json()["status"] == "ok"
    assert test_client.get("/api/v1/system/status").status_code == 200


def test_register_and_heartbeat(test_client):
    assert register(test_client).status_code == 200
    response = test_client.post("/api/v1/devices/heartbeat", json={"device_id": "test-device"})
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_event_schema_rejects_malformed_and_unknown_types(test_client):
    register(test_client)
    response = test_client.post("/api/v1/events", json={"event_id": "x", "event_type": "NOPE"})
    assert response.status_code == 422
    assert test_client.post("/api/v1/events", json=event(event_type="NOPE")).status_code == 422


def test_event_deduplicated_and_persisted(test_client):
    register(test_client)
    create_running_experiment(test_client)
    payload = event(event_id="same-id")
    first = test_client.post("/api/v1/events", json=payload).json()
    second = test_client.post("/api/v1/events", json=payload).json()
    assert first["accepted"] and not first["duplicate"]
    assert second["duplicate"]
    assert test_client.get("/api/v1/events/same-id").status_code == 200
    assert test_client.get("/api/v1/events").json()["total"] == 1


def test_experiment_create_start_stop(test_client):
    response = test_client.post("/api/v1/experiments", json={"name": "A"})
    assert response.status_code == 201
    exp_id = response.json()["experiment_id"]
    assert test_client.post(f"/api/v1/experiments/{exp_id}/start").json()["status"] == "running"
    assert test_client.post(f"/api/v1/experiments/{exp_id}/stop").json()["status"] == "stopped"


def test_protocol_order_and_step_completion(test_client):
    register(test_client); create_running_experiment(test_client)
    skipped = test_client.post("/api/v1/events", json=event(event_id="skip", event_type="STEP_STARTED", step_id="STEP_02")).json()
    assert not skipped["accepted"] and skipped["processing_status"] == "rejected"
    start = test_client.post("/api/v1/events", json=event(event_id="start")).json()
    complete = test_client.post("/api/v1/events", json=event(event_id="complete", event_type="STEP_COMPLETED")).json()
    assert start["accepted"] and complete["accepted"]
    detail = test_client.get("/api/v1/experiments/test-exp").json()
    assert detail["steps"][0]["status"] == "completed"


def test_low_confidence_and_unknown_step_deviations(test_client):
    register(test_client); create_running_experiment(test_client)
    low = test_client.post("/api/v1/events", json=event(event_id="low", confidence=0.1)).json()
    unknown = test_client.post("/api/v1/events", json=event(event_id="unknown", step_id="NO_STEP")).json()
    assert not low["accepted"] and not unknown["accepted"]
    assert test_client.get("/api/v1/deviations").json()["total"] == 2


def test_deviation_and_acknowledgement(test_client):
    register(test_client)
    payload = event(experiment_id=None, event_type="DEVIATION_DETECTED", step_id=None,
                    event_id="dev-event", evidence={"description": "test deviation"})
    assert test_client.post("/api/v1/events", json=payload).json()["accepted"]
    row = test_client.get("/api/v1/deviations").json()["items"][0]
    response = test_client.post(f"/api/v1/deviations/{row['deviation_id']}/acknowledge",
                                json={"operator_id": "operator-1", "note": "reviewed"})
    assert response.status_code == 200 and response.json()["acknowledged"]


def test_websocket_connection_heartbeat_and_multiple_clients(test_client):
    with test_client.websocket_connect("/ws/dashboard") as first, test_client.websocket_connect("/ws/dashboard") as second:
        assert first.receive_json()["type"] == "connection.ready"
        assert second.receive_json()["type"] == "connection.ready"
        first.send_text("ping")
        assert first.receive_json()["type"] == "pong"
        register(test_client)
        heartbeat = test_client.post("/api/v1/devices/heartbeat", json={"device_id": "test-device"})
        assert heartbeat.status_code == 200
        assert first.receive_json()["type"] == "device.heartbeat"
        assert second.receive_json()["type"] == "device.heartbeat"


def test_pagination_contract(test_client):
    register(test_client)
    data = test_client.get("/api/v1/devices?limit=1&offset=0").json()
    assert set(data) == {"items", "total", "limit", "offset"}
