"""Tests for the public, synthetic-data VLEP research core."""

from __future__ import annotations

import copy
import unittest

from vlep.research_mvp import (
    export_demo_bundle,
    load_synthetic_case,
    run_pipeline,
    verify_ledger_chain,
)


class ResearchMvpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = load_synthetic_case()

    def test_pipeline_is_deterministic(self) -> None:
        first = run_pipeline(self.case, "ILAE-2025")
        second = run_pipeline(self.case, "ILAE-2025")
        self.assertEqual(first, second)

    def test_ledger_chain_detects_tampering(self) -> None:
        run = run_pipeline(self.case, "ILAE-2017")
        self.assertTrue(verify_ledger_chain(run["ledger"]))
        tampered = copy.deepcopy(run["ledger"])
        tampered[1]["raw_text"] = "tampered text"
        self.assertFalse(verify_ledger_chain(tampered))

    def test_profile_contains_all_six_dimensions(self) -> None:
        run = run_pipeline(self.case, "ILAE-2017")
        dimensions = {item["dimension"] for item in run["profile"]["dimensions"]}
        self.assertEqual(
            dimensions,
            {"seizure", "etiology", "syndrome", "biomarkers", "comorbidity", "treatment"},
        )

    def test_framework_reinterpretation_preserves_ledger(self) -> None:
        source = run_pipeline(self.case, "ILAE-2017")
        target = run_pipeline(self.case, "ILAE-2025")
        self.assertEqual(source["ledger"], target["ledger"])
        self.assertEqual(source["ledger_head"], target["ledger_head"])
        self.assertNotEqual(source["profile"]["profile_hash"], target["profile"]["profile_hash"])

    def test_2025_mapping_is_conditional_and_reviewable(self) -> None:
        target = run_pipeline(self.case, "ILAE-2025")
        self.assertEqual(len(target["mappings"]), 1)
        mapping = target["mappings"][0]
        self.assertEqual(mapping["status"], "conditional")
        self.assertTrue(mapping["original_evidence_preserved"])
        self.assertIn("consciousness", mapping["target_term"].lower())

    def test_public_bundle_is_synthetic_and_reproducible(self) -> None:
        first = export_demo_bundle()
        second = export_demo_bundle()
        self.assertEqual(first, second)
        self.assertTrue(first["research_only"])
        self.assertEqual(first["case"]["fixture_type"], "synthetic")
        self.assertTrue(first["case"]["case_id"].startswith("SYN-"))

    def test_non_synthetic_payload_is_rejected(self) -> None:
        invalid = dict(self.case)
        invalid["fixture_type"] = "clinical"
        with self.assertRaises(ValueError):
            run_pipeline(invalid, "ILAE-2017")

    def test_identifier_shaped_fields_are_rejected_at_pipeline_boundary(self) -> None:
        invalid = dict(self.case)
        invalid["metadata"] = {"medical-record-number": "SYNTHETIC-BUT-DISALLOWED"}
        with self.assertRaises(ValueError):
            run_pipeline(invalid, "ILAE-2017")


if __name__ == "__main__":
    unittest.main()
