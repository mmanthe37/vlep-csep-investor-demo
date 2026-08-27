"""
VLEP Pipeline — Evidence Ledger Router.

Endpoints for querying the immutable, SHA-256 chained evidence ledger.
All write operations create new entries; existing events can never be
modified or deleted (append-only invariant enforced by DB triggers).

Routes
------
POST   /evidence/events                         Append a new ledger event
GET    /evidence/events                         List active events (paginated)
GET    /evidence/events/{event_id}              Get single event
POST   /evidence/events/{event_id}/supersede    Create a superseding correction
POST   /evidence/events/{event_id}/notes        Annotate with a note
GET    /evidence/patients/{patient_id}/events   Events for a specific patient
POST   /evidence/verify/{event_id}              Re-verify SHA-256 hash integrity
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.api.deps import AuthPrincipal, get_db, require_role
from vlep.services.evidence_ledger import EvidenceLedgerService

router = APIRouter(prefix="/evidence", tags=["Evidence Ledger"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class LedgerEventCreate(BaseModel):
    patient_id: uuid.UUID
    domain: str = Field(..., description="Evidence domain: clinical_observation, eeg, imaging, genetic, pro")
    data_element: dict[str, Any]
    observed_at: datetime
    source_attribution: str
    certainty_level: float = Field(0.8, ge=0.0, le=1.0)
    validation_status: str = Field("raw", description="raw | normalized | validated | superseded")
    source_system_id: uuid.UUID | None = None
    raw_resource_id: uuid.UUID | None = None
    normalized_codes: list[str] | None = None
    provenance: dict[str, Any] | None = None
    nosology_version_id: uuid.UUID | None = None


class LedgerEventSupersede(BaseModel):
    correction: dict[str, Any] = Field(..., description="Updated data_element for the correction event")
    source_attribution: str
    certainty_level: float = Field(0.8, ge=0.0, le=1.0)
    rationale: str | None = None


class LedgerNoteCreate(BaseModel):
    author_id: str
    note_text: str
    note_type: str = Field("clinical", description="clinical | audit | correction")


class LedgerEventOut(BaseModel):
    event_id: uuid.UUID
    patient_id: uuid.UUID
    domain: str
    data_element: dict[str, Any]
    observed_at: datetime
    ingested_at: datetime
    certainty_level: float
    validation_status: str
    hash_self: str | None
    supersedes_event_id: uuid.UUID | None

    model_config = {"from_attributes": True}


class HashVerifyOut(BaseModel):
    event_id: uuid.UUID
    valid: bool
    stored_hash: str | None
    computed_hash: str | None
    message: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post(
    "/events",
    response_model=LedgerEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Append a new immutable evidence event",
)
async def append_event(
    body: LedgerEventCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> LedgerEventOut:
    """Create an append-only evidence ledger entry with SHA-256 hash chain."""
    event = await EvidenceLedgerService.append_event(
        session=db,
        patient_id=body.patient_id,
        domain=body.domain,
        data_element=body.data_element,
        observed_at=body.observed_at,
        source_attribution=body.source_attribution,
        certainty_level=body.certainty_level,
        validation_status=body.validation_status,
        source_system_id=body.source_system_id,
        raw_resource_id=body.raw_resource_id,
        normalized_codes=body.normalized_codes,
        provenance=body.provenance,
        nosology_version_id=body.nosology_version_id,
    )
    return LedgerEventOut.model_validate(event)


@router.get(
    "/events",
    response_model=list[LedgerEventOut],
    summary="List active ledger events (paginated)",
)
async def list_events(
    patient_id: uuid.UUID | None = Query(None),
    domain: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    as_of: datetime | None = Query(None, description="Temporal query bound (ISO-8601)"),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[LedgerEventOut]:
    """List non-superseded ledger events, optionally filtered by patient, domain, and time."""
    events = await EvidenceLedgerService.query_active_events(
        session=db,
        patient_id=patient_id,
        domain=domain,
        as_of_time=as_of,
        limit=limit,
        offset=offset,
    )
    return [LedgerEventOut.model_validate(e) for e in events]


@router.get(
    "/events/{event_id}",
    response_model=LedgerEventOut,
    summary="Get a single ledger event",
)
async def get_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> LedgerEventOut:
    from sqlalchemy import select

    from vlep.models.evidence import LedgerEvent
    result = await db.execute(select(LedgerEvent).where(LedgerEvent.event_id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Ledger event not found")
    return LedgerEventOut.model_validate(event)


@router.post(
    "/events/{event_id}/supersede",
    response_model=LedgerEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Supersede an event with a correction",
)
async def supersede_event(
    event_id: uuid.UUID,
    body: LedgerEventSupersede,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> LedgerEventOut:
    """Create a new correction event that supersedes the specified event."""
    # Fetch original to copy required fields
    from sqlalchemy import select

    from vlep.models.evidence import LedgerEvent
    res = await db.execute(select(LedgerEvent).where(LedgerEvent.event_id == event_id))
    original = res.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Original event not found")

    correction = await EvidenceLedgerService.supersede_event(
        session=db,
        original_event_id=event_id,
        patient_id=original.patient_id,
        domain=original.domain,
        data_element=body.correction,
        observed_at=original.observed_at,
        source_attribution=body.source_attribution,
        certainty_level=body.certainty_level,
        rationale=body.rationale,
    )
    return LedgerEventOut.model_validate(correction)


@router.post(
    "/events/{event_id}/notes",
    status_code=status.HTTP_201_CREATED,
    summary="Annotate a ledger event with a note",
)
async def annotate_event(
    event_id: uuid.UUID,
    body: LedgerNoteCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> dict[str, Any]:
    """Append a clinical or audit note to an existing ledger event."""
    note = await EvidenceLedgerService.annotate_event(
        session=db,
        event_id=event_id,
        author_id=body.author_id,
        note_text=body.note_text,
        note_type=body.note_type,
    )
    return {
        "note_id": str(note.note_id),
        "event_id": str(event_id),
        "author_id": note.author_id,
        "note_type": note.note_type,
        "created_at": note.created_at.isoformat(),
    }


@router.get(
    "/patients/{patient_id}/events",
    response_model=list[LedgerEventOut],
    summary="List all active events for a patient",
)
async def patient_events(
    patient_id: uuid.UUID,
    as_of: datetime | None = Query(None),
    domain: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[LedgerEventOut]:
    """Return all non-superseded evidence events for a patient."""
    events = await EvidenceLedgerService.query_active_events(
        session=db,
        patient_id=patient_id,
        domain=domain,
        as_of_time=as_of,
        limit=limit,
    )
    return [LedgerEventOut.model_validate(e) for e in events]


@router.post(
    "/verify/{event_id}",
    response_model=HashVerifyOut,
    summary="Verify SHA-256 hash integrity of a ledger event",
)
async def verify_event_hash(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> HashVerifyOut:
    """Re-compute and compare the SHA-256 hash to detect tampering."""
    result = await EvidenceLedgerService.verify_event_integrity(session=db, event_id=event_id)
    return HashVerifyOut(
        event_id=event_id,
        valid=result["valid"],
        stored_hash=result.get("stored_hash"),
        computed_hash=result.get("computed_hash"),
        message=result.get("message", ""),
    )
