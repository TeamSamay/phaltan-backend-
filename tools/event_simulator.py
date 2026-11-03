"""Emit a complete five-step demo run. Run the backend before invoking."""
import argparse
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx

STEPS = ["STEP_01", "STEP_02", "STEP_03", "STEP_04", "STEP_05"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--device-id", default="simulator-01")
    parser.add_argument("--delay", type=float, default=0.25)
    args = parser.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=10) as client:
        client.post("/api/v1/devices/register", json={"device_id": args.device_id, "name": "SUTRA Event Simulator"}).raise_for_status()
        experiment = client.post("/api/v1/experiments", json={"name": "Simulated Five-Step Demo"}).json()
        exp_id = experiment["experiment_id"]
        client.post(f"/api/v1/experiments/{exp_id}/start").raise_for_status()
        for step in STEPS:
            for kind in ("STEP_STARTED", "STEP_COMPLETED"):
                event = {"schema_version": "1.0", "event_id": str(uuid4()), "source": "sutra-ai-engine",
                         "device_id": args.device_id, "experiment_id": exp_id,
                         "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": kind,
                         "step_id": step, "confidence": 0.94, "evidence": {"simulated": True}}
                response = client.post("/api/v1/events", json=event)
                print(response.status_code, response.json())
                response.raise_for_status()
                time.sleep(args.delay)
        print("Completed:", client.get(f"/api/v1/experiments/{exp_id}").json())


if __name__ == "__main__":
    main()
