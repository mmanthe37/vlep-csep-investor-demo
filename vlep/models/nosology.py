"""
VLEP ORM — ``nosology`` schema.

Tables: framework_versions, taxonomy_terms, taxonomy_edges,
        resolution_rules, reinterpretation_jobs, reinterpretation_results.
Source: migrations 002_core_ingestion_ontology_nosology_base.sql & 006_lpa_modeling_csep.sql
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from vlep.models.base import Base
from vlep.models.phenotyping import phenotype_dimension_enum


class FrameworkVersion(Base):
    """Versioned nosological taxonomy release (e.g. ILAE 2017 baseline)."""

    __tablename__ = "framework_versions"
    __table_args__ = (
        UniqueConstraint("framework_name", "version_label", name="uq_framework_versions_name_label"),
        {"schema": "nosology"},
    )

    nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    framework_name: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    authority: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    ruleset_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class TaxonomyTerm(Base):
    """Individual terms within a versioned nosological framework."""

    __tablename__ = "taxonomy_terms"
    __table_args__ = (
        UniqueConstraint("nosology_version_id", "dimension", "code", name="uq_taxonomy_terms_version_dim_code"),
        {"schema": "nosology"},
    )

    taxonomy_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    dimension: Mapped[str] = mapped_column(phenotype_dimension_enum, nullable=False)  # Enum value (phenotype_dimension)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    display: Mapped[str] = mapped_column(Text, nullable=False)
    parent_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="SET NULL"),
        nullable=True,
    )
    definition: Mapped[str | None] = mapped_column(Text, nullable=True)
    age_constraints: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    rule_expression: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class TaxonomyEdge(Base):
    """Hierarchical parent-child relationships between taxonomy terms."""

    __tablename__ = "taxonomy_edges"
    __table_args__ = (
        UniqueConstraint("parent_term_id", "child_term_id", "relation", name="uq_taxonomy_edges_parent_child_rel"),
        {"schema": "nosology"},
    )

    taxonomy_edge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.taxonomy_terms.taxonomy_term_id", ondelete="CASCADE"),
        nullable=False,
    )
    child_term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.taxonomy_terms.taxonomy_term_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False, server_default="is_a")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ResolutionRule(Base):
    """Rules specifying how phenotype conflicts are resolved under a specific framework."""

    __tablename__ = "resolution_rules"
    __table_args__ = (
        UniqueConstraint("nosology_version_id", "rule_name", name="uq_resolution_rules_version_name"),
        {"schema": "nosology"},
    )

    resolution_rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(Text, nullable=False)
    applies_to_dimension: Mapped[str | None] = mapped_column(phenotype_dimension_enum, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    rule_expression: Mapped[dict] = mapped_column(JSONB, nullable=False)
    action: Mapped[dict] = mapped_column(JSONB, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ReinterpretationJob(Base):
    """Queued jobs to run a framework conversion (e.g. forward-reversioning)."""

    __tablename__ = "reinterpretation_jobs"
    __table_args__ = {"schema": "nosology"}

    reinterpretation_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_nosology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    target_nosology_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.cohorts.cohort_id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ReinterpretationResult(Base):
    """Records the results/diffs for each patient after reinterpretation."""

    __tablename__ = "reinterpretation_results"
    __table_args__ = {"schema": "nosology"}

    reinterpretation_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    reinterpretation_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.reinterpretation_jobs.reinterpretation_job_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_csep_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_csep_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    changes_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
