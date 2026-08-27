"""
VLEP ORM — ``csep`` schema.

Tables: profiles, profile_assertion_trace, profile_event_trace, profile_claim_trace.
Source: migration 006_lpa_modeling_csep.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vlep.models.base import Base


class CSEPProfile(Base):
    """Current-State Epilepsy Profile (CSEP) — a multidimensional versioned snapshot."""

    __tablename__ = "profiles"
    __table_args__ = (
        UniqueConstraint("patient_id", "as_of_time", "nosology_version_id", "model_version_id", name="uq_profiles_patient_asof_nosology_model"),
        {"schema": "csep"},
    )

    csep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.model_versions.model_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    lpa_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.lpa_runs.lpa_run_id", ondelete="SET NULL"),
        nullable=True,
    )
    seizure_type_distribution: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    etiology_ranked_confidence: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    epilepsy_syndrome: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    biomarker_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    comorbidity_burden: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    treatment_response: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    predictive_outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    uncertainty: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    profile_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ProfileAssertionTrace(Base):
    """Traceability mapping linking CSEP profiles to their supporting assertions."""

    __tablename__ = "profile_assertion_trace"
    __table_args__ = {"schema": "csep"}

    csep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="CASCADE"),
        primary_key=True,
    )
    assertion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    trace_role: Mapped[str] = mapped_column(Text, nullable=False, server_default="supporting")
    contribution_weight: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)


class ProfileEventTrace(Base):
    """Traceability mapping linking CSEP profiles directly to their underlying ledger events."""

    __tablename__ = "profile_event_trace"
    __table_args__ = {"schema": "csep"}

    csep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    trace_role: Mapped[str] = mapped_column(Text, nullable=False, server_default="supporting")


class ProfileClaimTrace(Base):
    """Traceability mapping linking CSEP profiles to their biomedical literature priors."""

    __tablename__ = "profile_claim_trace"
    __table_args__ = {"schema": "csep"}

    csep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="CASCADE"),
        primary_key=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    trace_role: Mapped[str] = mapped_column(Text, nullable=False, server_default="literature_prior")
    contribution_weight: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
