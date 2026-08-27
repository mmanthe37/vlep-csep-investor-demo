"""
VLEP Pipeline — Governance, Review & Safety Router.

Endpoints for HIPAA access audit logs, clinical review tasks, issue reports,
adjudications, automated data quality runs, and model drift monitoring.

Routes
------
GET    /governance/access-logs                          List audit access logs
GET    /governance/access-logs/{patient_id}             Logs for specific patient

POST   /governance/alerts                              Create a clinical alert
GET    /governance/alerts                              List alert events

POST   /governance/reviews/tasks                       Create a review task
GET    /governance/reviews/tasks                       List review tasks
PATCH  /governance/reviews/tasks/{task_id}/decide      Record a decision

POST   /governance/reviews/issues                      Report an issue
PATCH  /governance/reviews/issues/{issue_id}/adjudicate Adjudicate an issue

POST   /governance/quality/run                         Trigger data quality audit
GET    /governance/quality/runs                        List DQ run history

POST   /governance/drift/run                           Trigger model drift check
GET    /governance/drift/runs                          List drift run history
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.api.deps import AuthPrincipal, get_db, require_role
from vlep.models.governance import AccessLog, AlertEvent, DataQualityRun, ModelDriftRun
from vlep.models.review import ReviewTask
from vlep.services.governance import GovernanceService
from vlep.services.review import ReviewService

router = APIRouter(prefix="/governance", tags=["Governance & Safety"])


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class AccessLogOut(BaseModel):
    log_id: uuid.UUID = Field(validation_alias="access_log_id")
    actor_id: str
    actor_role: str | None = None
    action: str
    resource_schema: str | None = None
    resource_table: str | None = None
    patient_id: uuid.UUID | None = None
    access_reason: str | None = None
    logged_at: datetime = Field(validation_alias="created_at")

    model_config = {"from_attributes": True}


class AlertCreate(BaseModel):
    alert_type: str
    severity: str = Field(..., description="passive | low | moderate | high | critical")
    patient_id: uuid.UUID | None = None
    csep_id: uuid.UUID | None = None
    interruptive: bool = False
    rationale: str | None = None
    metadata: dict[str, Any] | None = None


class AlertOut(BaseModel):
    alert_event_id: uuid.UUID
    alert_type: str
    severity: str
    patient_id: uuid.UUID | None
    interruptive: bool
    acknowledged: bool
    displayed_at: datetime | None

    model_config = {"from_attributes": True}


class ReviewTaskCreate(BaseModel):
    task_type: str
    priority: int = Field(100, ge=1, le=1000)
    assigned_to: str | None = None
    assigned_role: str | None = None
    claim_id: uuid.UUID | None = None
    assertion_id: uuid.UUID | None = None
    csep_id: uuid.UUID | None = None
    due_days: int = Field(7, ge=0)


class ReviewTaskOut(BaseModel):
    review_task_id: uuid.UUID
    task_type: str
    status: str
    priority: int
    assigned_to: str | None
    assigned_role: str | None
    created_at: datetime
    due_at: datetime | None

    model_config = {"from_attributes": True}


class DecisionCreate(BaseModel):
    decision: str = Field(..., description="accept | reject | needs_revision | escalate | no_action")
    reviewer_id: str
    decision_reason: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class IssueReportCreate(BaseModel):
    issue_type: str
    description: str
    reporter_id: str | None = None
    reporter_role: str | None = None
    severity: str = Field("moderate", description="low | moderate | high | critical")
    claim_id: uuid.UUID | None = None
    assertion_id: uuid.UUID | None = None
    csep_id: uuid.UUID | None = None


class IssueReportOut(BaseModel):
    issue_report_id: uuid.UUID
    issue_type: str
    description: str
    severity: str
    status: str
    reporter_id: str | None
    created_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class AdjudicationCreate(BaseModel):
    adjudicator_id: str
    adjudication_result: str
    rationale: str | None = None


class DQRunRequest(BaseModel):
    run_name: str = "Ad-hoc Data Quality Audit"


class DQRunOut(BaseModel):
    data_quality_run_id: uuid.UUID
    run_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any] | None
    findings: list[dict[str, Any]] | None

    model_config = {"from_attributes": True}


class DriftRunRequest(BaseModel):
    model_version_id: uuid.UUID
    cohort_id: uuid.UUID | None = None


class DriftRunOut(BaseModel):
    model_drift_run_id: uuid.UUID
    model_version_id: uuid.UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    drift_metrics: dict[str, Any] | None
    fairness_metrics: dict[str, Any] | None
    recommendation: str | None

    model_config = {"from_attributes": True}


# ── Access Log Endpoints ─────────────────────────────────────────────────────

@router.get(
    "/access-logs",
    response_model=list[AccessLogOut],
    summary="List governance access audit logs",
)
async def list_access_logs(
    actor_id: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> list[AccessLogOut]:
    stmt = select(AccessLog).order_by(AccessLog.created_at.desc()).offset(offset).limit(limit)
    if actor_id:
        stmt = stmt.where(AccessLog.actor_id == actor_id)
    result = await db.execute(stmt)
    return [AccessLogOut.model_validate(l) for l in result.scalars().all()]


@router.get(
    "/access-logs/patient/{patient_id}",
    response_model=list[AccessLogOut],
    summary="List access logs for a specific patient",
)
async def patient_access_logs(
    patient_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> list[AccessLogOut]:
    result = await db.execute(
        select(AccessLog)
        .where(AccessLog.patient_id == patient_id)
        .order_by(AccessLog.created_at.desc())
        .limit(limit)
    )
    return [AccessLogOut.model_validate(l) for l in result.scalars().all()]


# ── Alert Endpoints ──────────────────────────────────────────────────────────

@router.post(
    "/alerts",
    response_model=AlertOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a clinical safety alert",
)
async def create_alert(
    body: AlertCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> AlertOut:
    alert = await GovernanceService.create_alert_event(
        session=db,
        alert_type=body.alert_type,
        severity=body.severity,
        patient_id=body.patient_id,
        csep_id=body.csep_id,
        interruptive=body.interruptive,
        rationale=body.rationale,
        metadata=body.metadata,
    )
    await db.flush()
    return AlertOut.model_validate(alert)


@router.get(
    "/alerts",
    response_model=list[AlertOut],
    summary="List clinical alert events",
)
async def list_alerts(
    patient_id: uuid.UUID | None = Query(None),
    severity: str | None = Query(None),
    acknowledged: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[AlertOut]:
    stmt = select(AlertEvent).order_by(AlertEvent.displayed_at.desc()).limit(limit)
    if patient_id:
        stmt = stmt.where(AlertEvent.patient_id == patient_id)
    if severity:
        stmt = stmt.where(AlertEvent.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(AlertEvent.acknowledged == acknowledged)
    result = await db.execute(stmt)
    return [AlertOut.model_validate(a) for a in result.scalars().all()]


# ── Review Task Endpoints ────────────────────────────────────────────────────

@router.post(
    "/reviews/tasks",
    response_model=ReviewTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a clinical review task",
)
async def create_review_task(
    body: ReviewTaskCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> ReviewTaskOut:
    task = await ReviewService.create_review_task(
        session=db,
        task_type=body.task_type,
        priority=body.priority,
        assigned_to=body.assigned_to,
        assigned_role=body.assigned_role,
        claim_id=body.claim_id,
        assertion_id=body.assertion_id,
        csep_id=body.csep_id,
        due_days=body.due_days,
    )
    await db.flush()
    return ReviewTaskOut.model_validate(task)


@router.get(
    "/reviews/tasks",
    response_model=list[ReviewTaskOut],
    summary="List review tasks",
)
async def list_review_tasks(
    status_filter: str | None = Query(None, alias="status"),
    assigned_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinician")),
) -> list[ReviewTaskOut]:
    stmt = select(ReviewTask).order_by(ReviewTask.priority.asc()).limit(limit)
    if status_filter:
        stmt = stmt.where(ReviewTask.status == status_filter)
    if assigned_to:
        stmt = stmt.where(ReviewTask.assigned_to == assigned_to)
    result = await db.execute(stmt)
    return [ReviewTaskOut.model_validate(t) for t in result.scalars().all()]


@router.patch(
    "/reviews/tasks/{task_id}/decide",
    response_model=dict[str, Any],
    summary="Record a decision on a review task",
)
async def record_decision(
    task_id: uuid.UUID,
    body: DecisionCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> dict[str, Any]:
    dec = await ReviewService.create_review_decision(
        session=db,
        review_task_id=task_id,
        decision=body.decision,
        reviewer_id=body.reviewer_id,
        decision_reason=body.decision_reason,
        confidence=body.confidence,
    )
    await db.flush()
    return {
        "review_decision_id": str(dec.review_decision_id),
        "task_id": str(task_id),
        "decision": dec.decision,
        "reviewer_id": dec.reviewer_id,
    }


# ── Issue Report Endpoints ───────────────────────────────────────────────────

@router.post(
    "/reviews/issues",
    response_model=IssueReportOut,
    status_code=status.HTTP_201_CREATED,
    summary="Report a clinical discrepancy or issue",
)
async def report_issue(
    body: IssueReportCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinic_nurse")),
) -> IssueReportOut:
    report = await ReviewService.report_issue(
        session=db,
        issue_type=body.issue_type,
        description=body.description,
        reporter_id=body.reporter_id,
        reporter_role=body.reporter_role,
        severity=body.severity,
        claim_id=body.claim_id,
        assertion_id=body.assertion_id,
        csep_id=body.csep_id,
    )
    await db.flush()
    return IssueReportOut.model_validate(report)


@router.patch(
    "/reviews/issues/{issue_id}/adjudicate",
    response_model=dict[str, Any],
    summary="Adjudicate a reported issue",
)
async def adjudicate_issue(
    issue_id: uuid.UUID,
    body: AdjudicationCreate,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("epileptologist")),
) -> dict[str, Any]:
    adj = await ReviewService.adjudicate_issue(
        session=db,
        issue_report_id=issue_id,
        adjudicator_id=body.adjudicator_id,
        adjudication_result=body.adjudication_result,
        rationale=body.rationale,
    )
    await db.flush()
    return {
        "adjudication_id": str(adj.adjudication_id),
        "issue_report_id": str(issue_id),
        "result": adj.adjudication_result,
    }


# ── Data Quality Endpoints ───────────────────────────────────────────────────

@router.post(
    "/quality/run",
    response_model=DQRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger an automated data quality audit",
)
async def run_data_quality(
    body: DQRunRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> DQRunOut:
    """Execute automated checks: birth year outliers, future timestamps, sparse windows."""
    dq_run = await GovernanceService.run_data_quality_checks(
        session=db, run_name=body.run_name
    )
    await db.flush()
    return DQRunOut.model_validate(dq_run)


@router.get(
    "/quality/runs",
    response_model=list[DQRunOut],
    summary="List data quality audit runs",
)
async def list_dq_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> list[DQRunOut]:
    result = await db.execute(
        select(DataQualityRun).order_by(DataQualityRun.started_at.desc()).limit(limit)
    )
    return [DQRunOut.model_validate(r) for r in result.scalars().all()]


# ── Model Drift Endpoints ────────────────────────────────────────────────────

@router.post(
    "/drift/run",
    response_model=DriftRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger model drift & fairness monitoring",
)
async def run_drift_check(
    body: DriftRunRequest,
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> DriftRunOut:
    """Run KS-test, PSI, and demographic parity difference on model predictions."""
    drift_run = await GovernanceService.monitor_model_drift(
        session=db,
        model_version_id=body.model_version_id,
        cohort_id=body.cohort_id,
    )
    await db.flush()
    return DriftRunOut.model_validate(drift_run)


@router.get(
    "/drift/runs",
    response_model=list[DriftRunOut],
    summary="List model drift monitoring runs",
)
async def list_drift_runs(
    model_version_id: uuid.UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: AuthPrincipal = Depends(require_role("clinical_director")),
) -> list[DriftRunOut]:
    stmt = select(ModelDriftRun).order_by(ModelDriftRun.started_at.desc()).limit(limit)
    if model_version_id:
        stmt = stmt.where(ModelDriftRun.model_version_id == model_version_id)
    result = await db.execute(stmt)
    return [DriftRunOut.model_validate(r) for r in result.scalars().all()]
