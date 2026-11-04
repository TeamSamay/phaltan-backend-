from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml


@dataclass(frozen=True)
class ProtocolDefinition:
    protocol_id: str
    version: str
    name: str
    steps: list[dict[str, Any]]
    minimum_confidence: float = 0.60

    @classmethod
    def from_yaml(cls, path: Path) -> "ProtocolDefinition":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            protocol_id=data["protocol_id"], version=str(data["version"]), name=data["name"],
            steps=sorted(data["steps"], key=lambda step: step["sequence"]),
            minimum_confidence=float(data.get("minimum_confidence", 0.60)),
        )


class ExperimentEngine:
    """Deterministic state transition rules; validates claims but does not inspect video."""

    def __init__(self, protocol: ProtocolDefinition):
        self.protocol = protocol
        self.step_by_id = {step["step_id"]: step for step in protocol.steps}

    def validate(self, event_type: str, step_id: str | None, confidence: float | None,
                 step_states: list[dict[str, Any]]) -> tuple[bool, str | None, str | None]:
        if event_type not in {"STEP_STARTED", "STEP_COMPLETED"}:
            return True, None, None
        if not step_id or step_id not in self.step_by_id:
            return False, "unknown_step", f"Unknown or missing step_id: {step_id!r}"
        step = self.step_by_id[step_id]
        if confidence is None or confidence < self.protocol.minimum_confidence:
            value = "missing" if confidence is None else f"{confidence:.2f}"
            return False, "low_confidence", f"Confidence {value} is below required {self.protocol.minimum_confidence:.2f}"
        states = {item["step_id"]: item for item in step_states}
        prior_steps = [item for item in self.protocol.steps if item["sequence"] < step["sequence"]]
        if any(states.get(item["step_id"], {}).get("status") != "completed" for item in prior_steps):
            return False, "out_of_order", f"Step {step_id} arrived before all preceding steps were completed"
        current = states.get(step_id, {}).get("status", "pending")
        if event_type == "STEP_STARTED" and current == "started":
            return False, "duplicate_transition", f"Step {step_id} has already been started"
        if event_type == "STEP_STARTED" and current == "completed":
            return False, "late_event", f"Cannot start already completed step {step_id}"
        if event_type == "STEP_STARTED" and current != "pending":
            return False, "invalid_transition", f"Cannot start step {step_id} from state {current}"
        if event_type == "STEP_COMPLETED" and current != "started":
            return False, "invalid_transition", f"Step {step_id} must be started before completion (current: {current})"
        return True, None, None
