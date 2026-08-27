"""
VLEP Pipeline — Literature & Claims Router.

Endpoints for ingesting biomedical documents, managing phenotype claims,
triggering provenance tiering, and querying corpus releases.

Routes
------
POST   /literature/documents                          Ingest a new document
GET    /literature/documents/{document_id}            Get document metadata
POST   /literature/documents/{document_id}/claims     Extract / ingest claims
GET    /literature/claims                             List claims (paginated, filtered)
GET    /literature/claims/{claim_id}                  Get claim detail
POST   /literature/claims/{claim_id}/tier             Compute provenance tier
GET    /literature/corpus                             List corpus releases
POST   /literature/corpus                             Create a new corpus snapshot
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.api.deps import AuthPrincipal, get_db, require_role
from vlep.models.literature import CorpusRelease, Document, PhenotypeClaim
from vlep.services.literature import LiteratureService

router = APIRouter(prefix="/literature", tags=["Literature & Claims"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    pmid: str | None = None
    pmcid: str | None = None
    doi: str | None = None
    title: str
    abstract: str | None = None
    journal: str | None = None
    publication_year: int | None = None
    authors: list[str] | None = None
    study_design: str | None = None
    n_subjects: int | None = None
    p_value: float | None = None
    effect_size: float | None = None


class DocumentOut(BaseModel):
    document_id: uuid.UUID
    pmid: str | None
    doi: str | None
    title: str
    publication_year: int | None
    study_design: str | None
    n_subjects: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClaimCreate(BaseModel):
    document_id: uuid.UUID
    subject_text: str
    subject_concept_id: uuid.UUID | None = None
    predicate: str
    object_text: str
    object_concept_id: uuid.UUID | None = None
    source_sentence: str
    source_start_offset: int | None = None
    source_end_offset: int | None = None
    negated: bool = False
    certainty: float = Field(0.7, ge=0.0, le=1.0)


class ClaimOut(BaseModel):
    claim_id: uuid.UUID
    document_id: uuid.UUID = Field(validation_alias="source_document_id")
    subject_text: str
    predicate: str
    object_text: str
    negated: bool = Field(validation_alias="negation_status")
    certainty: float | None = Field(None, validation_alias="extraction_confidence")
    created_at: datetime

    model_config = {"from_attributes": True}


class TierResult(BaseModel):
    claim_id: uuid.UUID
    tier: int
    tier_label: str
    weight: float
    rationale: str


class CorpusReleaseOut(BaseModel):
    corpus_release_id: uuid.UUID
    release_name: str = Field(validation_alias="name")
    release_version: str = Field(validation_alias="version_label")
    claim_count: int | None = Field(None, validation_alias="intended_claim_count")
    released_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new biomedical document",
)
async def create_document(
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> DocumentOut:
    """Store document metadata and bibliographic information."""
    doc = await LiteratureService.create_document(
        session=db,
        title=body.title,
        pmid=body.pmid,
        pmcid=body.pmcid,
        doi=body.doi,
        abstract=body.abstract,
        journal=body.journal,
        publication_year=body.publication_year,
        authors=body.authors,
        study_design=body.study_design,
        n_subjects=body.n_subjects,
        p_value=body.p_value,
        effect_size=body.effect_size,
    )
    return DocumentOut.model_validate(doc)


@router.get(
    "/documents/{document_id}",
    response_model=DocumentOut,
    summary="Get document metadata",
)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> DocumentOut:
    result = await db.execute(select(Document).where(Document.document_id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut.model_validate(doc)


@router.post(
    "/documents/{document_id}/claims",
    response_model=ClaimOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an extracted phenotype claim",
)
async def create_claim(
    document_id: uuid.UUID,
    body: ClaimCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> ClaimOut:
    """Store an NLP-extracted phenotype claim and trigger tiering."""
    if body.document_id != document_id:
        raise HTTPException(status_code=422, detail="document_id in path and body must match")

    claim = await LiteratureService.ingest_claim(
        session=db,
        document_id=document_id,
        subject_text=body.subject_text,
        subject_concept_id=body.subject_concept_id,
        predicate=body.predicate,
        object_text=body.object_text,
        object_concept_id=body.object_concept_id,
        source_sentence=body.source_sentence,
        source_start_offset=body.source_start_offset,
        source_end_offset=body.source_end_offset,
        negated=body.negated,
        certainty=body.certainty,
    )
    return ClaimOut.model_validate(claim)


@router.get(
    "/claims",
    response_model=list[ClaimOut],
    summary="List phenotype claims (paginated)",
)
async def list_claims(
    document_id: uuid.UUID | None = Query(None),
    predicate: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[ClaimOut]:
    stmt = select(PhenotypeClaim)
    if document_id:
        stmt = stmt.where(PhenotypeClaim.document_id == document_id)
    if predicate:
        stmt = stmt.where(PhenotypeClaim.predicate == predicate)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [ClaimOut.model_validate(c) for c in result.scalars().all()]


@router.get(
    "/claims/{claim_id}",
    response_model=ClaimOut,
    summary="Get a single phenotype claim",
)
async def get_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> ClaimOut:
    result = await db.execute(select(PhenotypeClaim).where(PhenotypeClaim.claim_id == claim_id))
    claim = result.scalar_one_or_none()
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return ClaimOut.model_validate(claim)


@router.post(
    "/claims/{claim_id}/tier",
    response_model=TierResult,
    summary="Compute provenance tier for a claim",
)
async def tier_claim(
    claim_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> TierResult:
    """Run heuristic tiering on a claim and persist the result."""
    tier_data = await LiteratureService.tier_single_claim(session=db, claim_id=claim_id)
    return TierResult(
        claim_id=claim_id,
        tier=tier_data["tier"],
        tier_label=tier_data["tier_label"],
        weight=tier_data["weight"],
        rationale=tier_data["rationale"],
    )


@router.get(
    "/corpus",
    response_model=list[CorpusReleaseOut],
    summary="List corpus releases",
)
async def list_corpus_releases(
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[CorpusReleaseOut]:
    result = await db.execute(select(CorpusRelease).order_by(CorpusRelease.released_at.desc()))
    return [CorpusReleaseOut.model_validate(r) for r in result.scalars().all()]


@router.post(
    "/corpus",
    response_model=CorpusReleaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Snapshot the current claim corpus as a versioned release",
)
async def create_corpus_release(
    release_name: str,
    release_version: str,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> CorpusReleaseOut:
    """Create a versioned snapshot of all currently tiered claims."""
    release = await LiteratureService.generate_corpus_release(
        session=db,
        release_name=release_name,
        release_version=release_version,
    )
    return CorpusReleaseOut.model_validate(release)
