"""
VLEP ORM — ``ingestion`` schema.

Tables: source_systems, ingestion_runs, raw_resources.
Source: migration 002_core_ingestion_ontology_nosology_base.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vlep.models.base import Base

# Enums
source_system_kind_enum = ENUM(
    "FHIR_R4",
    "OMOP_CDM",
    "BULK_FHIR",
    "CDS_HOOKS",
    "SMART_ON_FHIR",
    "PATIENT_PORTAL",
    "MOBILE_DIARY",
    "EEG_SYSTEM",
    "IMAGING_SYSTEM",
    "GENETICS_LAB",
    "LITERATURE_API",
    "MANUAL_UPLOAD",
    "OTHER",
    name="source_system_kind",
    schema="ingestion",
)

ingestion_status_enum = ENUM(
    "RECEIVED",
    "NORMALIZED",
    "QUARANTINED",
    "FAILED",
    "COMPLETED",
    name="ingestion_status",
    schema="ingestion",
)


class SourceSystem(Base):
    """External data source registration in the ``ingestion`` schema."""

    __tablename__ = "source_systems"
    __table_args__ = (
        UniqueConstraint("name", name="uq_source_systems_name"),
        {"schema": "ingestion"},
    )

    source_system_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(source_system_kind_enum, nullable=False)
    base_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    owning_institution: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        back_populates="source_system",
    )


class IngestionRun(Base):
    """Tracks a batch ingestion execution in the ``ingestion`` schema."""

    __tablename__ = "ingestion_runs"
    __table_args__ = {"schema": "ingestion"}

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_system_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.source_systems.source_system_id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(ingestion_status_enum, nullable=False, server_default="RECEIVED")
    input_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    records_received: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_normalized: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    records_quarantined: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    source_system: Mapped[SourceSystem | None] = relationship(
        back_populates="ingestion_runs",
    )
    raw_resources: Mapped[list[RawResource]] = relationship(
        back_populates="ingestion_run",
    )


class RawResource(Base):
    """Raw ingested resource pointer in the ``ingestion`` schema."""

    __tablename__ = "raw_resources"
    __table_args__ = {"schema": "ingestion"}

    raw_resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.ingestion_runs.ingestion_run_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_system_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.source_systems.source_system_id", ondelete="SET NULL"),
        nullable=True,
    )
    external_resource_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    resource_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="SET NULL"),
        nullable=True,
    )
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    object_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(ingestion_status_enum, nullable=False, server_default="RECEIVED")
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    ingestion_run: Mapped[IngestionRun | None] = relationship(
        back_populates="raw_resources",
    )
