"""Independent API client exercising registration, lifecycle, duplicates and invalid events."""
import argparse
import json
from datetime import datetime, timezone
from uuid import uuid4
import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--device-id", default="mock-ai-01")
    parser.add_argument("--experiment-id", default="mock-experiment-01")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=10) as client:
        print("register", client.post("/api/v1/devices/register", json={"device_id": args.device_id, "name": "SUTRA mock AI"}).json())
        print("heartbeat", client.post("/api/v1/devices/heartbeat", json={"device_id": args.device_id}).json())
        print("experiment", client.post("/api/v1/experiments", json={"experiment_id": args.experiment_id, "name": "Independent Mock Run"}).json())
        print("start", client.post(f"/api/v1/experiments/{args.experiment_id}/start").json())
        def event(kind: str, step: str | None = None, evidence: dict | None = None) -> dict:
            return {"schema_version": "1.0", "event_id": str(uuid4()), "source": "sutra-ai-engine",
                    "device_id": args.device_id, "experiment_id": args.experiment_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": kind,
                    "step_id": step, "status": "COMPLETED" if kind == "STEP_COMPLETED" else None,
                    "confidence": 0.96 if step else None, "evidence": evidence or {}}
        for kind in ("STEP_STARTED", "STEP_COMPLETED"):
            payload = event(kind, "STEP_01")
            first = client.post("/api/v1/events", json=payload)
            print(kind, first.status_code, first.json())
            if kind == "STEP_STARTED":
                repeat = client.post("/api/v1/events", json=payload)
                print("duplicate", repeat.status_code, repeat.json())
        for kind in ("DEVIATION_DETECTED", "NEEDS_REVIEW"):
            response = client.post("/api/v1/events", json=event(kind, evidence={"description": f"Mock {kind} for integration check"}))
            print(kind, response.status_code, response.json())
        invalid = client.post("/api/v1/events", json={"schema_version": "9", "event_type": "NOT_REAL"})
        print("invalid rejection", invalid.status_code, invalid.json())
        print("deviations", json.dumps(client.get("/api/v1/deviations").json(), indent=2))


if __name__ == "__main__":
    main()
