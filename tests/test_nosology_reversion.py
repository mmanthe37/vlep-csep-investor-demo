"""
Unit and integration tests for Stage 6b: Nosological Reversioning & Re-interpretation.
Verifies nosological framework management, re-interpretation engine execution, and diff tracking.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from vlep.models.core import Patient
from vlep.models.csep import CSEPProfile
from vlep.models.evidence import LedgerEvent
from vlep.models.nosology import (
    FrameworkVersion,
    ReinterpretationResult,
)
from vlep.models.phenotyping import PhenotypeAssertion
from vlep.services.csep_resolver import CsepResolverService
from vlep.services.nosology import NosologyService


@pytest.fixture
async def framework_source(db_session) -> FrameworkVersion:
    """Create the source framework version (baseline ILAE 2017)."""
    fw = FrameworkVersion(
        framework_name="ILAE 2017 Baseline",
        version_label="v1.0-source",
        effective_from=date(2017, 1, 1),
    )
    db_session.add(fw)
    await db_session.commit()
    return fw


@pytest.fixture
async def framework_target(db_session) -> FrameworkVersion:
    """Create the target framework version (ILAE 2025 Revised)."""
    fw = FrameworkVersion(
        framework_name="ILAE 2025 Revised",
        version_label="v2.0-target",
        effective_from=date(2025, 1, 1),
    )
    db_session.add(fw)
    await db_session.commit()
    return fw


@pytest.fixture
async def reinterpretation_patient(db_session) -> Patient:
    """Create a patient for reinterpretation tests."""
    patient = Patient(source_patient_hash="reinterp-patient-hash")
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.mark.asyncio
async def test_nosological_framework_creation(db_session):
    """Test creating frameworks and resolution rules."""
    fw = await NosologyService.create_framework_version(
        session=db_session,
        framework_name="ILAE 2026 Sandbox",
        version_label="v1.0-sandbox",
        effective_from=date(2026, 1, 1),
    )
    await db_session.commit()

    assert fw.nosology_version_id is not None
    assert fw.framework_name == "ILAE 2026 Sandbox"

    # Create term
    term = await NosologyService.create_taxonomy_term(
        session=db_session,
        nosology_version_id=fw.nosology_version_id,
        dimension="syndrome",
        code="DRAVET",
        display="Dravet Syndrome",
    )
    await db_session.commit()
    assert term.taxonomy_term_id is not None

    # Create rule
    rule = await NosologyService.create_resolution_rule(
        session=db_session,
        nosology_version_id=fw.nosology_version_id,
        rule_name="genetic_override_unknown",
        rule_expression={"condition": "multiple_etiology_assertions"},
        action={"rank_first": "Genetic Etiology"},
        applies_to_dimension="etiology",
    )
    await db_session.commit()
    assert rule.resolution_rule_id is not None


@pytest.mark.asyncio
async def test_execute_reinterpretation_job(db_session, reinterpretation_patient, framework_source, framework_target):
    """Test running a framework reinterpretation/reversioning job end-to-end."""
    now = datetime.now(UTC)
    patient_id = reinterpretation_patient.patient_id

    # 1. Create a phenotype assertion for the patient under the source framework
    e1 = LedgerEvent(
        patient_id=patient_id,
        observed_at=now - timedelta(days=5),
        domain="clinical_observation",
        data_element={"display": "Focal Seizure"},
        source_attribution="clinician",
        certainty_level=0.90,
        validation_status="normalized",
    )
    db_session.add(e1)
    await db_session.commit()

    ass1 = PhenotypeAssertion(
        patient_id=patient_id,
        phenotype_dimension="seizure_type",
        phenotype_label_text="Focal Seizure",
        effective_start=now - timedelta(days=5),
        confidence_data_quality=0.90,
        confidence_recency=0.95,
        confidence_consistency=1.0,
        posterior_probability=0.85,
        final_score=0.88,
        status="active",
        nosology_version_id=framework_source.nosology_version_id,
    )
    ass_syndrome_source = PhenotypeAssertion(
        patient_id=patient_id,
        phenotype_dimension="syndrome",
        phenotype_label_text="Temporal Lobe Epilepsy",
        effective_start=now - timedelta(days=5),
        confidence_data_quality=0.80,
        confidence_recency=0.80,
        confidence_consistency=1.0,
        posterior_probability=0.75,
        final_score=0.78,
        status="active",
        nosology_version_id=framework_source.nosology_version_id,
    )
    db_session.add_all([ass1, ass_syndrome_source])
    await db_session.commit()

    # 2. Assemble CSEP profile under the source framework
    profile_source = await CsepResolverService.assemble_csep_profile(
        session=db_session,
        patient_id=patient_id,
        nosology_version_id=framework_source.nosology_version_id,
        as_of_time=now,
    )
    await db_session.commit()

    assert profile_source.nosology_version_id == framework_source.nosology_version_id

    # 3. Simulate new classification rules by creating a revised assertion under the target framework
    # In target framework, the patient is classified as having "Focal Epilepsy with Temporal Lobe Seizures"
    ass_syndrome_target = PhenotypeAssertion(
        patient_id=patient_id,
        phenotype_dimension="syndrome",
        phenotype_label_text="Focal Epilepsy with Temporal Lobe Seizures",
        effective_start=now - timedelta(days=5),
        confidence_data_quality=0.90,
        confidence_recency=0.90,
        confidence_consistency=1.0,
        posterior_probability=0.85,
        final_score=0.88,
        status="active",
        nosology_version_id=framework_target.nosology_version_id,
    )
    db_session.add(ass_syndrome_target)
    await db_session.commit()

    # 4. Create and run the reinterpretation job
    job = await NosologyService.create_reinterpretation_job(
        session=db_session,
        source_nosology_version_id=framework_source.nosology_version_id,
        target_nosology_version_id=framework_target.nosology_version_id,
    )
    await db_session.commit()

    assert job.status == "queued"

    completed_job = await NosologyService.execute_reinterpretation_job(
        session=db_session,
        reinterpretation_job_id=job.reinterpretation_job_id,
    )
    await db_session.commit()

    # 5. Assertions on completion
    assert completed_job.status == "completed"
    assert completed_job.finished_at is not None
    assert completed_job.metadata_ == {"patients_reinterpreted": 1}

    # Verify result records
    stmt_res = select(ReinterpretationResult).where(
        ReinterpretationResult.reinterpretation_job_id == job.reinterpretation_job_id
    )
    result_list = (await db_session.execute(stmt_res)).scalars().all()
    assert len(result_list) == 1

    res_val = result_list[0]
    assert res_val.patient_id == patient_id
    assert res_val.source_csep_id == profile_source.csep_id
    assert res_val.target_csep_id is not None

    # Check changes JSON shows the syndrome change
    assert res_val.changes_json["syndrome_changed"] is True
    assert res_val.changes_json["previous_syndrome"] == "Temporal Lobe Epilepsy"
    assert res_val.changes_json["new_syndrome"] == "Focal Epilepsy with Temporal Lobe Seizures"

    # Verify target profile exists in CSEPProfiles
    stmt_tgt = select(CSEPProfile).where(CSEPProfile.csep_id == res_val.target_csep_id)
    tgt_profile = (await db_session.execute(stmt_tgt)).scalar_one()
    assert tgt_profile.nosology_version_id == framework_target.nosology_version_id
    assert tgt_profile.epilepsy_syndrome["syndrome"] == "Focal Epilepsy with Temporal Lobe Seizures"
