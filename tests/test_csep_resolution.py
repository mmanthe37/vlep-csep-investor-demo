"""
Unit and integration tests for Stage 6a: CSEP Resolution Function F.
Verifies CSEP profile assembly, conflict resolution priorities, trace mapping, and hashing.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from vlep.models.core import Patient
from vlep.models.csep import (
    ProfileAssertionTrace,
)
from vlep.models.evidence import LedgerEvent
from vlep.models.modeling import LpaRun, Prediction, TimeToEventHazard
from vlep.models.nosology import FrameworkVersion
from vlep.models.phenotyping import PhenotypeAssertion
from vlep.services.csep_resolver import CsepResolverService


@pytest.fixture
async def sample_framework(db_session) -> FrameworkVersion:
    """Create a sample framework version."""
    fw = FrameworkVersion(
        framework_name="ILAE 2017 Baseline",
        version_label="v1.0-test-csep",
        effective_from=datetime.now(UTC).date(),
    )
    db_session.add(fw)
    await db_session.commit()
    return fw


@pytest.fixture
async def sample_csep_patient(db_session) -> Patient:
    """Create a sample patient."""
    patient = Patient(source_patient_hash="csep-patient-hash")
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.mark.asyncio
async def test_assemble_csep_profile_success(db_session, sample_csep_patient, sample_framework):
    """Test assembling a CSEP profile with active assertions, predictions, and hashing."""
    now = datetime.now(UTC)
    patient_id = sample_csep_patient.patient_id
    nosology_id = sample_framework.nosology_version_id

    # 1. Seed supporting ledger events and assertions
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

    # Create assertions
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
    )
    ass2 = PhenotypeAssertion(
        patient_id=patient_id,
        phenotype_dimension="etiology",
        phenotype_label_text="Unknown Etiology",
        effective_start=now - timedelta(days=5),
        confidence_data_quality=0.50,
        confidence_recency=0.50,
        confidence_consistency=1.0,
        posterior_probability=0.30,
        final_score=0.45,
        status="active",
    )
    ass3 = PhenotypeAssertion(
        patient_id=patient_id,
        phenotype_dimension="etiology",
        phenotype_label_text="Genetic Etiology",
        effective_start=now - timedelta(days=4),
        confidence_data_quality=0.95,
        confidence_recency=0.95,
        confidence_consistency=1.0,
        posterior_probability=0.95,
        final_score=0.95,
        status="active",
    )
    db_session.add_all([ass1, ass2, ass3])
    await db_session.commit()

    # 2. Seed modeling hazards & predictions
    run = LpaRun(run_kind="test-run")
    db_session.add(run)
    await db_session.commit()

    haz = TimeToEventHazard(
        lpa_run_id=run.lpa_run_id,
        patient_id=patient_id,
        event_type="sudep",
        as_of_time=now - timedelta(days=1),
        horizon_days=365,
        hazard_value=0.0025,
        survival_probability=0.9975,
        cumulative_incidence=0.0025,
    )
    pred = Prediction(
        lpa_run_id=run.lpa_run_id,
        patient_id=patient_id,
        prediction_type="early_shift_detection",
        as_of_time=now - timedelta(days=1),
        value_numeric=1.0,
        value_json={"transition_imminent": True, "lead_time_months": 4.2},
    )
    db_session.add_all([haz, pred])
    await db_session.commit()

    # 3. Assemble profile
    profile = await CsepResolverService.assemble_csep_profile(
        session=db_session,
        patient_id=patient_id,
        nosology_version_id=nosology_id,
        as_of_time=now,
        lpa_run_id=run.lpa_run_id,
    )
    await db_session.commit()

    # Assertions
    assert profile.csep_id is not None
    assert profile.profile_hash is not None
    assert profile.seizure_type_distribution == {"focal_seizure": 1.0}

    # Check that Genetic Etiology was ranked first (rank 1) over Unknown Etiology (rank 2)
    assert len(profile.etiology_ranked_confidence) == 2
    assert profile.etiology_ranked_confidence[0]["etiology"] == "Genetic Etiology"
    assert profile.etiology_ranked_confidence[0]["rank"] == 1
    assert profile.etiology_ranked_confidence[1]["etiology"] == "Unknown Etiology"
    assert profile.etiology_ranked_confidence[1]["rank"] == 2

    # Check predictions mapping
    assert "sudep_risk" in profile.predictive_outputs
    assert profile.predictive_outputs["sudep_risk"]["hazard_value"] == 0.0025
    assert profile.predictive_outputs["early_shift_detection"]["transition_imminent"] is True
    assert profile.predictive_outputs["early_shift_detection"]["lead_time_months"] == 4.2

    # Check trace tables
    stmt_ass_trace = select(ProfileAssertionTrace).where(ProfileAssertionTrace.csep_id == profile.csep_id)
    res_ass = await db_session.execute(stmt_ass_trace)
    traces_ass = res_ass.scalars().all()
    assert len(traces_ass) == 3
