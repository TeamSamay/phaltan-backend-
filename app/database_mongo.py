"""
MongoDB Database Connection and Lifecycle Management for SUTRA Backend.
Uses Motor for async operations and PyMongo for synchronous/script access.
"""

from __future__ import annotations

import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import pymongo
from pymongo import MongoClient

from app.config import settings

logger = logging.getLogger("sutra.mongo")


class MongoManager:
    def __init__(self) -> None:
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
        self.sync_client: Optional[MongoClient] = None
        self.is_connected: bool = False

    async def connect(self) -> bool:
        """Initialize async Motor connection and create necessary indexes."""
        if not settings.mongodb_enabled:
            logger.info("MongoDB is disabled in settings.")
            return False

        try:
            self.client = AsyncIOMotorClient(
                settings.mongodb_url,
                serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
                uuidRepresentation="standard"
            )
            # Verify connectivity with ping
            await self.client.admin.command("ping")
            self.db = self.client[settings.mongodb_db]
            self.is_connected = True
            logger.info("Connected successfully to MongoDB at %s (database: %s)", settings.mongodb_url, settings.mongodb_db)

            # Ensure indexes in background
            await self._ensure_indexes()
            return True
        except Exception as e:
            self.is_connected = False
            logger.warning("Could not connect to MongoDB (%s): %s. Running in fallback mode.", settings.mongodb_url, e)
            return False

    async def _ensure_indexes(self) -> None:
        """Create high-performance indexes for events, deviations, and experiments."""
        if self.db is None:
            return

        try:
            # 1. Telemetry Events Collection
            events_col = self.db["telemetry_events"]
            await events_col.create_index([("event_id", pymongo.ASCENDING)], unique=True)
            await events_col.create_index([("timestamp", pymongo.DESCENDING)])
            await events_col.create_index([("experiment_id", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)])
            await events_col.create_index([("event_type", pymongo.ASCENDING)])
            await events_col.create_index([("device_id", pymongo.ASCENDING)])

            # 2. Deviations Collection
            dev_col = self.db["deviations"]
            await dev_col.create_index([("deviation_id", pymongo.ASCENDING)], unique=True)
            await dev_col.create_index([("experiment_id", pymongo.ASCENDING)])
            await dev_col.create_index([("severity", pymongo.ASCENDING)])
            await dev_col.create_index([("acknowledged", pymongo.ASCENDING)])
            await dev_col.create_index([("created_at", pymongo.DESCENDING)])

            # 3. Devices Collection
            devices_col = self.db["devices"]
            await devices_col.create_index([("device_id", pymongo.ASCENDING)], unique=True)
            await devices_col.create_index([("status", pymongo.ASCENDING)])

            # 4. Experiments Collection
            exp_col = self.db["experiments"]
            await exp_col.create_index([("experiment_id", pymongo.ASCENDING)], unique=True)
            await exp_col.create_index([("status", pymongo.ASCENDING)])

            # 5. Protocols Collection
            proto_col = self.db["protocols"]
            await proto_col.create_index([("protocol_id", pymongo.ASCENDING), ("version", pymongo.ASCENDING)], unique=True)

            # 6. AI Engine Execution Runs Collection
            runs_col = self.db["ai_engine_runs"]
            await runs_col.create_index([("run_id", pymongo.ASCENDING)], unique=True)
            await runs_col.create_index([("started_at", pymongo.DESCENDING)])

            # 7. System Logs Collection
            logs_col = self.db["system_logs"]
            await logs_col.create_index([("created_at", pymongo.DESCENDING)])
            await logs_col.create_index([("level", pymongo.ASCENDING)])

            logger.info("MongoDB collections and indexes ensured successfully.")
        except Exception as e:
            logger.warning("Failed to configure MongoDB indexes: %s", e)

    async def disconnect(self) -> None:
        """Close Motor client connections."""
        if self.client:
            self.client.close()
            self.is_connected = False
            logger.info("MongoDB connection closed.")
        if self.sync_client:
            self.sync_client.close()

    def get_sync_db(self) -> Optional[pymongo.database.Database]:
        """Provides a synchronous pymongo database for scripts/workers."""
        if not settings.mongodb_enabled:
            return None
        if not self.sync_client:
            try:
                self.sync_client = MongoClient(
                    settings.mongodb_url,
                    serverSelectionTimeoutMS=settings.mongodb_timeout_ms
                )
            except Exception as e:
                logger.warning("Sync pymongo connection error: %s", e)
                return None
        return self.sync_client[settings.mongodb_db]


mongo_manager = MongoManager()


async def get_mongo_db() -> Optional[AsyncIOMotorDatabase]:
    """Dependency / accessor for async FastAPI route handlers."""
    if not mongo_manager.is_connected or mongo_manager.db is None:
        return None
    return mongo_manager.db
