"""
MongoDB Seeder for SUTRA Backend.
Populates initial collections with default protocol, AI device registry, and initial experiment run.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import yaml

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import pymongo
from app.config import settings


def seed_mongodb():
    print(f"Connecting to MongoDB at {settings.mongodb_url}...")
    try:
        client = pymongo.MongoClient(settings.mongodb_url, serverSelectionTimeoutMS=settings.mongodb_timeout_ms)
        client.admin.command("ping")
        db = client[settings.mongodb_db]
        print(f"Connected to database: {settings.mongodb_db}")
    except Exception as e:
        print(f"[ERROR] Failed to connect to MongoDB: {e}")
        return False

    # 1. Seed AI Device
    devices_col = db["devices"]
    ai_device = {
        "device_id": "ai-device-01",
        "name": "SUTRA On-Board AI Vision Engine",
        "device_type": "ai-vision",
        "status": "online",
        "token_hash": "",
        "registered_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "model": "YOLOv8 + Kinematic Pose Tracker",
            "source": "camera-0",
            "fps_target": 15.0
        }
    }
    devices_col.update_one({"device_id": "ai-device-01"}, {"$set": ai_device}, upsert=True)
    print("[OK] Seeded device: ai-device-01")

    # 2. Seed Default Protocol
    protocol_path = settings.protocol_path
    if not protocol_path.is_absolute() and not protocol_path.exists():
        protocol_path = backend_dir / protocol_path

    if protocol_path.exists():
        content = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
        protocol_doc = {
            "protocol_id": content.get("protocol_id", "demo-wetlab"),
            "version": str(content.get("version", "1.0")),
            "name": content.get("name", "Demo Wetlab Protocol"),
            "description": content.get("description", "Standard wetlab procedure"),
            "definition": content,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        db["protocols"].update_one(
            {"protocol_id": protocol_doc["protocol_id"], "version": protocol_doc["version"]},
            {"$set": protocol_doc},
            upsert=True
        )
        print(f"[OK] Seeded protocol: {protocol_doc['protocol_id']} v{protocol_doc['version']}")

    # 3. Seed Initial Demo Experiment
    exp_col = db["experiments"]
    exp_doc = {
        "experiment_id": "DEMO-WETLAB-01",
        "name": "Demo Wetlab Protocol Run",
        "protocol_id": "demo-wetlab",
        "protocol_version": "1.0",
        "status": "running",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"operator": "Lab Supervisor", "run_type": "automated"}
    }
    exp_col.update_one({"experiment_id": "DEMO-WETLAB-01"}, {"$set": exp_doc}, upsert=True)
    print("[OK] Seeded active experiment: DEMO-WETLAB-01")

    # Display counts
    print("-" * 50)
    print("MongoDB Collection Status:")
    for col_name in ["devices", "protocols", "experiments", "telemetry_events", "deviations"]:
        print(f"  * {col_name:20s}: {db[col_name].count_documents({})} documents")
    print("-" * 50)
    print("Seeding completed successfully!")
    return True


if __name__ == "__main__":
    seed_mongodb()
