"""
VLEP ORM — ``ontology`` schema.

Tables: vocabularies, concepts, concept_mappings, concept_edges,
        embedding_versions, concept_embeddings.
Source: migration 002_core_ingestion_ontology_nosology_base.sql
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vlep.models.base import Base

vocabulary_kind_enum = ENUM(
    'SNOMED_CT',
    'RxNorm',
    'LOINC',
    'ICD_10',
    'ICD_11',
    'CPT_HCPCS',
    'HPO',
    'UMLS',
    'OMOP_CONCEPT',
    'ILAE',
    'DSM_5',
    'LOCAL',
    'OTHER',
    name='vocabulary_kind',
    schema='ontology',
)


class Vocabulary(Base):
    """Clinical vocabulary registration (SNOMED CT, RxNorm, HPO, etc.)."""

    __tablename__ = "vocabularies"
    __table_args__ = (
        UniqueConstraint("kind", "version", name="uq_vocabularies_kind_version"),
        {"schema": "ontology"},
    )

    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    kind: Mapped[str] = mapped_column(vocabulary_kind_enum, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    concepts: Mapped[list[Concept]] = relationship(back_populates="vocabulary")


class Concept(Base):
    """Clinical concept (a single code within a vocabulary)."""

    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("vocabulary_id", "code", name="uq_concepts_vocab_code"),
        {"schema": "ontology"},
    )

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.vocabularies.vocabulary_id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    display: Mapped[str] = mapped_column(Text, nullable=False)
    concept_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    vocabulary: Mapped[Vocabulary] = relationship(back_populates="concepts")


class ConceptMapping(Base):
    """Cross-vocabulary concept mapping."""

    __tablename__ = "concept_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source_concept_id", "target_concept_id", "relation",
            name="uq_concept_mappings_src_tgt_relation",
        ),
        {"schema": "ontology"},
    )

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="CASCADE"),
        nullable=False,
    )
    target_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False, server_default="maps_to")
    mapping_confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    mapping_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ConceptEdge(Base):
    """Hierarchical edge in the ontology graph."""

    __tablename__ = "concept_edges"
    __table_args__ = (
        UniqueConstraint(
            "parent_concept_id", "child_concept_id", "relation",
            name="uq_concept_edges_parent_child_rel",
        ),
        {"schema": "ontology"},
    )

    edge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    parent_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="CASCADE"),
        nullable=False,
    )
    child_concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="CASCADE"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(Text, nullable=False, server_default="is_a")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class EmbeddingVersion(Base):
    """Tracks versions of ontology embedding models."""

    __tablename__ = "embedding_versions"
    __table_args__ = (
        UniqueConstraint("name", "version_label", name="uq_embedding_versions_name_ver"),
        {"schema": "ontology"},
    )

    embedding_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensionality: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm: Mapped[str] = mapped_column(Text, nullable=False, server_default="poincare")
    trained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )


class ConceptEmbedding(Base):
    """Dense vector embedding for a concept."""

    __tablename__ = "concept_embeddings"
    __table_args__ = {"schema": "ontology"}

    concept_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.embedding_versions.embedding_version_id", ondelete="CASCADE"),
        primary_key=True,
    )
    vector: Mapped[list[float]] = mapped_column(
        ARRAY(Float), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
