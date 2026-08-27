"""Typed domain records for the VLEP research MVP."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


Dimension = Literal[
    "seizure",
    "etiology",
    "syndrome",
    "biomarkers",
    "comorbidity",
    "treatment",
]


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    """One immutable observation supplied to the synthetic pipeline."""

    evidence_id: str
    observed_at: str
    domain: str
    raw_text: str
    source_reference: str
    source_confidence: float


@dataclass(frozen=True, slots=True)
class NormalizedConcept:
    """A canonical concept extracted by deterministic demo rules."""

    internal_code: str
    display: str
    dimension: Dimension
    confidence: float
    normalization_rule: str


@dataclass(frozen=True, slots=True)
class NormalizedEvidence:
    """Evidence plus the canonical concepts derived from it."""

    source: EvidenceInput
    concepts: tuple[NormalizedConcept, ...]
    normalization_status: Literal["mapped", "review_required"]


@dataclass(frozen=True, slots=True)
class PhenotypeAssertion:
    """An evidence-linked research assertion for one phenotype dimension."""

    assertion_id: str
    dimension: Dimension
    internal_code: str
    label: str
    demo_score: float
    supporting_event_ids: tuple[str, ...]
    scoring_method: str
    review_required: bool


@dataclass(frozen=True, slots=True)
class MappingDecision:
    """Auditable terminology mapping between nosology releases."""

    mapping_id: str
    source_framework: str
    target_framework: str
    internal_code: str
    source_term: str
    target_term: str
    status: Literal["exact", "conditional", "manual_review"]
    rationale: str
    original_evidence_preserved: bool = True


@dataclass(frozen=True, slots=True)
class ProfileDimension:
    """Resolved value for one of the six CSEP dimensions."""

    dimension: Dimension
    label: str
    internal_codes: tuple[str, ...]
    demo_score: float
    supporting_event_ids: tuple[str, ...]
    review_required: bool


def record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a typed record to a JSON-ready dictionary."""

    return asdict(record)
