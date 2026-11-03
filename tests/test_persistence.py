from tests.conftest import create_running_experiment, event, register


def test_data_survives_database_session_restart(test_client):
    register(test_client); create_running_experiment(test_client)
    payload = event(event_id="persist-me")
    assert test_client.post("/api/v1/events", json=payload).status_code == 200
    # Each request uses a fresh SQLAlchemy Session from the shared SQLite test database.
    assert test_client.get("/api/v1/events/persist-me").json()["event_id"] == "persist-me"
    assert test_client.get("/api/v1/experiments/test-exp").json()["status"] == "running"
