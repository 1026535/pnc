"""Offline CLI checks for the released-case tool surface."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.live_validation.cases import frozen_case_ids
from tools.live_validation.evidence import write_live_evidence
from tools.run_v44_live_cases import main as cli_main

from tests.unit.tools.live_validation.helpers import (
    assignment_payload,
    write_assignment,
)
from tests.unit.tools.live_validation.test_evidence import _evidence


def _write_evidence_file(tmp: Path) -> Path:
    path = tmp / "reports" / "v44-test-001-run1" / "live_evidence.json"
    return write_live_evidence(_evidence(tmp), path)


class RunV44LiveCasesCliTests(unittest.TestCase):
    def test_example_assignment_lists_every_frozen_case(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "assignment.json"
            self.assertEqual(0, cli_main(("example-assignment", "--output", str(path))))
            example = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(3, example["schema_version"])
        self.assertEqual("live_testing", example["target_role"])
        self.assertEqual(
            frozen_case_ids(),
            {selection["case_id"] for selection in example["selected_cases"]},
        )

    def test_refused_assignment_returns_exit_two(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            bad = dict(assignment_payload(tmp), schema_version=2)
            path = write_assignment(tmp, bad)
            code = cli_main(
                (
                    "validate",
                    "--assignment",
                    str(path),
                    "--result",
                    str(tmp / "anything.json"),
                )
            )
        self.assertEqual(2, code)

    def test_validate_happy_path_over_a_written_empty_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            binding_path = write_assignment(tmp, assignment_payload(tmp))
            evidence_path = _write_evidence_file(tmp)
            code = cli_main(
                (
                    "validate",
                    "--assignment",
                    str(binding_path),
                    "--result",
                    str(evidence_path),
                )
            )
        self.assertEqual(0, code)


if __name__ == "__main__":
    unittest.main()
