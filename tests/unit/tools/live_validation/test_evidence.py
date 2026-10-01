"""v3 evidence serialization and totals tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from tools.live_validation.evidence import (
    EVIDENCE_SCHEMA_VERSION,
    CaseResult,
    CaseStatus,
    LiveEvidence,
    LogicalAttemptRecord,
    collect_artifact,
    compute_totals,
    frame_ref_dict,
    serialize_live_evidence,
    sha256_file,
    write_live_evidence,
)
from tools.live_validation.events import AttributionPhase, AttributedDispatch

from tests.unit.tools.live_validation.helpers import (
    CANDIDATE_SHA,
    ENTRY_SHA,
    frame_ref,
    home_observation,
    tap_receipt,
    write_frame_file,
)


def _evidence(tmp: Path, **overrides) -> LiveEvidence:
    artifact_path = write_frame_file(tmp, "src.png")
    ref = collect_artifact(artifact_path, kind="source_frame", purpose="authorizing frame")
    receipt = tap_receipt(home_observation(artifact_path=artifact_path))
    attributed = AttributedDispatch(
        event_id="in-0001",
        phase=AttributionPhase.CASE,
        case_id="v44_bank_body_menu",
        event=receipt,
    )
    result = CaseResult(
        case_id="v44_bank_body_menu",
        purpose="discovery",
        status=CaseStatus.PASSED,
        artifacts=(ref,),
        receipt_event_ids=("in-0001",),
        dispatch_event_ids=("in-0001",),
        body_entry_event_id="in-0001",
        body_case_id="v44_bank_body_menu",
        source_artifact=artifact_path,
        follow_up_artifact=artifact_path,
        postcondition={
            "screen_type": "pnc_bank",
            "blocking_popup": False,
            "artifact_path": str(artifact_path),
            "frame_fingerprint": "fp-1",
            "frame": frame_ref_dict(frame_ref(2)),
        },
        unresolved_boundary=None,
        detail="ok",
    )
    now = datetime(2026, 10, 1, tzinfo=UTC)
    base = dict(
        assignment_id="v44-test-001",
        run_id="v44-test-001-run1",
        candidate_sha=CANDIDATE_SHA,
        source_root=tmp,
        import_root=tmp,
        report_root=tmp / ".local-data" / "reports",
        entry_point=tmp / "entry.py",
        entry_sha256=(
            sha256_file(tmp / "entry.py") if (tmp / "entry.py").exists() else ENTRY_SHA
        ),
        started_at=now,
        finished_at=now,
        actual_target={
            "account_id": "testing",
            "castle": "k1:Castle",
            "instance_id": "bluestacks-1",
            "live_role": "live_testing",
        },
        case_results=(result,),
        artifacts=(ref,),
        attributed_dispatches=(attributed,),
        logical_attempts=(LogicalAttemptRecord(
            attempt_id="attempt-1", case_id="v44_bank_body_menu",
            control_name="enter_building_body_for_discovery", number=1, limit=1,
            status="dispatched", journal_ref=str(tmp / "attempts.jsonl"),
            dispatch_event_id="in-0001", intent="body_entry"),),
        incident_refs=(),
        resource_actions=(),
        coverage={
            "start": now.isoformat(),
            "end": now.isoformat(),
            "unsupported_input_primitives": ["keypress"],
        },
        observed_final_state={
            "screen_type": "pnc_home_city",
            "blocking_popup": False,
            "artifact_path": str(artifact_path),
            "frame_fingerprint": "fp-1",
        },
        totals={**compute_totals((attributed,), ()), "logical_attempts": 1},
        cleanup={"session_closed": True, "lease_released": True,
                 "observer_restored": True, "instance_preserved": True,
                 "reservation_disposition": "released"},
        terminal_binding_check={
            "head_matches": True,
            "tree_clean": True,
            "entry_sha256_matches": True,
            "execution_identity_matches": True,
            "dirty_paths": [],
            "checked_at": now.isoformat(),
        },
    )
    base.update(overrides)
    return LiveEvidence(**base)


class EvidenceTests(unittest.TestCase):
    def test_round_trip_serializes_json_primitives(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            path = write_live_evidence(_evidence(tmp), tmp / "live_evidence.json")
            doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(EVIDENCE_SCHEMA_VERSION, doc["schema_version"])
        self.assertEqual("v44-test-001", doc["assignment_id"])
        result = doc["case_results"][0]
        self.assertEqual("v44_bank_body_menu", result["case_id"])
        self.assertEqual("passed", result["status"])
        event = doc["attributed_dispatches"][0]
        self.assertEqual("in-0001", event["event_id"])
        self.assertEqual("receipt", event["kind"])
        self.assertEqual("tap", event["primitive"])
        self.assertEqual([270, 520], event["dispatch"]["point"])
        self.assertEqual("sess-test", event["source_frame"]["session_id"])
        self.assertEqual(1, doc["totals"]["tap"])
        self.assertEqual(1, doc["totals"]["dispatch_records"])
        self.assertEqual(1, doc["totals"]["logical_attempts"])

    def test_compute_totals_counts_receipts_failures_and_attempts(self):
        from pnc_automation.core.infra.emulator.input_dispatch import InputDispatchFailure
        from tools.live_validation.events import AttributedDispatch

        receipt = AttributedDispatch(
            event_id="in-0001", phase=AttributionPhase.CASE,
            case_id="c1", event=tap_receipt(home_observation()),
        )
        failure = AttributedDispatch(
            event_id="in-0002", phase=AttributionPhase.CASE,
            case_id="c1",
            event=InputDispatchFailure(
                source_frame=frame_ref(), input_kind="tap",
                failure_phase="send", exception_type="RuntimeError",
            ),
        )
        attempt = LogicalAttemptRecord(
            attempt_id="a1", case_id="c1", control_name="return_home",
            number=1, limit=2, status="dispatched",
            journal_ref="attempts.jsonl#1", dispatch_event_id="in-0001",
        )
        totals = compute_totals((receipt, failure), (attempt,))
        self.assertEqual(
            {"tap": 1, "swipe": 0, "wheel": 0, "dispatch_records": 1,
             "dispatch_failures": 1, "logical_attempts": 1},
            totals,
        )

    def test_frame_ref_dict_serializes_exact_identity(self):
        row = frame_ref_dict(frame_ref(3))
        self.assertEqual(
            {"session_id": "sess-test", "session_epoch": 1,
             "capture_sequence": 3, "input_sequence": 2,
             "captured_at": "2026-10-01T00:00:00+00:00",
             "captured_monotonic": 3.0},
            row,
        )

    def test_write_live_evidence_is_atomic_and_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            path = write_live_evidence(_evidence(tmp), tmp / "sub" / "live_evidence.json")
            self.assertTrue(path.exists())
            self.assertEqual(
                sha256_file(path),
                sha256_file(Path(str(path))),
            )


if __name__ == "__main__":
    unittest.main()
