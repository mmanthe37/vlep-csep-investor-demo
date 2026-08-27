"""
VLEP ORM — ``evidence`` schema.

Tables: ledger_events, ledger_event_notes.
Source: migration 004_immutable_evidence_ledger.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vlep.models.base import Base

# Enums
ledger_domain_enum = ENUM(
    'clinical_observation',
    'medication_change',
    'EEG_biomarker',
    'imaging_biomarker',
    'genetic_result',
    'patient_reported_outcome',
    'literature_claim',
    'outcome_event',
    'model_output',
    'manual_review',
    'other',
    name='ledger_domain',
    schema='evidence',
)

source_attribution_enum = ENUM(
    'clinician',
    'automated_system',
    'patient_reported',
    'external_registry',
    'literature_pipeline',
    'model',
    'manual_curator',
    name='source_attribution',
    schema='evidence',
)

validation_status_enum = ENUM(
    'raw',
    'normalized',
    'verified',
    'disputed',
    'superseded',
    'rejected',
    name='validation_status',
    schema='evidence',
)


class LedgerEvent(Base):
    """Immutable evidence event — the atomic unit of clinical truth."""

    __tablename__ = "ledger_events"
    __table_args__ = {"schema": "evidence"}

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    event_seq: Mapped[int] = mapped_column(
        BigInteger, Identity(), nullable=False, unique=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    domain: Mapped[str] = mapped_column(
        ledger_domain_enum, nullable=False,
    )
    data_element: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
    )
    normalized_codes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="[]",
    )
    source_attribution: Mapped[str] = mapped_column(
        source_attribution_enum, nullable=False,
    )
    source_system_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.source_systems.source_system_id", ondelete="SET NULL"),
        nullable=True,
    )
    raw_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.raw_resources.raw_resource_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.documents.document_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="SET NULL"),
        nullable=True,
    )
    provenance: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    certainty_level: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="1.0",
    )
    validation_status: Mapped[str] = mapped_column(
        validation_status_enum, nullable=False, server_default="raw",
    )
    nosology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    supersedes_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="RESTRICT"),
        nullable=True,
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion.ingestion_runs.ingestion_run_id", ondelete="SET NULL"),
        nullable=True,
    )
    inserted_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Hash chain columns ──────────────────────────────────────────────────
    hash_prev: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    hash_self: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    # Relationships
    notes: Mapped[list[LedgerEventNote]] = relationship(
        back_populates="ledger_event", cascade="all, delete-orphan",
    )


class LedgerEventNote(Base):
    """Annotation on a ledger event."""

    __tablename__ = "ledger_event_notes"
    __table_args__ = {"schema": "evidence"}

    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="RESTRICT"),
        nullable=False,
    )
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    note_kind: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="curator_note",
    )
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    ledger_event: Mapped[LedgerEvent] = relationship(back_populates="notes")
