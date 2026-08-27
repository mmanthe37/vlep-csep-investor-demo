"""
Full Pipeline Smoke Test — End-to-End Integration.

Exercises the complete VLEP data flow in a single test transaction:

  Ingest → Evidence Ledger → Phenotype Assertion → Feature Window
  → Nosological Reinterpretation → Temporal Query → Hash Integrity → API Access
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.api.deps import get_db
from vlep.api.main import create_app
from vlep.models.core import Cohort, CohortMembership, Patient
from vlep.models.evidence import LedgerEvent
from vlep.models.nosology import FrameworkVersion
from vlep.models.phenotyping import FeatureSet, PhenotypeAssertion
from vlep.services.evidence_ledger import EvidenceLedgerService
from vlep.services.literature import LiteratureService
from vlep.services.nosology import NosologyService
from vlep.services.phenotyping import PhenotypingService

NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_full_pipeline_smoke(db_session: AsyncSession):
    """Run the entire longitudinal phenotype pipeline from ingestion to API serving."""
    # ------------------------------------------------------------------------
    # Stage 0 — Patient & Cohort Setup
    # ------------------------------------------------------------------------
    patient = Patient(
        source_patient_hash=f"smoke-{uuid.uuid4().hex}",
        birth_year=1978,
        sex_at_birth="female",
        race_ethnicity={"ethnicity": "hispanic_or_latino"},
    )
    cohort = Cohort(
        name=f"Smoke-Cohort-{uuid.uuid4().hex[:6]}",
        description="Pipeline smoke test cohort",
        inclusion_criteria={"min_age": 18},
    )
    db_session.add(patient)
    db_session.add(cohort)
    await db_session.flush()

    membership = CohortMembership(
        patient_id=patient.patient_id,
        cohort_id=cohort.cohort_id,
        status="active",
    )
    db_session.add(membership)
    await db_session.flush()

    patient_id = patient.patient_id
    cohort_id = cohort.cohort_id

    assert patient_id is not None
    assert cohort_id is not None

    # ------------------------------------------------------------------------
    # Stage 1 — Multi-Domain Evidence Ingestion
    # ------------------------------------------------------------------------
    domains = [
        ("clinical_observation", {"icd10": "G40.909", "description": "Focal epilepsy"}),
        ("EEG_biomarker", {"finding": "left_temporal_spike_wave", "duration_min": 30}),
        ("imaging_biomarker", {"modality": "MRI", "finding": "hippocampal_sclerosis_left"}),
        ("genetic_result", {"gene": "SCN1A", "variant": "c.4849C>T", "effect": "pathogenic"}),
    ]

    event_ids = []
    for domain, data_element in domains:
        event = await EvidenceLedgerService.append_event(
            session=db_session,
            patient_id=patient_id,
            domain=domain,
            data_element=data_element,
            observed_at=NOW - timedelta(days=90),
            source_attribution="automated_system",
            certainty_level=0.92,
            validation_status="verified",
        )
        assert event.event_id is not None
        assert event.hash_self is not None, f"Hash missing for domain {domain}"
        event_ids.append(event.event_id)

    result = await db_session.execute(
        select(LedgerEvent).where(LedgerEvent.patient_id == patient_id)
    )
    assert len(result.scalars().all()) == 4

    # ------------------------------------------------------------------------
    # Stage 2 — Hash Chain Verification
    # ------------------------------------------------------------------------
    result = await db_session.execute(
        select(LedgerEvent).where(LedgerEvent.patient_id == patient_id)
    )
    for event in result.scalars().all():
        assert event.hash_self is not None
        assert len(event.hash_self) == 64

    # ------------------------------------------------------------------------
    # Stage 3 — Event Annotation
    # ------------------------------------------------------------------------
    note = await EvidenceLedgerService.annotate_event(
        session=db_session,
        event_id=event_ids[0],
        curator_name="smoke_clinician",
        note_text="Confirmed by EEG report review.",
        note_kind="clinical",
    )
    assert note.note_id is not None

    # ------------------------------------------------------------------------
    # Stage 4 — Event Supersede / Correction
    # ------------------------------------------------------------------------
    result = await db_session.execute(
        select(LedgerEvent).where(
            LedgerEvent.patient_id == patient_id,
            LedgerEvent.domain == "clinical_observation",
        )
    )
    original = result.scalar_one()

    correction = await EvidenceLedgerService.supersede_event(
        session=db_session,
        original_event_id=original.event_id,
        correction_data={
            "patient_id": patient_id,
            "domain": "clinical_observation",
            "data_element": {"icd10": "G40.111", "description": "Focal onset aware seizure"},
            "observed_at": original.observed_at,
            "source_attribution": "manual_curator",
            "certainty_level": 0.97,
            "rationale": "Reclassified per ILAE 2017.",
        }
    )
    assert correction.supersedes_event_id == original.event_id

    await db_session.refresh(original)
    assert original.validation_status == "verified"
    correction_event_id = correction.event_id

    # ------------------------------------------------------------------------
    # Stage 5 — Literature Ingestion
    # ------------------------------------------------------------------------
    doc = await LiteratureService.create_document(
        session=db_session,
        title="SCN1A variants in Dravet syndrome: meta-analysis",
        pmid=f"SMOKE{uuid.uuid4().hex[:6].upper()}",
        doi=f"10.1000/smoke.{uuid.uuid4().hex[:8]}",
        publication_year=2022,
        study_design="meta-analysis",
        n_subjects=1240,
        p_value=0.001,
        effect_size=0.42,
    )
    assert doc.document_id is not None

    claim = await LiteratureService.ingest_claim(
        session=db_session,
        document_id=doc.document_id,
        subject_text="SCN1A LoF variants",
        predicate="associated_with",
        object_text="Dravet syndrome",
        source_sentence="SCN1A LoF variants strongly associated with Dravet (OR=12.4, p<0.001).",
        negated=False,
        certainty=0.95,
    )
    assert claim.claim_id is not None

    # ------------------------------------------------------------------------
    # Stage 6 — Phenotype Assertions (6 Dimensions)
    # ------------------------------------------------------------------------
    fw = FrameworkVersion(
        framework_name="ILAE 2017",
        version_label=f"2017.smoke-{uuid.uuid4().hex[:4]}",
        effective_from=date(2017, 1, 1),
    )
    db_session.add(fw)
    await db_session.flush()
    nosology_version_id = fw.nosology_version_id

    assertion = await PhenotypingService.create_assertion(
        session=db_session,
        patient_id=patient_id,
        dimension="seizure_type",
        phenotype_code="HP:0007359",
        phenotype_label="Focal-onset seizure",
        certainty_level=0.95,
        confidence_data_quality=0.90,
        confidence_recency=0.88,
        confidence_consistency=0.93,
        nosology_version_id=nosology_version_id,
    )
    assert assertion.assertion_id is not None
    assert assertion.final_score is not None
    assert 0.0 <= assertion.final_score <= 1.0

    # Remaining 5 phenotype dimensions are asserted
    dimensions = [
        ("etiology", "HP:0001250", "Seizure"),
        ("syndrome", "MONDO:0011071", "Dravet syndrome"),
        ("biomarker", "SCN1A_LOF", "SCN1A Loss-of-Function"),
        ("comorbidity", "HP:0001249", "Intellectual disability"),
        ("treatment_response", "CARBAMAZEPINE_FAILURE", "Carbamazepine non-responder"),
    ]
    for dim, code, label in dimensions:
        a = await PhenotypingService.create_assertion(
            session=db_session,
            patient_id=patient_id,
            dimension=dim,
            phenotype_code=code,
            phenotype_label=label,
            certainty_level=0.80,
            confidence_data_quality=0.85,
            confidence_recency=0.80,
            confidence_consistency=0.80,
            nosology_version_id=nosology_version_id,
        )
        assert a.assertion_id is not None, f"Assertion failed for {dim}"

    # ------------------------------------------------------------------------
    # Stage 7 — Feature Engineering & Temporal Windows
    # ------------------------------------------------------------------------
    fset = FeatureSet(
        name=f"Smoke-MVP-{uuid.uuid4().hex[:4]}",
        version_label="v1.0-smoke",
        description="Smoke test feature set",
        dimensionality=256,
        window_days=30,
    )
    db_session.add(fset)
    await db_session.flush()
    feature_set_id = fset.feature_set_id

    defs = await PhenotypingService.bootstrap_feature_definitions(
        session=db_session,
        feature_set_id=feature_set_id,
    )
    assert len(defs) == 256

    window, values = await PhenotypingService.build_feature_values_for_window(
        session=db_session,
        patient_id=patient_id,
        feature_set_id=feature_set_id,
        window_start=NOW - timedelta(days=180),
        window_end=NOW,
        as_of_time=NOW,
    )
    assert window.feature_window_id is not None
    assert window.patient_id == patient_id

    # ------------------------------------------------------------------------
    # Stage 8 — Nosological Reinterpretation
    # ------------------------------------------------------------------------
    target_fw = FrameworkVersion(
        framework_name="ILAE 2022",
        version_label=f"2022.smoke-{uuid.uuid4().hex[:4]}",
        effective_from=date(2022, 1, 1),
    )
    db_session.add(target_fw)
    await db_session.flush()

    job = await NosologyService.create_reinterpretation_job(
        session=db_session,
        source_nosology_version_id=nosology_version_id,
        target_nosology_version_id=target_fw.nosology_version_id,
        cohort_id=None,
    )
    assert job.status == "queued"

    await NosologyService.execute_reinterpretation_job(
        session=db_session,
        reinterpretation_job_id=job.reinterpretation_job_id,
        patient_ids=[patient_id],
    )
    await db_session.refresh(job)
    assert job.status in ("completed", "completed_with_warnings")

    # ------------------------------------------------------------------------
    # Stage 9 — Temporal Query & Integrity Verification
    # ------------------------------------------------------------------------
    active = await EvidenceLedgerService.query_active_events(
        session=db_session,
        patient_id=patient_id,
        as_of_time=NOW,
    )
    assert len(active) >= 1
    for event in active:
        assert event.validation_status != "superseded"

    # SHA-256 hash verification passes for the unmodified ledger
    valid = await EvidenceLedgerService.verify_integrity(session=db_session)
    assert valid is True

    # ------------------------------------------------------------------------
    # Stage 10 — HTTP API Access
    # ------------------------------------------------------------------------
    app = create_app()

    async def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Actor-ID": "smoke_director", "X-Actor-Role": "clinical_director"},
    ) as client:
        resp = await client.get(f"/api/v1/patients/{patient_id}")

    assert resp.status_code == 200
    assert resp.json()["patient_id"] == str(patient_id)

    # ------------------------------------------------------------------------
    # Stage 11 — Full Pipeline Summary Verification
    # ------------------------------------------------------------------------
    ev_result = await db_session.execute(
        select(LedgerEvent).where(LedgerEvent.patient_id == patient_id)
    )
    events = ev_result.scalars().all()

    pa_result = await db_session.execute(
        select(PhenotypeAssertion).where(
            PhenotypeAssertion.patient_id == patient_id
        )
    )
    assertions = pa_result.scalars().all()

    # >=5: 4 initial domains + 1 correction
    assert len(events) >= 5, f"Expected >=5 events, got {len(events)}"
    assert len(assertions) >= 6, f"Expected >=6 assertions, got {len(assertions)}"
