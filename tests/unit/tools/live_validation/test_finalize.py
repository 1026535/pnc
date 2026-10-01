"""Typed post-run finalization overlay tests (QR8)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tools.live_validation.evidence import sha256_file, write_live_evidence
from tools.live_validation.finalize import (
    FINALIZATION_SCHEMA_VERSION,
    FinalizationError,
    finalize_run,
    parse_annotations,
    write_run_finalization,
)

from tests.unit.tools.live_validation.test_evidence import _evidence


class FinalizationOverlayTests(unittest.TestCase):
    def _run_dir(self, tmp: Path) -> Path:
        run_dir = tmp / "run-1"
        write_live_evidence(_evidence(tmp), run_dir / "live_evidence.json")
        return run_dir

    def test_seeded_overlay_is_pending_and_does_not_touch_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            evidence_path = run_dir / "live_evidence.json"
            before = sha256_file(evidence_path)
            finalization = finalize_run(run_dir, annotations_path=None, now=datetime.now(UTC))
            after = sha256_file(evidence_path)
            doc = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
        self.assertEqual(before, after)
        self.assertEqual("pending_tester_review", finalization.review_state)
        self.assertEqual(doc["evidence_sha256"], before)
        self.assertEqual(FINALIZATION_SCHEMA_VERSION, doc["schema_version"])
        self.assertEqual([], doc["incident_annotations"])
        self.assertEqual([], doc["resource_actions"])

    def test_annotations_flip_review_state_and_reseal_the_evidence_hash(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            record = tmp / "live-test-failures" / "incidents" / "INC-1" / "record.json"
            record.parent.mkdir(parents=True)
            record.write_text("{}", encoding="utf-8")
            annotations = tmp / "annotations.json"
            annotations.write_text(json.dumps({
                "schema_version": FINALIZATION_SCHEMA_VERSION,
                "incident_annotations": [
                    {
                        "incident_id": "INC-1",
                        "record_path": str(record),
                        "case_ids": ["v44_bank_body_menu"],
                        "boundary": "qualified_body_entry",
                        "note": "recorded during run",
                    }
                ],
                "resource_actions": [
                    {
                        "action_id": "act-1",
                        "description": "none",
                        "resource_kind": "gems",
                        "quantity": 0,
                        "dispatch_event_id": "in-0001",
                    }
                ],
            }), encoding="utf-8")
            finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
            doc = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
        self.assertEqual("annotated", doc["review_state"])
        self.assertEqual("INC-1", doc["incident_annotations"][0]["incident_id"])
        self.assertEqual("in-0001", doc["resource_actions"][0]["dispatch_event_id"])

    def test_finalize_requires_existing_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(FinalizationError):
                finalize_run(Path(raw), annotations_path=None, now=datetime.now(UTC))

    def test_unknown_annotation_field_is_rejected(self):
        with self.assertRaisesRegex(FinalizationError, "unknown fields"):
            parse_annotations({"schema_version": 1, "surprise": []})

    def test_relative_incident_record_path_is_rejected(self):
        with self.assertRaisesRegex(FinalizationError, "record_path must be absolute"):
            parse_annotations({
                "schema_version": 1,
                "incident_annotations": [
                    {
                        "incident_id": "INC-1",
                        "record_path": "relative/record.json",
                        "case_ids": [],
                        "boundary": "",
                        "note": "",
                    }
                ],
            })

    def test_write_run_finalization_preserves_seeded_annotations(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            now = datetime.now(UTC)
            first = write_run_finalization(
                run_dir / "finalization.json",
                evidence_path=run_dir / "live_evidence.json",
                run_id="run-1",
                assignment_id="v44-test-001",
                now=now,
            )
            doc = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
        self.assertEqual("pending_tester_review", first.review_state)
        self.assertEqual("run-1", doc["run_id"])


if __name__ == "__main__":
    unittest.main()
