from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class DeviceRegister(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    name: str = Field(default="Mock AI Device", max_length=200)
    device_type: str = Field(default="ai", max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceHeartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=100)
    status: Literal["online", "busy", "offline"] = "online"


class ExperimentCreate(BaseModel):
    experiment_id: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    protocol_id: str = "demo-wetlab"
    protocol_version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    event_id: str = Field(min_length=1, max_length=150)
    source: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=100)
    experiment_id: str | None = Field(default=None, max_length=100)
    timestamp: datetime
    event_type: Literal[
        "HEARTBEAT", "STEP_STARTED", "STEP_COMPLETED", "DEVIATION_DETECTED",
        "CAMERA_DISCONNECTED", "CAMERA_RECONNECTED", "NEEDS_REVIEW", "SYSTEM_STATUS"
    ]
    step_id: str | None = Field(default=None, max_length=100)
    step_name: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=30)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    rack_coordinates: dict[str, float] | None = None
    requires_review: bool = False

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


class BatchEvents(BaseModel):
    events: list[EventContract] = Field(min_length=1, max_length=100)


class AcknowledgeRequest(BaseModel):
    operator_id: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=2000)


class ProtocolCreate(BaseModel):
    protocol_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    steps: list[dict[str, Any]] = Field(min_length=1)


class Pagination(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class APIError(BaseModel):
    error: dict[str, Any]
