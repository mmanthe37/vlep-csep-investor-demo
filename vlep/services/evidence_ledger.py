"""
VLEP Pipeline — Evidence Ledger Service.

Handles Stage 3: Evidence Ledger Management.
Includes append, supersede, annotate, and temporal querying of ledger events,
enforcing immutability, advisory locking, and hash chain integrity.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.evidence import LedgerEvent, LedgerEventNote
from vlep.utils.crypto import verify_ledger_chain

logger = logging.getLogger(__name__)

# The VLEP Evidence Ledger Advisory Lock ID
LEDGER_ADVISORY_LOCK_ID = 892347001


class EvidenceLedgerService:
    """Service handling Stage 3: Evidence Ledger Management."""

    @staticmethod
    async def append_event(
        session: AsyncSession,
        patient_id: uuid.UUID,
        observed_at: datetime,
        domain: str,
        data_element: dict[str, Any],
        normalized_codes: list[dict[str, Any]] | None = None,
        source_attribution: str = "automated_system",
        source_system_id: uuid.UUID | None = None,
        raw_resource_id: uuid.UUID | None = None,
        source_document_id: uuid.UUID | None = None,
        source_claim_id: uuid.UUID | None = None,
        provenance: dict[str, Any] | None = None,
        certainty_level: float = 1.0,
        validation_status: str = "normalized",
        nosology_version_id: uuid.UUID | None = None,
        supersedes_event_id: uuid.UUID | None = None,
        ingestion_run_id: uuid.UUID | None = None,
        inserted_by: str | None = None,
        request_id: str | None = None,
    ) -> LedgerEvent:
        """Append a new event to the evidence ledger.
        
        Acquires the database advisory lock to ensure serialization of hash chains,
        inserts the LedgerEvent, and lets the database trigger compute hash_prev/hash_self.
        """
        # Acquire advisory lock to serialize inserts
        await session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": LEDGER_ADVISORY_LOCK_ID}
        )

        event = LedgerEvent(
            patient_id=patient_id,
            observed_at=observed_at,
            domain=domain,
            data_element=data_element,
            normalized_codes=normalized_codes or [],
            source_attribution=source_attribution,
            source_system_id=source_system_id,
            raw_resource_id=raw_resource_id,
            source_document_id=source_document_id,
            source_claim_id=source_claim_id,
            provenance=provenance or {},
            certainty_level=certainty_level,
            validation_status=validation_status,
            nosology_version_id=nosology_version_id,
            supersedes_event_id=supersedes_event_id,
            ingestion_run_id=ingestion_run_id,
            inserted_by=inserted_by,
            request_id=request_id,
        )

        session.add(event)
        await session.flush()  # Populates auto-generated fields and triggers hash generation
        await session.refresh(event)  # Fetch database-generated hashes and sequence ID
        logger.info("Appended event %s to ledger (patient: %s)", event.event_id, patient_id)
        return event

    @staticmethod
    async def supersede_event(
        session: AsyncSession,
        original_event_id: uuid.UUID,
        correction_data: dict[str, Any],
    ) -> LedgerEvent:
        """Supersede an existing event by appending a correction event.
        
        Note: The original event is not modified (enforced by prevent_ledger_mutation trigger).
        Instead, the correction event is inserted with supersedes_event_id set to the original_event_id.
        """
        # Verify the original event exists
        stmt = select(LedgerEvent).where(LedgerEvent.event_id == original_event_id)
        result = await session.execute(stmt)
        original_event = result.scalar_one_or_none()
        if not original_event:
            raise ValueError(f"Original event with ID {original_event_id} not found.")

        # Ensure original event's patient_id is used if not provided
        patient_id = correction_data.get("patient_id", original_event.patient_id)

        # Merge or default key parameters from original event if missing
        observed_at = correction_data.get("observed_at", original_event.observed_at)
        domain = correction_data.get("domain", original_event.domain)
        data_element = correction_data.get("data_element", original_event.data_element)
        normalized_codes = correction_data.get("normalized_codes", original_event.normalized_codes)
        source_attribution = correction_data.get("source_attribution", "manual_curator")

        # Append the new correction event
        correction_event = await EvidenceLedgerService.append_event(
            session=session,
            patient_id=patient_id,
            observed_at=observed_at,
            domain=domain,
            data_element=data_element,
            normalized_codes=normalized_codes,
            source_attribution=source_attribution,
            source_system_id=correction_data.get("source_system_id"),
            raw_resource_id=correction_data.get("raw_resource_id"),
            source_document_id=correction_data.get("source_document_id"),
            source_claim_id=correction_data.get("source_claim_id"),
            provenance=correction_data.get("provenance"),
            certainty_level=correction_data.get("certainty_level", 1.0),
            validation_status=correction_data.get("validation_status", "normalized"),
            nosology_version_id=correction_data.get("nosology_version_id"),
            supersedes_event_id=original_event_id,  # Point to the original event
            ingestion_run_id=correction_data.get("ingestion_run_id"),
            inserted_by=correction_data.get("inserted_by"),
            request_id=correction_data.get("request_id"),
        )

        logger.info("Event %s superseded by event %s", original_event_id, correction_event.event_id)
        return correction_event

    @staticmethod
    async def annotate_event(
        session: AsyncSession,
        event_id: uuid.UUID,
        note_text: str,
        note_kind: str = "curator_note",
        curator_name: str | None = None,
    ) -> LedgerEventNote:
        """Add an annotation note to a ledger event."""
        # Check that event exists
        stmt = select(LedgerEvent).where(LedgerEvent.event_id == event_id)
        result = await session.execute(stmt)
        event = result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Ledger event with ID {event_id} not found.")

        note = LedgerEventNote(
            event_id=event_id,
            note_text=note_text,
            note_kind=note_kind,
            created_by=curator_name,
        )
        session.add(note)
        await session.flush()
        logger.info("Annotated event %s with note %s", event_id, note.note_id)
        return note

    @staticmethod
    async def query_active_events(
        session: AsyncSession,
        patient_id: uuid.UUID,
        as_of_time: datetime | None = None,
        domain: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[LedgerEvent]:
        """Query active ledger events for a patient as of a specific time.
        
        Excludes superseded events and enforces observed_at <= as_of_time.
        A superseding event only supersedes the original if the superseding event
        itself was observed at or before as_of_time.
        """
        if as_of_time is None:
            as_of_time = datetime.now(UTC)

        from sqlalchemy.orm import aliased

        newer_event = aliased(LedgerEvent)
        # Subquery to check if this event has been superseded as of as_of_time
        supersedes_subq = select(1).select_from(newer_event).where(
            and_(
                newer_event.supersedes_event_id == LedgerEvent.event_id,
                newer_event.validation_status.in_(["normalized", "verified"]),
                newer_event.observed_at <= as_of_time,
            )
        )

        conditions = [
            LedgerEvent.patient_id == patient_id,
            LedgerEvent.observed_at <= as_of_time,
            LedgerEvent.validation_status.in_(["normalized", "verified"]),
            ~supersedes_subq.exists(),
        ]
        if domain:
            conditions.append(LedgerEvent.domain == domain)

        stmt = (
            select(LedgerEvent)
            .where(and_(*conditions))
            .order_by(LedgerEvent.observed_at.asc(), LedgerEvent.event_seq.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def verify_integrity(session: AsyncSession) -> bool:
        """Verify the integrity of the ledger hash chain."""
        return await verify_ledger_chain(session)
