"""Offline CLI checks for the released-case tool surface."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from tools.live_validation.cases import frozen_case_ids
from tools.live_validation.evidence import write_live_evidence
from tools.run_v44_live_cases import main as cli_main

from tests.unit.tools.live_validation.helpers import (
    assignment_payload,
    write_assignment,
)
from tests.unit.tools.live_validation.test_evidence import _evidence

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENTRY = _REPO_ROOT / "tools" / "run_v44_live_cases.py"


def _write_evidence_file(tmp: Path) -> Path:
    path = tmp / "reports" / "v44-test-001-run1" / "live_evidence.json"
    return write_live_evidence(_evidence(tmp), path)


class RunV44LiveCasesCliTests(unittest.TestCase):
    def test_run_reports_invalid_evidence_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            payload = assignment_payload(tmp)
            payload["config_path"] = str(tmp / "accounts.yaml")
            assignment = write_assignment(tmp, payload)
            evidence = _evidence(tmp)
            path = write_live_evidence(evidence, tmp / "live_evidence.json")
            with patch("tools.run_v44_live_cases.LiveCaseRunner") as runner, patch(
                "tools.run_v44_live_cases.validate_live_evidence"
            ) as validate:
                runner.return_value.run.return_value = evidence, path
                validate.return_value = SimpleNamespace(valid=False, findings=[])
                self.assertEqual(1, cli_main(("run", "--assignment", str(assignment))))
                validate.assert_called_once()

    def test_direct_launch_help(self):
        """QR1: the tracked entry boots standalone and lists its subcommands."""
        completed = subprocess.run(
            [sys.executable, str(_ENTRY), "--help"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        for command in ("run", "validate", "inspect-v2", "finalize", "example-assignment"):
            self.assertIn(command, completed.stdout)

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

    def test_finalize_seeds_pending_review_overlay(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            evidence_path = _write_evidence_file(tmp)
            code = cli_main(("finalize", "--run-dir", str(evidence_path.parent)))
            overlay = json.loads(
                (evidence_path.parent / "finalization.json").read_text(encoding="utf-8")
            )
        self.assertEqual(0, code)
        self.assertEqual("pending_tester_review", overlay["review_state"])

    def test_finalize_refuses_when_no_evidence_exists(self):
        with tempfile.TemporaryDirectory() as raw:
            code = cli_main(("finalize", "--run-dir", raw))
        self.assertEqual(2, code)


if __name__ == "__main__":
    unittest.main()
