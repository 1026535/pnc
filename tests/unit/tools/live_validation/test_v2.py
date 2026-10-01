"""Historical v2 evidence inspection tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.live_validation.v2 import inspect_report, inspect_v2_evidence


def _v2_doc() -> dict:
    return {
        "schema_version": 2,
        "assignment_id": "live030",
        "candidate_sha": "d6a877ecc38538714385d27e58be0573f991bf8a",
        "captured_at": "datetime.datetime(2026, 9, 30, 12, 0)",
        "cases": [
            {"case_id": "live030_open_bank", "executed": True, "status": "observed"},
            {"case_id": "live030_return_home", "executed": False, "status": "skipped"},
        ],
        "dispatches": [
            {"point": [270, 520], "captured_at": "datetime(...)"},
        ],
        "totals": {"tap": 1},
        "summary": "free-form historical text",
    }


class InspectV2Tests(unittest.TestCase):
    def test_structural_inspection_reports_shape_and_warnings(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "evidence.json"
            path.write_text(json.dumps(_v2_doc()), encoding="utf-8")
            inspection = inspect_v2_evidence(path)
            report = inspect_report(inspection)
        self.assertEqual(2, inspection.schema_version)
        self.assertEqual("live030", inspection.assignment_id)
        self.assertEqual(
            ("live030_open_bank", "live030_return_home"),
            inspection.case_ids,
        )
        self.assertEqual({"observed": 1, "skipped": 1}, inspection.statuses)
        self.assertEqual(1, inspection.dispatch_count)
        self.assertIn("point", inspection.dispatch_repr_fields)
        self.assertEqual({"tap": 1}, inspection.physical_totals)
        # v2 fields are reported, never converted into trusted proof.
        self.assertTrue(any("not trusted" in w for w in inspection.warnings))
        self.assertTrue(any("self-reported" in w for w in inspection.warnings))
        self.assertEqual(2, report["case_count"])
        self.assertEqual(1, report["dispatch_count"])

    def test_non_object_document_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "evidence.json"
            path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_v2_evidence(path)


if __name__ == "__main__":
    unittest.main()
