from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"
    device_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    device_type: Mapped[str] = mapped_column(String(80), default="ai")
    token_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30), default="offline", index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class Experiment(Base):
    __tablename__ = "experiments"
    experiment_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    protocol_id: Mapped[str] = mapped_column(String(100), index=True)
    protocol_version: Mapped[str] = mapped_column(String(40), default="1.0")
    status: Mapped[str] = mapped_column(String(30), default="created", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class ExperimentProtocol(Base):
    __tablename__ = "experiment_protocols"
    protocol_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    definition_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExperimentStep(Base):
    __tablename__ = "experiment_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.experiment_id"), index=True)
    step_id: Mapped[str] = mapped_column(String(100))
    step_name: Mapped[str] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (UniqueConstraint("experiment_id", "step_id", name="uq_experiment_step"),)


class TelemetryEvent(Base):
    __tablename__ = "telemetry_events"
    event_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    schema_version: Mapped[str] = mapped_column(String(20), default="1.0")
    source: Mapped[str] = mapped_column(String(100))
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    step_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(String(30), default="accepted")
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (Index("ix_events_received_type", "received_at", "event_type"),)


class ActivityRecord(Base):
    __tablename__ = "activity_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("telemetry_events.event_id"), unique=True)
    experiment_id: Mapped[str] = mapped_column(String(100), index=True)
    step_id: Mapped[str] = mapped_column(String(100), index=True)
    activity: Mapped[str] = mapped_column(String(50))
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DeviationRecord(Base):
    __tablename__ = "deviation_records"
    deviation_id: Mapped[str] = mapped_column(String(150), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(150), index=True)
    experiment_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    device_id: Mapped[str] = mapped_column(String(100), index=True)
    category: Mapped[str] = mapped_column(String(80))
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    description: Mapped[str] = mapped_column(Text)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SystemLog(Base):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class OperatorAcknowledgement(Base):
    __tablename__ = "operator_acknowledgements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deviation_id: Mapped[str] = mapped_column(ForeignKey("deviation_records.deviation_id"), unique=True)
    operator_id: Mapped[str] = mapped_column(String(100))
    note: Mapped[str] = mapped_column(Text, default="")
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
