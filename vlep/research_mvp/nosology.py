"""Explicit version mappings used by the public research demonstration."""

from __future__ import annotations

from typing import Final

from vlep.research_mvp.hashing import sha256_json
from vlep.research_mvp.models import MappingDecision


FRAMEWORKS: Final[dict[str, dict[str, str]]] = {
    "ILAE-2017": {
        "label": "ILAE 2017",
        "source": "https://www.ilae.org/guidelines/definition-and-classification/operational-classification-2017",
    },
    "ILAE-2025": {
        "label": "ILAE 2025",
        "source": "https://www.ilae.org/updated-classification-epileptic-seizures-2025",
    },
}


_SEIZURE_TERMS: Final[dict[str, dict[str, str]]] = {
    "SEIZ:FIA": {
        "ILAE-2017": "Focal impaired awareness seizure",
        "ILAE-2025": "Focal impaired consciousness seizure",
    }
}


def framework_term(internal_code: str, framework: str, fallback: str) -> str:
    """Return a framework-specific display term for a canonical concept."""

    if framework not in FRAMEWORKS:
        raise ValueError(f"Unsupported framework: {framework}")
    return _SEIZURE_TERMS.get(internal_code, {}).get(framework, fallback)


def map_2017_to_2025(internal_code: str) -> MappingDecision | None:
    """Return the explicit demo mapping for a supported seizure concept.

    The mapping is conditional because the 2025 consciousness classifier
    considers both awareness and responsiveness. The software therefore flags
    the result for reviewer confirmation instead of claiming a lossless map.
    """

    terms = _SEIZURE_TERMS.get(internal_code)
    if not terms:
        return None
    source_term = terms["ILAE-2017"]
    target_term = terms["ILAE-2025"]
    mapping_id = f"MAP-{sha256_json([internal_code, source_term, target_term])[:12].upper()}"
    return MappingDecision(
        mapping_id=mapping_id,
        source_framework="ILAE-2017",
        target_framework="ILAE-2025",
        internal_code=internal_code,
        source_term=source_term,
        target_term=target_term,
        status="conditional",
        rationale=(
            "ILAE 2025 replaces the awareness classifier with consciousness, "
            "defined using awareness and responsiveness; reviewer confirmation "
            "is required before accepting the reinterpretation."
        ),
    )
