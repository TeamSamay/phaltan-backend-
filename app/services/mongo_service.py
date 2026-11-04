"""
MongoDB Service layer for SUTRA Backend.
Provides clean async document persistence and querying for telemetry, deviations,
protocols, devices, experiments, and AI engine execution logs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
import pymongo

from app.database_mongo import mongo_manager

logger = logging.getLogger("sutra.mongo_service")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_telemetry_event(event_data: dict[str, Any]) -> bool:
    """Store raw & processed telemetry event into MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["telemetry_events"]
        doc = dict(event_data)
        doc.setdefault("inserted_at", _utcnow_iso())
        # Use upsert based on event_id to prevent duplicates
        await col.update_one(
            {"event_id": doc["event_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to store telemetry event in MongoDB: %s", e)
        return False


async def get_telemetry_events(
    filter_query: Optional[dict[str, Any]] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve telemetry events with total count."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return [], 0
    try:
        col = mongo_manager.db["telemetry_events"]
        q = filter_query or {}
        total = await col.count_documents(q)
        cursor = col.find(q, {"_id": 0}).sort("timestamp", pymongo.DESCENDING).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        return items, total
    except Exception as e:
        logger.error("Failed to query telemetry events from MongoDB: %s", e)
        return [], 0


async def save_deviation_record(deviation_data: dict[str, Any]) -> bool:
    """Persist deviation event/record in MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["deviations"]
        doc = dict(deviation_data)
        doc.setdefault("created_at", _utcnow_iso())
        await col.update_one(
            {"deviation_id": doc["deviation_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to save deviation in MongoDB: %s", e)
        return False


async def get_deviations(
    filter_query: Optional[dict[str, Any]] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve deviations list from MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return [], 0
    try:
        col = mongo_manager.db["deviations"]
        q = filter_query or {}
        total = await col.count_documents(q)
        cursor = col.find(q, {"_id": 0}).sort("created_at", pymongo.DESCENDING).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        return items, total
    except Exception as e:
        logger.error("Failed to query deviations from MongoDB: %s", e)
        return [], 0


async def acknowledge_deviation_mongo(deviation_id: str, operator_id: str, note: str = "") -> bool:
    """Mark a deviation as acknowledged in MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["deviations"]
        now = _utcnow_iso()
        result = await col.update_one(
            {"deviation_id": deviation_id},
            {
                "$set": {
                    "acknowledged": True,
                    "acknowledged_by": operator_id,
                    "acknowledged_at": now,
                    "acknowledgement_note": note
                }
            }
        )
        return result.modified_count > 0
    except Exception as e:
        logger.error("Failed to acknowledge deviation in MongoDB: %s", e)
        return False


async def upsert_device(device_data: dict[str, Any]) -> bool:
    """Save or update device record in MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["devices"]
        doc = dict(device_data)
        doc.setdefault("updated_at", _utcnow_iso())
        await col.update_one(
            {"device_id": doc["device_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to upsert device in MongoDB: %s", e)
        return False


async def get_devices_mongo(
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """List devices from MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return [], 0
    try:
        col = mongo_manager.db["devices"]
        q = {"status": status_filter} if status_filter else {}
        total = await col.count_documents(q)
        cursor = col.find(q, {"_id": 0, "token_hash": 0}).sort("device_id", pymongo.ASCENDING).skip(offset).limit(limit)
        items = await cursor.to_list(length=limit)
        return items, total
    except Exception as e:
        logger.error("Failed to query devices from MongoDB: %s", e)
        return [], 0


async def upsert_experiment(exp_data: dict[str, Any]) -> bool:
    """Save or update experiment record in MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["experiments"]
        doc = dict(exp_data)
        doc.setdefault("updated_at", _utcnow_iso())
        await col.update_one(
            {"experiment_id": doc["experiment_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to upsert experiment in MongoDB: %s", e)
        return False


async def upsert_protocol(protocol_data: dict[str, Any]) -> bool:
    """Save or update protocol definition in MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["protocols"]
        doc = dict(protocol_data)
        await col.update_one(
            {"protocol_id": doc["protocol_id"], "version": doc.get("version", "1.0")},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to upsert protocol in MongoDB: %s", e)
        return False


async def record_ai_engine_run(run_info: dict[str, Any]) -> bool:
    """Track an execution run of the Sutra AI Engine process."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["ai_engine_runs"]
        doc = dict(run_info)
        doc.setdefault("recorded_at", _utcnow_iso())
        await col.update_one(
            {"run_id": doc["run_id"]},
            {"$set": doc},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("Failed to record AI engine run in MongoDB: %s", e)
        return False


async def get_ai_engine_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve history of AI engine executions."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return []
    try:
        col = mongo_manager.db["ai_engine_runs"]
        cursor = col.find({}, {"_id": 0}).sort("started_at", pymongo.DESCENDING).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception as e:
        logger.error("Failed to query AI engine runs from MongoDB: %s", e)
        return []


async def save_system_log(level: str, message: str, context: Optional[dict[str, Any]] = None) -> bool:
    """Save system audit log to MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return False
    try:
        col = mongo_manager.db["system_logs"]
        doc = {
            "level": level.upper(),
            "message": message,
            "context": context or {},
            "created_at": _utcnow_iso()
        }
        await col.insert_one(doc)
        return True
    except Exception as e:
        logger.error("Failed to save system log in MongoDB: %s", e)
        return False


async def get_mongo_stats() -> dict[str, Any]:
    """Provide overall document counts and storage metrics from MongoDB."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return {"connected": False, "status": "disconnected"}
    try:
        db = mongo_manager.db
        return {
            "connected": True,
            "database_name": db.name,
            "counts": {
                "telemetry_events": await db["telemetry_events"].count_documents({}),
                "deviations": await db["deviations"].count_documents({}),
                "devices": await db["devices"].count_documents({}),
                "experiments": await db["experiments"].count_documents({}),
                "protocols": await db["protocols"].count_documents({}),
                "ai_engine_runs": await db["ai_engine_runs"].count_documents({}),
                "system_logs": await db["system_logs"].count_documents({})
            }
        }
    except Exception as e:
        logger.error("Failed to gather MongoDB stats: %s", e)
        return {"connected": False, "error": str(e)}
