import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.models import ExperimentProtocol
from modules.experiment_engine.engine import ProtocolDefinition


def load_default_protocol(path: Path) -> tuple[ProtocolDefinition, dict]:
    raw = json.loads(json.dumps(__import__("yaml").safe_load(path.read_text(encoding="utf-8"))))
    return ProtocolDefinition.from_yaml(path), raw


def ensure_protocol(db: Session, path: Path) -> ProtocolDefinition:
    protocol, raw = load_default_protocol(path)
    record = db.get(ExperimentProtocol, (protocol.protocol_id, protocol.version))
    if not record:
        record = ExperimentProtocol(protocol_id=protocol.protocol_id, version=protocol.version,
            name=protocol.name, description=raw.get("notice", ""), definition_json=json.dumps(raw))
        db.add(record)
        try:
            db.commit()
        except Exception:
            db.rollback()
            record = db.get(ExperimentProtocol, (protocol.protocol_id, protocol.version))
            if not record:
                raise
    stored = json.loads(record.definition_json)
    return ProtocolDefinition(
        protocol_id=record.protocol_id,
        version=record.version,
        name=record.name,
        steps=sorted(stored["steps"], key=lambda step: step["sequence"]),
        minimum_confidence=float(stored.get("minimum_confidence", 0.60)),
    )
