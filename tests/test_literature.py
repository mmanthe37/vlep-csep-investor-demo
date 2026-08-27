"""
Unit and integration tests for Stage 2: Literature Ingestion & Provenance Tiering.
"""

from datetime import date

import pytest
from sqlalchemy import select, text

from vlep.models.literature import (
    CorpusClaim,
    HeuristicRuleset,
)
from vlep.services.literature import LiteratureService


@pytest.fixture
async def sample_ruleset(db_session):
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
async def test_calculate_provenance_tier_logic(sample_ruleset):
    rules = sample_ruleset.rules_json

    # Tier 1 - Causal Method
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="observational", n_subjects=10, p_value=None,
        causal_method="Mendelian Randomization", rules_json=rules
    )
    assert tier == "TIER_1"
    assert weight == 1.0

    # Tier 1 - Prospective RCT
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="prospective randomized clinical trial", n_subjects=250, p_value=0.005,
        causal_method="none", rules_json=rules
    )
    assert tier == "TIER_1"
    assert weight == 1.0

    # Tier 2 - Retrospective Cohort
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="retrospective cohort", n_subjects=80, p_value=0.02,
        causal_method="none", rules_json=rules
    )
    assert tier == "TIER_2"
    assert weight == 0.6

    # Tier 3 - Case-Series
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="observational case-series", n_subjects=35, p_value=0.05,
        causal_method="none", rules_json=rules
    )
    assert tier == "TIER_3"
    assert weight == 0.2

    # Tier 4 - Fallback (N >= 20, but fails p-value / designs for higher tiers)
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="observational", n_subjects=25, p_value=0.1,
        causal_method="none", rules_json=rules
    )
    assert tier == "TIER_4"
    assert weight == 0.1

    # Excluded - N < 20
    tier, weight, rat = LiteratureService.calculate_provenance_tier(
        study_design="case report", n_subjects=5, p_value=None,
        causal_method="none", rules_json=rules
    )
    assert tier == "EXCLUDED"
    assert weight == 0.0


@pytest.mark.asyncio
async def test_document_and_section_creation(db_session):
    # 1. Create or update document
    doc = await LiteratureService.create_or_update_document(
        session=db_session,
        source_kind="PubMed_MEDLINE",
        title="Seizure treatment patterns in 2026",
        doi="10.1000/xyz123",
        authors=["John Doe", "Jane Smith"],
        publication_date=date(2026, 6, 1),
    )
    assert doc.document_id is not None
    assert doc.title == "Seizure treatment patterns in 2026"
    assert doc.authors == ["John Doe", "Jane Smith"]

    # Verify update works on DOI
    doc_upd = await LiteratureService.create_or_update_document(
        session=db_session,
        source_kind="PubMed_MEDLINE",
        title="Seizure treatment patterns in 2026 (Updated)",
        doi="10.1000/xyz123",
        authors=["John Doe", "Jane Smith", "Bob Johnson"],
    )
    assert doc_upd.document_id == doc.document_id
    assert doc_upd.title == "Seizure treatment patterns in 2026 (Updated)"
    assert doc_upd.authors == ["John Doe", "Jane Smith", "Bob Johnson"]

    # 2. Create document section
    sect = await LiteratureService.create_or_update_document_section(
        session=db_session,
        document_id=doc.document_id,
        section_kind="METHODS",
        ordinal=1,
        text_content="We studied 100 patients retrospectively.",
    )
    assert sect.section_id is not None
    assert sect.document_id == doc.document_id
    assert sect.ordinal == 1
    assert sect.text_content == "We studied 100 patients retrospectively."


@pytest.mark.asyncio
async def test_claim_ingestion_and_tiering(db_session, sample_ruleset):
    # 1. Setup Document and Section
    doc = await LiteratureService.create_or_update_document(
        session=db_session,
        source_kind="PubMed_MEDLINE",
        title="Retrospective study of SCN1A mutations",
        doi="10.1000/scn1a",
    )
    sect = await LiteratureService.create_or_update_document_section(
        session=db_session,
        document_id=doc.document_id,
        section_kind="RESULTS",
        ordinal=2,
        text_content="SCN1A mutations exacerbate Dravet syndrome severity.",
    )

    # 2. Create Phenotype Claim
    claim = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="test-claim-scn1a",
        subject_text="SCN1A mutation",
        predicate="exacerbates",
        object_text="Dravet syndrome",
        source_document_id=doc.document_id,
        source_section_id=sect.section_id,
        source_start_offset=0,
        source_end_offset=15,
        source_sentence="SCN1A mutations exacerbate Dravet syndrome severity.",
        extraction_model_version="BioClinicalBERT v1",
    )
    assert claim.claim_id is not None
    assert claim.claim_key == "test-claim-scn1a"

    # 3. Create Evidence Metadata
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session,
        claim_id=claim.claim_id,
        study_design="retrospective cohort",
        n_subjects=75,
        p_value=0.01,
        causal_method="none",
        parsed_from_section="RESULTS",
    )

    # 4. Evaluate tiering
    tier_res = await LiteratureService.evaluate_claim_tiering(
        session=db_session,
        claim_id=claim.claim_id,
        ruleset_id=sample_ruleset.ruleset_id,
    )
    assert tier_res.tier == "TIER_2"
    assert float(tier_res.scalar_weight) == 0.6
    assert "Retrospective/cohort design" in tier_res.tier_rationale


@pytest.mark.asyncio
async def test_corpus_release_generation(db_session, sample_ruleset):
    # Setup two claims
    doc = await LiteratureService.create_or_update_document(
        session=db_session,
        source_kind="PubMed_MEDLINE",
        title="Consensus guide",
        doi="10.1000/consensus",
    )
    sect = await LiteratureService.create_or_update_document_section(
        session=db_session,
        document_id=doc.document_id,
        section_kind="DISCUSSION",
        ordinal=0,
        text_content="Valproate treats generalized seizures.",
    )

    # Claim 1 - Tier 1
    c1 = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="c1-valproate",
        subject_text="Valproate",
        predicate="treats",
        object_text="generalized seizures",
        source_document_id=doc.document_id,
        source_section_id=sect.section_id,
        source_start_offset=0,
        source_end_offset=9,
        source_sentence="Valproate treats generalized seizures.",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session,
        claim_id=c1.claim_id,
        study_design="prospective randomized clinical trial",
        n_subjects=300,
        p_value=0.001,
    )

    # Claim 2 - Excluded
    c2 = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="c2-valproate-rare",
        subject_text="Valproate",
        predicate="exacerbates",
        object_text="rare disease",
        source_document_id=doc.document_id,
        source_section_id=sect.section_id,
        source_start_offset=0,
        source_end_offset=9,
        source_sentence="Valproate exacerbates rare disease.",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session,
        claim_id=c2.claim_id,
        study_design="case report",
        n_subjects=3,
    )

    # Create Release
    release = await LiteratureService.create_corpus_release(
        session=db_session,
        name="Test Release",
        version_label="v1.0",
        ruleset_id=sample_ruleset.ruleset_id,
        description="A test corpus release.",
        claim_ids=[c1.claim_id, c2.claim_id],
    )

    assert release.corpus_release_id is not None
    assert release.intended_claim_count == 2
    assert release.tier_distribution.get("TIER_1") == 1
    assert release.tier_distribution.get("EXCLUDED") == 1

    # Verify relationships via query
    stmt = select(CorpusClaim).where(CorpusClaim.corpus_release_id == release.corpus_release_id)
    res = await db_session.execute(stmt)
    claims = res.scalars().all()
    assert len(claims) == 2


@pytest.mark.asyncio
async def test_claim_audit_view_integration(db_session, sample_ruleset):
    # 1. Setup Document, Section, Claim, and Metadata
    doc = await LiteratureService.create_or_update_document(
        session=db_session,
        source_kind="PubMed_MEDLINE",
        title="SCN1A audit study",
        doi="10.1000/scn1a-audit",
    )
    sect = await LiteratureService.create_or_update_document_section(
        session=db_session,
        document_id=doc.document_id,
        section_kind="RESULTS",
        ordinal=0,
        text_content="SCN1A acts as trigger.",
    )
    claim = await LiteratureService.create_or_update_phenotype_claim(
        session=db_session,
        claim_key="scn1a-audit-key",
        subject_text="SCN1A",
        predicate="acts as",
        object_text="trigger",
        source_document_id=doc.document_id,
        source_section_id=sect.section_id,
        source_start_offset=0,
        source_end_offset=5,
        source_sentence="SCN1A acts as trigger.",
        extraction_model_version="BioClinicalBERT v1",
    )
    await LiteratureService.create_or_update_claim_evidence_metadata(
        session=db_session,
        claim_id=claim.claim_id,
        study_design="retrospective cohort",
        n_subjects=120,
        p_value=0.01,
    )
    await LiteratureService.evaluate_claim_tiering(
        session=db_session,
        claim_id=claim.claim_id,
        ruleset_id=sample_ruleset.ruleset_id,
    )

    # 2. Query the claim_audit_view directly
    stmt = text("SELECT * FROM literature.claim_audit_view WHERE claim_key = :key")
    res = await db_session.execute(stmt, {"key": "scn1a-audit-key"})
    row = res.first()

    assert row is not None
    assert row.subject_text == "SCN1A"
    assert row.predicate == "acts as"
    assert row.object_text == "trigger"
    assert row.source_title == "SCN1A audit study"
    assert row.study_design == "retrospective cohort"
    assert int(row.n_subjects) == 120
    assert row.tier == "TIER_2"
    assert float(row.scalar_weight) == 0.6

