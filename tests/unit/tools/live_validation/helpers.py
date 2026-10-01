"""Shared fakes for the offline live-validation runner tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

from tools.live_validation.binding import SCHEMA_VERSION
from tools.live_validation.evidence import sha256_file

CANDIDATE_SHA = "d6a877ecc38538714385d27e58be0573f991bf8a"
ENTRY_SHA = "0" * 64


def frame_ref(
    sequence: int = 1,
    *,
    session_id: str = "sess-test",
    input_sequence: int | None = None,
) -> FrameRef:
    return FrameRef(
        session_id=session_id,
        session_epoch=1,
        capture_sequence=sequence,
        input_sequence=sequence - 1 if input_sequence is None else input_sequence,
        captured_at=datetime(2026, 10, 1, tzinfo=UTC),
        captured_monotonic=float(sequence),
    )


def write_frame_file(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(f"frame:{name}".encode("utf-8"))
    return path


def home_observation(
    *,
    artifact_path: Path | None = None,
    sequence: int = 1,
    screen_type: ScreenType = ScreenType.PNC_HOME_CITY,
    blocked: bool = False,
    input_sequence: int | None = None,
) -> Observation:
    return Observation(
        screen_type=screen_type,
        blocking_popup=blocked,
        visible_elements={},
        artifact_path=artifact_path,
        image_size=(540, 960),
        frame_fingerprint=f"fp-{sequence}",
        frame_ref=frame_ref(sequence, input_sequence=input_sequence),
    )


def tap_receipt(source: Observation, *, input_sequence: int | None = None) -> InputDispatchRecord:
    return InputDispatchRecord(
        source_frame=source.frame_ref,
        dispatch=TapDispatch(point=(270, 520), input_sequence=(
            source.frame_ref.input_sequence + 1 if input_sequence is None else input_sequence)),
        artifact_path=source.artifact_path,
        home_city=True,
    )


def assignment_payload(
    tmp: Path,
    *,
    case_ids: tuple[str, ...] = ("v44_bank_body_menu",),
    entry_point: Path | None = None,
    entry_sha256: str | None = None,
    expected_cleanup: dict | None = None,
) -> dict:
    entry = entry_point or (tmp / "entry.py")
    if not entry.exists():
        entry.write_text("x = 1\n", encoding="utf-8")
    if entry_sha256 is None:
        entry_sha256 = sha256_file(entry)
    report_root = tmp / ".local-data" / "reports"
    offline = tmp / "offline.json"
    offline.write_text(json.dumps({"succeeded": True, "metadata": {
        "commit_sha": CANDIDATE_SHA, "source_fingerprint": "0" * 64}}), encoding="utf-8")
    return {
        "schema_version": SCHEMA_VERSION,
        "assignment_id": "v44-test-001",
        "run_id": "v44-test-001-run1",
        "candidate_sha": CANDIDATE_SHA,
        "source_root": str(tmp),
        "import_root": str(tmp),
        "report_root": str(report_root),
        "entry_point": str(entry),
        "entry_sha256": entry_sha256,
        "target_account_id": "testing",
        "target_castle_ref": "k1:Castle",
        "target_instance_id": "bluestacks-1",
        "target_role": "live_testing",
        "selected_cases": [{"case_id": case_id, "params": {}} for case_id in case_ids],
        "resource_allowance_ref": None,
        "reservation_disposition": "released",
        "expected_cleanup": expected_cleanup
        or {
            "session_closed": True,
            "lease_released": True,
            "observer_restored": True,
            "instance_preserved": False,
        },
        "offline_evidence": [{"path": str(offline), "sha256": sha256_file(offline),
                              "description": "exact candidate test proof"}],
        "config_path": None,
    }


def write_assignment(tmp: Path, payload: dict, name: str = "assignment.json") -> Path:
    path = tmp / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
