"""
VLEP ORM — ``phenotyping`` schema.

Tables: phenotype_assertions, assertion_support_events, assertion_support_claims,
        feature_sets, feature_definitions, feature_weight_priors,
        temporal_feature_windows, feature_values, patient_trajectory_snapshots.
Source: migration 005_phenotype_assertions_features.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
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

# Enums
phenotype_dimension_enum = ENUM(
    'seizure_type',
    'epilepsy_type',
    'syndrome',
    'etiology',
    'biomarker',
    'comorbidity',
    'treatment_response',
    'drug_resistance',
    'risk',
    'other',
    name='phenotype_dimension',
    schema='phenotyping',
)

assertion_status_enum = ENUM(
    'active',
    'conflicting',
    'superseded',
    'under_review',
    'rejected',
    name='assertion_status',
    schema='phenotyping',
)


class PhenotypeAssertion(Base):
    """Binds formal phenotype labels to patients with confidence scores."""

    __tablename__ = "phenotype_assertions"
    __table_args__ = {"schema": "phenotyping"}

    assertion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    phenotype_dimension: Mapped[str] = mapped_column(
        phenotype_dimension_enum, nullable=False,
    )  # Enum value
    phenotype_label_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="SET NULL"),
        nullable=True,
    )
    phenotype_label_text: Mapped[str] = mapped_column(Text, nullable=False)
    effective_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence_data_quality: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="0.0",
    )
    confidence_recency: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="0.0",
    )
    confidence_consistency: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default="0.0",
    )
    posterior_probability: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    final_score: Mapped[float] = mapped_column(
        Numeric(6, 5), nullable=False, server_default="0.0",
    )
    status: Mapped[str] = mapped_column(assertion_status_enum, nullable=False, server_default="active")
    generated_by: Mapped[str] = mapped_column(Text, nullable=False, server_default="assertion_builder")
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.model_versions.model_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    nosology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    supersedes_assertion_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    @property
    def dimension(self) -> str:
        return self.phenotype_dimension

    @property
    def phenotype_label(self) -> str:
        return self.phenotype_label_text

    @property
    def asserted_at(self) -> datetime:
        return self.created_at

    @property
    def certainty_level(self) -> float:
        return float(self.metadata_.get("certainty_level", float(self.final_score)))

    @property
    def phenotype_code(self) -> str:
        return str(self.metadata_.get("phenotype_code", ""))



class AssertionSupportEvent(Base):
    """Intersection table linking phenotype assertions to supporting ledger events."""

    __tablename__ = "assertion_support_events"
    __table_args__ = {"schema": "phenotyping"}

    assertion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="CASCADE"),
        primary_key=True,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evidence.ledger_events.event_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    support_role: Mapped[str] = mapped_column(Text, nullable=False, server_default="supporting")
    support_weight: Mapped[float] = mapped_column(
        Numeric(6, 5), nullable=False, server_default="1.0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class AssertionSupportClaim(Base):
    """Intersection table linking phenotype assertions to literature claims."""

    __tablename__ = "assertion_support_claims"
    __table_args__ = {"schema": "phenotyping"}

    assertion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.phenotype_assertions.assertion_id", ondelete="CASCADE"),
        primary_key=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    ruleset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.heuristic_rulesets.ruleset_id", ondelete="SET NULL"),
        nullable=True,
    )
    support_role: Mapped[str] = mapped_column(Text, nullable=False, server_default="literature_prior")
    support_weight: Mapped[float] = mapped_column(
        Numeric(6, 5), nullable=False, server_default="1.0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class FeatureSet(Base):
    """VLEP feature set definition defining vector dimensionality and windows."""

    __tablename__ = "feature_sets"
    __table_args__ = (
        UniqueConstraint("name", "version_label", name="uq_feature_sets_name_version"),
        {"schema": "phenotyping"},
    )

    feature_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.embedding_versions.embedding_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    ruleset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.heuristic_rulesets.ruleset_id", ondelete="SET NULL"),
        nullable=True,
    )
    dimensionality: Mapped[int] = mapped_column(Integer, nullable=False)
    window_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class FeatureDefinition(Base):
    """Maps index coordinates in a feature set vector to physical concepts and decay rules."""

    __tablename__ = "feature_definitions"
    __table_args__ = (
        UniqueConstraint("feature_set_id", "feature_index", name="uq_feature_set_index"),
        UniqueConstraint("feature_set_id", "feature_name", name="uq_feature_set_name"),
        {"schema": "phenotyping"},
    )

    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    feature_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_sets.feature_set_id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_name: Mapped[str] = mapped_column(Text, nullable=False)
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_dimension: Mapped[str | None] = mapped_column(phenotype_dimension_enum, nullable=True)
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="SET NULL"),
        nullable=True,
    )
    aggregation_method: Mapped[str] = mapped_column(Text, nullable=False, server_default="tfidf_weighted_pooling")
    decay_lambda: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_static: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class FeatureWeightPrior(Base):
    """Stores literature-derived weights for specific features."""

    __tablename__ = "feature_weight_priors"
    __table_args__ = {"schema": "phenotyping"}

    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_definitions.feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.heuristic_rulesets.ruleset_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    scalar_weight: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    derived_from_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    source_claim_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}",
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class TemporalFeatureWindow(Base):
    """Cohort time windows for patient feature vectors."""

    __tablename__ = "temporal_feature_windows"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "feature_set_id", "window_start", "window_end", "as_of_time",
            name="uq_temporal_feature_windows_unique",
        ),
        {"schema": "phenotyping"},
    )

    feature_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_sets.feature_set_id", ondelete="RESTRICT"),
        nullable=False,
    )
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    missingness_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class FeatureValue(Base):
    """Stores the specific vector dimension value (raw, weighted, and imputed)."""

    __tablename__ = "feature_values"
    __table_args__ = {"schema": "phenotyping"}

    feature_window_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.temporal_feature_windows.feature_window_id", ondelete="CASCADE"),
        primary_key=True,
    )
    feature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_definitions.feature_id", ondelete="CASCADE"),
        primary_key=True,
    )
    raw_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    imputed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    imputation_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}",
    )
    source_claim_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class PatientTrajectorySnapshot(Base):
    """Time-series snapshot matrices representing longitudinal patient trajectories."""

    __tablename__ = "patient_trajectory_snapshots"
    __table_args__ = {"schema": "phenotyping"}

    trajectory_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_sets.feature_set_id", ondelete="RESTRICT"),
        nullable=False,
    )
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    trajectory_matrix_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    trajectory_matrix_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )
