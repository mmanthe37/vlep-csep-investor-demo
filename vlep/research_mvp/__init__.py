"""Deterministic, synthetic-data research MVP for the VLEP project.

This package is intentionally dependency-light. It demonstrates the software
contracts behind evidence preservation, CSEP resolution, and nosology-aware
reinterpretation without accepting PHI or making clinical predictions.
"""

from vlep.research_mvp.engine import export_demo_bundle, run_pipeline
from vlep.research_mvp.fixtures import load_synthetic_case
from vlep.research_mvp.hashing import verify_ledger_chain

__all__ = [
    "export_demo_bundle",
    "load_synthetic_case",
    "run_pipeline",
    "verify_ledger_chain",
]
