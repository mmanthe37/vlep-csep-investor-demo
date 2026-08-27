"""Loader and guardrails for the bundled synthetic case."""

from __future__ import annotations

import json
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any

from vlep.research_mvp.models import EvidenceInput


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FIXTURE = _PROJECT_ROOT / "data" / "synthetic_case_v1.json"
_PROHIBITED_IDENTIFIER_KEYS = {
    "address",
    "date_of_birth",
    "dob",
    "email",
    "first_name",
    "full_name",
    "last_name",
    "medical_record_number",
    "mrn",
    "name",
    "phone",
    "ssn",
}


def _find_prohibited_key(value: Any, path: str = "case") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().casefold().replace("-", "_").replace(" ", "_")
            if normalized in _PROHIBITED_IDENTIFIER_KEYS:
                return f"{path}.{key}"
            match = _find_prohibited_key(child, f"{path}.{key}")
            if match:
                return match
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            match = _find_prohibited_key(child, f"{path}[{index}]")
            if match:
                return match
    elif is_dataclass(value):
        return None
    return None


def validate_synthetic_case(payload: dict[str, Any]) -> None:
    """Enforce the minimum public-demo data contract at every entry point."""

    if payload.get("fixture_type") != "synthetic":
        raise ValueError("Research MVP accepts synthetic fixtures only.")
    if not str(payload.get("case_id", "")).startswith("SYN-"):
        raise ValueError("Synthetic case IDs must start with 'SYN-'.")
    prohibited_path = _find_prohibited_key(payload)
    if prohibited_path:
        raise ValueError(f"Direct identifier field is prohibited: {prohibited_path}.")
    evidence = payload.get("evidence")
    if not isinstance(evidence, (list, tuple)) or not evidence:
        raise ValueError("Synthetic fixtures must contain at least one evidence event.")


def load_synthetic_case(path: Path | None = None) -> dict[str, Any]:
    """Load the public demo fixture and enforce its no-PHI contract."""

    fixture_path = path or _DEFAULT_FIXTURE
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    validate_synthetic_case(payload)
    payload["evidence"] = [EvidenceInput(**item) for item in payload["evidence"]]
    return payload
