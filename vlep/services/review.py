"""
VLEP Pipeline — Review & Adjudication Service.

Handles Stage 7: Clinical review tasks, decisions, issue reports,
adjudications, and validation observations.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.review import (
    Adjudication,
    IssueReport,
    ReviewDecision,
    ReviewTask,
    SourceTextVerification,
    ValidationCohort,
    ValidationObservation,
)

logger = logging.getLogger(__name__)


class ReviewService:
    """Service handling Stage 7 human-in-the-loop review, clinical issue reporting, and adjudications."""

    @staticmethod
    async def create_review_task(
        session: AsyncSession,
        task_type: str,
        priority: int = 100,
        claim_id: uuid.UUID | None = None,
        assertion_id: uuid.UUID | None = None,
        csep_id: uuid.UUID | None = None,
        event_id: uuid.UUID | None = None,
        assigned_to: str | None = None,
        assigned_role: str | None = None,
        due_days: int = 7,
    ) -> ReviewTask:
        """Create a clinical review task (for claims, assertions, or CSEPs)."""
        due_at = datetime.now(UTC) + timedelta(days=due_days) if due_days > 0 else None
        task = ReviewTask(
            task_type=task_type,
            priority=priority,
            claim_id=claim_id,
            assertion_id=assertion_id,
            csep_id=csep_id,
            event_id=event_id,
            assigned_to=assigned_to,
            assigned_role=assigned_role,
            status="open",
            due_at=due_at,
        )
        session.add(task)
        await session.flush()
        logger.info("Created ReviewTask %s of type %s", task.review_task_id, task_type)
        return task

    @staticmethod
    async def create_review_decision(
        session: AsyncSession,
        review_task_id: uuid.UUID,
        decision: str,
        reviewer_id: str,
        decision_reason: str | None = None,
        confidence: float | None = None,
    ) -> ReviewDecision:
        """Record a decision on a review task and close the task."""
        # Check task
        stmt = select(ReviewTask).where(ReviewTask.review_task_id == review_task_id)
        res = await session.execute(stmt)
        task = res.scalar_one()
        task.status = "closed"

        dec = ReviewDecision(
            review_task_id=review_task_id,
            decision=decision,
            reviewer_id=reviewer_id,
            decision_reason=decision_reason,
            confidence=confidence,
        )
        session.add(dec)
        await session.flush()
        logger.info("Recorded ReviewDecision for task %s: %s", review_task_id, decision)
        return dec

    @staticmethod
    async def verify_source_text(
        session: AsyncSession,
        claim_id: uuid.UUID,
        verifier_id: str,
        offset_verified: bool,
        triple_verified: bool,
        negation_temporal_context_verified: bool = False,
        notes: str | None = None,
    ) -> SourceTextVerification:
        """Verify the offset details and subject/predicate/object triplet for an extracted literature claim."""
        ver = SourceTextVerification(
            claim_id=claim_id,
            verifier_id=verifier_id,
            offset_verified=offset_verified,
            triple_verified=triple_verified,
            negation_temporal_context_verified=negation_temporal_context_verified,
            notes=notes,
        )
        session.add(ver)
        await session.flush()
        logger.info("Verified literature claim %s by %s", claim_id, verifier_id)
        return ver

    @staticmethod
    async def report_issue(
        session: AsyncSession,
        issue_type: str,
        description: str,
        reporter_id: str | None = None,
        reporter_role: str | None = None,
        severity: str = "moderate",
        claim_id: uuid.UUID | None = None,
        assertion_id: uuid.UUID | None = None,
        csep_id: uuid.UUID | None = None,
        event_id: uuid.UUID | None = None,
    ) -> IssueReport:
        """Submit a discrepancy report or issue regarding a clinical phenotyping element."""
        report = IssueReport(
            issue_type=issue_type,
            description=description,
            reporter_id=reporter_id,
            reporter_role=reporter_role,
            severity=severity,
            claim_id=claim_id,
            assertion_id=assertion_id,
            csep_id=csep_id,
            event_id=event_id,
            status="open",
        )
        session.add(report)
        await session.flush()
        logger.info("Reported Clinical Issue %s (Type: %s)", report.issue_report_id, issue_type)
        return report

    @staticmethod
    async def adjudicate_issue(
        session: AsyncSession,
        issue_report_id: uuid.UUID,
        adjudicator_id: str,
        adjudication_result: str,
        rationale: str | None = None,
    ) -> Adjudication:
        """Record final clinical adjudication resolving a reported issue."""
        stmt = select(IssueReport).where(IssueReport.issue_report_id == issue_report_id)
        res = await session.execute(stmt)
        report = res.scalar_one()

        report.status = "resolved"
        report.resolved_at = datetime.now(UTC)
        report.resolution = adjudication_result

        adj = Adjudication(
            issue_report_id=issue_report_id,
            adjudicator_id=adjudicator_id,
            adjudication_result=adjudication_result,
            rationale=rationale,
        )
        session.add(adj)
        await session.flush()
        logger.info("Adjudicated Clinical Issue %s with result: %s", issue_report_id, adjudication_result)
        return adj

    @staticmethod
    async def create_validation_cohort(
        session: AsyncSession,
        name: str,
        validation_phase: str,
        cohort_id: uuid.UUID | None = None,
        n_target: int | None = None,
        n_actual: int | None = None,
        protocol_uri: str | None = None,
    ) -> ValidationCohort:
        """Register a validation cohort representing clinical ground truth."""
        vc = ValidationCohort(
            name=name,
            validation_phase=validation_phase,
            cohort_id=cohort_id,
            n_target=n_target,
            n_actual=n_actual,
            protocol_uri=protocol_uri,
        )
        session.add(vc)
        await session.flush()
        logger.info("Created ValidationCohort %s (%s)", name, validation_phase)
        return vc

    @staticmethod
    async def record_validation_observation(
        session: AsyncSession,
        validation_cohort_id: uuid.UUID,
        patient_id: uuid.UUID,
        outcome_name: str,
        outcome_value: dict[str, Any],
        outcome_time: datetime | None = None,
        adjudicated_by: str | None = None,
    ) -> ValidationObservation:
        """Record human-adjudicated clinical endpoint outcomes for model validation."""
        obs = ValidationObservation(
            validation_cohort_id=validation_cohort_id,
            patient_id=patient_id,
            outcome_name=outcome_name,
            outcome_value=outcome_value,
            outcome_time=outcome_time or datetime.now(UTC),
            adjudicated_by=adjudicated_by,
        )
        session.add(obs)
        await session.flush()
        logger.info("Recorded validation observation for patient %s (Outcome: %s)", patient_id, outcome_name)
        return obs
