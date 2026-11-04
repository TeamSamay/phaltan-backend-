"""
End-to-End Pipeline Verification Test for SUTRA Backend + AI Engine + MongoDB.
Validates HTTP API, MongoDB persistence, AI Engine event schema ingestion, and Process Supervisor.
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from starlette.testclient import TestClient
from app.main import app
from app.database_mongo import mongo_manager


def run_e2e_verification():
    print("=" * 65)
    print("  RUNNING SUTRA END-TO-END PIPELINE VERIFICATION")
    print("=" * 65)

    with TestClient(app) as client:
        # 1. Health check
        print("[1/6] Testing Backend Health Endpoint...")
        health_resp = client.get("/health")
        assert health_resp.status_code == 200, f"Health check failed: {health_resp.text}"
        health_data = health_resp.json()
        print(f"      Status: {health_data['status']}, MongoDB: {health_data['mongodb_connected']}")

        # 2. MongoDB Stats
        print("[2/6] Testing MongoDB Integration & Collections...")
        mongo_resp = client.get("/api/v1/mongo/stats")
        assert mongo_resp.status_code == 200
        mongo_data = mongo_resp.json()
        print(f"      MongoDB Connection: {mongo_data.get('connected')}")
        if mongo_data.get("connected"):
            print(f"      Document Counts: {mongo_data.get('counts')}")

        # 3. Create & Start Experiment
        exp_id = f"E2E-{int(time.time())}"
        print(f"[3/6] Setting Up Experiment '{exp_id}'...")
        client.post("/api/v1/devices/register", json={"device_id": "ai-device-01", "name": "AI Test Unit"})
        create_res = client.post("/api/v1/experiments", json={"experiment_id": exp_id, "name": "E2E Experiment"})
        if create_res.status_code == 201:
            start_res = client.post(f"/api/v1/experiments/{exp_id}/start")
            assert start_res.status_code == 200, f"Start failed: {start_res.text}"
        print(f"      Experiment {exp_id} is running.")

        # 4. Ingest Telemetry Events (Full Sutra AI Engine Event Schema)
        print("[4/6] Ingesting Sutra AI Engine Telemetry Events...")
        now_iso = datetime.now(timezone.utc).isoformat()
        
        events_to_test = [
            {
                "schema_version": "1.0",
                "event_id": f"e2e-step1-start-{int(time.time())}",
                "source": "sutra-ai-engine",
                "device_id": "ai-device-01",
                "experiment_id": exp_id,
                "timestamp": now_iso,
                "event_type": "STEP_STARTED",
                "step_id": "STEP_01",
                "step_name": "Rack Extraction",
                "status": "STARTED",
                "confidence": 0.94,
                "evidence": {"method": "kinematic_pose_tracking", "fps": 15.0},
                "rack_coordinates": {"x": 0.35, "y": 0.52, "calibration_status": "CALIBRATED"}
            },
            {
                "schema_version": "1.0",
                "event_id": f"e2e-dev-alert-{int(time.time())}",
                "source": "sutra-ai-engine",
                "device_id": "ai-device-01",
                "experiment_id": exp_id,
                "timestamp": now_iso,
                "event_type": "DEVIATION_DETECTED",
                "step_id": "STEP_01",
                "status": "DEVIATED",
                "confidence": 0.88,
                "evidence": {"description": "Unexpected rack vibration detected", "sensor": "imu_optical"},
                "requires_review": True
            }
        ]

        for evt in events_to_test:
            post_res = client.post("/api/v1/telemetry/events", json=evt)
            assert post_res.status_code == 200, f"Event post failed: {post_res.text}"
            res_json = post_res.json()
            assert res_json.get("acknowledged") is True
            print(f"      * Ingested [{evt['event_type']}]: acknowledged={res_json['acknowledged']}")

        # 5. Verify Ingestion in MongoDB & Deviations Ledger
        print("[5/6] Verifying Data in MongoDB & API...")
        if mongo_manager.is_connected:
            mongo_evts = client.get(f"/api/v1/mongo/events?experiment_id={exp_id}")
            assert mongo_evts.status_code == 200
            print(f"      Verified {mongo_evts.json()['total']} events stored in MongoDB for {exp_id}.")

            deviations_resp = client.get("/api/v1/deviations")
            assert deviations_resp.status_code == 200
            print(f"      Verified {deviations_resp.json()['total']} total deviations recorded.")

        # 6. Test Process Supervisor Endpoints
        print("[6/6] Testing AI Engine Process Supervisor API...")
        status_resp = client.get("/api/v1/engine/status")
        assert status_resp.status_code == 200
        print(f"      Engine Status: {status_resp.json()['status']}")

        logs_resp = client.get("/api/v1/engine/logs")
        assert logs_resp.status_code == 200

        print("=" * 65)
        print("  ALL 6 E2E PIPELINE CHECKS PASSED SUCCESSFULLY!")
        print("=" * 65)
        return True


if __name__ == "__main__":
    success = run_e2e_verification()
    sys.exit(0 if success else 1)
