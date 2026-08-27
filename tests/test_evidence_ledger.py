"""
Unit and integration tests for Stage 3: Evidence Ledger Management.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import selectinload

from vlep.models.core import Patient
from vlep.models.evidence import LedgerEvent
from vlep.services.evidence_ledger import EvidenceLedgerService


@pytest.fixture
async def sample_patient(db_session) -> Patient:
    """Create and return a sample patient."""
    patient = Patient(source_patient_hash="test-patient-hash-ledger")
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.mark.asyncio
async def test_append_event_success(db_session, sample_patient):
    """Test that appending a ledger event succeeds and computes hashes via DB trigger."""
    observed = datetime.now(UTC) - timedelta(days=1)

    event = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=observed,
        domain="clinical_observation",
        data_element={"condition": "Epilepsy", "status": "active"},
        normalized_codes=[{"system": "http://snomed.info/sct", "code": "84757009"}],
        source_attribution="clinician",
        certainty_level=0.95,
        validation_status="normalized",
    )
    await db_session.commit()

    assert event.event_id is not None
    assert event.event_seq is not None
    assert event.domain == "clinical_observation"
    assert float(event.certainty_level) == 0.95  # Numeric(5,4)

    # Assert hashes are populated by the database trigger
    assert event.hash_self is not None
    assert len(event.hash_self) == 64  # SHA-256 is 64 hex characters

    # Since this is the first/only event, hash_prev may be NULL/None
    # Let's verify we can fetch it back
    stmt = select(LedgerEvent).where(LedgerEvent.event_id == event.event_id)
    result = await db_session.execute(stmt)
    fetched = result.scalar_one()
    assert fetched.hash_self == event.hash_self


@pytest.mark.asyncio
async def test_hash_chain_linkage(db_session, sample_patient):
    """Test that multiple appends form a cryptographically linked hash chain."""
    observed_base = datetime.now(UTC) - timedelta(days=5)

    # Append first event
    e1 = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=observed_base,
        domain="clinical_observation",
        data_element={"event": "initial"},
    )
    await db_session.commit()

    # Append second event
    e2 = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=observed_base + timedelta(days=1),
        domain="clinical_observation",
        data_element={"event": "second"},
    )
    await db_session.commit()

    # Append third event
    e3 = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=observed_base + timedelta(days=2),
        domain="clinical_observation",
        data_element={"event": "third"},
    )
    await db_session.commit()

    # Verify the chain links
    assert e2.hash_prev == e1.hash_self
    assert e3.hash_prev == e2.hash_self

    # Verify using verify_integrity
    is_valid = await EvidenceLedgerService.verify_integrity(db_session)
    assert is_valid is True


@pytest.mark.asyncio
async def test_ledger_immutability_update(db_session, sample_patient):
    """Test that modifying a ledger event raises an error."""
    event = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=datetime.now(UTC),
        domain="clinical_observation",
        data_element={"immutable": "test"},
    )
    await db_session.commit()

    # Attempt to UPDATE event
    with pytest.raises(DBAPIError) as exc_info:
        await db_session.execute(
            text("UPDATE evidence.ledger_events SET validation_status = 'verified' WHERE event_id = :id"),
            {"id": event.event_id}
        )
        await db_session.commit()
    assert "is append-only" in str(exc_info.value)


@pytest.mark.asyncio
async def test_ledger_immutability_delete(db_session, sample_patient):
    """Test that deleting a ledger event raises an error."""
    event = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=datetime.now(UTC),
        domain="clinical_observation",
        data_element={"immutable": "test"},
    )
    await db_session.commit()

    # Attempt to DELETE event
    with pytest.raises(DBAPIError) as exc_info:
        await db_session.execute(
            text("DELETE FROM evidence.ledger_events WHERE event_id = :id"),
            {"id": event.event_id}
        )
        await db_session.commit()
    assert "is append-only" in str(exc_info.value)



@pytest.mark.asyncio
async def test_supersede_event_and_query_active(db_session, sample_patient):
    """Test supersession of events and how they behave under query_active_events."""
    t1 = datetime.now(UTC) - timedelta(days=10)
    t2 = t1 + timedelta(days=2)

    # 1. Ingest original event
    orig = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=t1,
        domain="clinical_observation",
        data_element={"code": "G40.9", "note": "Original incorrect entry"},
        validation_status="normalized"
    )
    await db_session.commit()

    # Verify original is active as of t1
    active_events = await EvidenceLedgerService.query_active_events(db_session, sample_patient.patient_id, t1)
    assert len(active_events) == 1
    assert active_events[0].event_id == orig.event_id

    # 2. Supersede with a correction event observed at t2
    correction_data = {
        "observed_at": t2,
        "data_element": {"code": "G40.3", "note": "Corrected entry"},
        "validation_status": "normalized",
        "source_attribution": "manual_curator"
    }
    corrected = await EvidenceLedgerService.supersede_event(
        session=db_session,
        original_event_id=orig.event_id,
        correction_data=correction_data
    )
    await db_session.commit()

    # Query active events as of t1 (before the correction was observed)
    # The original event should still be active because the correction wasn't active yet!
    active_t1 = await EvidenceLedgerService.query_active_events(db_session, sample_patient.patient_id, t1)
    assert len(active_t1) == 1
    assert active_t1[0].event_id == orig.event_id

    # Query active events as of t2 (when correction is active)
    # The original event should now be excluded (superseded), and only the corrected event remains active.
    active_t2 = await EvidenceLedgerService.query_active_events(db_session, sample_patient.patient_id, t2)
    assert len(active_t2) == 1
    assert active_t2[0].event_id == corrected.event_id


@pytest.mark.asyncio
async def test_temporal_query_enforcement(db_session, sample_patient):
    """Test that events in the future relative to as_of_time are filtered out."""
    now = datetime.now(UTC)
    past = now - timedelta(days=2)
    future = now + timedelta(days=2)

    await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=past,
        domain="clinical_observation",
        data_element={"time": "past"},
    )
    await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=future,
        domain="clinical_observation",
        data_element={"time": "future"},
    )
    await db_session.commit()

    # Query active events as of 'now'
    events = await EvidenceLedgerService.query_active_events(db_session, sample_patient.patient_id, now)
    assert len(events) == 1
    assert events[0].data_element["time"] == "past"


@pytest.mark.asyncio
async def test_annotate_event(db_session, sample_patient):
    """Test annotating a ledger event with notes."""
    event = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=datetime.now(UTC),
        domain="clinical_observation",
        data_element={"test": "annotation"},
    )
    await db_session.commit()

    note = await EvidenceLedgerService.annotate_event(
        session=db_session,
        event_id=event.event_id,
        note_text="This is a curator note",
        note_kind="curator_note",
        curator_name="Dr. Smith"
    )
    await db_session.commit()

    assert note.note_id is not None
    assert note.event_id == event.event_id
    assert note.note_text == "This is a curator note"
    assert note.created_by == "Dr. Smith"

    # Fetch notes via relationship (using selectinload for async session compatibility)
    stmt = (
        select(LedgerEvent)
        .options(selectinload(LedgerEvent.notes))
        .where(LedgerEvent.event_id == event.event_id)
    )
    result = await db_session.execute(stmt)
    fetched = result.scalar_one()
    assert len(fetched.notes) == 1
    assert fetched.notes[0].note_text == "This is a curator note"


@pytest.mark.asyncio
async def test_verify_integrity_tampering_detection(db_session, sample_patient):
    """Test that verify_integrity correctly raises a ValueError if the ledger is tampered with."""
    # 1. Set up a valid ledger chain
    observed = datetime.now(UTC)
    e1 = await EvidenceLedgerService.append_event(
        session=db_session,
        patient_id=sample_patient.patient_id,
        observed_at=observed,
        domain="clinical_observation",
        data_element={"order": 1},
    )
    await db_session.commit()

    # Verify starting state is valid
    assert await EvidenceLedgerService.verify_integrity(db_session) is True

    # 2. Simulate tampering by disabling trigger temporarily and inserting an invalid hash
    await db_session.execute(text("ALTER TABLE evidence.ledger_events DISABLE TRIGGER trg_ledger_events_hash"))

    # Insert tampered event directly using raw SQL or custom INSERT to bypass automatic hashing logic
    tampered_id = uuid.uuid4()
    await db_session.execute(
        text("""
            INSERT INTO evidence.ledger_events 
            (event_id, patient_id, observed_at, domain, data_element, source_attribution, hash_prev, hash_self)
            VALUES (:id, :patient_id, :observed_at, 'clinical_observation', '{"order": 2}'::jsonb, 'automated_system', :hash_prev, :hash_self)
        """),
        {
            "id": tampered_id,
            "patient_id": sample_patient.patient_id,
            "observed_at": observed + timedelta(minutes=1),
            "hash_prev": e1.hash_self,
            "hash_self": "fakehash1234567890fakehash1234567890fakehash1234567890fakehash123"  # invalid hash
        }
    )
    await db_session.commit()

    # Re-enable trigger
    await db_session.execute(text("ALTER TABLE evidence.ledger_events ENABLE TRIGGER trg_ledger_events_hash"))
    await db_session.commit()

    # 3. Assert verify_integrity raises ValueError due to mismatch between computed and recorded hash
    with pytest.raises(ValueError) as exc_info:
        await EvidenceLedgerService.verify_integrity(db_session)
    assert "tamper check failed" in str(exc_info.value)
