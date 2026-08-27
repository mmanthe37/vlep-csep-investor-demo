"""
Unit tests for Stage 5: LPA Core — Longitudinal Modeling.
Verifies model registration, GLMM baseline, HMM Viterbi decoding,
Survival ensemble, trajectory velocity, and validation metrics.
"""

from datetime import UTC, datetime, timedelta

import pytest

from vlep.models.core import Patient
from vlep.models.evidence import LedgerEvent
from vlep.models.phenotyping import (
    FeatureSet,
)
from vlep.services.lpa_engine import LpaEngineService
from vlep.services.phenotyping import PhenotypingService


@pytest.fixture
async def lpa_feature_set(db_session) -> FeatureSet:
    """Create a sample feature set for LPA tests."""
    fset = FeatureSet(
        name="LPA MVP Feature Vector",
        version_label="v1.0-lpa",
        description="LPA test feature set",
        dimensionality=256,
        window_days=30,
    )
    db_session.add(fset)
    await db_session.commit()
    return fset


@pytest.fixture
async def lpa_patient(db_session) -> Patient:
    """Create a sample patient for LPA tests."""
    patient = Patient(
        source_patient_hash="lpa-patient-hash",
        birth_year=1995,
        sex_at_birth="Female",
    )
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.mark.asyncio
async def test_model_version_registration(db_session):
    """Test model version registration."""
    mver = await LpaEngineService.register_model_version(
        session=db_session,
        name="LPA HMM Model",
        family="HMM",
        version_label="v1.0.0",
        hyperparameters={"states": 4},
        model_card={"author": "VLEP Team"},
    )
    await db_session.commit()

    assert mver.model_version_id is not None
    assert mver.name == "LPA HMM Model"
    assert mver.family == "HMM"
    assert mver.version_label == "v1.0.0"
    assert mver.hyperparameters == {"states": 4}


@pytest.mark.asyncio
async def test_lpa_run_lifecycle(db_session, lpa_feature_set):
    """Test starting, completing, and failing LPA runs."""
    mver = await LpaEngineService.register_model_version(
        session=db_session,
        name="LPA GLMM Model",
        family="GLMM",
        version_label="v1.0.0",
    )
    await db_session.commit()

    # Start Run
    run = await LpaEngineService.start_lpa_run(
        session=db_session,
        run_kind="cohort_simulation",
        model_version_id=mver.model_version_id,
        feature_set_id=lpa_feature_set.feature_set_id,
    )
    await db_session.commit()

    assert run.lpa_run_id is not None
    assert run.status == "running"
    assert run.started_at is not None

    # Complete Run
    run_completed = await LpaEngineService.complete_lpa_run(
        session=db_session,
        lpa_run_id=run.lpa_run_id,
        patients_processed=10,
        metrics={"avg_runtime_sec": 1.2},
    )
    await db_session.commit()

    assert run_completed.status == "completed"
    assert run_completed.patients_processed == 10
    assert run_completed.finished_at is not None
    assert run_completed.metrics == {"avg_runtime_sec": 1.2}

    # Fail Run
    run2 = await LpaEngineService.start_lpa_run(
        session=db_session,
        run_kind="cohort_simulation",
        model_version_id=mver.model_version_id,
        feature_set_id=lpa_feature_set.feature_set_id,
    )
    await db_session.commit()

    run_failed = await LpaEngineService.fail_lpa_run(
        session=db_session,
        lpa_run_id=run2.lpa_run_id,
        error_summary="ConvergenceWarning: Solver failed to converge",
    )
    await db_session.commit()

    assert run_failed.status == "failed"
    assert run_failed.error_summary == "ConvergenceWarning: Solver failed to converge"


@pytest.mark.asyncio
async def test_run_glmm_baseline(db_session, lpa_patient):
    """Test GLMM baseline vector P(0) calculation."""
    P_0 = await LpaEngineService.run_glmm_baseline(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        dimensionality=256,
    )

    assert len(P_0) == 256
    # Ensure it calculates non-negative float values
    for val in P_0:
        assert isinstance(val, float)
        assert val >= 0.0


@pytest.mark.asyncio
async def test_run_hmm_viterbi_and_velocity(db_session, lpa_patient, lpa_feature_set):
    """Test chronological HMM decoding and trajectory velocity calculation."""
    now = datetime.now(UTC)

    # 1. Bootstrap feature definitions
    defs = await PhenotypingService.bootstrap_feature_definitions(
        session=db_session,
        feature_set_id=lpa_feature_set.feature_set_id,
    )
    await db_session.commit()

    # 2. Append events representing 2 time points (35 days apart)
    # Timepoint 1: 45 days ago
    e1 = LedgerEvent(
        patient_id=lpa_patient.patient_id,
        observed_at=now - timedelta(days=45),
        domain="clinical_observation",
        data_element={"display": "Focal Seizure"},
        source_attribution="clinician",
        certainty_level=0.90,
        validation_status="normalized",
    )
    # Timepoint 2: 10 days ago
    e2 = LedgerEvent(
        patient_id=lpa_patient.patient_id,
        observed_at=now - timedelta(days=10),
        domain="clinical_observation",
        data_element={"display": "Focal Seizure"},
        source_attribution="clinician",
        certainty_level=0.95,
        validation_status="normalized",
    )
    # Add a drug resistance event to Timepoint 2 to simulate a transition
    e3 = LedgerEvent(
        patient_id=lpa_patient.patient_id,
        observed_at=now - timedelta(days=10),
        domain="clinical_observation",
        data_element={"display": "Drug Resistance"},
        source_attribution="clinician",
        certainty_level=0.98,
        validation_status="normalized",
    )
    db_session.add_all([e1, e2, e3])
    await db_session.commit()

    # 3. Build features for Window 1: [now - 60 days, now - 30 days]
    w1, vals1 = await PhenotypingService.build_feature_values_for_window(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        feature_set_id=lpa_feature_set.feature_set_id,
        window_start=now - timedelta(days=60),
        window_end=now - timedelta(days=30),
        as_of_time=now - timedelta(days=30),
    )
    # Build features for Window 2: [now - 30 days, now]
    w2, vals2 = await PhenotypingService.build_feature_values_for_window(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        feature_set_id=lpa_feature_set.feature_set_id,
        window_start=now - timedelta(days=30),
        window_end=now,
        as_of_time=now,
    )
    await db_session.commit()

    # Get baseline P(0)
    P_0 = await LpaEngineService.run_glmm_baseline(
        session=db_session,
        patient_id=lpa_patient.patient_id,
    )

    # Start run
    run = await LpaEngineService.start_lpa_run(
        session=db_session,
        run_kind="simulation",
        feature_set_id=lpa_feature_set.feature_set_id,
    )
    await db_session.commit()

    # Run HMM decoding
    sequences = await LpaEngineService.run_hmm_viterbi(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        lpa_run_id=run.lpa_run_id,
        feature_set_id=lpa_feature_set.feature_set_id,
        as_of_time=now,
        P_0=P_0,
    )
    await db_session.commit()

    assert len(sequences) == 2
    assert sequences[0].state_label in [
        "Controlled / Seizure Free",
        "Mild / Fluctuating",
        "Severe / Drug Resistant",
        "Refractory Transition",
    ]
    assert 0.0 <= sequences[0].state_probability <= 1.0
    assert sequences[0].viterbi_path is not None

    # Calculate Trajectory Velocity and transition prediction
    pred = await LpaEngineService.compute_trajectory_velocity(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        lpa_run_id=run.lpa_run_id,
        feature_set_id=lpa_feature_set.feature_set_id,
        as_of_time=now,
        P_0=P_0,
    )
    await db_session.commit()

    # Since Window 2 includes e3 ("Drug Resistance"), the feature velocity
    # should trigger transition_imminent = True
    assert pred is not None
    assert pred.prediction_type == "early_shift_detection"
    assert pred.value_json["transition_imminent"] is True
    assert pred.value_json["lead_time_months"] == 4.2


@pytest.mark.asyncio
async def test_run_survival_ensemble_and_metrics(db_session, lpa_patient):
    """Test survival hazard calculations and metric evaluation."""
    # Generate mock phenotype vector
    P_t = [0.1] * 256
    P_t[1] = 0.8  # High generalized seizure value
    P_t[7] = 0.9  # High drug resistance value

    run = await LpaEngineService.start_lpa_run(
        session=db_session,
        run_kind="simulation",
    )
    await db_session.commit()

    as_of = datetime.now(UTC)
    hazards = await LpaEngineService.run_survival_ensemble(
        session=db_session,
        patient_id=lpa_patient.patient_id,
        lpa_run_id=run.lpa_run_id,
        P_t=P_t,
        as_of_time=as_of,
        current_state_index=2,
    )
    await db_session.commit()

    assert len(hazards) == 3
    event_types = [h.event_type for h in hazards]
    assert "sudep" in event_types
    assert "drug_resistance" in event_types
    assert "seizure_freedom" in event_types

    # Verify column values
    for h in hazards:
        assert h.hazard_value > 0.0
        assert 0.0 <= float(h.survival_probability) <= 1.0
        assert 0.0 <= float(h.cumulative_incidence) <= 1.0
        assert h.feature_contributions is not None

    # Evaluate validation metrics
    results = await LpaEngineService.evaluate_run_performance(
        session=db_session,
        lpa_run_id=run.lpa_run_id,
    )
    await db_session.commit()

    assert len(results) == 3
    metric_names = [m.metric_name for m in results]
    assert "Concordance Index (C-index)" in metric_names
    assert "Brier Score" in metric_names
    assert "AUROC" in metric_names
    for m in results:
        assert m.metric_value > 0.0
