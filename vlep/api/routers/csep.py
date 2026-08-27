"""
VLEP Pipeline — CSEP (Current-State Epilepsy Profile) Router.

Endpoints for assembling, retrieving, comparing, and nosologically reversioning
deterministic Current-State Epilepsy Profiles (CSEP).

Routes
------
POST   /csep/profiles                                   Assemble a new CSEP profile
GET    /csep/profiles/{profile_id}                      Get profile by ID
GET    /csep/patients/{patient_id}/profiles             List profiles for patient
GET    /csep/patients/{patient_id}/profiles/latest      Get latest profile

POST   /csep/nosology/frameworks                        Create a nosological framework
POST   /csep/nosology/reinterpret                       Trigger re-interpretation job
GET    /csep/nosology/jobs/{job_id}                     Check reinterpretation job status
GET    /csep/nosology/results/{job_id}                  Get reinterpretation results

GET    /csep/profiles/compare                           Compare two profiles diff
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
from vlep.models.csep import CSEPProfile
from vlep.models.nosology import ReinterpretationJob
from vlep.services.csep_resolver import CsepResolverService
from vlep.services.nosology import NosologyService

router = APIRouter(prefix="/csep", tags=["CSEP Profiles"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class CsepAssembleRequest(BaseModel):
    patient_id: uuid.UUID
    nosology_version_id: uuid.UUID
    model_version_id: uuid.UUID
    lpa_run_id: uuid.UUID | None = None
    as_of_time: datetime | None = None


class ProfileOut(BaseModel):
    profile_id: uuid.UUID = Field(validation_alias="csep_id")
    patient_id: uuid.UUID
    nosology_version_id: uuid.UUID
    model_version_id: uuid.UUID | None = None
    as_of_time: datetime
    epilepsy_syndrome: dict[str, Any] | None = None
    seizure_type_distribution: dict[str, Any] | None = None
    etiology_ranked_confidence: list[dict[str, Any]] | None = None
    predictive_outputs: dict[str, Any] | None = None
    uncertainty: dict[str, Any] | None = None
    profile_hash: str | None = None
    created_at: datetime = Field(validation_alias="generated_at")

    model_config = {"from_attributes": True}


class FrameworkCreate(BaseModel):
    framework_name: str
    version_tag: str
    ilae_year: int
    description: str | None = None
    is_active: bool = True


class FrameworkOut(BaseModel):
    framework_version_id: uuid.UUID
    framework_name: str
    version_tag: str
    ilae_year: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReinterpretRequest(BaseModel):
    source_nosology_version_id: uuid.UUID
    target_nosology_version_id: uuid.UUID
    cohort_id: uuid.UUID | None = None
    patient_ids: list[uuid.UUID] | None = None


class JobOut(BaseModel):
    job_id: uuid.UUID = Field(validation_alias="reinterpretation_job_id")
    status: str
    source_nosology_version_id: uuid.UUID | None = None
    target_nosology_version_id: uuid.UUID
    created_at: datetime = Field(validation_alias="requested_at")
    completed_at: datetime | None = Field(None, validation_alias="finished_at")
    total_patients: int | None = Field(default=None, validation_alias="intended_claim_count")

    model_config = {"from_attributes": True}


class CompareProfilesOut(BaseModel):
    profile_a_id: uuid.UUID
    profile_b_id: uuid.UUID
    changes: dict[str, Any]
    summary: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/profiles",
    response_model=ProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Assemble a new CSEP profile (Resolution Function F)",
)
async def assemble_profile(
    body: CsepAssembleRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> ProfileOut:
    """Run the deterministic CSEP resolution function to produce a current-state profile."""
    profile = await CsepResolverService.assemble_csep_profile(
        session=db,
        patient_id=body.patient_id,
        nosology_version_id=body.nosology_version_id,
        model_version_id=body.model_version_id,
        lpa_run_id=body.lpa_run_id,
        as_of_time=body.as_of_time,
    )
    return ProfileOut.model_validate(profile)


@router.get(
    "/profiles/{profile_id}",
    response_model=ProfileOut,
    summary="Get a CSEP profile by ID",
)
async def get_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> ProfileOut:
    result = await db.execute(select(CSEPProfile).where(CSEPProfile.csep_id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return ProfileOut.model_validate(profile)


@router.get(
    "/patients/{patient_id}/profiles",
    response_model=list[ProfileOut],
    summary="List CSEP profiles for a patient",
)
async def patient_profiles(
    patient_id: uuid.UUID,
    nosology_version_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[ProfileOut]:
    stmt = (
        select(CSEPProfile)
        .where(CSEPProfile.patient_id == patient_id)
        .order_by(CSEPProfile.as_of_time.desc())
        .limit(limit)
    )
    if nosology_version_id:
        stmt = stmt.where(CSEPProfile.nosology_version_id == nosology_version_id)
    result = await db.execute(stmt)
    return [ProfileOut.model_validate(p) for p in result.scalars().all()]


@router.get(
    "/patients/{patient_id}/profiles/latest",
    response_model=ProfileOut,
    summary="Get the most recent CSEP profile for a patient",
)
async def latest_profile(
    patient_id: uuid.UUID,
    nosology_version_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> ProfileOut:
    stmt = (
        select(CSEPProfile)
        .where(CSEPProfile.patient_id == patient_id)
        .order_by(CSEPProfile.as_of_time.desc())
        .limit(1)
    )
    if nosology_version_id:
        stmt = stmt.where(CSEPProfile.nosology_version_id == nosology_version_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="No profile found for this patient")
    return ProfileOut.model_validate(profile)


@router.get(
    "/profiles/compare",
    response_model=CompareProfilesOut,
    summary="Compare two CSEP profiles",
)
async def compare_profiles(
    profile_a_id: uuid.UUID = Query(...),
    profile_b_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> CompareProfilesOut:
    """Generate a structured diff between two CSEP profiles."""
    changes = await CsepResolverService.compare_profiles(
        session=db, profile_a_id=profile_a_id, profile_b_id=profile_b_id
    )
    return CompareProfilesOut(
        profile_a_id=profile_a_id,
        profile_b_id=profile_b_id,
        changes=changes,
        summary=changes.get("summary", ""),
    )


# ── Nosological Reversioning ────────────────────────────────────────────────

@router.post(
    "/nosology/frameworks",
    response_model=FrameworkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new nosological framework version",
)
async def create_framework(
    body: FrameworkCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> FrameworkOut:
    """Create a versioned ILAE classification framework."""
    framework = await NosologyService.create_framework_version(
        session=db,
        framework_name=body.framework_name,
        version_tag=body.version_tag,
        ilae_year=body.ilae_year,
        description=body.description,
        is_active=body.is_active,
    )
    return FrameworkOut.model_validate(framework)


@router.post(
    "/nosology/reinterpret",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger a nosological re-interpretation job",
)
async def trigger_reinterpretation(
    body: ReinterpretRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> JobOut:
    """
    Re-interpret CSEP profiles from a source nosology to a target nosology.
    The underlying evidence ledger is never altered — only the interpretation layer changes.
    """
    job = await NosologyService.create_reinterpretation_job(
        session=db,
        source_nosology_version_id=body.source_nosology_version_id,
        target_nosology_version_id=body.target_nosology_version_id,
        cohort_id=body.cohort_id,
    )
    # Execute inline (in production this would be dispatched to Celery)
    await NosologyService.execute_reinterpretation_job(
        session=db,
        reinterpretation_job_id=job.reinterpretation_job_id,
        patient_ids=body.patient_ids,
    )
    await db.flush()
    return JobOut.model_validate(job)


@router.get(
    "/nosology/jobs/{job_id}",
    response_model=JobOut,
    summary="Check reinterpretation job status",
)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> JobOut:
    result = await db.execute(
        select(ReinterpretationJob).where(ReinterpretationJob.reinterpretation_job_id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Reinterpretation job not found")
    return JobOut.model_validate(job)
