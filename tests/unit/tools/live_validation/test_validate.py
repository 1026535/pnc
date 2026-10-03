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
    def test_dispatch_must_advance_source_exactly_once(self):
        with tempfile.TemporaryDirectory() as raw:
            binding, _, path = self._setup(Path(raw))
            doc = json.loads(path.read_text())
            doc["attributed_dispatches"][0]["dispatch"]["input_sequence"] += 3
            path.write_text(json.dumps(doc))
            report = validate_live_evidence(binding, path)
            self.assertTrue(any("advance its source by one" in f.detail for f in report.findings))

    def test_passed_return_requires_control_receipt_and_guarded_home(self):
        from tests.unit.tools.live_validation.test_runner import _binding, _deps, _armed_exchange
        from tools.live_validation.runner import LiveCaseRunner
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_bank_body_menu", "v44_bank_return_home")
            _, path = LiveCaseRunner(binding, _deps(tmp, {}, annotation_factory=_armed_exchange)).run()
            original = json.loads(path.read_text())
            for defect in ("missing_control", "wrong_screen", "wrong_guard"):
                with self.subTest(defect=defect):
                    doc = json.loads(json.dumps(original))
                    row = doc["case_results"][1]
                    if defect == "missing_control":
                        doc["logical_attempts"] = doc["logical_attempts"][:1]
                        doc["totals"]["logical_attempts"] = 1
                    elif defect == "wrong_screen":
                        row["postcondition"]["screen_type"] = "unknown"
                    else:
                        row["postcondition"]["guard"] = "blocked"
                    path.write_text(json.dumps(doc))
                    self.assertFalse(validate_live_evidence(binding, path).valid)

    def test_passed_control_discovery_requires_annotation_not_guarded_home(self):
        from tests.unit.tools.live_validation.test_runner import _binding, _deps, _armed_exchange
        from tools.live_validation.runner import LiveCaseRunner
        from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
        from pnc_automation.app.pnc.enums.screen_type import ScreenType
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(
                tmp,
                "v44_watchtower_body_menu",
                "v44_watchtower_selected_control_entry",
            )
            holder = {"core_kwargs": {
                "post_entry_screens": {
                    HomeCityObjectId.WATCHTOWER: ScreenType.PNC_HOME_CITY,
                },
            }}
            _, path = LiveCaseRunner(
                binding, _deps(tmp, holder, annotation_factory=_armed_exchange)
            ).run()
            original = json.loads(path.read_text())
            row = original["case_results"][1]
            self.assertEqual("control_discovery", row["purpose"])
            self.assertEqual("pnc_home_city", row["postcondition"]["screen_type"])
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )
            for defect in ("missing_annotation", "missing_control"):
                with self.subTest(defect=defect):
                    doc = json.loads(json.dumps(original))
                    if defect == "missing_annotation":
                        doc["case_results"][1]["artifacts"] = [
                            ref for ref in doc["case_results"][1]["artifacts"]
                            if ref.get("kind") != "annotation_response"
                        ]
                    else:
                        doc["logical_attempts"] = doc["logical_attempts"][:1]
                        doc["totals"]["logical_attempts"] = 1
                    path.write_text(json.dumps(doc))
                    self.assertFalse(validate_live_evidence(binding, path).valid)

    def test_passed_acceptance_route_requires_qualified_evidence(self):
        from tests.unit.tools.live_validation.test_runner import (
            _binding, _deps,
        )
        from tools.live_validation.runner import LiveCaseRunner
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = _binding(tmp, "v44_watchtower_public_open_return")
            _, path = LiveCaseRunner(binding, _deps(tmp, {})).run()
            original = json.loads(path.read_text())
            report = validate_live_evidence(binding, path)
            self.assertTrue(
                report.valid,
                [f"{f.check}: {f.detail}" for f in report.findings],
            )
            for defect in (
                "missing_route",
                "wrong_operation",
                "wrong_endpoint_screen",
                "wrong_endpoint_layout",
                "truncated_opening",
                "empty_return",
                "wrong_back_selector",
                "stale_endpoint_frame",
                "body_entry_witness",
                "wrong_intent",
                "second_attempt",
                "bad_postcondition",
            ):
                with self.subTest(defect=defect):
                    doc = json.loads(json.dumps(original))
                    row = doc["case_results"][0]
                    if defect == "missing_route":
                        row["route"] = None
                    elif defect == "wrong_operation":
                        row["route"]["operation_id"] = "other_route"
                    elif defect == "wrong_endpoint_screen":
                        row["route"]["endpoint_screen"] = "pnc_market"
                    elif defect == "wrong_endpoint_layout":
                        row["route"]["endpoint_layout_id"] = "building_market"
                    elif defect == "truncated_opening":
                        row["route"]["opening_receipt_ids"] = \
                            row["route"]["opening_receipt_ids"][:1]
                    elif defect == "empty_return":
                        row["route"]["return_receipt_ids"] = []
                    elif defect == "wrong_back_selector":
                        row["route"]["back_selector"] = \
                            "pnc_home_selected_building_upgrade_chip"
                    elif defect == "stale_endpoint_frame":
                        row["route"]["endpoint_frame"]["input_sequence"] = 0
                    elif defect == "body_entry_witness":
                        row["body_entry_event_id"] = "in-0001"
                    elif defect == "wrong_intent":
                        doc["logical_attempts"][0]["intent"] = "control"
                    elif defect == "second_attempt":
                        extra = dict(doc["logical_attempts"][0])
                        extra["attempt_id"] = "attempt-2"
                        doc["logical_attempts"].append(extra)
                        doc["totals"]["logical_attempts"] = 2
                    elif defect == "bad_postcondition":
                        row["postcondition"]["screen_type"] = "pnc_popup"
                    path.write_text(json.dumps(doc))
                    report = validate_live_evidence(binding, path)
                    self.assertFalse(report.valid, defect)

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
