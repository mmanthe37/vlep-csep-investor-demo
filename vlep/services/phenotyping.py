"""
VLEP Pipeline — Phenotyping & Feature Engineering Service.

Handles Stage 4: Phenotype Assertion & Feature Engineering.
Includes bootstrapping feature definitions, building phenotype assertions
with multi-dimensional confidence, Bayesian updates, temporal windowing,
recency decay, literature prior weight sync, and feature vector value calculations.
"""

from __future__ import annotations

import logging
import math
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.evidence import LedgerEvent
from vlep.models.literature import ClaimTieringResult, PhenotypeClaim
from vlep.models.ontology import Concept
from vlep.models.phenotyping import (
    AssertionSupportClaim,
    AssertionSupportEvent,
    FeatureDefinition,
    FeatureSet,
    FeatureValue,
    FeatureWeightPrior,
    PhenotypeAssertion,
    TemporalFeatureWindow,
)

logger = logging.getLogger(__name__)


class PhenotypingService:
    """Service handling Stage 4: Phenotype Assertion and Feature Engineering."""

    @staticmethod
    async def bootstrap_feature_definitions(
        session: AsyncSession,
        feature_set_id: uuid.UUID,
    ) -> list[FeatureDefinition]:
        """Bootstrap 256 feature definitions for the given FeatureSet if they do not exist."""
        # 1. Check if feature definitions already exist
        stmt = select(FeatureDefinition).where(FeatureDefinition.feature_set_id == feature_set_id)
        result = await session.execute(stmt)
        existing = result.scalars().all()

        if existing:
            logger.info("Feature definitions already bootstrapped for feature_set_id %s", feature_set_id)
            return list(existing)

        # Get the feature set to verify dimensionality
        stmt_set = select(FeatureSet).where(FeatureSet.feature_set_id == feature_set_id)
        result_set = await session.execute(stmt_set)
        fset = result_set.scalar_one()

        # Define some key phenotype dimension mappings for the first few indices
        MVP_DIMENSION_MAPPINGS = {
            0: ("seizure_type", "Focal Seizure", "http://snomed.info/sct", "29753000"),
            1: ("seizure_type", "Generalized Seizure", "http://snomed.info/sct", "24657003"),
            2: ("etiology", "Genetic Etiology", "http://snomed.info/sct", "261665006"),
            3: ("etiology", "Structural Etiology", "http://snomed.info/sct", "261665005"),
            4: ("syndrome", "Dravet Syndrome", "http://snomed.info/sct", "84757009"),  # Stub code or generic
            5: ("biomarker", "EEG Spike Wave", "http://snomed.info/sct", "193150005"),
            6: ("comorbidity", "Cognitive Impairment", "http://snomed.info/sct", "386806002"),
            7: ("treatment_response", "Drug Resistance", "http://snomed.info/sct", "370927003"),
        }

        defs = []
        for index in range(fset.dimensionality):
            name = f"Feature {index}"
            dimension = "other"
            concept_id = None

            if index in MVP_DIMENSION_MAPPINGS:
                dim, display, system, code = MVP_DIMENSION_MAPPINGS[index]
                dimension = dim
                name = f"{dim.replace('_', ' ').title()} - {display}"

                # Try to find corresponding concept if seeded
                stmt_c = select(Concept).where(Concept.code == code)
                res_c = await session.execute(stmt_c)
                concept = res_c.scalar_one_or_none()
                if concept:
                    concept_id = concept.concept_id

            fdef = FeatureDefinition(
                feature_set_id=feature_set_id,
                feature_name=name,
                feature_index=index,
                feature_dimension=dimension,
                concept_id=concept_id,
                aggregation_method="tfidf_weighted_pooling",
                decay_lambda=0.005,  # 0.005 daily decay
                is_static=(dimension == "etiology"),
            )
            session.add(fdef)
            defs.append(fdef)

        await session.flush()
        logger.info("Bootstrapped %d feature definitions for feature_set_id %s", len(defs), feature_set_id)
        return defs

    @staticmethod
    async def create_assertion(
        session: AsyncSession,
        patient_id: uuid.UUID,
        phenotype_dimension: str | None = None,
        phenotype_label_text: str | None = None,
        effective_start: datetime | None = None,
        supporting_event_ids: list[uuid.UUID] | None = None,
        supporting_claim_ids: list[uuid.UUID] | None = None,
        phenotype_label_concept_id: uuid.UUID | None = None,
        effective_end: datetime | None = None,
        validation_status: str = "active",
        nosology_version_id: uuid.UUID | None = None,
        model_version_id: uuid.UUID | None = None,
        supersedes_assertion_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        # Alternative/legacy kwargs from router / smoke tests
        dimension: str | None = None,
        phenotype_code: str | None = None,
        phenotype_label: str | None = None,
        certainty_level: float | None = None,
        confidence_data_quality: float | None = None,
        confidence_recency: float | None = None,
        confidence_consistency: float | None = None,
    ) -> PhenotypeAssertion:
        """Create a phenotype assertion and calculate/assign confidence scores."""
        # 1. Resolve arguments
        dim = phenotype_dimension or dimension
        if not dim:
            raise ValueError("phenotype_dimension or dimension is required.")

        label = phenotype_label_text or phenotype_label
        if not label:
            raise ValueError("phenotype_label_text or phenotype_label is required.")

        start = effective_start or datetime.now(UTC)
        claim_ids = supporting_claim_ids or []
        event_ids = supporting_event_ids or []

        # Resolve phenotype_label_concept_id from phenotype_code if not explicitly passed
        concept_id = phenotype_label_concept_id
        if not concept_id and phenotype_code:
            stmt_concept = select(Concept.concept_id).where(Concept.code == phenotype_code)
            res_concept = await session.execute(stmt_concept)
            concept_id = res_concept.scalar_one_or_none()

        # 2. Fetch supporting events to calculate confidence scores
        events = []
        if event_ids:
            stmt_ev = select(LedgerEvent).where(LedgerEvent.event_id.in_(event_ids))
            res_ev = await session.execute(stmt_ev)
            events = res_ev.scalars().all()

        confidence_dq = confidence_data_quality
        confidence_rec = confidence_recency
        confidence_const = confidence_consistency

        if events:
            # A. Calculate confidence_data_quality (average certainty_level of events)
            certainties = [float(e.certainty_level) for e in events]
            confidence_dq = sum(certainties) / len(certainties)

            # B. Calculate confidence_recency (exponential decay based on newest event)
            newest_event = max(events, key=lambda e: e.observed_at)
            delta_days = (datetime.now(UTC) - newest_event.observed_at.replace(tzinfo=UTC)).days
            confidence_rec = math.exp(-0.005 * max(0, delta_days))

            # C. Calculate confidence_consistency
            stmt_all_ev = select(LedgerEvent).where(
                and_(
                    LedgerEvent.patient_id == patient_id,
                    LedgerEvent.domain == newest_event.domain
                )
            )
            res_all_ev = await session.execute(stmt_all_ev)
            all_events = res_all_ev.scalars().all()
            matching_count = len(events)
            total_count = len(all_events)
            confidence_const = (matching_count / total_count) if total_count > 0 else 1.0

            # D. Bayesian Update for posterior_probability
            prior = 0.1
            if claim_ids:
                stmt_weights = select(ClaimTieringResult.scalar_weight).where(
                    ClaimTieringResult.claim_id.in_(claim_ids)
                )
                res_weights = await session.execute(stmt_weights)
                weights = res_weights.scalars().all()
                if weights:
                    max_lit_weight = float(max(weights))
                    prior = max(0.1, max_lit_weight * 0.5)

            odds = prior / (1.0 - prior) if prior < 1.0 else 999.0
            for ev in events:
                domain_multiplier = 1.0
                if ev.domain in ["genetic_result", "EEG_biomarker", "imaging_biomarker"]:
                    domain_multiplier = 2.0
                elif ev.domain == "patient_reported_outcome":
                    domain_multiplier = 0.5

                tp = min(0.99, float(ev.certainty_level) * domain_multiplier)
                fp = 0.1
                lr = tp / fp if tp > 0 else 1.0
                odds *= lr

            posterior_probability = odds / (1.0 + odds)
            posterior_probability = min(max(posterior_probability, 0.0), 1.0)
        else:
            # Fallback when no events are provided (e.g. from smoke test)
            if confidence_dq is None or confidence_rec is None or confidence_const is None:
                raise ValueError("Phenotype assertion must have supporting events or explicit confidence scores.")
            posterior_probability = certainty_level if certainty_level is not None else 0.8

        # E. Final Score (weighted combination)
        final_score = (
            0.4 * posterior_probability +
            0.2 * confidence_dq +
            0.2 * confidence_rec +
            0.2 * confidence_const
        )
        final_score = min(max(final_score, 0.0), 1.0)

        # Merge metadata
        meta = metadata or {}
        if phenotype_code:
            meta["phenotype_code"] = phenotype_code
        if certainty_level is not None:
            meta["certainty_level"] = certainty_level

        # Create Assertion
        assertion = PhenotypeAssertion(
            patient_id=patient_id,
            phenotype_dimension=dim,
            phenotype_label_concept_id=concept_id,
            phenotype_label_text=label,
            effective_start=start,
            effective_end=effective_end,
            confidence_data_quality=confidence_dq,
            confidence_recency=confidence_rec,
            confidence_consistency=confidence_const,
            posterior_probability=posterior_probability,
            final_score=final_score,
            status=validation_status,
            nosology_version_id=nosology_version_id,
            model_version_id=model_version_id,
            supersedes_assertion_id=supersedes_assertion_id,
            metadata_=meta,
        )
        session.add(assertion)
        await session.flush()

        # Link supporting events
        if events:
            for ev in events:
                sup_ev = AssertionSupportEvent(
                    assertion_id=assertion.assertion_id,
                    event_id=ev.event_id,
                    support_role="supporting",
                    support_weight=1.0,
                )
                session.add(sup_ev)

        # Link supporting claims
        if claim_ids:
            for claim_id in claim_ids:
                sup_cl = AssertionSupportClaim(
                    assertion_id=assertion.assertion_id,
                    claim_id=claim_id,
                    support_role="literature_prior",
                    support_weight=1.0,
                )
                session.add(sup_cl)

        await session.flush()
        logger.info(
            "Created PhenotypeAssertion %s (Patient: %s, Dimension: %s, Score: %.4f)",
            assertion.assertion_id, patient_id, dim, final_score
        )
        return assertion


    @staticmethod
    async def sync_feature_weight_priors(
        session: AsyncSession,
        feature_set_id: uuid.UUID,
        ruleset_id: uuid.UUID,
    ) -> list[FeatureWeightPrior]:
        """Align literature claims and their heuristic tier weights to features."""
        # 1. Fetch feature definitions
        stmt_defs = select(FeatureDefinition).where(FeatureDefinition.feature_set_id == feature_set_id)
        res_defs = await session.execute(stmt_defs)
        feature_defs = res_defs.scalars().all()

        priors = []
        for fdef in feature_defs:
            # Query claims that mention the feature name/concept display
            claim_q = select(PhenotypeClaim.claim_id, ClaimTieringResult.scalar_weight).join(
                ClaimTieringResult, PhenotypeClaim.claim_id == ClaimTieringResult.claim_id
            ).where(
                and_(
                    ClaimTieringResult.ruleset_id == ruleset_id,
                    (
                        func.strpos(func.lower(fdef.feature_name), func.lower(PhenotypeClaim.subject_text)) > 0
                    ) | (
                        func.strpos(func.lower(fdef.feature_name), func.lower(PhenotypeClaim.object_text)) > 0
                    )
                )
            )
            res_claims = await session.execute(claim_q)
            rows = res_claims.all()

            if not rows:
                continue

            claim_ids = [r[0] for r in rows]
            weights = [float(r[1]) for r in rows]
            avg_weight = sum(weights) / len(weights)

            # Upsert FeatureWeightPrior
            prior = FeatureWeightPrior(
                feature_id=fdef.feature_id,
                ruleset_id=ruleset_id,
                scalar_weight=avg_weight,
                derived_from_claim_count=len(claim_ids),
                source_claim_ids=claim_ids,
            )
            await session.merge(prior)
            priors.append(prior)

        await session.flush()
        logger.info("Synced %d feature weight priors for ruleset %s", len(priors), ruleset_id)
        return priors

    @staticmethod
    async def build_feature_values_for_window(
        session: AsyncSession,
        patient_id: uuid.UUID,
        feature_set_id: uuid.UUID,
        window_start: datetime,
        window_end: datetime,
        as_of_time: datetime,
    ) -> tuple[TemporalFeatureWindow, list[FeatureValue]]:
        """Calculate and store feature values for a patient in a specific temporal window."""
        # 1. Fetch all active ledger events for the patient observed up to as_of_time
        # that fall within [window_start, window_end]
        from vlep.services.evidence_ledger import EvidenceLedgerService
        active_events = await EvidenceLedgerService.query_active_events(
            session=session,
            patient_id=patient_id,
            as_of_time=as_of_time,
        )

        # Filter events in window
        window_events = [
            e for e in active_events
            if window_start <= e.observed_at.replace(tzinfo=UTC) <= window_end
        ]

        # 2. Fetch feature definitions
        stmt_defs = select(FeatureDefinition).where(FeatureDefinition.feature_set_id == feature_set_id)
        res_defs = await session.execute(stmt_defs)
        feature_defs = res_defs.scalars().all()

        # 3. Create TemporalFeatureWindow
        window = TemporalFeatureWindow(
            patient_id=patient_id,
            feature_set_id=feature_set_id,
            window_start=window_start,
            window_end=window_end,
            as_of_time=as_of_time,
            event_count=len(window_events),
        )
        session.add(window)
        await session.flush()

        # 4. Compute each FeatureValue
        feature_values = []
        missing_features_count = 0

        for fdef in feature_defs:
            # Filter events matching the feature definition
            matching_events = []
            for ev in window_events:
                is_match = False

                # Check concept mapping
                if fdef.concept_id:
                    for code_entry in ev.normalized_codes:
                        # code_entry might contain "code", check if it matches concept
                        # (since concept_id was checked, we can query it)
                        stmt_concept = select(Concept).where(Concept.concept_id == fdef.concept_id)
                        res_concept = await session.execute(stmt_concept)
                        concept_obj = res_concept.scalar_one_or_none()
                        if concept_obj and code_entry.get("code") == concept_obj.code:
                            is_match = True
                            break

                # Fallback: name match in display or dimension
                if not is_match:
                    display_text = ev.data_element.get("display", "").lower()
                    if display_text and display_text in fdef.feature_name.lower() or fdef.feature_dimension and fdef.feature_dimension.lower() in ev.domain.lower():
                        is_match = True

                if is_match:
                    matching_events.append(ev)

            # A. Compute raw_value with exponential recency decay kernel
            raw_value = None
            source_event_ids = []
            if matching_events:
                source_event_ids = [e.event_id for e in matching_events]
                # Aggregate value: TF-IDF weighted pooling using certainty * decay
                decay_sum = 0.0
                for ev in matching_events:
                    # observed_at time difference relative to window_end
                    delta_days = (window_end - ev.observed_at.replace(tzinfo=UTC)).total_seconds() / 86400.0
                    decay_lambda = fdef.decay_lambda or 0.005
                    # Heaviside step H(t - tau) is implicitly True because we filter observed_at <= window_end
                    kernel_val = math.exp(-decay_lambda * max(0.0, delta_days))
                    decay_sum += float(ev.certainty_level) * kernel_val
                raw_value = decay_sum
            else:
                missing_features_count += 1

            # B. Compute weighted_value using literature prior
            weighted_value = raw_value
            source_claim_ids = []
            if raw_value is not None:
                # Look up literature weight prior for this feature
                stmt_prior = select(FeatureWeightPrior).where(FeatureWeightPrior.feature_id == fdef.feature_id)
                res_prior = await session.execute(stmt_prior)
                prior_obj = res_prior.scalar_one_or_none()
                if prior_obj:
                    weighted_value = raw_value * float(prior_obj.scalar_weight)
                    source_claim_ids = prior_obj.source_claim_ids

            # C. Imputation (Default: Forward Carry or zero-fill)
            imputed_value = weighted_value
            imputation_method = None
            if weighted_value is None:
                # Try to fetch the most recent non-null FeatureValue for this patient and feature index
                stmt_prev = select(FeatureValue).join(
                    TemporalFeatureWindow, FeatureValue.feature_window_id == TemporalFeatureWindow.feature_window_id
                ).where(
                    and_(
                        TemporalFeatureWindow.patient_id == patient_id,
                        FeatureValue.feature_id == fdef.feature_id,
                        TemporalFeatureWindow.window_end < window_start,
                        FeatureValue.weighted_value.is_not(None)
                    )
                ).order_by(TemporalFeatureWindow.window_end.desc()).limit(1)

                res_prev = await session.execute(stmt_prev)
                prev_val = res_prev.scalar_one_or_none()
                if prev_val:
                    imputed_value = prev_val.weighted_value
                    imputation_method = "forward_fill"
                else:
                    imputed_value = 0.0
                    imputation_method = "zero_fill"

            fval = FeatureValue(
                feature_window_id=window.feature_window_id,
                feature_id=fdef.feature_id,
                raw_value=raw_value,
                weighted_value=weighted_value,
                imputed_value=imputed_value,
                imputation_method=imputation_method,
                source_event_ids=source_event_ids,
                source_claim_ids=source_claim_ids,
            )
            session.add(fval)
            feature_values.append(fval)

        # Update window missingness score
        window.missingness_score = missing_features_count / len(feature_defs) if feature_defs else 1.0
        await session.flush()

        logger.info(
            "Built window %s (Patient: %s, Events: %d, Missing: %.2f%%)",
            window.feature_window_id, patient_id, len(window_events), window.missingness_score * 100
        )
        return window, feature_values
