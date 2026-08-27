"""Deterministic six-stage VLEP research pipeline.

The implementation is deliberately transparent. It is a reproducible software
demonstration over bundled synthetic observations, not a diagnostic model and
not evidence of clinical performance.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Final

from vlep.research_mvp.fixtures import load_synthetic_case, validate_synthetic_case
from vlep.research_mvp.hashing import (
    calculate_ledger_hash,
    sha256_json,
    verify_ledger_chain,
)
from vlep.research_mvp.models import (
    Dimension,
    EvidenceInput,
    NormalizedConcept,
    NormalizedEvidence,
    PhenotypeAssertion,
    ProfileDimension,
)
from vlep.research_mvp.nosology import FRAMEWORKS, framework_term, map_2017_to_2025


ENGINE_VERSION: Final[str] = "0.3.0-research"
SCORING_METHOD: Final[str] = "source reliability × rule confidence × temporal half-life"

_SOURCE_RELIABILITY: Final[dict[str, float]] = {
    "clinical_note": 0.88,
    "eeg": 0.98,
    "imaging": 0.98,
    "medication": 0.80,
    "patient_diary": 0.72,
}

_HALF_LIFE_DAYS: Final[dict[Dimension, float]] = {
    "seizure": 180.0,
    "etiology": 3650.0,
    "syndrome": 730.0,
    "biomarkers": 730.0,
    "comorbidity": 180.0,
    "treatment": 90.0,
}

_RULES: Final[tuple[dict[str, Any], ...]] = (
    {
        "rule": "focal-impaired-awareness-phrase",
        "needle": "impaired awareness",
        "code": "SEIZ:FIA",
        "display": "Focal impaired awareness seizure",
        "dimension": "seizure",
        "confidence": 0.96,
    },
    {
        "rule": "temporal-lobe-syndrome-phrase",
        "needle": "temporal lobe epilepsy",
        "code": "SYN:TLE",
        "display": "Temporal lobe epilepsy",
        "dimension": "syndrome",
        "confidence": 0.84,
    },
    {
        "rule": "reported-depressive-symptoms",
        "needle": "depressive symptoms",
        "code": "COMORB:DEP-REPORTED",
        "display": "Depressive symptoms (reported)",
        "dimension": "comorbidity",
        "confidence": 0.78,
    },
    {
        "rule": "left-temporal-sharp-waves",
        "needle": "left temporal sharp waves",
        "code": "BIO:EEG-LT-SHARP",
        "display": "Left temporal epileptiform activity",
        "dimension": "biomarkers",
        "confidence": 0.94,
    },
    {
        "rule": "left-mesial-temporal-sclerosis",
        "needle": "left mesial temporal sclerosis",
        "code": "BIO:MTS-LEFT",
        "display": "Left mesial temporal sclerosis",
        "dimension": "biomarkers",
        "confidence": 0.95,
    },
    {
        "rule": "structural-etiology-from-mts",
        "needle": "left mesial temporal sclerosis",
        "code": "ETIO:STRUCTURAL",
        "display": "Structural etiology",
        "dimension": "etiology",
        "confidence": 0.90,
    },
    {
        "rule": "levetiracetam-trial",
        "needle": "levetiracetam",
        "code": "TX:LEVETIRACETAM-TRIAL",
        "display": "Levetiracetam trial",
        "dimension": "treatment",
        "confidence": 0.90,
    },
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC)


def _normalize(evidence: EvidenceInput) -> NormalizedEvidence:
    lowered = evidence.raw_text.casefold()
    source_weight = _SOURCE_RELIABILITY.get(evidence.domain, 0.70)
    concepts: list[NormalizedConcept] = []
    for rule in _RULES:
        if str(rule["needle"]).casefold() not in lowered:
            continue
        confidence = round(
            min(1.0, evidence.source_confidence * source_weight * float(rule["confidence"])),
            4,
        )
        concepts.append(
            NormalizedConcept(
                internal_code=str(rule["code"]),
                display=str(rule["display"]),
                dimension=rule["dimension"],
                confidence=confidence,
                normalization_rule=str(rule["rule"]),
            )
        )
    return NormalizedEvidence(
        source=evidence,
        concepts=tuple(concepts),
        normalization_status="mapped" if concepts else "review_required",
    )


def _build_ledger(normalized: list[NormalizedEvidence]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    previous = "GENESIS"
    for seq, item in enumerate(sorted(normalized, key=lambda entry: entry.source.observed_at), start=1):
        source = item.source
        event: dict[str, Any] = {
            "seq": seq,
            "event_id": source.evidence_id,
            "observed_at": source.observed_at,
            "domain": source.domain,
            "raw_text": source.raw_text,
            "source_reference": source.source_reference,
            "source_confidence": source.source_confidence,
            "normalization_status": item.normalization_status,
            "concepts": [asdict(concept) for concept in item.concepts],
        }
        event["hash_prev"] = previous
        event["hash_self"] = calculate_ledger_hash(event, previous)
        event["integrity"] = "verified"
        ledger.append(event)
        previous = event["hash_self"]
    return ledger


def _score_concept(
    concept: dict[str, Any],
    observed_at: str,
    as_of_time: str,
) -> float:
    dimension: Dimension = concept["dimension"]
    age_days = max(0.0, (_parse_utc(as_of_time) - _parse_utc(observed_at)).total_seconds() / 86400)
    recency = math.exp(-math.log(2) * age_days / _HALF_LIFE_DAYS[dimension])
    return round(float(concept["confidence"]) * (0.85 + 0.15 * recency), 4)


def _assert(ledger: list[dict[str, Any]], as_of_time: str) -> list[PhenotypeAssertion]:
    grouped: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)
    for event in ledger:
        for concept in event["concepts"]:
            score = _score_concept(concept, event["observed_at"], as_of_time)
            key = (concept["dimension"], concept["internal_code"], concept["display"])
            grouped[key].append((event["event_id"], score))

    assertions: list[PhenotypeAssertion] = []
    for (dimension, internal_code, label), support in sorted(grouped.items()):
        event_ids = tuple(sorted(event_id for event_id, _ in support))
        scores = [score for _, score in support]
        demo_score = round(sum(scores) / len(scores), 4)
        assertion_id = f"AST-{sha256_json([dimension, internal_code, event_ids])[:12].upper()}"
        assertions.append(
            PhenotypeAssertion(
                assertion_id=assertion_id,
                dimension=dimension,
                internal_code=internal_code,
                label=label,
                demo_score=demo_score,
                supporting_event_ids=event_ids,
                scoring_method=SCORING_METHOD,
                review_required=dimension == "syndrome",
            )
        )
    return assertions


def _resolve_profile(
    assertions: list[PhenotypeAssertion],
    framework: str,
    case_id: str,
    as_of_time: str,
    ledger_head: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_dimension: dict[Dimension, list[PhenotypeAssertion]] = defaultdict(list)
    for assertion in assertions:
        by_dimension[assertion.dimension].append(assertion)

    dimensions: list[ProfileDimension] = []
    mappings: list[dict[str, Any]] = []
    order: tuple[Dimension, ...] = (
        "seizure",
        "etiology",
        "syndrome",
        "biomarkers",
        "comorbidity",
        "treatment",
    )
    for dimension in order:
        candidates = sorted(
            by_dimension.get(dimension, []),
            key=lambda assertion: (-assertion.demo_score, assertion.internal_code),
        )
        if not candidates:
            dimensions.append(
                ProfileDimension(
                    dimension=dimension,
                    label="Insufficient synthetic evidence",
                    internal_codes=(),
                    demo_score=0.0,
                    supporting_event_ids=(),
                    review_required=True,
                )
            )
            continue

        if dimension == "biomarkers":
            selected = candidates
            label = "; ".join(candidate.label for candidate in selected)
            score = round(sum(candidate.demo_score for candidate in selected) / len(selected), 4)
        else:
            selected = [candidates[0]]
            label = candidates[0].label
            score = candidates[0].demo_score

        review_required = any(candidate.review_required for candidate in selected)
        if dimension == "seizure":
            label = framework_term(selected[0].internal_code, framework, label)
            if framework == "ILAE-2025":
                decision = map_2017_to_2025(selected[0].internal_code)
                if decision:
                    mappings.append(asdict(decision))
                    review_required = decision.status != "exact"

        event_ids = tuple(
            sorted({event_id for candidate in selected for event_id in candidate.supporting_event_ids})
        )
        dimensions.append(
            ProfileDimension(
                dimension=dimension,
                label=label,
                internal_codes=tuple(candidate.internal_code for candidate in selected),
                demo_score=score,
                supporting_event_ids=event_ids,
                review_required=review_required,
            )
        )

    profile_body = {
        "case_id": case_id,
        "as_of_time": as_of_time,
        "framework": framework,
        "framework_label": FRAMEWORKS[framework]["label"],
        "ledger_head": ledger_head,
        "dimensions": [asdict(item) for item in dimensions],
        "mappings": mappings,
        "clinical_use": False,
    }
    profile_hash = sha256_json(profile_body)
    resolved_count = sum(not item.review_required for item in dimensions)
    review_count = len(dimensions) - resolved_count
    profile = {
        **profile_body,
        "profile_id": f"CSEP-{profile_hash[:12].upper()}",
        "profile_hash": profile_hash,
        "resolution_status": {
            "resolved": resolved_count,
            "review_required": review_count,
        },
        "integrity": "verified",
        "score_notice": "Synthetic demo scores; not calibrated clinical probabilities.",
    }
    return profile, mappings


def run_pipeline(case: dict[str, Any], framework: str) -> dict[str, Any]:
    """Run all six deterministic stages for a synthetic case."""

    validate_synthetic_case(case)
    if framework not in FRAMEWORKS:
        raise ValueError(f"Unsupported framework: {framework}")

    evidence: list[EvidenceInput] = case["evidence"]
    normalized = [_normalize(item) for item in evidence]
    ledger = _build_ledger(normalized)
    if not verify_ledger_chain(ledger):
        raise RuntimeError("Evidence ledger integrity verification failed.")
    assertions = _assert(ledger, case["as_of_time"])
    ledger_head = ledger[-1]["hash_self"] if ledger else "GENESIS"
    profile, mappings = _resolve_profile(
        assertions,
        framework,
        case["case_id"],
        case["as_of_time"],
        ledger_head,
    )
    source_hash = sha256_json([asdict(item) for item in evidence])
    run_seed = sha256_json([case["case_id"], case["as_of_time"], source_hash])
    run_hash = sha256_json(
        {
            "engine": ENGINE_VERSION,
            "seed": run_seed,
            "framework": framework,
            "ledger_head": ledger_head,
            "profile_hash": profile["profile_hash"],
        }
    )

    stages = [
        {"number": 1, "name": "Ingest", "status": "complete", "output": f"{len(evidence)} synthetic observations"},
        {"number": 2, "name": "Normalize", "status": "complete", "output": f"{sum(len(item.concepts) for item in normalized)} canonical concepts"},
        {"number": 3, "name": "Ledger", "status": "complete", "output": f"{len(ledger)} hash-chained events"},
        {"number": 4, "name": "Assert", "status": "complete", "output": f"{len(assertions)} evidence-linked assertions"},
        {"number": 5, "name": "Model", "status": "complete", "output": "Deterministic research scoring"},
        {"number": 6, "name": "Resolve", "status": "complete", "output": f"CSEP under {FRAMEWORKS[framework]['label']}"},
    ]

    return {
        "run_id": f"RUN-{run_hash[:16].upper()}",
        "run_hash": run_hash,
        "deterministic_seed": run_seed,
        "engine_version": ENGINE_VERSION,
        "case_id": case["case_id"],
        "as_of_time": case["as_of_time"],
        "framework": framework,
        "fixture_type": "synthetic",
        "stages": stages,
        "ledger": ledger,
        "ledger_verified": True,
        "ledger_head": ledger_head,
        "assertions": [asdict(assertion) for assertion in assertions],
        "profile": profile,
        "mappings": mappings,
        "limitations": [
            "Synthetic fixture only; no PHI is accepted or processed.",
            "Scores are deterministic demo outputs, not calibrated clinical probabilities.",
            "Terminology reinterpretation can require expert review and is not assumed lossless.",
            "This run does not establish diagnostic validity, clinical utility, or patient safety.",
        ],
    }


def export_demo_bundle() -> dict[str, Any]:
    """Build the complete public artifact consumed by the investor web app."""

    case = load_synthetic_case()
    runs = {framework: run_pipeline(case, framework) for framework in FRAMEWORKS}
    public_case = {
        key: value
        for key, value in case.items()
        if key != "evidence"
    }
    public_case["evidence"] = [asdict(item) for item in case["evidence"]]
    bundle = {
        "schema_version": "1.0.0",
        "product": "VLEP Research MVP",
        "generated_from": "bundled deterministic synthetic fixture",
        "case": public_case,
        "frameworks": FRAMEWORKS,
        "runs": runs,
        "sources": [
            {
                "title": "ILAE Operational Classification of Seizure Types (2017)",
                "url": FRAMEWORKS["ILAE-2017"]["source"],
            },
            {
                "title": "ILAE Updated Classification of Epileptic Seizures (2025)",
                "url": FRAMEWORKS["ILAE-2025"]["source"],
            },
        ],
        "research_only": True,
    }
    bundle["bundle_hash"] = sha256_json(bundle)
    return bundle
