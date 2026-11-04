from tests.conftest import create_running_experiment, event, register


def test_health_and_system_status(test_client):
    response = test_client.get("/health")
    assert response.json()["status"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert test_client.get("/api/v1/system/status").status_code == 200


def test_register_and_heartbeat(test_client):
    assert register(test_client).status_code == 200
    response = test_client.post("/api/v1/devices/heartbeat", json={"device_id": "test-device"})
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_heartbeat_for_unknown_device_returns_not_found(test_client):
    response = test_client.post("/api/v1/devices/heartbeat", json={"device_id": "missing-device"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "device_not_found"


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


def test_experiment_list_name_sort_is_ascending(test_client):
    for experiment_id, name in (("z-exp", "Zulu"), ("a-exp", "Alpha")):
        response = test_client.post("/api/v1/experiments", json={"experiment_id": experiment_id, "name": name})
        assert response.status_code == 201
    result = test_client.get("/api/v1/experiments?sort=name").json()
    assert [item["name"] for item in result["items"]] == ["Alpha", "Zulu"]


def test_protocol_order_and_step_completion(test_client):
    register(test_client); create_running_experiment(test_client)
    skipped = test_client.post("/api/v1/events", json=event(event_id="skip", event_type="STEP_STARTED", step_id="STEP_02")).json()
    assert not skipped["accepted"] and skipped["processing_status"] == "rejected"
    start = test_client.post("/api/v1/events", json=event(event_id="start")).json()
    complete = test_client.post("/api/v1/events", json=event(event_id="complete", event_type="STEP_COMPLETED")).json()
    assert start["accepted"] and complete["accepted"]
    detail = test_client.get("/api/v1/experiments/test-exp").json()
    assert detail["steps"][0]["status"] == "completed"


def test_repeated_step_start_is_rejected_without_overwriting_start_time(test_client):
    register(test_client); create_running_experiment(test_client)
    first = test_client.post("/api/v1/events", json=event(event_id="start-once")).json()
    repeated = test_client.post("/api/v1/events", json=event(event_id="start-twice")).json()
    assert first["accepted"]
    assert not repeated["accepted"]
    assert "already been started" in repeated["processing_error"]
    detail = test_client.get("/api/v1/experiments/test-exp").json()
    assert detail["steps"][0]["status"] == "started"


def test_step_event_while_experiment_stopped_is_saved_as_rejected(test_client):
    register(test_client); create_running_experiment(test_client)
    assert test_client.post("/api/v1/experiments/test-exp/stop").status_code == 200
    result = test_client.post("/api/v1/events", json=event(event_id="after-stop")).json()
    assert not result["accepted"] and result["processing_status"] == "rejected"
    persisted = test_client.get("/api/v1/events/after-stop").json()
    assert persisted["processing_status"] == "rejected"
    assert test_client.get("/api/v1/deviations").json()["total"] == 1


def test_duplicate_of_rejected_event_reports_rejected_result(test_client):
    register(test_client); create_running_experiment(test_client)
    payload = event(event_id="rejected-once", step_id="STEP_02")
    first = test_client.post("/api/v1/events", json=payload).json()
    duplicate = test_client.post("/api/v1/events", json=payload).json()
    assert not first["accepted"] and not duplicate["accepted"]
    assert duplicate["duplicate"]
    assert duplicate["processing_status"] == "rejected"
    assert test_client.get("/api/v1/events").json()["total"] == 1


def test_missing_step_confidence_is_rejected_and_saved(test_client):
    register(test_client); create_running_experiment(test_client)
    payload = event(event_id="missing-confidence")
    payload.pop("confidence")
    result = test_client.post("/api/v1/events", json=payload).json()
    assert not result["accepted"] and result["processing_status"] == "rejected"
    assert "Confidence missing" in result["processing_error"]


def test_protocol_creation_validates_steps(test_client):
    payload = {"protocol_id": "custom", "version": "1.0", "name": "Custom",
               "steps": [{"step_id": "A", "name": "Step A", "sequence": 1},
                         {"step_id": "A", "name": "Duplicate", "sequence": 2}]}
    assert test_client.post("/api/v1/protocols", json=payload).status_code == 422
    payload["steps"][1]["step_id"] = "B"
    assert test_client.post("/api/v1/protocols", json=payload).status_code == 201


def test_experiment_uses_requested_stored_protocol_version(test_client):
    protocol = {"protocol_id": "custom", "version": "2.0", "name": "Custom Protocol",
                "steps": [{"step_id": "CUSTOM_01", "name": "Custom step", "sequence": 1}]}
    assert test_client.post("/api/v1/protocols", json=protocol).status_code == 201
    experiment = test_client.post("/api/v1/experiments", json={"name": "Custom run",
        "protocol_id": "custom", "protocol_version": "2.0"})
    assert experiment.status_code == 201
    assert experiment.json()["protocol_id"] == "custom"
    detail = test_client.get(f"/api/v1/experiments/{experiment.json()['experiment_id']}").json()
    assert [step["step_id"] for step in detail["steps"]] == ["CUSTOM_01"]


def test_default_protocol_uses_persisted_version_after_yaml_changes(test_client):
    register(test_client)
    create_running_experiment(test_client)
    payload = event(event_id="persisted-protocol-start", step_id="STEP_01")
    assert test_client.post("/api/v1/events", json=payload).json()["accepted"]
    completion = event(event_id="persisted-protocol-complete", event_type="STEP_COMPLETED", step_id="STEP_01")
    assert test_client.post("/api/v1/events", json=completion).json()["accepted"]


def test_unknown_experiment_event_is_persisted_with_warning(test_client):
    register(test_client)
    payload = event(event_id="unknown-exp-event", experiment_id="does-not-exist")
    response = test_client.post("/api/v1/events", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert not result["accepted"] and result["processing_status"] == "rejected"
    assert test_client.get("/api/v1/deviations").json()["total"] == 1


def test_step_event_marked_requires_review_does_not_advance(test_client):
    register(test_client); create_running_experiment(test_client)
    payload = event(event_id="review-required-step", requires_review=True)
    result = test_client.post("/api/v1/events", json=payload).json()
    assert not result["accepted"]
    detail = test_client.get("/api/v1/experiments/test-exp").json()
    assert detail["steps"][0]["status"] == "pending"
    assert test_client.get("/api/v1/deviations").json()["total"] == 1


def test_step_transition_after_experiment_completion_is_rejected(test_client):
    register(test_client); create_running_experiment(test_client)
    # Complete the configured five-step protocol in order.
    for sequence in range(1, 6):
        step_id = f"STEP_0{sequence}"
        started = test_client.post("/api/v1/events", json=event(
            event_id=f"start-{sequence}", event_type="STEP_STARTED", step_id=step_id)).json()
        completed = test_client.post("/api/v1/events", json=event(
            event_id=f"complete-{sequence}", event_type="STEP_COMPLETED", step_id=step_id)).json()
        assert started["accepted"] and completed["accepted"]
    assert test_client.get("/api/v1/experiments/test-exp").json()["status"] == "completed"
    late = test_client.post("/api/v1/events", json=event(
        event_id="late-after-completion", event_type="STEP_STARTED", step_id="STEP_05")).json()
    assert not late["accepted"] and late["processing_status"] == "rejected"


def test_system_status_events_broadcast_health_after_ingestion(test_client):
    register(test_client)
    with test_client.websocket_connect("/ws/dashboard") as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        response = test_client.post("/api/v1/events", json=event(
            experiment_id=None, step_id=None, event_type="SYSTEM_STATUS", event_id="system-status",
            status="unhealthy"))
        assert response.status_code == 200
        messages = [socket.receive_json() for _ in range(4)]
        assert any(message.get("type") == "system.health" for message in messages)
        alert = next(message["alert"] for message in messages if message.get("type") == "alert")
        assert alert["severity"] == "critical"


def test_camera_events_broadcast_health_state(test_client):
    register(test_client)
    with test_client.websocket_connect("/ws/dashboard") as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        for event_type, expected in (("CAMERA_DISCONNECTED", "camera_disconnected"),
                                     ("CAMERA_RECONNECTED", "camera_reconnected")):
            response = test_client.post("/api/v1/events", json=event(
                experiment_id=None, step_id=None, event_type=event_type, event_id=f"event-{event_type}"))
            assert response.status_code == 200
            messages = [socket.receive_json() for _ in range(4)]
            assert any(message.get("type") == "system.health" and message.get("status") == expected
                       for message in messages)


def test_deviation_event_broadcasts_deviation_alert(test_client):
    register(test_client)
    with test_client.websocket_connect("/ws/dashboard") as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        response = test_client.post("/api/v1/events", json=event(
            experiment_id=None, step_id=None, event_type="DEVIATION_DETECTED",
            event_id="deviation-broadcast", evidence={"description": "test deviation"}))
        assert response.status_code == 200
        messages = [socket.receive_json() for _ in range(4)]
        assert any(message.get("type") == "deviation.alert" and
                   message.get("event_id") == "deviation-broadcast" for message in messages)


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
    assert test_client.get("/api/v1/devices?status=unknown").status_code == 422
    assert test_client.get("/api/v1/experiments?status=unknown").status_code == 422
