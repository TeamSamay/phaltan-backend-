import json
import logging
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.models import (ActivityRecord, DeviationRecord, Device, Experiment, ExperimentProtocol, ExperimentStep,
                               OperatorAcknowledgement, SystemLog, TelemetryEvent)
from app.schemas.schemas import EventContract
from app.websocket.manager import manager
from app.services.alerts import make_alert
from modules.experiment_engine.engine import ExperimentEngine, ProtocolDefinition

logger = logging.getLogger(__name__)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def ingest_event(db: Session, event: EventContract, engine: ExperimentEngine) -> dict:
    duplicate = db.get(TelemetryEvent, event.event_id)
    if duplicate:
        return {"event_id": event.event_id, "accepted": duplicate.processing_status == "accepted", "duplicate": True,
                "processing_status": duplicate.processing_status, "processing_error": duplicate.processing_error}
    device = db.get(Device, event.device_id)
    if not device:
        raise ValueError(f"Device {event.device_id} is not registered")
    now = datetime.now(timezone.utc)
    device.last_seen_at, device.status = now, "online"
    experiment = db.get(Experiment, event.experiment_id) if event.experiment_id else None
    protocol_error = None
    if experiment:
        stored_protocol = db.get(ExperimentProtocol, (experiment.protocol_id, experiment.protocol_version))
        if not stored_protocol:
            protocol_error = "Experiment references an unavailable protocol version"
        else:
            try:
                protocol_definition = json.loads(stored_protocol.definition_json)
                engine = ExperimentEngine(ProtocolDefinition(
                    protocol_id=experiment.protocol_id,
                    version=experiment.protocol_version,
                    name=stored_protocol.name,
                    steps=sorted(protocol_definition["steps"], key=lambda step: step["sequence"]),
                    minimum_confidence=float(protocol_definition.get("minimum_confidence", 0.60)),
                ))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                protocol_error = f"Experiment protocol definition is invalid: {exc}"
    event_record = TelemetryEvent(
        event_id=event.event_id, schema_version=event.schema_version, source=event.source,
        device_id=event.device_id, experiment_id=event.experiment_id, timestamp=_aware(event.timestamp),
        received_at=now, event_type=event.event_type, step_id=event.step_id, status=event.status,
        confidence=event.confidence, payload_json=event.model_dump_json(), processing_status="accepted")
    db.add(event_record)
    alert = None
    experiment_completed = False
    try:
        if protocol_error:
            event_record.processing_status = "rejected"
            event_record.processing_error = protocol_error
        if event.experiment_id and not experiment:
            event_record.processing_status = "rejected"
            event_record.processing_error = f"Experiment {event.experiment_id} not found"
        if event.experiment_id and not experiment:
            dev = DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                experiment_id=event.experiment_id, device_id=event.device_id, category="unknown_experiment",
                severity="warning", description=event_record.processing_error or "Experiment not found",
                details_json=event.model_dump_json())
            db.add(dev)
            alert = make_alert("warning", "Experiment not found", event_record.processing_error or
                               "Event references an unknown experiment", "warning",
                               event.experiment_id, event.event_id)
        elif event.experiment_id and protocol_error:
            db.add(DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                experiment_id=event.experiment_id, device_id=event.device_id,
                category="unknown_protocol", severity="warning",
                description=event_record.processing_error or "Protocol validation unavailable",
                details_json=event.model_dump_json()))
            alert = make_alert("warning", "Protocol unavailable", event_record.processing_error or
                               "Experiment protocol validation is unavailable", "warning",
                               event.experiment_id, event.event_id)
        latest_event = None
        if event.experiment_id:
            latest_event = db.scalars(
                select(TelemetryEvent)
                .where(TelemetryEvent.experiment_id == event.experiment_id,
                      TelemetryEvent.event_id != event.event_id,
                      TelemetryEvent.processing_status == "accepted")
                .order_by(desc(TelemetryEvent.timestamp))
                .limit(1)
            ).first()
        timestamp_error = None
        if latest_event and _aware(event.timestamp) < _aware(latest_event.timestamp):
            timestamp_error = "Event timestamp is earlier than the latest recorded experiment event"
        if _aware(event.timestamp) > now and (_aware(event.timestamp) - now).total_seconds() > 300:
            timestamp_error = "Event timestamp is more than five minutes in the future"
        if timestamp_error and event_record.processing_status != "rejected":
            event_record.processing_status, event_record.processing_error = "rejected", timestamp_error
            db.add(DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                experiment_id=event.experiment_id, device_id=event.device_id, category="late_event",
                severity="warning", description=timestamp_error, details_json=event.model_dump_json()))
            alert = make_alert("warning", "Event timestamp out of order", timestamp_error,
                               "warning", event.experiment_id, event.event_id)
        if event_record.processing_status == "rejected":
            if alert is None and (event.experiment_id or event.requires_review):
                alert = make_alert("warning", "Event rejected", event_record.processing_error or
                                   "Event did not pass experiment validation", "warning",
                                   event.experiment_id, event.event_id)
        elif event.experiment_id and experiment and event.event_type in {"STEP_STARTED", "STEP_COMPLETED"}:
            if event.requires_review:
                error = "Step transition requires operator review and was not applied"
                event_record.processing_status, event_record.processing_error = "rejected", error
                db.add(DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                    experiment_id=event.experiment_id, device_id=event.device_id,
                    category="needs_review", severity="warning", description=error,
                    details_json=event.model_dump_json()))
                alert = make_alert("low_confidence_review", "Operator review required", error,
                                   "warning", event.experiment_id, event.event_id)
            elif experiment.status != "running":
                error = f"Experiment is not running (status: {experiment.status})"
                event_record.processing_status, event_record.processing_error = "rejected", error
                db.add(DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                    experiment_id=event.experiment_id, device_id=event.device_id,
                    category="experiment_completed" if experiment.status == "completed" else "experiment_not_running",
                    severity="warning", description=error,
                    details_json=event.model_dump_json()))
                alert = make_alert("warning", "Experiment is not accepting step events", error,
                                   "warning", event.experiment_id, event.event_id)
            else:
                steps = db.scalars(select(ExperimentStep).where(ExperimentStep.experiment_id == event.experiment_id).order_by(ExperimentStep.sequence)).all()
                states = [{"step_id": item.step_id, "status": item.status} for item in steps]
                valid, code, error = engine.validate(event.event_type, event.step_id, event.confidence, states)
                if not valid:
                    event_record.processing_status, event_record.processing_error = "rejected", error
                    dev = DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                        experiment_id=event.experiment_id, device_id=event.device_id, category=code or "protocol_violation",
                        severity="critical" if code in {"out_of_order", "unknown_step"} else "warning",
                        description=error or "Protocol validation failed", details_json=event.model_dump_json())
                    db.add(dev)
                    alert = make_alert("critical_deviation" if dev.severity == "critical" else "warning",
                        "Protocol deviation", dev.description, dev.severity, event.experiment_id, event.event_id)
                else:
                    step = next(item for item in steps if item.step_id == event.step_id)
                    if event.event_type == "STEP_STARTED":
                        step.status, step.started_at = "started", _aware(event.timestamp)
                        alert = make_alert("step_started", "Step started", step.step_name, "info", event.experiment_id, event.event_id)
                    else:
                        step.status, step.completed_at, step.confidence = "completed", _aware(event.timestamp), event.confidence
                        db.add(ActivityRecord(event_id=event.event_id, experiment_id=event.experiment_id,
                            step_id=event.step_id, activity="STEP_COMPLETED", confidence=event.confidence,
                            occurred_at=_aware(event.timestamp)))
                        alert = make_alert("step_completed", "Step completed", step.step_name, "info", event.experiment_id, event.event_id)
                        if all(item.status == "completed" for item in steps):
                            experiment.status, experiment.stopped_at = "completed", now
                            experiment_completed = True
        elif event.event_type == "DEVIATION_DETECTED" or event.event_type == "NEEDS_REVIEW" or event.requires_review:
            description = str(event.evidence.get("description", event.status or "Review required"))
            dev = DeviationRecord(deviation_id=f"dev-{uuid4().hex}", event_id=event.event_id,
                experiment_id=event.experiment_id, device_id=event.device_id,
                category="needs_review" if event.event_type == "NEEDS_REVIEW" else "ai_deviation",
                severity="warning", description=description, details_json=event.model_dump_json())
            db.add(dev)
            alert = make_alert("low_confidence_review" if event.event_type == "NEEDS_REVIEW" else "warning",
                "Review required" if event.event_type == "NEEDS_REVIEW" else "Deviation detected",
                description, "warning", event.experiment_id, event.event_id)
        elif event.event_type == "CAMERA_DISCONNECTED":
            alert = make_alert("camera_disconnected", "Camera disconnected", "AI device reported camera disconnection", "warning", event.experiment_id, event.event_id)
        elif event.event_type == "CAMERA_RECONNECTED":
            alert = make_alert("camera_reconnected", "Camera reconnected", "AI device reported camera reconnection", "info", event.experiment_id, event.event_id)
        elif event.event_type == "SYSTEM_STATUS":
            reported_status = (event.status or "reported").strip().lower()
            health_severity = "critical" if reported_status in {"error", "critical", "unhealthy", "offline"} else "info"
            alert = make_alert("system_health", "System health update",
                event.status or "Device reported a system status update", health_severity,
                event.experiment_id, event.event_id)
        elif event.event_type == "HEARTBEAT":
            alert = None
        db.add(SystemLog(level="INFO", message="event_ingested", context_json=json.dumps({"event_id": event.event_id, "type": event.event_type})))
        db.commit()
    except IntegrityError:
        db.rollback()
        try:
            duplicate = db.get(TelemetryEvent, event.event_id)
            if duplicate:
                return {"event_id": event.event_id, "accepted": duplicate.processing_status == "accepted",
                        "duplicate": True, "processing_status": duplicate.processing_status,
                        "processing_error": duplicate.processing_error}
        except Exception:
            db.rollback()
        logger.exception("Database integrity failure while ingesting event_id=%s", event.event_id)
        raise
    except Exception:
        db.rollback()
        logger.exception("Event ingestion failed for event_id=%s", event.event_id)
        raise
    if experiment_completed and experiment:
        await manager.broadcast({"type": "experiment.status", "experiment_id": experiment.experiment_id, "status": "completed"})
    summary = {"type": "event.new", "event": {"event_id": event.event_id, "event_type": event.event_type,
        "device_id": event.device_id, "experiment_id": event.experiment_id, "step_id": event.step_id,
        "timestamp": event.timestamp.isoformat(), "processing_status": event_record.processing_status}}
    await manager.broadcast(summary)
    if alert:
        await manager.broadcast({"type": "alert", "alert": alert})
        if alert.get("category") == "system_health":
            await manager.broadcast({"type": "system.health", "status": event.status or "reported",
                                    "device_id": event.device_id})
        elif alert.get("category") == "camera_disconnected":
            await manager.broadcast({"type": "system.health", "status": "camera_disconnected",
                                     "device_id": event.device_id})
        elif alert.get("category") == "camera_reconnected":
            await manager.broadcast({"type": "system.health", "status": "camera_reconnected",
                                     "device_id": event.device_id})
        elif alert.get("category") == "critical_deviation":
            await manager.broadcast({"type": "deviation.alert", "severity": alert["severity"],
                                     "experiment_id": event.experiment_id,
                                     "event_id": event.event_id, "title": alert["title"],
                                     "description": alert["description"]})
        elif alert.get("severity") == "warning" and event.event_type in {"DEVIATION_DETECTED", "NEEDS_REVIEW"}:
            await manager.broadcast({"type": "deviation.alert", "severity": "warning",
                                     "experiment_id": event.experiment_id,
                                     "event_id": event.event_id, "title": alert["title"],
                                     "description": alert["description"]})
    await manager.broadcast({"type": "device.heartbeat", "device_id": event.device_id, "status": "online"})
    return {"event_id": event.event_id, "accepted": event_record.processing_status == "accepted",
            "duplicate": False, "processing_status": event_record.processing_status,
            "processing_error": event_record.processing_error}
