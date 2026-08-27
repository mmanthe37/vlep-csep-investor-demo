"""
VLEP Pipeline — Nosology Service.

Handles Stage 6b: Nosological Reversioning & Re-interpretation.
Manages nosological frameworks, taxonomy terms, taxonomical edge relationships,
conflict resolution rules, re-interpretation jobs, and multi-version comparison report generation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.core import Patient
from vlep.models.csep import CSEPProfile
from vlep.models.nosology import (
    FrameworkVersion,
    ReinterpretationJob,
    ReinterpretationResult,
    ResolutionRule,
    TaxonomyEdge,
    TaxonomyTerm,
)
from vlep.services.csep_resolver import CsepResolverService

logger = logging.getLogger(__name__)


class NosologyService:
    """Service handling Stage 6b: Nosological Reversioning and Re-interpretation."""

    @staticmethod
    async def create_framework_version(
        session: AsyncSession,
        framework_name: str,
        version_label: str,
        effective_from: date,
        authority: str | None = None,
        is_default: bool = False,
    ) -> FrameworkVersion:
        """Create a new nosological framework release."""
        # Check if already exists
        stmt = select(FrameworkVersion).where(
            and_(
                FrameworkVersion.framework_name == framework_name,
                FrameworkVersion.version_label == version_label
            )
        )
        res = await session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            logger.info("FrameworkVersion '%s' (%s) already exists.", framework_name, version_label)
            return existing

        fw = FrameworkVersion(
            framework_name=framework_name,
            version_label=version_label,
            effective_from=effective_from,
            authority=authority,
            is_default=is_default,
            status="active",
        )
        session.add(fw)
        await session.flush()
        logger.info("Created FrameworkVersion %s (ID: %s)", framework_name, fw.nosology_version_id)
        return fw

    @staticmethod
    async def create_taxonomy_term(
        session: AsyncSession,
        nosology_version_id: uuid.UUID,
        dimension: str,
        code: str,
        display: str,
        parent_code: str | None = None,
        concept_id: uuid.UUID | None = None,
        definition: str | None = None,
        age_constraints: dict[str, Any] | None = None,
        rule_expression: dict[str, Any] | None = None,
    ) -> TaxonomyTerm:
        """Add a taxonomy term within a framework version."""
        term = TaxonomyTerm(
            nosology_version_id=nosology_version_id,
            dimension=dimension,
            code=code,
            display=display,
            parent_code=parent_code,
            concept_id=concept_id,
            definition=definition,
            age_constraints=age_constraints or {},
            rule_expression=rule_expression or {},
            active=True,
        )
        session.add(term)
        await session.flush()
        return term

    @staticmethod
    async def create_taxonomy_edge(
        session: AsyncSession,
        nosology_version_id: uuid.UUID,
        parent_term_id: uuid.UUID,
        child_term_id: uuid.UUID,
        relation: str = "is_a",
    ) -> TaxonomyEdge:
        """Establish a hierarchical link between taxonomy terms."""
        edge = TaxonomyEdge(
            nosology_version_id=nosology_version_id,
            parent_term_id=parent_term_id,
            child_term_id=child_term_id,
            relation=relation,
        )
        session.add(edge)
        await session.flush()
        return edge

    @staticmethod
    async def create_resolution_rule(
        session: AsyncSession,
        nosology_version_id: uuid.UUID,
        rule_name: str,
        rule_expression: dict[str, Any],
        action: dict[str, Any],
        applies_to_dimension: str | None = None,
        priority: int = 100,
    ) -> ResolutionRule:
        """Register a conflict resolution rule."""
        rule = ResolutionRule(
            nosology_version_id=nosology_version_id,
            rule_name=rule_name,
            applies_to_dimension=applies_to_dimension,
            priority=priority,
            rule_expression=rule_expression,
            action=action,
            active=True,
        )
        session.add(rule)
        await session.flush()
        logger.info("Registered ResolutionRule '%s' for framework %s", rule_name, nosology_version_id)
        return rule

    @staticmethod
    async def create_reinterpretation_job(
        session: AsyncSession,
        source_nosology_version_id: uuid.UUID,
        target_nosology_version_id: uuid.UUID,
        cohort_id: uuid.UUID | None = None,
        requested_by: str | None = "system",
    ) -> ReinterpretationJob:
        """Create a queued framework reversioning job."""
        job = ReinterpretationJob(
            source_nosology_version_id=source_nosology_version_id,
            target_nosology_version_id=target_nosology_version_id,
            cohort_id=cohort_id,
            requested_by=requested_by,
            status="queued",
        )
        session.add(job)
        await session.flush()
        logger.info("Created ReinterpretationJob (ID: %s)", job.reinterpretation_job_id)
        return job

    @staticmethod
    async def execute_reinterpretation_job(
        session: AsyncSession,
        reinterpretation_job_id: uuid.UUID,
        patient_ids: list[uuid.UUID] | None = None,
    ) -> ReinterpretationJob:
        """
        Execute framework conversion: runs CSEP assembly under the target framework
        for all cohort patients, compares profiles, and records diffs.
        """
        # 1. Fetch job
        stmt_job = select(ReinterpretationJob).where(ReinterpretationJob.reinterpretation_job_id == reinterpretation_job_id)
        res_job = await session.execute(stmt_job)
        job = res_job.scalar_one()

        job.status = "running"
        job.started_at = datetime.now(UTC)
        await session.flush()

        # 2. Identify patients to process
        # If cohort is provided, get patients in cohort. Otherwise, get all patients with a CSEP in source nosology.
        if patient_ids:
            target_patient_ids = patient_ids
        elif job.cohort_id:
            # Query cohort patients
            stmt_pts = select(Patient.patient_id).join(
                Patient.cohort_memberships
            ).where(
                text(f"cohort_id = '{job.cohort_id}'")
            )
            res_pts = await session.execute(stmt_pts)
            target_patient_ids = res_pts.scalars().all()
        else:
            # All patients with a profile under the source nosology
            stmt_pts = select(CSEPProfile.patient_id).where(
                CSEPProfile.nosology_version_id == job.source_nosology_version_id
            ).distinct()
            res_pts = await session.execute(stmt_pts)
            target_patient_ids = res_pts.scalars().all()

        processed_count = 0
        for pat_id in target_patient_ids:
            # A. Fetch latest profile under source nosology
            stmt_prev = select(CSEPProfile).where(
                and_(
                    CSEPProfile.patient_id == pat_id,
                    CSEPProfile.nosology_version_id == job.source_nosology_version_id
                )
            ).order_by(CSEPProfile.as_of_time.desc()).limit(1)
            res_prev = await session.execute(stmt_prev)
            prev_profile = res_prev.scalar_one_or_none()

            if not prev_profile:
                continue

            # B. Assemble new profile under target nosology at the same as_of_time
            new_profile = await CsepResolverService.assemble_csep_profile(
                session=session,
                patient_id=pat_id,
                nosology_version_id=job.target_nosology_version_id,
                as_of_time=prev_profile.as_of_time,
                model_version_id=prev_profile.model_version_id,
                lpa_run_id=prev_profile.lpa_run_id,
            )

            # C. Generate detailed profile differences
            diffs = NosologyService.compare_profiles(prev_profile, new_profile)

            # D. Record Result
            res = ReinterpretationResult(
                reinterpretation_job_id=job.reinterpretation_job_id,
                patient_id=pat_id,
                source_csep_id=prev_profile.csep_id,
                target_csep_id=new_profile.csep_id,
                changes_json=diffs,
            )
            session.add(res)
            processed_count += 1

        # 3. Update job completion
        job.status = "completed"
        job.finished_at = datetime.now(UTC)
        job.metadata_ = {"patients_reinterpreted": processed_count}
        await session.flush()

        logger.info(
            "ReinterpretationJob %s completed successfully. Reinterpreted %d patients.",
            reinterpretation_job_id, processed_count
        )
        return job

    @staticmethod
    def compare_profiles(prev: CSEPProfile, curr: CSEPProfile) -> dict[str, Any]:
        """Compare two profiles for the same patient and generate a diff report."""
        diffs = {
            "syndrome_changed": False,
            "seizure_distribution_changed": False,
            "top_etiology_changed": False,
            "previous_syndrome": prev.epilepsy_syndrome.get("syndrome"),
            "new_syndrome": curr.epilepsy_syndrome.get("syndrome"),
        }

        # Syndrome comparison
        if diffs["previous_syndrome"] != diffs["new_syndrome"]:
            diffs["syndrome_changed"] = True

        # Seizure type distribution comparison
        prev_dist = prev.seizure_type_distribution or {}
        curr_dist = curr.seizure_type_distribution or {}
        if set(prev_dist.keys()) != set(curr_dist.keys()):
            diffs["seizure_distribution_changed"] = True
        else:
            for k in prev_dist:
                if abs(float(prev_dist[k]) - float(curr_dist[k])) > 1e-4:
                    diffs["seizure_distribution_changed"] = True
                    break

        # Top etiology comparison
        prev_top = prev.etiology_ranked_confidence[0]["etiology"] if prev.etiology_ranked_confidence else None
        curr_top = curr.etiology_ranked_confidence[0]["etiology"] if curr.etiology_ranked_confidence else None
        diffs["previous_top_etiology"] = prev_top
        diffs["new_top_etiology"] = curr_top
        if prev_top != curr_top:
            diffs["top_etiology_changed"] = True

        return diffs
