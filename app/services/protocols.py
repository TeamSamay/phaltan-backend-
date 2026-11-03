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
        db.add(ExperimentProtocol(protocol_id=protocol.protocol_id, version=protocol.version,
            name=protocol.name, description=raw.get("notice", ""), definition_json=json.dumps(raw)))
        db.commit()
    return protocol
