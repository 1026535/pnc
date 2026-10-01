"""Frozen V44 Home-city case registry.

Selection, execution, and result rows all derive from this one frozen set.
Python definitions are the released contract; no YAML commands, plugin
loading, or free-form input exists. ``discovery`` invokes the qualified body
entry and preserves one raw follow-up; ``development_validation`` additionally
consumes a tester-attested measured control through the dedicated executor
operation. A captured task-owned menu never satisfies an ``acceptance`` route.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalCasePurpose,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class CasePurpose(StrEnum):
    """Case intent released by the assignment, never inferred from its result."""

    DISCOVERY = "discovery"
    DEVELOPMENT_VALIDATION = "development_validation"
    ACCEPTANCE = "acceptance"


class CaseGate(StrEnum):
    """Machine-checkable case boundary tokens owned by this registry."""

    GUARDED_HOME_CITY = "guarded_home_city"
    RAW_FOLLOW_UP_CAPTURED = "raw_follow_up_captured"


BODY_ENTRY_OPERATION_ID = "enter_building_body_for_discovery"
"""The named existing navigation operation every measured body entry uses."""


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """One frozen case definition a released assignment may select."""

    case_id: str
    purpose: CasePurpose
    target: HomeCityObjectId
    home_city_slot: HomeCitySlotSelector | None
    operation_id: str
    entry_effect: WorkflowEffect
    released_action_id: str
    control_name: str | None
    control_effect: WorkflowEffect | None
    allowed_source_screens: frozenset[ScreenType]
    max_control_attempts: int
    required_preconditions: frozenset[CaseGate]
    required_postconditions: frozenset[CaseGate]
    params: Mapping[str, Any] = field(default=MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.purpose is CasePurpose.DISCOVERY:
            if self.control_name is not None or self.control_effect is not None:
                raise ValueError(f"Discovery case '{self.case_id}' cannot name a control.")
            if self.max_control_attempts != 0:
                raise ValueError(f"Discovery case '{self.case_id}' cannot allow control attempts.")
        else:
            if not self.control_name or self.control_effect is None:
                raise ValueError(f"Control case '{self.case_id}' requires a named control and effect.")
            if self.max_control_attempts <= 0:
                raise ValueError(f"Control case '{self.case_id}' requires a positive attempt limit.")
            if not self.allowed_source_screens:
                raise ValueError(f"Control case '{self.case_id}' requires allowed source screens.")

    @property
    def developmental_purpose(self) -> DevelopmentalCasePurpose | None:
        """Maps this case to the executor purpose when it performs a control."""

        if self.purpose is CasePurpose.DEVELOPMENT_VALIDATION:
            return DevelopmentalCasePurpose.CONTROL_VALIDATION
        return None


def _spec(
    case_id: str,
    *,
    purpose: CasePurpose,
    target: HomeCityObjectId,
    home_city_slot: HomeCitySlotSelector | None,
    released_action_id: str,
    control_name: str | None = None,
    control_effect: WorkflowEffect | None = None,
    allowed_source_screens: frozenset[ScreenType] = frozenset(),
    max_control_attempts: int = 0,
    required_postconditions: frozenset[CaseGate],
) -> CaseSpec:
    return CaseSpec(
        case_id=case_id,
        purpose=purpose,
        target=target,
        home_city_slot=home_city_slot,
        operation_id=BODY_ENTRY_OPERATION_ID,
        entry_effect=WorkflowEffect.READ_ONLY,
        released_action_id=released_action_id,
        control_name=control_name,
        control_effect=control_effect,
        allowed_source_screens=allowed_source_screens,
        max_control_attempts=max_control_attempts,
        required_preconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
        required_postconditions=required_postconditions,
    )


CASE_REGISTRY: Mapping[str, CaseSpec] = MappingProxyType(
    {
        spec.case_id: spec
        for spec in (
            _spec(
                "v44_bank_body_menu",
                purpose=CasePurpose.DISCOVERY,
                target=HomeCityObjectId.BANK,
                home_city_slot=None,
                released_action_id=BODY_ENTRY_OPERATION_ID,
                required_postconditions=frozenset({CaseGate.RAW_FOLLOW_UP_CAPTURED}),
            ),
            _spec(
                "v44_bank_return_home",
                purpose=CasePurpose.DEVELOPMENT_VALIDATION,
                target=HomeCityObjectId.BANK,
                home_city_slot=None,
                released_action_id="v44_bank_menu_return_home",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset({ScreenType.UNKNOWN, ScreenType.PNC_POPUP}),
                max_control_attempts=2,
                required_postconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
            ),
            _spec(
                "v44_watchtower_body_menu",
                purpose=CasePurpose.DISCOVERY,
                target=HomeCityObjectId.WATCHTOWER,
                home_city_slot=HomeCitySlotSelector(slot_index=4),
                released_action_id=BODY_ENTRY_OPERATION_ID,
                required_postconditions=frozenset({CaseGate.RAW_FOLLOW_UP_CAPTURED}),
            ),
            _spec(
                "v44_watchtower_return_home",
                purpose=CasePurpose.DEVELOPMENT_VALIDATION,
                target=HomeCityObjectId.WATCHTOWER,
                home_city_slot=HomeCitySlotSelector(slot_index=4),
                released_action_id="v44_watchtower_menu_return_home",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset(
                    {ScreenType.PNC_WATCHTOWER, ScreenType.UNKNOWN, ScreenType.PNC_POPUP}
                ),
                max_control_attempts=2,
                required_postconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
            ),
        )
    }
)


def require_case(case_id: str) -> CaseSpec:
    """Returns one frozen case or rejects an unreleased selection."""

    spec = CASE_REGISTRY.get(case_id)
    if spec is None:
        raise KeyError(f"Case '{case_id}' is not in the frozen V44 registry.")
    return spec


def frozen_case_ids() -> frozenset[str]:
    """Returns every released case id."""

    return frozenset(CASE_REGISTRY)
