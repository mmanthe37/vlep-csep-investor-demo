"""
VLEP ORM — ``governance`` schema.

Tables: access_logs, alert_events, data_quality_runs, model_drift_runs.
Source: migration 007_review_validation_governance.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vlep.models.base import Base

alert_severity_enum = ENUM(
    'passive',
    'low',
    'moderate',
    'high',
    'critical',
    name='alert_severity',
    schema='governance',
)


class AccessLog(Base):
    """Governance audit logs capturing patient-level data accesses (HIPAA compliance)."""

    __tablename__ = "access_logs"
    __table_args__ = {"schema": "governance"}

    access_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    actor_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_schema: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_table: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="SET NULL"),
        nullable=True,
    )
    access_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class AlertEvent(Base):
    """Clinical alerts triggered during phenotyping or nosology updates."""

    __tablename__ = "alert_events"
    __table_args__ = {"schema": "governance"}

    alert_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=True,
    )
    csep_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="SET NULL"),
        nullable=True,
    )
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(alert_severity_enum, nullable=False)  # Enum (alert_severity)
    interruptive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    displayed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    @property
    def acknowledged(self) -> bool:
        return self.acknowledged_at is not None


class DataQualityRun(Base):
    """Executes and records automated checks for clinical data anomalies."""

    __tablename__ = "data_quality_runs"
    __table_args__ = {"schema": "governance"}

    data_quality_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    run_name: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    findings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ModelDriftRun(Base):
    """Monitors model predictive performance and demographic fairness drift over time."""

    __tablename__ = "model_drift_runs"
    __table_args__ = {"schema": "governance"}

    model_drift_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.model_versions.model_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.cohorts.cohort_id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drift_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    fairness_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
