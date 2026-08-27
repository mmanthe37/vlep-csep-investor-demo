"""
VLEP Pipeline — Literature Extraction & Provenance Tiering (CESP) Service.

Coordinates document ingestion, section parsing, claim extraction, and
heuristic provenance tiering computation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Any

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from vlep.models.literature import (
    ClaimEvidenceMetadata,
    ClaimTieringResult,
    CorpusClaim,
    CorpusRelease,
    Document,
    DocumentSection,
    HeuristicRuleset,
    PhenotypeClaim,
)

logger = logging.getLogger(__name__)


class LiteratureService:
    """Service handling Stage 2: Literature Ingestion and Provenance Tiering."""

    @staticmethod
    async def create_document(
        session: AsyncSession,
        title: str,
        pmid: str | None = None,
        pmcid: str | None = None,
        doi: str | None = None,
        abstract: str | None = None,
        journal: str | None = None,
        publication_year: int | None = None,
        authors: list[str] = [],
        study_design: str | None = None,
        n_subjects: int | None = None,
        p_value: float | None = None,
        effect_size: float | None = None,
    ) -> Document:
        """Helper to create a document with default source_kind/external_id, matching API router and test expectations."""
        source_kind = "PubMed_MEDLINE" if pmid else ("PMC_OPEN_ACCESS" if pmcid else "Other")
        external_id = pmid or pmcid or doi or f"manual-{uuid.uuid4().hex[:12]}"

        publication_date = None
        if publication_year:
            publication_date = date(publication_year, 1, 1)

        metadata = {}
        if abstract:
            metadata["abstract"] = abstract
        if study_design:
            metadata["study_design"] = study_design
        if n_subjects is not None:
            metadata["n_subjects"] = n_subjects
        if p_value is not None:
            metadata["p_value"] = p_value
        if effect_size is not None:
            metadata["effect_size"] = effect_size

        return await LiteratureService.create_or_update_document(
            session=session,
            source_kind=source_kind,
            title=title,
            external_id=external_id,
            doi=doi,
            pmid=pmid,
            pmcid=pmcid,
            journal=journal,
            publication_date=publication_date,
            authors=authors,
            metadata=metadata,
        )

    @staticmethod
    async def create_or_update_document(
        session: AsyncSession,
        source_kind: str,
        title: str,
        external_id: str | None = None,
        doi: str | None = None,
        pmid: str | None = None,
        pmcid: str | None = None,
        journal: str | None = None,
        publication_date: date | None = None,
        authors: list[str] = [],
        peer_review_status: str | None = None,
        license: str | None = None,
        access_policy: str = "metadata_or_permitted_text",
        source_uri: str | None = None,
        object_uri: str | None = None,
        sha256: str | None = None,
        text_extraction_status: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Create a new document or update an existing one based on DOI or source_kind + external_id."""
        doc = None

        # 1. Try finding by DOI
        if doi:
            stmt = select(Document).where(Document.doi == doi)
            result = await session.execute(stmt)
            doc = result.scalar_one_or_none()

        # 2. Try finding by source_kind + external_id
        if not doc and external_id:
            stmt = select(Document).where(
                and_(
                    Document.source_kind == source_kind,
                    Document.external_id == external_id
                )
            )
            result = await session.execute(stmt)
            doc = result.scalar_one_or_none()

        if doc:
            # Update existing fields
            doc.title = title
            if pmid:
                doc.pmid = pmid
            if pmcid:
                doc.pmcid = pmcid
            if journal:
                doc.journal = journal
            if publication_date:
                doc.publication_date = publication_date
            if authors:
                doc.authors = authors
            if peer_review_status:
                doc.peer_review_status = peer_review_status
            if license:
                doc.license = license
            if access_policy:
                doc.access_policy = access_policy
            if source_uri:
                doc.source_uri = source_uri
            if object_uri:
                doc.object_uri = object_uri
            if sha256:
                doc.sha256 = sha256
            if text_extraction_status:
                doc.text_extraction_status = text_extraction_status
            if metadata:
                doc.metadata_ = metadata
        else:
            # Create new document
            doc = Document(
                source_kind=source_kind,
                external_id=external_id,
                doi=doi,
                pmid=pmid,
                pmcid=pmcid,
                title=title,
                journal=journal,
                publication_date=publication_date,
                authors=authors,
                peer_review_status=peer_review_status,
                license=license,
                access_policy=access_policy,
                source_uri=source_uri,
                object_uri=object_uri,
                sha256=sha256,
                text_extraction_status=text_extraction_status,
                metadata_=metadata or {},
            )
            session.add(doc)

        await session.commit()
        return doc

    @staticmethod
    async def create_or_update_document_section(
        session: AsyncSession,
        document_id: uuid.UUID,
        section_kind: str,
        ordinal: int,
        section_label: str | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        text_content: str | None = None,
        token_count: int | None = None,
        extraction_model_version: str | None = None,
    ) -> DocumentSection:
        """Create a new document section or update an existing one under a document with matching ordinal."""
        stmt = select(DocumentSection).where(
            and_(
                DocumentSection.document_id == document_id,
                DocumentSection.ordinal == ordinal
            )
        )
        res = await session.execute(stmt)
        sect = res.scalar_one_or_none()

        if sect:
            sect.section_kind = section_kind
            sect.section_label = section_label
            sect.char_start = char_start
            sect.char_end = char_end
            sect.text_content = text_content
            sect.token_count = token_count
            sect.extraction_model_version = extraction_model_version
        else:
            sect = DocumentSection(
                document_id=document_id,
                section_kind=section_kind,
                section_label=section_label,
                ordinal=ordinal,
                char_start=char_start,
                char_end=char_end,
                text_content=text_content,
                token_count=token_count,
                extraction_model_version=extraction_model_version,
            )
            session.add(sect)

        await session.commit()
        return sect

    @staticmethod
    async def ingest_claim(
        session: AsyncSession,
        document_id: uuid.UUID,
        subject_text: str,
        predicate: str,
        object_text: str,
        source_sentence: str,
        negated: bool = False,
        certainty: float = 0.95,
    ) -> PhenotypeClaim:
        """Helper to ingest a claim from tests."""
        claim_key = f"smoke-{uuid.uuid4().hex[:12]}"
        return await LiteratureService.create_or_update_phenotype_claim(
            session=session,
            claim_key=claim_key,
            subject_text=subject_text,
            predicate=predicate,
            object_text=object_text,
            source_document_id=document_id,
            source_start_offset=0,
            source_end_offset=len(source_sentence),
            source_sentence=source_sentence,
            extraction_model_version="smoke-nlp-v1",
            negation_status=negated,
            extraction_confidence=certainty,
        )

    @staticmethod
    async def create_or_update_phenotype_claim(
        session: AsyncSession,
        claim_key: str,
        subject_text: str,
        predicate: str,
        object_text: str,
        source_document_id: uuid.UUID,
        source_start_offset: int,
        source_end_offset: int,
        source_sentence: str,
        extraction_model_version: str,
        subject_concept_id: uuid.UUID | None = None,
        object_concept_id: uuid.UUID | None = None,
        relation_context: dict | None = None,
        negation_status: bool = False,
        conditionality: str | None = None,
        temporal_context: str | None = None,
        age_context: str | None = None,
        sex_context: str | None = None,
        source_section_id: uuid.UUID | None = None,
        extraction_confidence: float | None = None,
        metadata: dict | None = None,
    ) -> PhenotypeClaim:
        """Create or update a phenotype claim by its unique claim key."""
        stmt = select(PhenotypeClaim).where(PhenotypeClaim.claim_key == claim_key)
        res = await session.execute(stmt)
        claim = res.scalar_one_or_none()

        if claim:
            claim.subject_text = subject_text
            claim.predicate = predicate
            claim.object_text = object_text
            claim.source_document_id = source_document_id
            claim.source_start_offset = source_start_offset
            claim.source_end_offset = source_end_offset
            claim.source_sentence = source_sentence
            claim.extraction_model_version = extraction_model_version
            if subject_concept_id:
                claim.subject_concept_id = subject_concept_id
            if object_concept_id:
                claim.object_concept_id = object_concept_id
            if relation_context:
                claim.relation_context = relation_context
            claim.negation_status = negation_status
            claim.conditionality = conditionality
            claim.temporal_context = temporal_context
            claim.age_context = age_context
            claim.sex_context = sex_context
            if source_section_id:
                claim.source_section_id = source_section_id
            if extraction_confidence is not None:
                claim.extraction_confidence = extraction_confidence
            if metadata:
                claim.metadata_ = metadata
        else:
            claim = PhenotypeClaim(
                claim_key=claim_key,
                subject_text=subject_text,
                predicate=predicate,
                object_text=object_text,
                source_document_id=source_document_id,
                source_start_offset=source_start_offset,
                source_end_offset=source_end_offset,
                source_sentence=source_sentence,
                extraction_model_version=extraction_model_version,
                subject_concept_id=subject_concept_id,
                object_concept_id=object_concept_id,
                relation_context=relation_context or {},
                negation_status=negation_status,
                conditionality=conditionality,
                temporal_context=temporal_context,
                age_context=age_context,
                sex_context=sex_context,
                source_section_id=source_section_id,
                extraction_confidence=extraction_confidence,
                metadata_=metadata or {},
            )
            session.add(claim)

        await session.commit()
        return claim

    @staticmethod
    async def create_or_update_claim_evidence_metadata(
        session: AsyncSession,
        claim_id: uuid.UUID,
        study_design: str | None = None,
        n_subjects: int | None = None,
        p_value: float | None = None,
        confidence_interval: str | None = None,
        correction_method: str | None = None,
        effect_size: float | None = None,
        causal_method: str = "none",
        peer_review_status: str | None = None,
        journal_metric: float | None = None,
        replication_density: float | None = None,
        publication_recency_days: int | None = None,
        parsed_from_section: str | None = None,
        metadata: dict | None = None,
    ) -> ClaimEvidenceMetadata:
        """Create or update evidence metadata for a claim."""
        stmt = select(ClaimEvidenceMetadata).where(ClaimEvidenceMetadata.claim_id == claim_id)
        res = await session.execute(stmt)
        ev_meta = res.scalar_one_or_none()

        if ev_meta:
            ev_meta.study_design = study_design
            ev_meta.n_subjects = n_subjects
            ev_meta.p_value = p_value
            ev_meta.confidence_interval = confidence_interval
            ev_meta.correction_method = correction_method
            ev_meta.effect_size = effect_size
            ev_meta.causal_method = causal_method
            ev_meta.peer_review_status = peer_review_status
            ev_meta.journal_metric = journal_metric
            ev_meta.replication_density = replication_density
            ev_meta.publication_recency_days = publication_recency_days
            ev_meta.parsed_from_section = parsed_from_section
            if metadata:
                ev_meta.metadata_ = metadata
        else:
            ev_meta = ClaimEvidenceMetadata(
                claim_id=claim_id,
                study_design=study_design,
                n_subjects=n_subjects,
                p_value=p_value,
                confidence_interval=confidence_interval,
                correction_method=correction_method,
                effect_size=effect_size,
                causal_method=causal_method,
                peer_review_status=peer_review_status,
                journal_metric=journal_metric,
                replication_density=replication_density,
                publication_recency_days=publication_recency_days,
                parsed_from_section=parsed_from_section,
                metadata_=metadata or {},
            )
            session.add(ev_meta)

        await session.commit()
        return ev_meta

    @staticmethod
    def calculate_provenance_tier(
        study_design: str | None,
        n_subjects: int | None,
        p_value: float | None,
        causal_method: str | None,
        rules_json: dict,
    ) -> tuple[str, float, str]:
        """Evaluate a claim's evidence stats against a ruleset to determine the Tier, weight, and rationale."""
        tier = "TIER_4"
        rationale = "Does not meet specific criteria for higher tiers."

        # Normalize inputs
        design = (study_design or "").lower()
        causal = (causal_method or "").lower()
        n = n_subjects if n_subjects is not None else 0
        p = p_value if p_value is not None else 1.0

        # Check Tier 1 Causal Methods first
        t1_rules = rules_json.get("tier_1", {})
        t1_causal_methods = [m.lower() for m in t1_rules.get("causal_methods", ["Mendelian Randomization", "LDSC"])]
        if any(m in causal for m in t1_causal_methods) and causal != "none" and causal != "":
            tier = "TIER_1"
            rationale = f"Causal method '{causal_method}' matches Tier 1 rules."
            weight = rules_json.get("weights", {}).get("TIER_1", 1.0)
            return tier, weight, rationale

        # Check Excluded
        excl_rules = rules_json.get("excluded", {})
        n_max_excl = excl_rules.get("n_max_exclusive", 20)
        if n < n_max_excl:
            tier = "EXCLUDED"
            rationale = f"Sample size (N={n}) is below threshold of {n_max_excl}."
            weight = rules_json.get("weights", {}).get("EXCLUDED", 0.0)
            return tier, weight, rationale

        # Check Tier 1 prospective/RCT
        t1_pros = t1_rules.get("prospective_or_rct", {"n_min": 200, "p_value_max": 0.01})
        t1_n_min = t1_pros.get("n_min", 200)
        t1_p_max = t1_pros.get("p_value_max", 0.01)
        is_pros = any(kw in design for kw in ["prospective", "randomized", "rct", "trial"])
        if is_pros and n >= t1_n_min and p <= t1_p_max:
            tier = "TIER_1"
            rationale = f"Prospective/RCT design, N={n} >= {t1_n_min}, p={p} <= {t1_p_max}."
            weight = rules_json.get("weights", {}).get("TIER_1", 1.0)
            return tier, weight, rationale

        # Check Tier 2
        t2_rules = rules_json.get("tier_2", {})
        t2_designs = [d.lower() for d in t2_rules.get("designs", ["retrospective", "cross-sectional", "cohort"])]
        t2_n_min = t2_rules.get("n_min", 50)
        t2_p_max = t2_rules.get("p_value_max", 0.05)
        is_t2_design = any(d in design for d in t2_designs)
        if is_t2_design and n >= t2_n_min and p <= t2_p_max:
            tier = "TIER_2"
            rationale = f"Retrospective/cohort design, N={n} >= {t2_n_min}, p={p} <= {t2_p_max}."
            weight = rules_json.get("weights", {}).get("TIER_2", 0.6)
            return tier, weight, rationale

        # Check Tier 3
        t3_rules = rules_json.get("tier_3", {})
        t3_designs = [d.lower() for d in t3_rules.get("designs", ["observational case-series", "case-series"])]
        t3_n_min = t3_rules.get("n_min", 20)
        t3_n_max = t3_rules.get("n_max_exclusive", 50)
        is_t3_design = any(d in design for d in t3_designs)
        if is_t3_design and n >= t3_n_min and n < t3_n_max:
            tier = "TIER_3"
            rationale = f"Case-series design, N={n} in [{t3_n_min}, {t3_n_max})."
            weight = rules_json.get("weights", {}).get("TIER_3", 0.2)
            return tier, weight, rationale

        weight = rules_json.get("weights", {}).get("TIER_4", 0.1)
        return tier, weight, rationale

    @staticmethod
    async def evaluate_claim_tiering(
        session: AsyncSession,
        claim_id: uuid.UUID,
        ruleset_id: uuid.UUID,
    ) -> ClaimTieringResult:
        """Run the heuristic ruleset on a specific phenotype claim to assign a tier, save and return the result."""
        # 1. Fetch claim and its evidence metadata
        stmt_claim = select(PhenotypeClaim).where(PhenotypeClaim.claim_id == claim_id)
        res_claim = await session.execute(stmt_claim)
        claim = res_claim.scalar_one()

        stmt_meta = select(ClaimEvidenceMetadata).where(ClaimEvidenceMetadata.claim_id == claim_id)
        res_meta = await session.execute(stmt_meta)
        ev_meta = res_meta.scalar_one_or_none()

        # 2. Fetch ruleset
        stmt_rs = select(HeuristicRuleset).where(HeuristicRuleset.ruleset_id == ruleset_id)
        res_rs = await session.execute(stmt_rs)
        ruleset = res_rs.scalar_one()

        study_design = ev_meta.study_design if ev_meta else None
        n_subjects = ev_meta.n_subjects if ev_meta else None
        p_value = ev_meta.p_value if ev_meta else None
        causal_method = ev_meta.causal_method if ev_meta else "none"

        tier, weight, rationale = LiteratureService.calculate_provenance_tier(
            study_design=study_design,
            n_subjects=n_subjects,
            p_value=p_value,
            causal_method=causal_method,
            rules_json=ruleset.rules_json,
        )

        # 3. Create or update result
        stmt_res = select(ClaimTieringResult).where(
            and_(
                ClaimTieringResult.claim_id == claim_id,
                ClaimTieringResult.ruleset_id == ruleset_id
            )
        )
        res_res = await session.execute(stmt_res)
        tiering_res = res_res.scalar_one_or_none()

        evidence_features = {
            "study_design": study_design,
            "n_subjects": n_subjects,
            "p_value": float(p_value) if p_value is not None else None,
            "causal_method": causal_method,
        }

        if tiering_res:
            tiering_res.tier = tier
            tiering_res.scalar_weight = weight
            tiering_res.tier_rationale = rationale
            tiering_res.evidence_features = evidence_features
            tiering_res.evaluated_at = func.now()
        else:
            tiering_res = ClaimTieringResult(
                claim_id=claim_id,
                ruleset_id=ruleset_id,
                tier=tier,
                scalar_weight=weight,
                tier_rationale=rationale,
                evidence_features=evidence_features,
                evaluated_at=func.now(),
            )
            session.add(tiering_res)

        await session.commit()
        return tiering_res

    @staticmethod
    async def create_corpus_release(
        session: AsyncSession,
        name: str,
        version_label: str,
        ruleset_id: uuid.UUID,
        description: str | None = None,
        claim_ids: list[uuid.UUID] = [],
    ) -> CorpusRelease:
        """Create a new CorpusRelease snapshot of the given claims under the specified ruleset."""
        # 1. Run tiering on all claims with this ruleset
        for claim_id in claim_ids:
            await LiteratureService.evaluate_claim_tiering(session, claim_id, ruleset_id)

        # 2. Count tiers for distribution
        tier_counts = {}
        if claim_ids:
            stmt_counts = (
                select(ClaimTieringResult.tier, func.count(ClaimTieringResult.claim_id))
                .where(
                    and_(
                        ClaimTieringResult.ruleset_id == ruleset_id,
                        ClaimTieringResult.claim_id.in_(claim_ids)
                    )
                )
                .group_by(ClaimTieringResult.tier)
            )
            res_counts = await session.execute(stmt_counts)
            for tier, count in res_counts.all():
                tier_counts[tier] = count

        # 3. Create release record
        stmt_rel = select(CorpusRelease).where(
            and_(
                CorpusRelease.name == name,
                CorpusRelease.version_label == version_label
            )
        )
        res_rel = await session.execute(stmt_rel)
        release = res_rel.scalar_one_or_none()

        if release:
            release.description = description
            release.intended_claim_count = len(claim_ids)
            release.ruleset_id = ruleset_id
            release.tier_distribution = tier_counts
            release.released_at = func.now()
            release.release_status = "released"
        else:
            release = CorpusRelease(
                name=name,
                version_label=version_label,
                description=description,
                intended_claim_count=len(claim_ids),
                ruleset_id=ruleset_id,
                release_status="released",
                tier_distribution=tier_counts,
                released_at=func.now(),
            )
            session.add(release)
            await session.flush()

        # 4. Associate claims
        stmt_del = text("DELETE FROM literature.corpus_claims WHERE corpus_release_id = :rel_id")
        await session.execute(stmt_del, {"rel_id": release.corpus_release_id})

        for i, claim_id in enumerate(claim_ids):
            corpus_claim = CorpusClaim(
                corpus_release_id=release.corpus_release_id,
                claim_id=claim_id,
                included=True,
                inclusion_reason="Ingested and tiered in release.",
                ordinal=i,
            )
            session.add(corpus_claim)

        await session.commit()
        return release
