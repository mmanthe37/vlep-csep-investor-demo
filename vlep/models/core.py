"""
VLEP ORM — ``core`` schema.

Tables: patients, cohorts, cohort_memberships.
Source: migration 002_core_ingestion_ontology_nosology_base.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vlep.models.base import Base


class Patient(Base):
    """Pseudonymous patient identity in the ``core`` schema."""

    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("source_patient_hash", name="uq_patients_source_hash"),
        {"schema": "core"},
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_patient_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sex_at_birth: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    race_ethnicity: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    deceased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    cohort_memberships: Mapped[list[CohortMembership]] = relationship(
        back_populates="patient", cascade="all, delete-orphan",
    )


class Cohort(Base):
    """Patient cohort definition in the ``core`` schema."""

    __tablename__ = "cohorts"
    __table_args__ = (
        UniqueConstraint("name", name="uq_cohorts_name"),
        {"schema": "core"},
    )

    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    inclusion_criteria: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    exclusion_criteria: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    memberships: Mapped[list[CohortMembership]] = relationship(
        back_populates="cohort", cascade="all, delete-orphan",
    )


class CohortMembership(Base):
    """Links patients to cohorts in the ``core`` schema."""

    __tablename__ = "cohort_memberships"
    __table_args__ = {"schema": "core"}

    cohort_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.cohorts.cohort_id", ondelete="CASCADE"),
        primary_key=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        primary_key=True,
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    # Relationships
    patient: Mapped[Patient] = relationship(back_populates="cohort_memberships")
    cohort: Mapped[Cohort] = relationship(back_populates="memberships")
