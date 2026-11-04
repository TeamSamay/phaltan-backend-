import json
from contextlib import asynccontextmanager
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models.models import ExperimentProtocol
from app.services.rate_limit import RateLimiter


@pytest.fixture()
def test_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        definition = {
            "protocol_id": "demo-wetlab", "version": "1.0", "name": "Demo Five-Step Wet-Lab Protocol",
            "steps": [
                {"step_id": f"STEP_0{i}", "name": f"Demo Step {i}", "sequence": i}
                for i in range(1, 6)
            ],
        }
        db.add(ExperimentProtocol(protocol_id="demo-wetlab", version="1.0", name="Demo protocol",
                                  description="mock", definition_json=json.dumps(definition)))
        db.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    original_lifespan = app.router.lifespan_context
    original_limiter = app.state.request_limiter if hasattr(app.state, "request_limiter") else None
    app.state.request_limiter = RateLimiter(limit=10000)
    @asynccontextmanager
    async def no_lifespan(application):
        yield

    app.router.lifespan_context = no_lifespan
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.router.lifespan_context = original_lifespan
        if original_limiter is None:
            del app.state.request_limiter
        else:
            app.state.request_limiter = original_limiter
        Base.metadata.drop_all(engine)
        engine.dispose()


def register(client: TestClient, device_id="test-device"):
    return client.post("/api/v1/devices/register", json={"device_id": device_id, "name": "Test Device"})


def create_running_experiment(client: TestClient, experiment_id="test-exp"):
    response = client.post("/api/v1/experiments", json={"experiment_id": experiment_id, "name": "Test Experiment"})
    assert response.status_code == 201
    assert client.post(f"/api/v1/experiments/{experiment_id}/start").status_code == 200
    return experiment_id


def event(device_id="test-device", experiment_id="test-exp", event_type="STEP_STARTED", step_id="STEP_01", event_id="evt-1", **extra):
    from datetime import datetime, timezone
    payload = {"schema_version": "1.0", "event_id": event_id, "source": "sutra-ai-engine",
               "device_id": device_id, "experiment_id": experiment_id,
               "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": event_type,
               "step_id": step_id, "confidence": 0.95, "evidence": {}}
    payload.update(extra)
    return payload
