"""
VLEP ORM — ``literature`` schema.

Tables: documents, document_sections, phenotype_claims, claim_evidence_metadata,
        heuristic_rulesets, claim_tiering_results, claim_supporting_sources,
        corpus_releases, corpus_claims.
Source: migration 003_literature_documents_claims.sql
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
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from vlep.models.base import Base

# Enums matching the database definitions
document_source_kind_enum = ENUM(
    "PubMed_MEDLINE",
    "PMC_OPEN_ACCESS",
    "Embase",
    "ClinicalTrials_gov",
    "Institutional_Guideline",
    "Cochrane",
    "Preprint",
    "Manual",
    "Other",
    name="document_source_kind",
    schema="literature",
)

document_section_kind_enum = ENUM(
    "TITLE",
    "ABSTRACT",
    "INTRODUCTION",
    "METHODS",
    "RESULTS",
    "DISCUSSION",
    "CONCLUSION",
    "GUIDELINE",
    "TABLE",
    "FIGURE",
    "SUPPLEMENT",
    "METADATA",
    "FULL_TEXT",
    "UNKNOWN",
    name="document_section_kind",
    schema="literature",
)

claim_tier_enum = ENUM(
    "TIER_1",
    "TIER_2",
    "TIER_3",
    "TIER_4",
    "EXCLUDED",
    "UNREVIEWED",
    name="claim_tier",
    schema="literature",
)


class Document(Base):
    """Source biomedical publication."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_kind", "external_id", name="uq_documents_source_ext"),
        {"schema": "literature"},
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    source_kind: Mapped[str] = mapped_column(document_source_kind_enum, nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    doi: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    pmid: Mapped[str | None] = mapped_column(Text, nullable=True)
    pmcid: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    journal: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    authors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    peer_review_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_policy: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="metadata_or_permitted_text",
    )
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_extraction_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    @property
    def publication_year(self) -> int | None:
        return self.publication_date.year if self.publication_date else None

    @property
    def study_design(self) -> str | None:
        return self.metadata_.get("study_design")

    @property
    def n_subjects(self) -> int | None:
        return self.metadata_.get("n_subjects")

    # Relationships
    sections: Mapped[list[DocumentSection]] = relationship(
        back_populates="document", cascade="all, delete-orphan",
    )
    claims: Mapped[list[PhenotypeClaim]] = relationship(
        back_populates="source_document", foreign_keys="[PhenotypeClaim.source_document_id]"
    )
    supporting_sources: Mapped[list[ClaimSupportingSource]] = relationship(
        back_populates="supporting_document", cascade="all, delete-orphan"
    )


class DocumentSection(Base):
    """Parsed section of a source document."""

    __tablename__ = "document_sections"
    __table_args__ = {"schema": "literature"}

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    section_kind: Mapped[str] = mapped_column(document_section_kind_enum, nullable=False)
    section_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    document: Mapped[Document] = relationship(back_populates="sections")
    claims: Mapped[list[PhenotypeClaim]] = relationship(
        back_populates="source_section", cascade="all, delete-orphan"
    )


class HeuristicRuleset(Base):
    """Deterministic provenance tiering ruleset."""

    __tablename__ = "heuristic_rulesets"
    __table_args__ = (
        UniqueConstraint("name", "version_label", name="uq_heuristic_rulesets_name_ver"),
        {"schema": "literature"},
    )

    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    rules_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    tiering_results: Mapped[list[ClaimTieringResult]] = relationship(
        back_populates="ruleset",
    )
    corpus_releases: Mapped[list[CorpusRelease]] = relationship(
        back_populates="ruleset",
    )


class PhenotypeClaim(Base):
    """Atomic evidence assertion extracted from literature.

    Stores the subject–predicate–object triple with exact source provenance
    (character offsets) and normalized ontology concept links.
    """

    __tablename__ = "phenotype_claims"
    __table_args__ = {"schema": "literature"}

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    claim_key: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    subject_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_text: Mapped[str] = mapped_column(Text, nullable=False)
    predicate: Mapped[str] = mapped_column(Text, nullable=False)
    object_concept_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ontology.concepts.concept_id", ondelete="SET NULL"),
        nullable=True,
    )
    object_text: Mapped[str] = mapped_column(Text, nullable=False)
    relation_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    negation_status: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    conditionality: Mapped[str | None] = mapped_column(Text, nullable=True)
    temporal_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    age_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    sex_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.documents.document_id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.document_sections.section_id", ondelete="SET NULL"),
        nullable=True,
    )
    source_start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_model_version: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    source_document: Mapped[Document] = relationship(
        back_populates="claims", foreign_keys=[source_document_id]
    )
    source_section: Mapped[DocumentSection | None] = relationship(back_populates="claims")
    evidence_metadata: Mapped[ClaimEvidenceMetadata | None] = relationship(
        back_populates="claim", uselist=False, cascade="all, delete-orphan",
    )
    tiering_results: Mapped[list[ClaimTieringResult]] = relationship(
        back_populates="claim", cascade="all, delete-orphan",
    )
    supporting_sources: Mapped[list[ClaimSupportingSource]] = relationship(
        back_populates="primary_claim", cascade="all, delete-orphan",
    )
    corpus_claims: Mapped[list[CorpusClaim]] = relationship(
        back_populates="claim", cascade="all, delete-orphan",
    )


class ClaimEvidenceMetadata(Base):
    """Study design, sample size, and statistics for a claim."""

    __tablename__ = "claim_evidence_metadata"
    __table_args__ = {"schema": "literature"}

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        primary_key=True,
    )
    study_design: Mapped[str | None] = mapped_column(Text, nullable=True)
    n_subjects: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    confidence_interval: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    effect_size: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    causal_method: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    peer_review_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_metric: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    replication_density: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    publication_recency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_from_section: Mapped[str | None] = mapped_column(document_section_kind_enum, nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    claim: Mapped[PhenotypeClaim] = relationship(back_populates="evidence_metadata")


class ClaimTieringResult(Base):
    """Tier assignment from heuristic provenance scoring."""

    __tablename__ = "claim_tiering_results"
    __table_args__ = (
        UniqueConstraint("claim_id", "ruleset_id", name="uq_claim_tiering_claim_ruleset"),
        {"schema": "literature"},
    )

    claim_tiering_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        nullable=False,
    )
    ruleset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.heuristic_rulesets.ruleset_id", ondelete="RESTRICT"),
        nullable=False,
    )
    tier: Mapped[str] = mapped_column(claim_tier_enum, nullable=False)
    scalar_weight: Mapped[float] = mapped_column(
        Numeric(6, 5), nullable=False,
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Numeric(6, 5), nullable=True,
    )
    tier_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    evidence_features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )

    # Relationships
    claim: Mapped[PhenotypeClaim] = relationship(back_populates="tiering_results")
    ruleset: Mapped[HeuristicRuleset] = relationship(back_populates="tiering_results")


class ClaimSupportingSource(Base):
    """Links supporting publications/replications to a primary phenotype claim."""

    __tablename__ = "claim_supporting_sources"
    __table_args__ = {"schema": "literature"}

    support_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    primary_claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        nullable=False,
    )
    supporting_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.documents.document_id", ondelete="RESTRICT"),
        nullable=False,
    )
    supporting_section_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.document_sections.section_id", ondelete="SET NULL"),
        nullable=True,
    )
    support_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="replication")
    similarity_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    primary_claim: Mapped[PhenotypeClaim] = relationship(back_populates="supporting_sources")
    supporting_document: Mapped[Document] = relationship(back_populates="supporting_sources")


class CorpusRelease(Base):
    """Versioned snapshot of the literature claim corpus."""

    __tablename__ = "corpus_releases"
    __table_args__ = (
        UniqueConstraint("name", "version_label", name="uq_corpus_releases_name_ver"),
        {"schema": "literature"},
    )

    corpus_release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    version_label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intended_claim_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ruleset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.heuristic_rulesets.ruleset_id", ondelete="SET NULL"),
        nullable=True,
    )
    release_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    tier_distribution: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}",
    )
    artifact_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Relationships
    ruleset: Mapped[HeuristicRuleset | None] = relationship(back_populates="corpus_releases")
    corpus_claims: Mapped[list[CorpusClaim]] = relationship(
        back_populates="corpus_release", cascade="all, delete-orphan",
    )


class CorpusClaim(Base):
    """Links a claim to a specific corpus release."""

    __tablename__ = "corpus_claims"
    __table_args__ = {"schema": "literature"}

    corpus_release_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.corpus_releases.corpus_release_id", ondelete="CASCADE"),
        primary_key=True,
    )
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("literature.phenotype_claims.claim_id", ondelete="CASCADE"),
        primary_key=True,
    )
    included: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    inclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    corpus_release: Mapped[CorpusRelease] = relationship(
        back_populates="corpus_claims",
    )
    claim: Mapped[PhenotypeClaim] = relationship(
        back_populates="corpus_claims",
    )

