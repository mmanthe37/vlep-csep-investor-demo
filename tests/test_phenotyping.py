"""
Unit and integration tests for Stage 4: Phenotype Assertion & Feature Engineering.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from vlep.models.core import Patient
from vlep.models.evidence import LedgerEvent
from vlep.models.literature import HeuristicRuleset
from vlep.models.phenotyping import (
    AssertionSupportClaim,
    AssertionSupportEvent,
    FeatureSet,
    FeatureWeightPrior,
)
from vlep.services.literature import LiteratureService
from vlep.services.phenotyping import PhenotypingService


@pytest.fixture
async def sample_feature_set(db_session) -> FeatureSet:
    """Create a sample feature set for tests."""
    fset = FeatureSet(
        name="Test MVP Feature Vector",
        version_label="v1.0-test",
        description="Test feature set",
        dimensionality=256,
        window_days=30,
    )
    db_session.add(fset)
    await db_session.commit()
    return fset


@pytest.fixture
async def sample_patient(db_session) -> Patient:
    """Create a sample patient."""
    patient = Patient(source_patient_hash="test-patient-hash-phenotyping")
    db_session.add(patient)
    await db_session.commit()
    return patient


@pytest.fixture
async def sample_ruleset(db_session) -> HeuristicRuleset:
    """Seed a sample ruleset in the test database."""
    rules_json = {
        "tier_1": {
            "causal_methods": ["Mendelian Randomization", "LDSC"],
            "prospective_or_rct": {"n_min": 200, "p_value_max": 0.01}
        },
        "tier_2": {
            "designs": ["retrospective", "cross-sectional", "cohort"],
            "n_min": 50,
            "p_value_max": 0.05
        },
        "tier_3": {
            "designs": ["observational case-series", "case-series"],
            "n_min": 20,
            "n_max_exclusive": 50
        },
        "excluded": {
            "n_max_exclusive": 20
        },
        "weights": {
            "TIER_1": 1.0,
            "TIER_2": 0.6,
            "TIER_3": 0.2,
            "TIER_4": 0.1,
            "EXCLUDED": 0.0
        }
    }
    ruleset = HeuristicRuleset(
        name="Test ruleset",
        version_label="v1.0-test",
        status="active",
        rules_json=rules_json,
    )
    db_session.add(ruleset)
    await db_session.commit()
    return ruleset


@pytest.mark.asyncio
async def test_bootstrap_feature_definitions(db_session, sample_feature_set):
    """Test that 256 feature definitions are created with correct index mapping."""
    defs = await PhenotypingService.bootstrap_feature_definitions(db_session, sample_feature_set.feature_set_id)
    await db_session.commit()

    assert len(defs) == 256

    # Verify index mapping
    indices = [d.feature_index for d in defs]
    assert indices == list(range(256))

    # Verify first index (Seizure Type)
    assert defs[0].feature_dimension == "seizure_type"
    assert "Focal Seizure" in defs[0].feature_name
    assert defs[0].is_static is False

    # Verify etiology index (Etiology is static)
    assert defs[2].feature_dimension == "etiology"
    assert defs[2].is_static is True


@pytest.mark.asyncio
async def test_create_assertion_success(db_session, sample_patient, sample_ruleset):
    """Test that phenotype assertions are built with calculated confidence, Bayesian posterior, and links."""
    now = datetime.now(UTC)

    # 1. Add supporting ledger events
    e1 = LedgerEvent(
        patient_id=sample_patient.patient_id,
        observed_at=now - timedelta(days=2),
        domain="clinical_observation",
        data_element={"display": "Focal Seizure"},
        source_attribution="clinician",
        certainty_level=0.90,
        validation_status="normalized",
    )
    e2 = LedgerEvent(
        patient_id=sample_patient.patient_id,
        observed_at=now - timedelta(days=5),
        domain="clinical_observation",
        data_element={"display": "Second Seizure"},
        source_attribution="automated_system",
        certainty_level=0.80,
        validation_status="normalized",
    )
    db_session.add_all([e1, e2])
    await db_session.commit()

    # 2. Add supporting claim (literature prior)
    doc = await LiteratureService.create_or_update_document(
        session=db_session, source_kind="PubMed_MEDLINE", title="Study", doi="10.1000/study"
    )
    claim = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="study-claim-key",
        subject_text="Focal Seizure",
        predicate="associated_with",
        object_text="Epilepsy",
        source_document_id=doc.document_id,
        source_start_offset=0,
        source_end_offset=15,
        source_sentence="Focal Seizure is associated with Epilepsy",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session, claim_id=claim.claim_id, study_design="retrospective cohort", n_subjects=100, p_value=0.01
    )
    await LiteratureService.evaluate_claim_tiering(session=db_session, claim_id=claim.claim_id, ruleset_id=sample_ruleset.ruleset_id)
    await db_session.commit()

    # Create Assertion
    assertion = await PhenotypingService.create_assertion(
        session=db_session,
        patient_id=sample_patient.patient_id,
        phenotype_dimension="seizure_type",
        phenotype_label_text="Focal Seizure",
        effective_start=now - timedelta(days=2),
        supporting_event_ids=[e1.event_id, e2.event_id],
        supporting_claim_ids=[claim.claim_id],
    )
    await db_session.commit()

    assert assertion.assertion_id is not None
    assert assertion.phenotype_dimension == "seizure_type"
    assert assertion.phenotype_label_text == "Focal Seizure"

    # Assert confidence calculations are floats in [0, 1]
    assert 0.0 <= float(assertion.confidence_data_quality) <= 1.0
    assert 0.0 <= float(assertion.confidence_recency) <= 1.0
    assert 0.0 <= float(assertion.confidence_consistency) <= 1.0
    assert 0.0 <= float(assertion.posterior_probability) <= 1.0
    assert 0.0 <= float(assertion.final_score) <= 1.0

    # Verify support linkages
    stmt_evs = select(AssertionSupportEvent).where(AssertionSupportEvent.assertion_id == assertion.assertion_id)
    res_evs = await db_session.execute(stmt_evs)
    linked_evs = res_evs.scalars().all()
    assert len(linked_evs) == 2

    stmt_cls = select(AssertionSupportClaim).where(AssertionSupportClaim.assertion_id == assertion.assertion_id)
    res_cls = await db_session.execute(stmt_cls)
    linked_cls = res_cls.scalars().all()
    assert len(linked_cls) == 1
    assert linked_cls[0].claim_id == claim.claim_id


@pytest.mark.asyncio
async def test_sync_feature_weight_priors(db_session, sample_feature_set, sample_ruleset):
    """Test mapping and syncing literature claims/weights to feature priors."""
    # 1. Bootstrap feature definitions
    defs = await PhenotypingService.bootstrap_feature_definitions(db_session, sample_feature_set.feature_set_id)
    await db_session.commit()

    # 2. Add literature claims matching focal/generalized seizures
    doc = await LiteratureService.create_or_update_document(
        session=db_session, source_kind="PubMed_MEDLINE", title="Focal Guide", doi="10.1000/focal"
    )
    claim1 = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="focal-seizure-claim",
        subject_text="Focal Seizure",
        predicate="treats",
        object_text="epilepsy",
        source_document_id=doc.document_id,
        source_start_offset=0,
        source_end_offset=15,
        source_sentence="Focal Seizure treats epilepsy",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session, claim_id=claim1.claim_id, study_design="prospective randomized clinical trial", n_subjects=300, p_value=0.001
    )
    await LiteratureService.evaluate_claim_tiering(session=db_session, claim_id=claim1.claim_id, ruleset_id=sample_ruleset.ruleset_id)
    await db_session.commit()

    # 3. Sync priors
    priors = await PhenotypingService.sync_feature_weight_priors(db_session, sample_feature_set.feature_set_id, sample_ruleset.ruleset_id)
    await db_session.commit()

    assert len(priors) > 0
    # Prior for "Seizure Type - Focal Seizure" (feature definition at index 0)
    # should be synced because its display name matches the claim
    fdef_focal = defs[0]
    stmt_prior = select(FeatureWeightPrior).where(FeatureWeightPrior.feature_id == fdef_focal.feature_id)
    res_prior = await db_session.execute(stmt_prior)
    prior_focal = res_prior.scalar_one_or_none()
    assert prior_focal is not None
    assert float(prior_focal.scalar_weight) == 1.0  # TIER_1 claim weight is 1.0


@pytest.mark.asyncio
async def test_build_feature_values_in_window(db_session, sample_patient, sample_feature_set, sample_ruleset):
    """Test temporal windowing, decay aggregation, prior scaling, and value imputation."""
    now = datetime.now(UTC)

    # 1. Bootstrap definitions and sync priors
    defs = await PhenotypingService.bootstrap_feature_definitions(db_session, sample_feature_set.feature_set_id)

    # Add a claim for focal seizure to get a tier weight
    doc = await LiteratureService.create_or_update_document(
        session=db_session, source_kind="PubMed_MEDLINE", title="Focal In Window", doi="10.1000/focal-win"
    )
    claim = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="focal-win-claim",
        subject_text="Focal Seizure",
        predicate="exacerbates",
        object_text="epilepsy",
        source_document_id=doc.document_id,
        source_start_offset=0,
        source_end_offset=15,
        source_sentence="Focal Seizure exacerbates epilepsy",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session, claim_id=claim.claim_id, study_design="retrospective cohort", n_subjects=100, p_value=0.01
    )
    await LiteratureService.evaluate_claim_tiering(session=db_session, claim_id=claim.claim_id, ruleset_id=sample_ruleset.ruleset_id)
    await db_session.commit()

    await PhenotypingService.sync_feature_weight_priors(db_session, sample_feature_set.feature_set_id, sample_ruleset.ruleset_id)
    await db_session.commit()

    # 2. Append active ledger event inside the window matching focal seizure
    # Observed 10 days ago (relative to window_end which is now)
    observed_time = now - timedelta(days=10)
    e1 = LedgerEvent(
        patient_id=sample_patient.patient_id,
        observed_at=observed_time,
        domain="clinical_observation",
        data_element={"display": "Focal Seizure"},
        source_attribution="clinician",
        certainty_level=0.90,
        validation_status="normalized",
    )
    db_session.add(e1)
    await db_session.commit()

    # 3. Create temporal window and calculate values
    window_start = now - timedelta(days=30)
    window_end = now
    as_of_time = now

    window, values = await PhenotypingService.build_feature_values_for_window(
        session=db_session,
        patient_id=sample_patient.patient_id,
        feature_set_id=sample_feature_set.feature_set_id,
        window_start=window_start,
        window_end=window_end,
        as_of_time=as_of_time,
    )
    await db_session.commit()

    assert window.event_count == 1
    assert len(values) == 256

    # Assert focal seizure feature value (index 0) has raw, weighted, and imputed values
    fval_focal = next(v for v in values if v.feature_id == defs[0].feature_id)
    assert fval_focal.raw_value is not None
    # Raw value should be certainty_level * decay
    # certainty_level = 0.90, decay = exp(-0.005 * 10) = exp(-0.05) ~ 0.9512
    # expected_raw ~ 0.90 * 0.9512 ~ 0.856
    assert 0.84 <= fval_focal.raw_value <= 0.87

    # Weighted value should be raw_value * scalar_weight
    # claim weight is 0.6 (TIER_2), so weighted_value ~ 0.856 * 0.6 = 0.5136
    assert 0.50 <= fval_focal.weighted_value <= 0.53
    assert fval_focal.imputed_value == fval_focal.weighted_value
    assert fval_focal.imputation_method is None

    # Assert that missing features (e.g. index 1) are imputed
    fval_missing = next(v for v in values if v.feature_id == defs[1].feature_id)
    assert fval_missing.raw_value is None
    assert fval_missing.weighted_value is None
    assert fval_missing.imputed_value == 0.0
    assert fval_missing.imputation_method == "zero_fill"
