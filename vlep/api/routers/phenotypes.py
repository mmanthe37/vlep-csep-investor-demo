"""
VLEP Pipeline — Phenotypes Router.

Endpoints for phenotype assertions, feature engineering, and temporal windows.
Assertions bind formal clinical labels to evidence ledger events with Bayesian
confidence scores across the 6-domain phenotype vector.

Routes
------
POST   /phenotypes/assertions                        Create a phenotype assertion
GET    /phenotypes/assertions                        List assertions (paginated)
GET    /phenotypes/assertions/{assertion_id}         Get single assertion
GET    /phenotypes/patients/{patient_id}/assertions  All assertions for patient

POST   /phenotypes/features/bootstrap                Bootstrap feature definitions
GET    /phenotypes/patients/{patient_id}/windows     Temporal feature windows
POST   /phenotypes/patients/{patient_id}/windows     Compute a new feature window
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.api.deps import AuthPrincipal, get_db, require_role
from vlep.models.phenotyping import PhenotypeAssertion, TemporalFeatureWindow
from vlep.services.phenotyping import PhenotypingService

router = APIRouter(prefix="/phenotypes", tags=["Phenotypes"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class AssertionCreate(BaseModel):
    patient_id: uuid.UUID
    dimension: str = Field(..., description="seizure_type | etiology | syndrome | biomarker | comorbidity | treatment_response")
    phenotype_code: str
    phenotype_label: str
    certainty_level: float = Field(0.75, ge=0.0, le=1.0)
    confidence_data_quality: float = Field(0.8, ge=0.0, le=1.0)
    confidence_recency: float = Field(0.8, ge=0.0, le=1.0)
    confidence_consistency: float = Field(0.8, ge=0.0, le=1.0)
    nosology_version_id: uuid.UUID | None = None
    supporting_event_ids: list[uuid.UUID] | None = None
    supporting_claim_ids: list[uuid.UUID] | None = None
    effective_start: datetime | None = None
    effective_end: datetime | None = None


class AssertionOut(BaseModel):
    assertion_id: uuid.UUID
    patient_id: uuid.UUID
    dimension: str
    phenotype_code: str
    phenotype_label: str
    certainty_level: float
    final_score: float | None
    posterior_probability: float | None
    asserted_at: datetime
    effective_start: datetime | None
    effective_end: datetime | None

    model_config = {"from_attributes": True}


class TemporalWindowOut(BaseModel):
    feature_window_id: uuid.UUID
    patient_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    missingness_score: float | None
    computed_at: datetime

    model_config = {"from_attributes": True}


class FeatureWindowRequest(BaseModel):
    feature_set_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    as_of_time: datetime | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/assertions",
    response_model=AssertionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new phenotype assertion",
)
async def create_assertion(
    body: AssertionCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> AssertionOut:
    """Assert a formal phenotype label for a patient dimension."""
    assertion = await PhenotypingService.create_assertion(
        session=db,
        patient_id=body.patient_id,
        dimension=body.dimension,
        phenotype_code=body.phenotype_code,
        phenotype_label=body.phenotype_label,
        certainty_level=body.certainty_level,
        confidence_data_quality=body.confidence_data_quality,
        confidence_recency=body.confidence_recency,
        confidence_consistency=body.confidence_consistency,
        nosology_version_id=body.nosology_version_id,
        supporting_event_ids=body.supporting_event_ids,
        supporting_claim_ids=body.supporting_claim_ids,
        effective_start=body.effective_start,
        effective_end=body.effective_end,
    )
    return AssertionOut.model_validate(assertion)


@router.get(
    "/assertions",
    response_model=list[AssertionOut],
    summary="List phenotype assertions (paginated)",
)
async def list_assertions(
    patient_id: uuid.UUID | None = Query(None),
    dimension: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[AssertionOut]:
    stmt = select(PhenotypeAssertion)
    if patient_id:
        stmt = stmt.where(PhenotypeAssertion.patient_id == patient_id)
    if dimension:
        stmt = stmt.where(PhenotypeAssertion.dimension == dimension)
    stmt = stmt.offset(offset).limit(limit)
    result = await db.execute(stmt)
    return [AssertionOut.model_validate(a) for a in result.scalars().all()]


@router.get(
    "/assertions/{assertion_id}",
    response_model=AssertionOut,
    summary="Get a single phenotype assertion",
)
async def get_assertion(
    assertion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> AssertionOut:
    result = await db.execute(
        select(PhenotypeAssertion).where(PhenotypeAssertion.assertion_id == assertion_id)
    )
    assertion = result.scalar_one_or_none()
    if not assertion:
        raise HTTPException(status_code=404, detail="Assertion not found")
    return AssertionOut.model_validate(assertion)


@router.get(
    "/patients/{patient_id}/assertions",
    response_model=list[AssertionOut],
    summary="List all phenotype assertions for a patient",
)
async def patient_assertions(
    patient_id: uuid.UUID,
    dimension: str | None = Query(None),
    as_of: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[AssertionOut]:
    stmt = select(PhenotypeAssertion).where(PhenotypeAssertion.patient_id == patient_id)
    if dimension:
        stmt = stmt.where(PhenotypeAssertion.dimension == dimension)
    if as_of:
        stmt = stmt.where(PhenotypeAssertion.asserted_at <= as_of)
    result = await db.execute(stmt)
    return [AssertionOut.model_validate(a) for a in result.scalars().all()]


@router.post(
    "/features/bootstrap",
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap the 256-dim MVP feature definition set",
)
async def bootstrap_features(
    feature_set_name: str = "MVP Phenotype Vector v1",
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Initialize the 256-dimensional feature definition set (idempotent)."""
    feature_set = await PhenotypingService.bootstrap_feature_definitions(
        session=db, feature_set_name=feature_set_name
    )
    return {
        "feature_set_id": str(feature_set.feature_set_id),
        "name": feature_set.name,
        "dimensionality": feature_set.dimensionality,
        "status": "bootstrapped",
    }


@router.get(
    "/patients/{patient_id}/windows",
    response_model=list[TemporalWindowOut],
    summary="List temporal feature windows for a patient",
)
async def list_windows(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[TemporalWindowOut]:
    result = await db.execute(
        select(TemporalFeatureWindow).where(TemporalFeatureWindow.patient_id == patient_id)
    )
    return [TemporalWindowOut.model_validate(w) for w in result.scalars().all()]


@router.post(
    "/patients/{patient_id}/windows",
    response_model=TemporalWindowOut,
    status_code=status.HTTP_201_CREATED,
    summary="Compute a new temporal feature window",
)
async def compute_window(
    patient_id: uuid.UUID,
    body: FeatureWindowRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> TemporalWindowOut:
    """Compute feature values for a specified time window for a patient."""
    window = await PhenotypingService.build_feature_values_in_window(
        session=db,
        patient_id=patient_id,
        feature_set_id=body.feature_set_id,
        window_start=body.window_start,
        window_end=body.window_end,
        as_of_time=body.as_of_time,
    )
    return TemporalWindowOut.model_validate(window)
