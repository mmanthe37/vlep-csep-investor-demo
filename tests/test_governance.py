"""
Unit and integration tests for Stage 7: Review, Governance & Safety.
Verifies audit middleware logging, review task lifecycle, issue report adjudications,
data quality runs, and model drift and fairness monitoring.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import vlep.api.middleware.audit
from vlep.api.middleware.audit import GovernanceAuditMiddleware
from vlep.models.core import Patient
from vlep.models.evidence import LedgerEvent
from vlep.models.governance import AccessLog
from vlep.models.modeling import LpaRun, ModelVersion, Prediction
from vlep.models.review import IssueReport, ReviewTask
from vlep.services.governance import GovernanceService
from vlep.services.review import ReviewService


@pytest.fixture
async def gov_patient(db_session) -> Patient:
    """Create a sample patient for governance tests."""
    patient = Patient(
        source_patient_hash="gov-patient-hash-new",
        birth_year=1980,
        sex_at_birth="Male",
    )
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.fixture
async def gov_model_version(db_session) -> ModelVersion:
    """Create a sample model version for drift checks."""
    mver = ModelVersion(
        name="Gov XGBoost Model",
        family="XGBOOST",
        version_label="v1.0-gov",
    )
    db_session.add(mver)
    await db_session.commit()
    return mver


@pytest.mark.asyncio
async def test_audit_middleware_logging(db_session, gov_patient):
    """Test that the FastAPI audit middleware captures patient data accesses for HIPAA compliance."""
    app = FastAPI()
    app.add_middleware(GovernanceAuditMiddleware)

    # Override AsyncSessionLocal in middleware to use test db_session transaction
    @asynccontextmanager
    async def mock_session_local():
        yield db_session

    original_session_local = vlep.api.middleware.audit.AsyncSessionLocal
    vlep.api.middleware.audit.AsyncSessionLocal = mock_session_local

    try:
        # Route that mimics viewing patient detail
        @app.get("/api/patients/{patient_id}")
        async def get_patient(patient_id: uuid.UUID):
            return {"patient_id": str(patient_id), "status": "loaded"}

        # Run request using AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {
                "X-Actor-ID": "dr_smith",
                "X-Actor-Role": "clinical_director",
                "X-Access-Reason": "audit_test",
                "user-agent": "httpx-test",
            }
            url = f"/api/patients/{gov_patient.patient_id}"
            response = await client.get(url, headers=headers)
            assert response.status_code == 200

        # Query access_logs to verify mapping
        stmt = select(AccessLog).where(AccessLog.actor_id == "dr_smith")
        res = await db_session.execute(stmt)
        logs = res.scalars().all()

        assert len(logs) == 1
        log = logs[0]
        assert log.actor_role == "clinical_director"
        assert log.action == f"GET {url}"
        assert log.patient_id == gov_patient.patient_id
        assert log.access_reason == "audit_test"
        assert log.resource_schema == "core"
        assert log.resource_table == "patients"
    finally:
        # Restore original AsyncSessionLocal
        vlep.api.middleware.audit.AsyncSessionLocal = original_session_local


@pytest.mark.asyncio
async def test_review_task_lifecycle(db_session, gov_patient):
    """Test creating review tasks, decisions, and source text verifications."""
    # 1. Create a clinical review task
    task = await ReviewService.create_review_task(
        session=db_session,
        task_type="csep_profile_adjudication",
        priority=50,
        assigned_to="dr_jones",
        assigned_role="epileptologist",
    )
    await db_session.commit()

    assert task.review_task_id is not None
    assert task.status == "open"

    # 2. Record review decision
    # Valid enum values: accept, reject, needs_revision, escalate, no_action
    dec = await ReviewService.create_review_decision(
        session=db_session,
        review_task_id=task.review_task_id,
        decision="accept",
        reviewer_id="dr_jones",
        decision_reason="Trajectory matches clinical observation",
        confidence=0.9500,
    )
    await db_session.commit()

    assert dec.review_decision_id is not None
    assert dec.decision == "accept"
    assert float(dec.confidence) == 0.9500

    # Assert task is closed
    stmt = select(ReviewTask).where(ReviewTask.review_task_id == task.review_task_id)
    res_task = (await db_session.execute(stmt)).scalar_one()
    assert res_task.status == "closed"


@pytest.mark.asyncio
async def test_clinical_discrepancy_reporting_and_adjudication(db_session, gov_patient):
    """Test reporting clinical issues and resolving them via adjudication."""
    # 1. Submit an issue report
    report = await ReviewService.report_issue(
        session=db_session,
        issue_type="model_prediction_mismatch",
        description="Predicted SUDEP risk is unexpectedly high given recent seizure freedom.",
        reporter_id="nurse_kelly",
        reporter_role="clinic_nurse",
        severity="high",
    )
    await db_session.commit()

    assert report.issue_report_id is not None
    assert report.status == "open"

    # 2. Adjudicate issue
    adj = await ReviewService.adjudicate_issue(
        session=db_session,
        issue_report_id=report.issue_report_id,
        adjudicator_id="dr_smith",
        adjudication_result="re_evaluate_model",
        rationale="Hazard was elevated due to an outdated EEG biomarker event.",
    )
    await db_session.commit()

    assert adj.adjudication_id is not None
    assert adj.adjudication_result == "re_evaluate_model"

    # Assert report status is resolved
    stmt = select(IssueReport).where(IssueReport.issue_report_id == report.issue_report_id)
    res_rep = (await db_session.execute(stmt)).scalar_one()
    assert res_rep.status == "resolved"
    assert res_rep.resolution == "re_evaluate_model"
    assert res_rep.resolved_at is not None


@pytest.mark.asyncio
async def test_data_quality_runs(db_session, gov_patient):
    """Test running automated data quality checks and validating findings."""
    from sqlalchemy.orm import attributes as orm_attributes
    now = datetime.now(UTC)

    # DB CHECK constraint: birth_year BETWEEN 1900 AND EXTRACT(YEAR FROM now())::INT
    # Strategy: insert with valid year 1920, flush to DB, then use
    # `set_committed_value` to tell SQLAlchemy the "committed" value is 2035
    # without marking the object as dirty (so no UPDATE is sent to the DB).
    # The DQ service queries the session which sees 2035 in the identity map.
    outlier_pt = Patient(
        source_patient_hash="outlier-hash-new",
        birth_year=1920,          # valid — passes DB check constraint
        sex_at_birth="Female",
    )
    db_session.add(outlier_pt)
    await db_session.flush()      # INSERT with valid birth_year=1920

    # Overwrite the committed snapshot so SQLAlchemy thinks 2035 was always the value.
    # This makes the attribute appear "clean" (not dirty) so no UPDATE is issued.
    orm_attributes.set_committed_value(outlier_pt, "birth_year", 2035)

    # Add a ledger event observed in the future
    future_ev = LedgerEvent(
        patient_id=gov_patient.patient_id,
        observed_at=now + timedelta(days=5),
        domain="clinical_observation",
        data_element={"display": "Future Seizure"},
        source_attribution="clinician",
        certainty_level=0.90,
        validation_status="normalized",
    )
    db_session.add(future_ev)
    await db_session.flush()

    # Run data quality checks — the SELECT loads from session identity map,
    # which now shows outlier_pt.birth_year == 2035.
    dq_run = await GovernanceService.run_data_quality_checks(
        session=db_session,
        run_name="Weekly DQ Audit",
    )
    await db_session.commit()

    assert dq_run.status == "completed"
    assert dq_run.metrics["patients_checked"] >= 2
    assert dq_run.metrics["outlier_birth_years_count"] >= 1
    assert dq_run.metrics["future_timestamp_count"] >= 1
    assert len(dq_run.findings) >= 2


@pytest.mark.asyncio
async def test_model_drift_checks(db_session, gov_patient, gov_model_version):
    """Test computing model drift (KS test, PSI) and fairness metrics."""
    now = datetime.now(UTC)

    # 1. Seed reference predictions (older than 90 days) — 6 samples
    run = LpaRun(run_kind="drift_evaluation")
    db_session.add(run)
    await db_session.commit()

    for days_ago in [180, 160, 140, 130, 120, 110]:
        pred_ref = Prediction(
            lpa_run_id=run.lpa_run_id,
            patient_id=gov_patient.patient_id,
            prediction_type="sudep_risk",
            as_of_time=now - timedelta(days=days_ago),
            value_numeric=0.10,
        )
        db_session.add(pred_ref)

    # 2. Seed target predictions (within last 90 days, higher risk → simulates drift) — 6 samples
    # Total = 12, which exceeds the min-sample threshold of 10.
    for days_ago in [60, 45, 30, 15, 7, 2]:
        pred_tgt = Prediction(
            lpa_run_id=run.lpa_run_id,
            patient_id=gov_patient.patient_id,
            prediction_type="sudep_risk",
            as_of_time=now - timedelta(days=days_ago),
            value_numeric=0.45,  # higher risk -> drift
        )
        db_session.add(pred_tgt)
    await db_session.commit()

    # 3. Monitor drift
    drift_run = await GovernanceService.monitor_model_drift(
        session=db_session,
        model_version_id=gov_model_version.model_version_id,
    )
    await db_session.commit()

    assert drift_run.status == "completed"
    assert "kolmogorov_smirnov_p_value" in drift_run.drift_metrics
    assert "population_stability_index" in drift_run.drift_metrics
    assert "demographic_parity_difference" in drift_run.fairness_metrics
    assert drift_run.recommendation is not None
