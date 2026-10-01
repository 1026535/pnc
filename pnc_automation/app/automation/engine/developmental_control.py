"""Typed, case-bound evidence for a measured developmental UI control."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import Bounds, Observation
from pnc_automation.app.pnc.domain.screen_decision import ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.emulator.input_dispatch import InputDispatchRecord
from pnc_automation.core.infra.emulator.provenance import FrameRef


class DevelopmentalCasePurpose(StrEnum):
    """Purpose named by a released developmental case, not by its result."""

    CAPTURE_ONLY = "capture_only"
    CONTROL_DISCOVERY = "control_discovery"
    CONTROL_VALIDATION = "control_validation"


@dataclass(frozen=True, slots=True)
class BodyEntryWitness:
    """One attributed exact body action and its actual physical tap receipt."""

    case_id: str
    operation_id: str
    observation: Observation
    action: TapSpatialObjectAction
    receipt: InputDispatchRecord


@dataclass(frozen=True, slots=True)
class ConsumedCaseAttempt:
    """Runner-owned logical attempt, including refusals before physical input.

    ``number`` is cumulative within the case; it is not a dispatch count.
    """

    case_id: str
    control_name: str
    number: int
    limit: int
    journal_ref: str


@dataclass(frozen=True, slots=True)
class DevelopmentalControlScope:
    """Exact released case authority plus its attributed input chain.

    Construction does not itself grant a case. The tracked runner must derive
    this value from its frozen CaseSpec and consume the case attempt first.
    ``input_chain`` starts with ``body_entry.receipt`` and contains every
    case-attributed physical input since that body entry.
    """

    assignment_id: str
    case_id: str
    case_spec_ref: str
    purpose: DevelopmentalCasePurpose
    operation_id: str
    released_action_id: str
    control_name: str
    target: HomeCityObjectId
    home_city_slot: HomeCitySlotSelector | None
    allowed_source_screens: frozenset[ScreenType]
    effect: WorkflowEffect
    read_only: bool
    resource_allowance_ref: str | None
    attempt: ConsumedCaseAttempt
    body_entry: BodyEntryWitness
    input_chain: tuple[InputDispatchRecord, ...]
    latest_input_follow_up: Observation


@dataclass(frozen=True, slots=True)
class MeasuredControlProof:
    """Tester-attested foreground control measured on one persisted frame."""

    frame_ref: FrameRef
    artifact_path: Path
    frame_fingerprint: str
    image_size: tuple[int, int]
    decision: ScreenDecision
    screen_type: ScreenType
    control_name: str
    foreground_target: HomeCityObjectId
    task_owned_foreground: bool
    visual_reason: str
    intended_effect: WorkflowEffect
    bounds: Bounds
    action_point: tuple[int, int]


@dataclass(frozen=True, slots=True)
class DevelopmentalControlResult:
    """Actual input receipt and immediate persisted, uninterpreted follow-up."""

    receipt: InputDispatchRecord
    follow_up: Observation
