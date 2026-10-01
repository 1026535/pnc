"""Assignment-binding parse and static-gate tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.live_validation.binding import (
    AssignmentBindingError,
    binding_static_findings,
    load_assignment_binding,
)
from tools.live_validation.cases import frozen_case_ids

from tests.unit.tools.live_validation.helpers import (
    CANDIDATE_SHA,
    ENTRY_SHA,
    assignment_payload,
    write_assignment,
)


class AssignmentBindingTests(unittest.TestCase):
    def _load(self, payload: dict, tmp: Path):
        return load_assignment_binding(write_assignment(tmp, payload))

    def test_valid_assignment_binds_exactly(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding = self._load(assignment_payload(tmp), tmp)
        self.assertEqual("v44-test-001", binding.assignment_id)
        self.assertEqual(CANDIDATE_SHA, binding.candidate_sha)
        self.assertEqual(("v44_bank_body_menu",), tuple(s.case_id for s in binding.selected_cases))
        self.assertEqual(
            [],
            binding_static_findings(binding, case_ids=frozen_case_ids()),
        )

    def test_rejects_wrong_schema_version(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["schema_version"] = 2
            with self.assertRaises(AssignmentBindingError):
                self._load(payload, tmp)

    def test_rejects_duplicate_case_selection(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(
                tmp, case_ids=("v44_bank_body_menu", "v44_bank_body_menu")
            )
            with self.assertRaisesRegex(AssignmentBindingError, "must not repeat"):
                self._load(payload, tmp)

    def test_rejects_malformed_candidate_sha(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["candidate_sha"] = "nothex"
            with self.assertRaisesRegex(AssignmentBindingError, "candidate_sha"):
                self._load(payload, tmp)

    def test_rejects_malformed_entry_sha(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp, entry_sha256="zzz")
            with self.assertRaisesRegex(AssignmentBindingError, "entry_sha256"):
                self._load(payload, tmp)

    def test_rejects_unknown_top_level_field(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["developer_notes"] = "not part of the release"
            with self.assertRaisesRegex(AssignmentBindingError, "unknown fields"):
                self._load(payload, tmp)

    def test_rejects_unsafe_run_id_token(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["run_id"] = "../escape"
            with self.assertRaisesRegex(AssignmentBindingError, "run_id"):
                self._load(payload, tmp)

    def test_rejects_non_boolean_read_only(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["read_only"] = "yes"
            with self.assertRaisesRegex(AssignmentBindingError, "read_only"):
                self._load(payload, tmp)

    def test_rejects_unknown_cleanup_key(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(
                tmp, expected_cleanup={"session_closed": True, "surprise": False}
            )
            with self.assertRaisesRegex(AssignmentBindingError, "unknown key"):
                self._load(payload, tmp)

    def test_static_findings_flag_unknown_case_and_wrong_role(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp, case_ids=("v44_nope",))
            payload["target_role"] = "routine_automation"
            binding = self._load(payload, tmp)
            findings = binding_static_findings(binding, case_ids=frozen_case_ids())
        self.assertTrue(any("v44_nope" in f for f in findings))
        self.assertTrue(any("live_testing" in f for f in findings))

    def test_static_findings_flag_relative_entry_point(self):
        import dataclasses

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            binding = self._load(payload, tmp)
            relative = dataclasses.replace(binding, entry_point=Path("tools/x.py"))
            self.assertEqual(
                ["entry_point must be absolute."],
                binding_static_findings(relative, case_ids=frozen_case_ids()),
            )

    def test_example_assignment_sha_constants(self):
        self.assertEqual(64, len(ENTRY_SHA))


if __name__ == "__main__":
    unittest.main()
