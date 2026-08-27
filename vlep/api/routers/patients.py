"""
VLEP Pipeline — Patients Router.

Endpoints for pseudonymous patient identity management.
All endpoints require at minimum the ``clinician`` role.

Routes
------
POST   /patients/                  Create a new patient record
GET    /patients/                  List patients (paginated)
GET    /patients/{patient_id}      Get patient details
PATCH  /patients/{patient_id}      Update demographics
DELETE /patients/{patient_id}      Soft-delete (admin only)
POST   /patients/{patient_id}/cohorts/{cohort_id}   Enroll in cohort
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
from vlep.models.core import Cohort, CohortMembership, Patient
from vlep.services.pipeline_orchestrator import VlepPipelineOrchestrator

router = APIRouter(prefix="/patients", tags=["Patients"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    source_patient_hash: str = Field(..., description="Pseudonymous de-identified hash of the source patient ID")
    birth_year: int | None = Field(None, ge=1900, description="Year of birth (1900–current year)")
    sex_at_birth: str | None = Field(None, max_length=50)
    gender_identity: str | None = Field(None, max_length=100)
    race_ethnicity: dict[str, Any] | None = Field(default_factory=dict)
    metadata: dict[str, Any] | None = Field(default_factory=dict)


class PatientUpdate(BaseModel):
    birth_year: int | None = Field(None, ge=1900)
    sex_at_birth: str | None = Field(None, max_length=50)
    gender_identity: str | None = Field(None, max_length=100)
    race_ethnicity: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class PatientOut(BaseModel):
    patient_id: uuid.UUID
    source_patient_hash: str
    birth_year: int | None
    sex_at_birth: str | None
    gender_identity: str | None
    race_ethnicity: dict[str, Any]
    deceased_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PatientListOut(BaseModel):
    total: int
    patients: list[PatientOut]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=PatientOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient",
)
async def create_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_db),
    principal: AuthPrincipal = Depends(require_role("clinician")),
) -> PatientOut:
    """Create a new pseudonymous patient record."""
    patient = Patient(
        source_patient_hash=body.source_patient_hash,
        birth_year=body.birth_year,
        sex_at_birth=body.sex_at_birth,
        gender_identity=body.gender_identity,
        race_ethnicity=body.race_ethnicity or {},
        metadata_=body.metadata or {},
    )
    db.add(patient)
    await db.flush()
    return PatientOut.model_validate(patient)


@router.get(
    "/",
    response_model=PatientListOut,
    summary="List all patients (paginated)",
)
async def list_patients(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> PatientListOut:
    """Return a paginated list of patient records."""
    result = await db.execute(select(Patient).offset(offset).limit(limit))
    patients = result.scalars().all()
    count_result = await db.execute(select(Patient))
    total = len(count_result.scalars().all())
    return PatientListOut(
        total=total,
        patients=[PatientOut.model_validate(p) for p in patients],
    )


@router.get(
    "/{patient_id}",
    response_model=PatientOut,
    summary="Get patient by ID",
)
async def get_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> PatientOut:
    """Retrieve a patient by their UUID."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    return PatientOut.model_validate(patient)


@router.patch(
    "/{patient_id}",
    response_model=PatientOut,
    summary="Update patient demographics",
)
async def update_patient(
    patient_id: uuid.UUID,
    body: PatientUpdate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> PatientOut:
    """Partial update of patient demographic fields."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "metadata":
            patient.metadata_ = value
        else:
            setattr(patient, field, value)

    await db.flush()
    return PatientOut.model_validate(patient)


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a patient record (admin only)",
)
async def delete_patient(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("admin")),
) -> None:
    """Hard-delete a patient record. Requires admin role."""
    result = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
    await db.delete(patient)


@router.post(
    "/{patient_id}/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger the 6-stage VLEP analysis pipeline",
)
async def analyze_patient(
    patient_id: uuid.UUID,
    nosology_version_id: uuid.UUID = Query(..., description="Target ILAE framework version ID"),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> dict[str, Any]:
    """Execute the full 6-stage profiling pipeline for this patient."""
    pat_res = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    if not pat_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    orchestrator = VlepPipelineOrchestrator(db)
    result = await orchestrator.run_full_pipeline(
        patient_id=patient_id,
        nosology_version_id=nosology_version_id
    )
    return result

@router.post(
    "/{patient_id}/cohorts/{cohort_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Enroll patient in a cohort",
)
async def enroll_in_cohort(
    patient_id: uuid.UUID,
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> dict[str, str]:
    """Add a patient to a study cohort."""
    # Verify patient and cohort exist
    pat_res = await db.execute(select(Patient).where(Patient.patient_id == patient_id))
    if not pat_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")
    coh_res = await db.execute(select(Cohort).where(Cohort.cohort_id == cohort_id))
    if not coh_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Cohort not found")

    membership = CohortMembership(patient_id=patient_id, cohort_id=cohort_id, status="active")
    db.add(membership)
    await db.flush()
    return {"status": "enrolled", "patient_id": str(patient_id), "cohort_id": str(cohort_id)}
