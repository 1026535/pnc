"""Fail-closed offline result-validation tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.live_validation.binding import load_assignment_binding
from tools.live_validation.evidence import (
    collect_artifact,
    write_live_evidence,
)
from tools.live_validation.validate import validate_live_evidence

from tests.unit.tools.live_validation.helpers import assignment_payload, write_assignment
from tests.unit.tools.live_validation.test_evidence import _evidence


class ValidateLiveEvidenceTests(unittest.TestCase):
    def _setup(self, tmp: Path, **overrides):
        binding = load_assignment_binding(write_assignment(tmp, assignment_payload(tmp)))
        evidence = _evidence(tmp, **overrides)
        path = write_live_evidence(evidence, tmp / "live_evidence.json")
        return binding, evidence, path

    def _report(self, tmp: Path, **overrides):
        binding, _ev, path = self._setup(tmp, **overrides)
        return validate_live_evidence(binding, path)

    def test_valid_result_passes(self):
        with tempfile.TemporaryDirectory() as raw:
            report = self._report(Path(raw))
        self.assertTrue(report.valid, [f"{f.check}: {f.detail}" for f in report.findings])
        self.assertEqual([], [f for f in report.findings if f.severity == "error"])

    def test_missing_document_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            report = validate_live_evidence(binding, tmp / "absent.json")
        self.assertFalse(report.valid)

    def test_wrong_assignment_id_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding, evidence, path = self._setup(tmp)
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["assignment_id"] = "v44-other"
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("assignment_id" in f.detail for f in report.findings))

    def test_missing_case_result_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding, _ev, path = self._setup(tmp)
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["case_results"] = []
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("v44_bank_body_menu" in f.detail for f in report.findings))

    def test_tampered_totals_fail(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["totals"]["tap"] = 99
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("totals" in f.check for f in report.findings))

    def test_wrong_case_attribution_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["attributed_dispatches"][0]["case_id"] = "v44_watchtower_body_menu"
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)

    def test_artifact_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding, _ev, path = self._setup(tmp)
            target = binding.report_root
            for doc_artifact in json.loads(path.read_text(encoding="utf-8"))["artifacts"]:
                (tmp / doc_artifact["path"]).write_bytes(b"tampered")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("sha256" in f.detail for f in report.findings))

    def test_missing_cleanup_key_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["cleanup"].pop("session_closed")
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)

    def test_frame_missing_captured_monotonic_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["attributed_dispatches"][0]["source_frame"].pop("captured_monotonic")
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("captured_monotonic" in f.detail for f in report.findings))

    def test_duplicate_physical_input_identity_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            duplicate = dict(doc["attributed_dispatches"][0])
            duplicate["event_id"] = "in-0002"
            doc["attributed_dispatches"].append(duplicate)
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(
            any("physical identity" in f.detail for f in report.findings)
        )

    def test_passed_case_without_postcondition_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["case_results"][0]["postcondition"] = None
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("postcondition" in f.detail for f in report.findings))

    def test_body_entry_event_attributed_to_the_wrong_case_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["attributed_dispatches"][0]["case_id"] = "v44_watchtower_body_menu"
            doc["attributed_dispatches"][0]["phase"] = "case"
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)

    def test_unbound_terminal_source_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _binding, _ev, path = self._setup(tmp)
            binding = load_assignment_binding(
                write_assignment(tmp, assignment_payload(tmp))
            )
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc["terminal_binding_check"]["head_matches"] = False
            path.write_text(json.dumps(doc), encoding="utf-8")
            report = validate_live_evidence(binding, path)
        self.assertFalse(report.valid)
        self.assertTrue(any("terminal" in f.check for f in report.findings))


if __name__ == "__main__":
    unittest.main()
