from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import new_device_token, token_hash, validate_device_token
from app.core.logging import configure_logging
from app.database import SessionLocal, get_db, init_db
from app.database_mongo import mongo_manager, get_mongo_db
from app.models.models import (ActivityRecord, DeviationRecord, Device, Experiment, ExperimentProtocol,
                               ExperimentStep, OperatorAcknowledgement, SystemLog, TelemetryEvent)
from app.schemas.schemas import (AcknowledgeRequest, BatchEvents, DeviceHeartbeat, DeviceRegister,
                                 EventContract, ExperimentCreate, ProtocolCreate,
                                 EngineStartRequest, EngineStopRequest)
from app.services.alerts import make_alert
from app.services.ingestion import ingest_event
from app.services.protocols import ensure_protocol
from app.services.rate_limit import RateLimiter
from app.services.process_manager import process_manager
from app.services.mongo_service import (
    get_mongo_stats, get_telemetry_events as mongo_get_events,
    get_deviations as mongo_get_deviations, get_ai_engine_runs,
    upsert_protocol, upsert_device
)
from app.websocket.manager import manager
from modules.experiment_engine.engine import ExperimentEngine, ProtocolDefinition

configure_logging()
logger = logging.getLogger("sutra")


@asynccontextmanager
async def lifespan(application: FastAPI):
    # 1. Initialize relational database (SQLite/PostgreSQL)
    init_db()

    # 2. Connect to MongoDB
    await mongo_manager.connect()

    # 3. Seed default protocol and pre-register AI engine device
    with SessionLocal() as db:
        proto = ensure_protocol(db, settings.protocol_path)
        # Pre-register default AI engine device for zero-friction ingestion
        ai_dev = db.get(Device, "ai-device-01")
        if not ai_dev:
            ai_dev = Device(
                device_id="ai-device-01",
                name="SUTRA On-board AI Vision Engine",
                device_type="ai-vision",
                token_hash="",
                status="online",
                metadata_json=json.dumps({"capabilities": ["yolo_v8", "pose_tracking", "fsm_protocol_guardian"]})
            )
            db.add(ai_dev)
            try:
                db.commit()
            except Exception:
                db.rollback()

        # Sync protocol and device to MongoDB if connected
        try:
            if mongo_manager.is_connected:
                definition = json.loads(proto.definition_json) if isinstance(proto.definition_json, str) else proto.definition_json
                await upsert_protocol({
                    "protocol_id": proto.protocol_id,
                    "version": proto.version,
                    "name": proto.name,
                    "description": proto.description,
                    "definition": definition
                })
                await upsert_device({
                    "device_id": "ai-device-01",
                    "name": "SUTRA On-board AI Vision Engine",
                    "device_type": "ai-vision",
                    "status": "online"
                })
        except Exception as e:
            logger.debug("Mongo initial sync note: %s", e)

    yield

    # Clean shutdown
    logger.info("Shutting down SUTRA backend...")
    process_manager.stop()
    await mongo_manager.disconnect()


app = FastAPI(
    title="SUTRA Backend & AI Engine Hub",
    version="1.0.0",
    description="Event ingestion, MongoDB document ledger, and AI Engine process supervisor",
    lifespan=lifespan
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"]
)
app.state.request_limiter = RateLimiter(settings.rate_limit_per_minute)


def current_engine(db: Session) -> ExperimentEngine:
    protocol = ensure_protocol(db, settings.protocol_path)
    return ExperimentEngine(protocol)


def pagination(items, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def iso(value):
    return value.isoformat() if value else None


@app.middleware("http")
async def request_controls(request: Request, call_next):
    if int(request.headers.get("content-length", "0") or 0) > settings.max_request_bytes:
        return __import__("fastapi").responses.JSONResponse(
            status_code=413,
            content={"error": {"code": "request_too_large", "message": "Request body exceeds configured limit"}}
        )
    if request.url.path.startswith("/api/"):
        try:
            key = request.client.host if request.client else "unknown"
            request.app.state.request_limiter.check(key)
        except HTTPException as exc:
            return __import__("fastapi").responses.JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request exception")
        response = __import__("fastapi").responses.JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "Internal server error"}}
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    from fastapi.responses import JSONResponse
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "http_error", "message": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"error": {
        "code": "validation_error", "message": "Request validation failed",
        "details": jsonable_encoder(exc.errors()),
    }})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "sutra-backend",
        "version": app.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mongodb_connected": mongo_manager.is_connected,
        "ai_engine_running": process_manager.is_running
    }


@app.get("/api/v1/system/status")
def system_status(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "environment": settings.environment,
        "mongodb_connected": mongo_manager.is_connected,
        "ai_engine_running": process_manager.is_running,
        "devices_online": db.query(Device).filter(Device.status == "online").count(),
        "active_experiments": db.query(Experiment).filter(Experiment.status == "running").count(),
        "websocket_clients": len(manager.active)
    }


# ============================================================================
# DEVICE REGISTRATION & HEARTBEAT
# ============================================================================

@app.post("/api/v1/devices/register")
def register_device(body: DeviceRegister, db: Session = Depends(get_db)):
    device = db.get(Device, body.device_id)
    token = new_device_token() if not settings.dev_auth else "development-mode"
    if not device:
        device = Device(
            device_id=body.device_id, name=body.name, device_type=body.device_type,
            token_hash=token_hash(token) if not settings.dev_auth else "", status="offline",
            metadata_json=json.dumps(body.metadata)
        )
        db.add(device)
    else:
        device.name, device.device_type = body.name, body.device_type
        device.metadata_json = json.dumps(body.metadata)
        if not settings.dev_auth:
            device.token_hash = token_hash(token)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(device)
    return {
        "device_id": device.device_id,
        "status": device.status,
        "auth_mode": "development" if settings.dev_auth else "token",
        "device_token": token if not settings.dev_auth else None
    }


@app.post("/api/v1/devices/heartbeat")
async def device_heartbeat(body: DeviceHeartbeat, db: Session = Depends(get_db), x_device_token: str | None = Header(default=None)):
    device = db.get(Device, body.device_id)
    if not device:
        raise HTTPException(404, detail={"code": "device_not_found", "message": "Register device first"})
    validate_device_token(db, body.device_id, x_device_token)
    device.last_seen_at, device.status = datetime.now(timezone.utc), body.status
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(device)
    await manager.broadcast({"type": "device.heartbeat", "device_id": device.device_id, "status": device.status, "timestamp": iso(device.last_seen_at)})
    return {"device_id": device.device_id, "status": device.status, "last_seen_at": iso(device.last_seen_at)}


@app.get("/api/v1/devices")
def list_devices(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Device)
    if status:
        if status not in {"online", "busy", "offline"}:
            raise HTTPException(422, detail={"code": "invalid_device_status", "message": "status must be online, busy, or offline"})
        query = query.filter(Device.status == status)
    total = query.count()
    items = query.order_by(Device.device_id).offset(offset).limit(limit).all()
    return pagination([{"device_id": x.device_id, "name": x.name, "device_type": x.device_type, "status": x.status, "last_seen_at": iso(x.last_seen_at)} for x in items], total, limit, offset)


@app.get("/api/v1/devices/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db)):
    x = db.get(Device, device_id)
    if not x:
        raise HTTPException(404, detail={"code": "device_not_found", "message": "Device not found"})
    return {"device_id": x.device_id, "name": x.name, "device_type": x.device_type, "status": x.status, "registered_at": iso(x.registered_at), "last_seen_at": iso(x.last_seen_at), "metadata": json.loads(x.metadata_json)}


# ============================================================================
# EXPERIMENT MANAGEMENT
# ============================================================================

@app.post("/api/v1/experiments", status_code=201)
async def create_experiment(body: ExperimentCreate, db: Session = Depends(get_db)):
    ensure_protocol(db, settings.protocol_path)
    protocol_id, version = body.protocol_id, body.protocol_version
    protocol_record = db.get(ExperimentProtocol, (protocol_id, version))
    if not protocol_record:
        raise HTTPException(404, detail={"code": "protocol_not_found", "message": "Protocol version not found"})
    experiment_id = body.experiment_id or f"exp-{uuid4().hex[:12]}"
    if db.get(Experiment, experiment_id):
        raise HTTPException(409, detail={"code": "experiment_exists", "message": "Experiment ID already exists"})
    record = Experiment(experiment_id=experiment_id, name=body.name, protocol_id=protocol_id,
                        protocol_version=version, status="created", metadata_json=json.dumps(body.metadata))
    db.add(record)
    definition = json.loads(db.get(ExperimentProtocol, (protocol_id, version)).definition_json)
    for step in definition["steps"]:
        db.add(ExperimentStep(experiment_id=experiment_id, step_id=step["step_id"], step_name=step["name"], sequence=step["sequence"], status="pending"))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(record)
    return {"experiment_id": experiment_id, "name": record.name, "protocol_id": protocol_id, "protocol_version": version, "status": record.status, "created_at": iso(record.created_at)}


@app.get("/api/v1/experiments")
def list_experiments(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), status: str | None = None, sort: str = Query("created_at", pattern="^(created_at|name|status)$"), db: Session = Depends(get_db)):
    query = db.query(Experiment)
    if status:
        if status not in {"created", "running", "stopped", "completed"}:
            raise HTTPException(422, detail={"code": "invalid_experiment_status", "message": "status must be created, running, stopped, or completed"})
        query = query.filter(Experiment.status == status)
    total = query.count()
    column = getattr(Experiment, sort)
    ordering = column.asc() if sort == "name" else desc(column)
    rows = query.order_by(ordering).offset(offset).limit(limit).all()
    return pagination([{"experiment_id": x.experiment_id, "name": x.name, "status": x.status, "protocol_id": x.protocol_id, "created_at": iso(x.created_at)} for x in rows], total, limit, offset)


@app.get("/api/v1/experiments/current")
def current_experiment(db: Session = Depends(get_db)):
    x = db.query(Experiment).filter(Experiment.status == "running").order_by(desc(Experiment.started_at)).first()
    return {"experiment": None if not x else {"experiment_id": x.experiment_id, "name": x.name, "status": x.status, "started_at": iso(x.started_at)}}


@app.get("/api/v1/experiments/{experiment_id}")
def get_experiment(experiment_id: str, db: Session = Depends(get_db)):
    x = db.get(Experiment, experiment_id)
    if not x:
        raise HTTPException(404, detail={"code": "experiment_not_found", "message": "Experiment not found"})
    steps = db.scalars(select(ExperimentStep).where(ExperimentStep.experiment_id == experiment_id).order_by(ExperimentStep.sequence)).all()
    return {"experiment_id": x.experiment_id, "name": x.name, "status": x.status, "protocol_id": x.protocol_id, "protocol_version": x.protocol_version, "created_at": iso(x.created_at), "started_at": iso(x.started_at), "stopped_at": iso(x.stopped_at), "steps": [{"step_id": s.step_id, "step_name": s.step_name, "sequence": s.sequence, "status": s.status, "started_at": iso(s.started_at), "completed_at": iso(s.completed_at), "confidence": s.confidence} for s in steps]}


@app.post("/api/v1/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: str, db: Session = Depends(get_db)):
    x = db.get(Experiment, experiment_id)
    if not x:
        raise HTTPException(404, detail={"code": "experiment_not_found", "message": "Experiment not found"})
    if x.status == "running":
        raise HTTPException(409, detail={"code": "already_running", "message": "Experiment is already running"})
    if x.status == "completed":
        raise HTTPException(409, detail={"code": "already_completed", "message": "Completed experiment cannot be restarted"})
    x.status, x.started_at, x.stopped_at = "running", datetime.now(timezone.utc), None
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(x)
    await manager.broadcast({"type": "experiment.status", "experiment_id": x.experiment_id, "status": x.status})
    return {"experiment_id": x.experiment_id, "status": x.status, "started_at": iso(x.started_at)}


@app.post("/api/v1/experiments/{experiment_id}/stop")
async def stop_experiment(experiment_id: str, db: Session = Depends(get_db)):
    x = db.get(Experiment, experiment_id)
    if not x:
        raise HTTPException(404, detail={"code": "experiment_not_found", "message": "Experiment not found"})
    if x.status != "running":
        raise HTTPException(409, detail={"code": "not_running", "message": "Only running experiments can be stopped"})
    x.status, x.stopped_at = "stopped", datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(x)
    await manager.broadcast({"type": "experiment.status", "experiment_id": x.experiment_id, "status": x.status})
    return {"experiment_id": x.experiment_id, "status": x.status, "stopped_at": iso(x.stopped_at)}


# ============================================================================
# EVENT INGESTION & SUTRA AI ENGINE TELEMETRY BRIDGE
# ============================================================================

@app.post("/api/v1/events")
async def post_event(body: EventContract, request: Request, db: Session = Depends(get_db), x_device_token: str | None = Header(default=None)):
    validate_device_token(db, body.device_id, x_device_token)
    try:
        result = await ingest_event(db, body, current_engine(db))
        return result
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "event_rejected", "message": str(exc)}) from exc


@app.post("/api/v1/telemetry/events")
async def post_telemetry_event_bridge(body: EventContract, db: Session = Depends(get_db), x_device_token: str | None = Header(default=None)):
    """Direct compatibility endpoint for Sutra AI Engine publisher."""
    validate_device_token(db, body.device_id, x_device_token)
    try:
        result = await ingest_event(db, body, current_engine(db))
        return {
            "acknowledged": True,
            "event_id": body.event_id,
            "is_duplicate": result.get("duplicate", False),
            "accepted": result.get("accepted", True),
            "processing_status": result.get("processing_status", "accepted")
        }
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "event_rejected", "message": str(exc)}) from exc


@app.get("/api/v1/telemetry/events")
def get_telemetry_events_bridge(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Retrieve stored events for Sutra AI Engine test assertions."""
    query = db.query(TelemetryEvent).order_by(desc(TelemetryEvent.timestamp)).limit(limit)
    rows = query.all()
    events = [json.loads(x.payload_json) for x in rows]
    return {"count": len(events), "events": events}


@app.post("/api/v1/telemetry/reset")
def reset_telemetry_ledger(db: Session = Depends(get_db)):
    """Reset telemetry records for test runs."""
    count = db.query(TelemetryEvent).delete()
    db.commit()
    return {"status": "RESET", "cleared_events": count}


@app.post("/api/v1/events/batch")
async def post_events_batch(body: BatchEvents, db: Session = Depends(get_db), x_device_token: str | None = Header(default=None)):
    results = []
    engine = current_engine(db)
    for event in body.events:
        validate_device_token(db, event.device_id, x_device_token)
        try:
            results.append(await ingest_event(db, event, engine))
        except ValueError as exc:
            results.append({"event_id": event.event_id, "accepted": False, "error": str(exc)})
    return {"items": results, "total": len(results)}


@app.get("/api/v1/events")
def list_events(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), event_type: str | None = None, experiment_id: str | None = None, device_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(TelemetryEvent)
    for attr, value in (("event_type", event_type), ("experiment_id", experiment_id), ("device_id", device_id)):
        if value:
            query = query.filter(getattr(TelemetryEvent, attr) == value)
    total = query.count()
    rows = query.order_by(desc(TelemetryEvent.timestamp)).offset(offset).limit(limit).all()
    return pagination([{"event_id": x.event_id, "event_type": x.event_type, "device_id": x.device_id, "experiment_id": x.experiment_id, "step_id": x.step_id, "timestamp": iso(x.timestamp), "received_at": iso(x.received_at), "processing_status": x.processing_status, "processing_error": x.processing_error} for x in rows], total, limit, offset)


@app.get("/api/v1/events/{event_id}")
def get_event(event_id: str, db: Session = Depends(get_db)):
    x = db.get(TelemetryEvent, event_id)
    if not x:
        raise HTTPException(404, detail={"code": "event_not_found", "message": "Event not found"})
    return {"event_id": x.event_id, "event_type": x.event_type, "device_id": x.device_id, "experiment_id": x.experiment_id, "timestamp": iso(x.timestamp), "received_at": iso(x.received_at), "processing_status": x.processing_status, "processing_error": x.processing_error, "payload": json.loads(x.payload_json)}


# ============================================================================
# SUTRA AI ENGINE PROCESS SUPERVISOR API
# ============================================================================

@app.post("/api/v1/engine/start")
async def start_ai_engine(req: EngineStartRequest):
    """Start the Sutra AI Engine as a background process managed by FastAPI."""
    res = process_manager.start(
        mode=req.mode,
        source=req.source,
        publish=req.publish,
        headless=req.headless,
        frames=req.frames,
        port=req.port
    )
    if not res.get("success"):
        raise HTTPException(400, detail={"code": "engine_start_failed", "message": res.get("message")})
    await manager.broadcast({"type": "engine.started", "mode": req.mode, "pid": res.get("pid")})
    return res


@app.post("/api/v1/engine/stop")
async def stop_ai_engine(req: EngineStopRequest = EngineStopRequest()):
    """Terminate the running Sutra AI Engine process."""
    res = process_manager.stop(force=req.force)
    await manager.broadcast({"type": "engine.stopped", "status": res.get("status")})
    return res


@app.get("/api/v1/engine/status")
def get_ai_engine_status():
    """Retrieve live metrics, CPU/memory usage, and status of the AI Engine."""
    return process_manager.get_status()


@app.get("/api/v1/engine/logs")
def get_ai_engine_logs(limit: int = Query(100, ge=1, le=500)):
    """Fetch recent standard output and error lines from the AI Engine."""
    return {"lines": process_manager.get_logs(max_lines=limit)}


@app.get("/api/v1/engine/runs")
async def list_ai_engine_runs(limit: int = Query(20, ge=1, le=100)):
    """Retrieve history of AI engine process executions from MongoDB."""
    runs = await get_ai_engine_runs(limit=limit)
    return {"runs": runs, "total": len(runs)}


# ============================================================================
# MONGODB DOCUMENT QUERY API
# ============================================================================

@app.get("/api/v1/mongo/stats")
async def mongo_system_stats():
    """Retrieve overall storage document counts and database metrics from MongoDB."""
    return await get_mongo_stats()


@app.get("/api/v1/mongo/events")
async def mongo_list_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str | None = None,
    experiment_id: str | None = None,
    device_id: str | None = None
):
    """Directly query event documents from MongoDB."""
    q: dict[str, Any] = {}
    if event_type: q["event_type"] = event_type
    if experiment_id: q["experiment_id"] = experiment_id
    if device_id: q["device_id"] = device_id

    items, total = await mongo_get_events(q, limit, offset)
    return pagination(items, total, limit, offset)


@app.get("/api/v1/mongo/deviations")
async def mongo_list_deviations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    severity: str | None = None,
    acknowledged: bool | None = None
):
    """Directly query deviation records from MongoDB."""
    q: dict[str, Any] = {}
    if severity: q["severity"] = severity
    if acknowledged is not None: q["acknowledged"] = acknowledged

    items, total = await mongo_get_deviations(q, limit, offset)
    return pagination(items, total, limit, offset)


# ============================================================================
# PROTOCOLS & TIMELINES & DEVIATIONS
# ============================================================================

@app.get("/api/v1/protocols")
def list_protocols(db: Session = Depends(get_db)):
    rows = db.query(ExperimentProtocol).order_by(ExperimentProtocol.protocol_id, ExperimentProtocol.version).all()
    return {"items": [{"protocol_id": x.protocol_id, "version": x.version, "name": x.name, "description": x.description} for x in rows], "total": len(rows)}


@app.post("/api/v1/protocols", status_code=201)
def create_protocol(body: ProtocolCreate, db: Session = Depends(get_db)):
    if db.get(ExperimentProtocol, (body.protocol_id, body.version)):
        raise HTTPException(409, detail={"code": "protocol_exists", "message": "Protocol/version already exists"})
    steps = [step.model_dump() for step in body.steps]
    row = ExperimentProtocol(protocol_id=body.protocol_id, version=body.version, name=body.name,
        description=body.description, definition_json=json.dumps({"steps": steps, "protocol_id": body.protocol_id, "version": body.version, "name": body.name}))
    db.add(row); db.commit()
    db.refresh(row)
    return {"protocol_id": row.protocol_id, "version": row.version, "name": row.name}


@app.get("/api/v1/protocols/{protocol_id}")
def get_protocol(protocol_id: str, version: str = "1.0", db: Session = Depends(get_db)):
    ensure_protocol(db, settings.protocol_path)
    x = db.get(ExperimentProtocol, (protocol_id, version))
    if not x:
        raise HTTPException(404, detail={"code": "protocol_not_found", "message": "Protocol not found"})
    return {"protocol_id": x.protocol_id, "version": x.version, "name": x.name, "description": x.description, "definition": json.loads(x.definition_json)}


@app.get("/api/v1/experiments/{experiment_id}/timeline")
def experiment_timeline(experiment_id: str, limit: int = Query(200, ge=1, le=500), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if not db.get(Experiment, experiment_id):
        raise HTTPException(404, detail={"code": "experiment_not_found", "message": "Experiment not found"})
    query = db.query(TelemetryEvent).filter(TelemetryEvent.experiment_id == experiment_id)
    total = query.count(); rows = query.order_by(TelemetryEvent.timestamp).offset(offset).limit(limit).all()
    return pagination([{"event_id": x.event_id, "event_type": x.event_type, "step_id": x.step_id, "timestamp": iso(x.timestamp), "processing_status": x.processing_status, "processing_error": x.processing_error} for x in rows], total, limit, offset)


@app.get("/api/v1/deviations")
def list_deviations(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), acknowledged: bool | None = None, db: Session = Depends(get_db)):
    query = db.query(DeviationRecord)
    if acknowledged is not None: query = query.filter(DeviationRecord.acknowledged == acknowledged)
    total = query.count(); rows = query.order_by(desc(DeviationRecord.created_at)).offset(offset).limit(limit).all()
    return pagination([{"deviation_id": x.deviation_id, "event_id": x.event_id, "experiment_id": x.experiment_id, "category": x.category, "severity": x.severity, "description": x.description, "acknowledged": x.acknowledged, "created_at": iso(x.created_at)} for x in rows], total, limit, offset)


@app.post("/api/v1/deviations/{deviation_id}/acknowledge")
async def acknowledge_deviation(deviation_id: str, body: AcknowledgeRequest, db: Session = Depends(get_db)):
    x = db.get(DeviationRecord, deviation_id)
    if not x:
        raise HTTPException(404, detail={"code": "deviation_not_found", "message": "Deviation not found"})
    if x.acknowledged:
        raise HTTPException(409, detail={"code": "already_acknowledged", "message": "Deviation already acknowledged"})
    now = datetime.now(timezone.utc)
    x.acknowledged, x.acknowledged_by, x.acknowledged_at = True, body.operator_id, now
    db.add(OperatorAcknowledgement(deviation_id=deviation_id, operator_id=body.operator_id, note=body.note, acknowledged_at=now))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    await manager.broadcast({"type": "deviation.acknowledged", "deviation_id": deviation_id, "operator_id": body.operator_id})
    return {"deviation_id": deviation_id, "acknowledged": True, "acknowledged_at": iso(now)}


@app.get("/api/v1/system/metrics")
def system_metrics():
    process = psutil.Process()
    return {"cpu_percent": psutil.cpu_percent(interval=None), "memory_percent": psutil.virtual_memory().percent,
            "process_memory_bytes": process.memory_info().rss, "process_cpu_percent": process.cpu_percent(interval=None)}


@app.get("/api/v1/system/logs")
def system_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), level: str | None = None, db: Session = Depends(get_db)):
    query = db.query(SystemLog)
    if level: query = query.filter(SystemLog.level == level.upper())
    total = query.count(); rows = query.order_by(desc(SystemLog.created_at)).offset(offset).limit(limit).all()
    return pagination([{"id": x.id, "level": x.level, "message": x.message, "context": json.loads(x.context_json), "created_at": iso(x.created_at)} for x in rows], total, limit, offset)


@app.websocket("/ws/dashboard")
async def dashboard_socket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connection.ready",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "heartbeat_interval_seconds": 30,
            "engine_status": process_manager.get_status()
        })
        while True:
            message = await websocket.receive_text()
            if message.lower() in {"ping", "heartbeat"}:
                await websocket.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
        logger.info("Dashboard websocket disconnected")
