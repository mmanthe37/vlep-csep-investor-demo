"""
VLEP ORM — ``modeling`` schema.

Tables: model_versions, lpa_runs, latent_state_sequences,
        time_to_event_hazards, predictions, validation_metric_results.
Source: migration 006_lpa_modeling_csep.sql
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
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

model_family_enum = ENUM(
    'GLMM',
    'HMM',
    'SURVIVAL_ENSEMBLE',
    'RANDOM_SURVIVAL_FOREST',
    'LOGISTIC_REGRESSION',
    'MIXED_POISSON_EXPONENTIAL',
    'LSTM',
    'XGBOOST',
    'NLP_TRANSFORMER',
    'OTHER',
    name='model_family',
    schema='modeling',
)


class ModelVersion(Base):
    """Registered machine learning / statistical model checkpoints."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("name", "version_label", name="uq_model_versions_name_label"),
        {"schema": "modeling"},
    )

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(model_family_enum, nullable=False)  # Enum (model_family)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    training_dataset_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_dataset_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_sets.feature_set_id", ondelete="SET NULL"),
        nullable=True,
    )
    corpus_release_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.corpus_releases.corpus_release_id", ondelete="SET NULL"),
        nullable=True,
    )
    nosology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    hyperparameters: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    model_card: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="registered")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class LpaRun(Base):
    """Tracks execution parameters, metrics, and state of a longitudinal modeling pipeline run."""

    __tablename__ = "lpa_runs"
    __table_args__ = {"schema": "modeling"}

    lpa_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    run_kind: Mapped[str] = mapped_column(Text, nullable=False)
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.model_versions.model_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    feature_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("phenotyping.feature_sets.feature_set_id", ondelete="SET NULL"),
        nullable=True,
    )
    corpus_release_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.corpus_releases.corpus_release_id", ondelete="SET NULL"),
        nullable=True,
    )
    nosology_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("nosology.framework_versions.nosology_version_id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    patients_processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class LatentStateSequence(Base):
    """Longitudinal hidden states inferred via HMM Viterbi decoding."""

    __tablename__ = "latent_state_sequences"
    __table_args__ = {"schema": "modeling"}

    latent_state_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    lpa_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.lpa_runs.lpa_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state_label: Mapped[str] = mapped_column(Text, nullable=False)
    state_probability: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    state_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viterbi_path: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    emission_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class TimeToEventHazard(Base):
    """Dynamic survival hazards (SUDEP, DRE transition, seizure freedom forecasting)."""

    __tablename__ = "time_to_event_hazards"
    __table_args__ = {"schema": "modeling"}

    hazard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    lpa_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.lpa_runs.lpa_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    hazard_value: Mapped[float] = mapped_column(Float, nullable=False)
    survival_probability: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    cumulative_incidence: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    feature_contributions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class Prediction(Base):
    """General-purpose model predictions (continuous and classification target predictions)."""

    __tablename__ = "predictions"
    __table_args__ = {"schema": "modeling"}

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    lpa_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.lpa_runs.lpa_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    prediction_type: Mapped[str] = mapped_column(Text, nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    probability: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    uncertainty: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ValidationMetricResult(Base):
    """Historical evaluation metrics (Brier Score, C-index, AUROC, AUPRC) calculated per run."""

    __tablename__ = "validation_metric_results"
    __table_args__ = {"schema": "modeling"}

    metric_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    model_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.model_versions.model_version_id", ondelete="CASCADE"),
        nullable=True,
    )
    lpa_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modeling.lpa_runs.lpa_run_id", ondelete="CASCADE"),
        nullable=True,
    )
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("core.cohorts.cohort_id", ondelete="SET NULL"),
        nullable=True,
    )
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    metric_context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
