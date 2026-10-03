"""Shared fakes for the offline live-validation runner tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from pnc_automation.app.pnc.domain.observation import (
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds

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
    layout_id: str | None = None,
    visible_elements: Mapping[UiElementId, VisibleElement] | None = None,
) -> Observation:
    return Observation(
        decision=ScreenDecision(
            base_screen=screen_type,
            effective_screen=screen_type,
            layout_id=layout_id,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
        ),
        visible_elements={} if visible_elements is None else visible_elements,
        artifact_path=artifact_path,
        image_size=(540, 960),
        frame_fingerprint=f"fp-{sequence}",
        frame_ref=frame_ref(sequence, input_sequence=input_sequence),
    )


def chip_element(
    source: Observation,
    *,
    bounds: Bounds = Bounds(300, 400, 78, 62),
    confidence: float = 0.97,
    frame_ref: FrameRef | None = None,
    source_screen: ScreenType | None = ScreenType.PNC_HOME_CITY,
    source_layout_id: str | None = "home_city",
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    action_point: tuple[int, int] | None = None,
) -> VisibleElement:
    """One provenanced Upgrade-chip element bound to ``source``'s frame."""

    return VisibleElement(
        selector_id=UiElementId.PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP,
        bounds=bounds,
        confidence=confidence,
        source_kind=source_kind,
        action_point=action_point,
        frame_ref=source.frame_ref if frame_ref is None else frame_ref,
        source_screen=source_screen,
        source_layout_id=source_layout_id,
    )


def chip_observation(
    *,
    artifact_path: Path | None = None,
    sequence: int = 1,
    **kwargs,
) -> Observation:
    """A Home observation carrying one canonical chip element on its frame."""

    observation = home_observation(
        artifact_path=artifact_path,
        sequence=sequence,
        layout_id="home_city",
        **kwargs,
    )
    object.__setattr__(
        observation,
        "visible_elements",
        {UiElementId.PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP: chip_element(observation)},
    )
    return observation


def back_element(
    source: Observation,
    *,
    bounds: Bounds = Bounds(10, 10, 100, 50),
    confidence: float = 0.99,
    frame_ref: FrameRef | None = None,
    source_screen: ScreenType | None = ScreenType.PNC_WATCHTOWER,
    source_layout_id: str | None = "building_watchtower",
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    action_point: tuple[int, int] | None = None,
) -> VisibleElement:
    """One provenanced canonical Back element bound to ``source``'s frame."""

    return VisibleElement(
        selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
        bounds=bounds,
        confidence=confidence,
        source_kind=source_kind,
        action_point=action_point,
        frame_ref=source.frame_ref if frame_ref is None else frame_ref,
        source_screen=source_screen,
        source_layout_id=source_layout_id,
    )


def watchtower_observation(
    *,
    artifact_path: Path | None = None,
    sequence: int = 1,
    layout_id: str | None = "building_watchtower",
    screen_type: ScreenType = ScreenType.PNC_WATCHTOWER,
    with_back: bool = True,
    **kwargs,
) -> Observation:
    """A Watchtower panel observation carrying its canonical Back element."""

    observation = home_observation(
        artifact_path=artifact_path,
        sequence=sequence,
        screen_type=screen_type,
        layout_id=layout_id,
        **kwargs,
    )
    object.__setattr__(
        observation,
        "visible_elements",
        ({UiElementId.PNC_BACK_BUTTON_TOP_LEFT: back_element(observation)}
         if with_back else {}),
    )
    return observation


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
