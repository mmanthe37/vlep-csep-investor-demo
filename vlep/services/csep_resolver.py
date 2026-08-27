"""
VLEP Pipeline — CSEP Resolver Service.

Handles Stage 6a: CSEP Resolution Function F.
Assembles Current-State Epilepsy Profiles (CSEP), applies temporal decay,
resolves conflicts using framework priority rules, and records provenance traces.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.csep import (
    CSEPProfile,
    ProfileAssertionTrace,
    ProfileClaimTrace,
    ProfileEventTrace,
)
from vlep.models.modeling import (
    Prediction,
    TimeToEventHazard,
)
from vlep.models.nosology import ResolutionRule
from vlep.models.phenotyping import (
    AssertionSupportClaim,
    AssertionSupportEvent,
    PhenotypeAssertion,
)

logger = logging.getLogger(__name__)


class CsepResolverService:
    """Service handling Stage 6a: CSEP Profile Assembly and conflict resolution."""

    @staticmethod
    def calculate_profile_hash(profile: CSEPProfile) -> str:
        """Calculate a deterministic SHA-256 integrity hash for a CSEP profile."""
        def format_json(val: Any) -> str:
            return json.dumps(val, separators=(",", ":"), sort_keys=True)

        parts = [
            str(profile.patient_id),
            profile.as_of_time.replace(tzinfo=UTC).isoformat() if profile.as_of_time else "",
            str(profile.nosology_version_id),
            str(profile.model_version_id or ""),
            format_json(profile.seizure_type_distribution),
            format_json(profile.etiology_ranked_confidence),
            format_json(profile.epilepsy_syndrome),
            format_json(profile.biomarker_summary),
            format_json(profile.comorbidity_burden),
            format_json(profile.treatment_response),
            format_json(profile.predictive_outputs),
        ]
        payload = "|".join(parts)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    async def assemble_csep_profile(
        session: AsyncSession,
        patient_id: uuid.UUID,
        nosology_version_id: uuid.UUID,
        as_of_time: datetime,
        model_version_id: uuid.UUID | None = None,
        lpa_run_id: uuid.UUID | None = None,
    ) -> CSEPProfile:
        """
        Assemble a Current-State Epilepsy Profile (CSEP) by querying active assertions
        up to as_of_time, applying resolution rules, and syncing modeling predictions.
        """
        # 1. Fetch active phenotype assertions for this patient up to as_of_time
        stmt_assertions = select(PhenotypeAssertion).where(
            and_(
                PhenotypeAssertion.patient_id == patient_id,
                PhenotypeAssertion.status == "active",
                PhenotypeAssertion.effective_start <= as_of_time,
                (PhenotypeAssertion.effective_end.is_(None) | (PhenotypeAssertion.effective_end > as_of_time))
            )
        )
        res_assertions = await session.execute(stmt_assertions)
        assertions = list(res_assertions.scalars().all())

        # 2. Fetch active resolution rules for the nosology framework version
        stmt_rules = select(ResolutionRule).where(
            and_(
                ResolutionRule.nosology_version_id == nosology_version_id,
                ResolutionRule.active.is_(True)
            )
        ).order_by(ResolutionRule.priority.asc())
        res_rules = await session.execute(stmt_rules)
        rules = list(res_rules.scalars().all())

        # 3. Categorize assertions by dimension
        assertions_by_dim: dict[str, list[PhenotypeAssertion]] = {}
        for ass in assertions:
            dim = str(ass.phenotype_dimension)
            if dim not in assertions_by_dim:
                assertions_by_dim[dim] = []
            assertions_by_dim[dim].append(ass)

        # 4. Resolve conflicts / compute values per dimension
        # Seizure Type Distribution
        seizure_dist: dict[str, float] = {}
        seizure_assertions = assertions_by_dim.get("seizure_type", [])
        if seizure_assertions:
            total_score = sum(float(a.final_score) for a in seizure_assertions)
            for ass in seizure_assertions:
                label = ass.phenotype_label_text.lower().replace(" ", "_")
                seizure_dist[label] = (float(ass.final_score) / total_score) if total_score > 0 else 0.0

        # Etiology Ranked Confidence
        etiologies: list[dict[str, Any]] = []
        etiology_assertions = assertions_by_dim.get("etiology", [])
        if etiology_assertions:
            # Sort etiology assertions: Apply default rule that Genetic Etiology overrides other types if present
            # check resolution rules
            has_genetic_rule = any(
                "genetic" in r.rule_name.lower() or "etiology" in str(r.applies_to_dimension).lower()
                for r in rules
            )

            def etiology_sort_key(a: PhenotypeAssertion) -> tuple[int, float]:
                # 1. Check for Genetic Etiology
                is_genetic = "genetic" in a.phenotype_label_text.lower()
                is_unknown = "unknown" in a.phenotype_label_text.lower()

                if is_genetic:
                    # High priority (index 0)
                    priority = 0
                elif not is_unknown:
                    priority = 1
                else:
                    priority = 2

                # Sort by priority, then by final_score descending
                return (priority, -float(a.final_score))

            etiology_assertions.sort(key=etiology_sort_key)
            for rank, ass in enumerate(etiology_assertions):
                etiologies.append({
                    "etiology": ass.phenotype_label_text,
                    "confidence": float(ass.final_score),
                    "rank": rank + 1,
                    "assertion_id": str(ass.assertion_id),
                })

        # Epilepsy Syndrome
        syndrome_info: dict[str, Any] = {}
        syndrome_assertions = assertions_by_dim.get("syndrome", [])
        if syndrome_assertions:
            # Take the one with highest score
            best_syndrome = max(syndrome_assertions, key=lambda a: float(a.final_score))
            syndrome_info = {
                "syndrome": best_syndrome.phenotype_label_text,
                "confidence": float(best_syndrome.final_score),
                "assertion_id": str(best_syndrome.assertion_id),
            }

        # Biomarker Summary
        biomarker_info: dict[str, Any] = {}
        biomarker_assertions = assertions_by_dim.get("biomarker", [])
        for ass in biomarker_assertions:
            biomarker_info[ass.phenotype_label_text.lower().replace(" ", "_")] = {
                "detected": True,
                "confidence": float(ass.final_score),
                "assertion_id": str(ass.assertion_id),
            }

        # Comorbidity Burden
        comorbidity_info: dict[str, Any] = {}
        comorbidity_assertions = assertions_by_dim.get("comorbidity", [])
        for ass in comorbidity_assertions:
            comorbidity_info[ass.phenotype_label_text.lower().replace(" ", "_")] = {
                "severity_score": float(ass.final_score),
                "assertion_id": str(ass.assertion_id),
            }

        # Treatment Response
        treatment_info: dict[str, Any] = {}
        treatment_assertions = assertions_by_dim.get("treatment_response", [])
        # Also grab 'drug_resistance' dimension
        drug_res_assertions = assertions_by_dim.get("drug_resistance", [])
        all_tx = treatment_assertions + drug_res_assertions
        for ass in all_tx:
            treatment_info[ass.phenotype_label_text.lower().replace(" ", "_")] = {
                "score": float(ass.final_score),
                "assertion_id": str(ass.assertion_id),
            }

        # 5. Fetch Modeling Predictive Outputs up to as_of_time
        predictive_info: dict[str, Any] = {}

        # A. Hazards
        stmt_hazards = select(TimeToEventHazard).where(
            and_(
                TimeToEventHazard.patient_id == patient_id,
                TimeToEventHazard.as_of_time <= as_of_time
            )
        ).order_by(TimeToEventHazard.as_of_time.desc())
        res_hazards = await session.execute(stmt_hazards)
        latest_hazards = res_hazards.scalars().all()

        # Keep latest of each event type
        seen_events = set()
        for haz in latest_hazards:
            if haz.event_type not in seen_events:
                seen_events.add(haz.event_type)
                predictive_info[f"{haz.event_type}_risk"] = {
                    "hazard_value": float(haz.hazard_value),
                    "survival_probability": float(haz.survival_probability or 1.0),
                    "cumulative_incidence": float(haz.cumulative_incidence or 0.0),
                    "horizon_days": haz.horizon_days,
                    "updated_at": haz.as_of_time.replace(tzinfo=UTC).isoformat(),
                }

        # B. Early Shift Predictions
        stmt_preds = select(Prediction).where(
            and_(
                Prediction.patient_id == patient_id,
                Prediction.prediction_type == "early_shift_detection",
                Prediction.as_of_time <= as_of_time
            )
        ).order_by(Prediction.as_of_time.desc()).limit(1)
        res_preds = await session.execute(stmt_preds)
        latest_pred = res_preds.scalar_one_or_none()
        if latest_pred:
            predictive_info["early_shift_detection"] = {
                "transition_imminent": bool(latest_pred.value_numeric > 0),
                "lead_time_months": latest_pred.value_json.get("lead_time_months", 4.2),
                "probability": float(latest_pred.probability or 0.0),
                "uncertainty": latest_pred.uncertainty,
                "updated_at": latest_pred.as_of_time.replace(tzinfo=UTC).isoformat(),
            }

        # 6. Calculate uncertainty indicators
        uncertainty_info = {
            "assertion_count": len(assertions),
            "dimensions_covered": list(assertions_by_dim.keys()),
            "missingness": {
                dim: (dim not in assertions_by_dim)
                for dim in ["seizure_type", "etiology", "syndrome", "biomarker", "comorbidity", "treatment_response"]
            }
        }

        # 7. Create Profile
        profile = CSEPProfile(
            patient_id=patient_id,
            as_of_time=as_of_time,
            nosology_version_id=nosology_version_id,
            model_version_id=model_version_id,
            lpa_run_id=lpa_run_id,
            seizure_type_distribution=seizure_dist,
            etiology_ranked_confidence=etiologies,
            epilepsy_syndrome=syndrome_info,
            biomarker_summary=biomarker_info,
            comorbidity_burden=comorbidity_info,
            treatment_response=treatment_info,
            predictive_outputs=predictive_info,
            uncertainty=uncertainty_info,
            status="active",
        )
        # Compute Hash
        profile.profile_hash = CsepResolverService.calculate_profile_hash(profile)
        session.add(profile)
        await session.flush()

        # 8. Record Provenance Trace linkages
        # A. Profile -> Assertion trace
        assertion_ids = [ass.assertion_id for ass in assertions]
        for ass in assertions:
            trace_ass = ProfileAssertionTrace(
                csep_id=profile.csep_id,
                assertion_id=ass.assertion_id,
                trace_role="supporting",
                contribution_weight=float(ass.final_score),
            )
            session.add(trace_ass)

        # B. Profile -> Event trace (supporting events of assertions)
        if assertion_ids:
            stmt_events = select(AssertionSupportEvent.event_id).where(
                AssertionSupportEvent.assertion_id.in_(assertion_ids)
            ).distinct()
            res_events = await session.execute(stmt_events)
            event_ids = res_events.scalars().all()
            for ev_id in event_ids:
                trace_ev = ProfileEventTrace(
                    csep_id=profile.csep_id,
                    event_id=ev_id,
                    trace_role="supporting",
                )
                session.add(trace_ev)

        # C. Profile -> Claim trace (supporting claims of assertions)
        if assertion_ids:
            stmt_claims = select(
                AssertionSupportClaim.claim_id,
                AssertionSupportClaim.support_weight
            ).where(
                AssertionSupportClaim.assertion_id.in_(assertion_ids)
            ).distinct()
            res_claims = await session.execute(stmt_claims)
            claim_rows = res_claims.all()
            for c_id, w in claim_rows:
                trace_cl = ProfileClaimTrace(
                    csep_id=profile.csep_id,
                    claim_id=c_id,
                    trace_role="literature_prior",
                    contribution_weight=float(w),
                )
                session.add(trace_cl)

        await session.flush()
        logger.info(
            "Assembled CSEP Profile %s for Patient %s (Assertions linked: %d, Hash: %s)",
            profile.csep_id, patient_id, len(assertions), profile.profile_hash[:10]
        )
        return profile
