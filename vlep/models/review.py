"""
VLEP ORM — ``review`` schema.

Tables: review_tasks, review_decisions, source_text_verifications,
        issue_reports, adjudications, validation_cohorts, validation_observations.
Source: migration 007_review_validation_governance.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vlep.models.base import Base

review_decision_enum = ENUM(
    'accept',
    'reject',
    'needs_revision',
    'escalate',
    'no_action',
    name='review_decision',
    schema='review',
)

alert_severity_enum = ENUM(
    'passive',
    'low',
    'moderate',
    'high',
    'critical',
    name='alert_severity',
    schema='governance',
)


class ReviewTask(Base):
    """Workflow task for human curators or clinicians to review evidence or models."""

    __tablename__ = "review_tasks"
    __table_args__ = {"schema": "review"}

    review_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    task_type: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        nullable=True,
    )
    assertion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="CASCADE"),
        nullable=True,
    )
    csep_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="CASCADE"),
        nullable=True,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ReviewDecision(Base):
    """The outcome of a review task."""

    __tablename__ = "review_decisions"
    __table_args__ = {"schema": "review"}

    review_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    review_task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review.review_tasks.review_task_id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(review_decision_enum, nullable=False)  # Enum (review_decision)
    reviewer_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class SourceTextVerification(Base):
    """Validates the sentence offset and triple mapping of literature-extracted claims."""

    __tablename__ = "source_text_verifications"
    __table_args__ = {"schema": "review"}

    verification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        nullable=False,
    )
    verifier_id: Mapped[str] = mapped_column(Text, nullable=False)
    offset_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    triple_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    negation_temporal_context_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class IssueReport(Base):
    """User-reported issues or model discrepancies regarding clinical profiles."""

    __tablename__ = "issue_reports"
    __table_args__ = {"schema": "review"}

    issue_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    reporter_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(alert_severity_enum, nullable=False, server_default="moderate")  # Enum (alert_severity)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="SET NULL"),
        nullable=True,
    )
    assertion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="SET NULL"),
        nullable=True,
    )
    csep_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("csep.profiles.csep_id", ondelete="SET NULL"),
        nullable=True,
    )
    event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class Adjudication(Base):
    """Final clinical decision resolving an issue report."""

    __tablename__ = "adjudications"
    __table_args__ = {"schema": "review"}

    adjudication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    issue_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review.issue_reports.issue_report_id", ondelete="CASCADE"),
        nullable=True,
    )
    adjudicator_id: Mapped[str] = mapped_column(Text, nullable=False)
    adjudication_result: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ValidationCohort(Base):
    """Validation cohort registry representing human-adjudicated ground truth patient subsets."""

    __tablename__ = "validation_cohorts"
    __table_args__ = (
        UniqueConstraint("name", "validation_phase", name="uq_validation_cohorts_name_phase"),
        {"schema": "review"},
    )

    validation_cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.cohorts.cohort_id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    validation_phase: Mapped[str] = mapped_column(Text, nullable=False)
    n_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    n_actual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ValidationObservation(Base):
    """Clinician-adjudicated clinical endpoints for model validation."""

    __tablename__ = "validation_observations"
    __table_args__ = {"schema": "review"}

    validation_observation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    validation_cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review.validation_cohorts.validation_cohort_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    outcome_name: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    adjudicated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
