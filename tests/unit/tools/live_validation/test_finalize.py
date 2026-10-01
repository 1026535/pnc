"""Typed post-run finalization overlay tests (QR8)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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

    def _annotations(self, run_dir: Path, **overrides) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": FINALIZATION_SCHEMA_VERSION,
            "run_id": "v44-test-001-run1",
            "assignment_id": "v44-test-001",
            "evidence_sha256": sha256_file(run_dir / "live_evidence.json"),
            "review_complete": True,
            "incident_annotations": [],
            "resource_actions": [],
        }
        payload.update(overrides)
        return payload

    def _write_annotations(self, tmp: Path, payload: dict[str, object]) -> Path:
        path = tmp / "annotations.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _publish_incident(self, tmp: Path, *, incident_id: str = "INC-1") -> Path:
        folder = tmp / ".local-data" / "reports" / "live-test-failures" / "incidents" / incident_id
        folder.mkdir(parents=True)
        (folder / "README.md").write_text("Published incident\n", encoding="utf-8")
        (folder / "record.json").write_text(json.dumps({
            "id": incident_id,
            "kind": "incident",
            "run_id": "v44-test-001-run1",
            "case_ids": ["v44_bank_body_menu"],
            "record_path": f"incidents/{incident_id}/README.md",
        }), encoding="utf-8")
        return folder / "record.json"

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
        self.assertEqual("v44-test-001-run1", doc["run_id"])
        self.assertEqual("v44-test-001", doc["assignment_id"])
        self.assertEqual(FINALIZATION_SCHEMA_VERSION, doc["schema_version"])
        self.assertEqual([], doc["incident_annotations"])
        self.assertEqual([], doc["resource_actions"])

    def test_published_incident_and_known_dispatch_complete_review(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            record = self._publish_incident(tmp)
            annotations = self._write_annotations(tmp, self._annotations(run_dir,
                incident_annotations=[
                    {
                        "incident_id": "INC-1",
                        "record_path": str(record),
                        "case_ids": ["v44_bank_body_menu"],
                        "boundary": "qualified_body_entry",
                        "note": "recorded during run",
                    }
                ],
                resource_actions=[
                    {
                        "action_id": "act-1",
                        "description": "none",
                        "resource_kind": "gems",
                        "quantity": 0,
                        "dispatch_event_id": "in-0001",
                    }
                ],
            ))
            with patch("tools.live_validation.finalize._report_repository_root", return_value=tmp):
                finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
            doc = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
        self.assertEqual("annotated", doc["review_state"])
        self.assertEqual("INC-1", doc["incident_annotations"][0]["incident_id"])
        self.assertEqual("in-0001", doc["resource_actions"][0]["dispatch_event_id"])

    def test_empty_completed_review_survives_finalization_without_annotations(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            annotations = self._write_annotations(tmp, self._annotations(run_dir))
            first = finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
            before = (run_dir / "finalization.json").read_bytes()
            second = finalize_run(run_dir, annotations_path=None, now=datetime.now(UTC))
            after = (run_dir / "finalization.json").read_bytes()
        self.assertEqual("annotated", first.review_state)
        self.assertEqual("annotated", second.review_state)
        self.assertEqual(before, after)

    def test_wrong_evidence_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            annotations = self._write_annotations(
                tmp, self._annotations(run_dir, evidence_sha256="0" * 64)
            )
            with self.assertRaisesRegex(FinalizationError, "evidence_sha256"):
                finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
            self.assertFalse((run_dir / "finalization.json").exists())

    def test_unknown_case_and_dispatch_references_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            record = self._publish_incident(tmp)
            incident = {
                "incident_id": "INC-1", "record_path": str(record),
                "case_ids": ["unknown"], "boundary": "setup", "note": "",
            }
            action = {
                "action_id": "act-1", "description": "", "resource_kind": "gems",
                "quantity": 1, "dispatch_event_id": "unknown",
            }
            for field, row, error in (
                ("incident_annotations", incident, "unknown case_id"),
                ("resource_actions", action, "unknown dispatch_event_id"),
            ):
                with self.subTest(field=field):
                    annotations = self._write_annotations(
                        tmp, self._annotations(run_dir, **{field: [row]})
                    )
                    with self.assertRaisesRegex(FinalizationError, error):
                        finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))

    def test_unpublished_or_mismatched_incident_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            record = self._publish_incident(tmp)
            incident = {
                "incident_id": "INC-1", "record_path": str(record),
                "case_ids": ["v44_bank_body_menu"], "boundary": "setup", "note": "",
            }
            annotations = self._write_annotations(
                tmp, self._annotations(run_dir, incident_annotations=[incident])
            )
            with patch("tools.live_validation.finalize._report_repository_root", return_value=tmp):
                outside = dict(incident, record_path=str(tmp / "other" / "record.json"))
                self._write_annotations(
                    tmp, self._annotations(run_dir, incident_annotations=[outside])
                )
                with self.assertRaisesRegex(FinalizationError, "outside the primary"):
                    finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
                self._write_annotations(
                    tmp, self._annotations(run_dir, incident_annotations=[incident])
                )
                (record.parent / "README.md").unlink()
                with self.assertRaisesRegex(FinalizationError, "README.md is not published"):
                    finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))
                (record.parent / "README.md").write_text("Published\n", encoding="utf-8")
                record.write_text(json.dumps({
                    "id": "INC-wrong", "kind": "incident",
                    "run_id": "v44-test-001-run1",
                    "case_ids": ["v44_bank_body_menu"],
                    "record_path": "incidents/INC-1/README.md",
                }), encoding="utf-8")
                with self.assertRaisesRegex(FinalizationError, "incident_id does not match"):
                    finalize_run(run_dir, annotations_path=annotations, now=datetime.now(UTC))

    def test_finalize_requires_existing_evidence(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(FinalizationError):
                finalize_run(Path(raw), annotations_path=None, now=datetime.now(UTC))

    def test_unknown_annotation_field_is_rejected(self):
        with self.assertRaisesRegex(FinalizationError, "unknown fields"):
            parse_annotations({"schema_version": 1, "surprise": []})

    def test_review_complete_marker_is_required(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            with self.assertRaisesRegex(FinalizationError, "review_complete"):
                parse_annotations(self._annotations(run_dir, review_complete=False))

    def test_relative_incident_record_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            with self.assertRaisesRegex(FinalizationError, "record_path must be absolute"):
                parse_annotations(self._annotations(run_dir,
                incident_annotations=[
                    {
                        "incident_id": "INC-1",
                        "record_path": "relative/record.json",
                        "case_ids": [],
                        "boundary": "",
                        "note": "",
                    }
                ],
                ))

    def test_write_run_finalization_preserves_seeded_annotations(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            run_dir = self._run_dir(tmp)
            now = datetime.now(UTC)
            first = write_run_finalization(
                run_dir / "finalization.json",
                evidence_path=run_dir / "live_evidence.json",
                run_id="v44-test-001-run1",
                assignment_id="v44-test-001",
                now=now,
            )
            doc = json.loads((run_dir / "finalization.json").read_text(encoding="utf-8"))
        self.assertEqual("pending_tester_review", first.review_state)
        self.assertEqual("v44-test-001-run1", doc["run_id"])


if __name__ == "__main__":
    unittest.main()
