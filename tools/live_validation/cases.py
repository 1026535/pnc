"""Frozen V44 Home-city case registry.

Selection, execution, and result rows all derive from this one frozen set.
Python definitions are the released contract; no YAML commands, plugin
loading, or free-form input exists. ``discovery`` invokes the qualified body
entry and preserves one raw follow-up; ``control_discovery`` sends one
measured control — tester-attested, or through the case's declared
``measurement_selector_id`` current-frame template element — and preserves
its raw follow-up without claiming a destination; ``development_validation``
consumes a tester-attested measured control through the dedicated executor
operation while reusing its declared discovery case's retained body witness —
a return case never re-enters the building itself. ``acceptance`` runs one
released production route through the public navigation seam; a captured
task-owned menu never satisfies it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from pnc_automation.app.automation.engine.developmental_control import (
    DevelopmentalCasePurpose,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class CasePurpose(StrEnum):
    """Case intent released by the assignment, never inferred from its result."""

    DISCOVERY = "discovery"
    CONTROL_DISCOVERY = "control_discovery"
    DEVELOPMENT_VALIDATION = "development_validation"
    ACCEPTANCE = "acceptance"


class CaseGate(StrEnum):
    """Machine-checkable case boundary tokens owned by this registry."""

    GUARDED_HOME_CITY = "guarded_home_city"
    RAW_FOLLOW_UP_CAPTURED = "raw_follow_up_captured"
    RETAINED_BODY_CONTEXT = "retained_body_context"


BODY_ENTRY_OPERATION_ID = "enter_building_body_for_discovery"
"""The named existing navigation operation every measured body entry uses."""

WATCHTOWER_OPEN_RETURN_OPERATION_ID = "watchtower_public_open_return"
"""The named production navigation route an acceptance case may execute."""

RELEASED_ROUTE_OPERATION_IDS = frozenset({WATCHTOWER_OPEN_RETURN_OPERATION_ID})
"""Route operation ids released to the tracked runner; all others refuse."""


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """One frozen case definition a released assignment may select.

    ``body_case_id`` names the case that owns the building body entry a
    control case relies on. Discovery cases always own their own body entry
    (``body_case_id == case_id``); a dependent case names the discovery case
    whose retained witness authorizes its control without a second body tap.

    ``measurement_selector_id`` names the canonical selector whose current-
    frame template element supplies the control measurement for this case
    instead of manual tester attestation. It identifies the visible control
    only; it grants no action and claims no destination. Only a control case
    may declare one.

    An ``acceptance`` case is one production route executed through the
    public navigation seam, not a measured control: it names no control,
    declares no selector measurement, retains no discovery body witness, and
    keeps ``body_case_id == case_id`` only for the existing selection-order
    convention. ``operation_id`` names the released route; ``entry_effect``
    describes the body selection that opens the route.
    """

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
    body_case_id: str
    required_preconditions: frozenset[CaseGate]
    required_postconditions: frozenset[CaseGate]
    measurement_selector_id: UiElementId | None = None
    params: Mapping[str, Any] = field(default=MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.purpose is CasePurpose.DISCOVERY:
            if self.control_name is not None or self.control_effect is not None:
                raise ValueError(f"Discovery case '{self.case_id}' cannot name a control.")
            if self.max_control_attempts != 0:
                raise ValueError(f"Discovery case '{self.case_id}' cannot allow control attempts.")
            if self.measurement_selector_id is not None:
                raise ValueError(
                    f"Discovery case '{self.case_id}' cannot declare a selector measurement."
                )
            if self.body_case_id != self.case_id:
                raise ValueError(f"Discovery case '{self.case_id}' must own its body entry.")
        elif self.purpose is CasePurpose.ACCEPTANCE:
            if self.control_name is not None or self.control_effect is not None:
                raise ValueError(f"Acceptance case '{self.case_id}' cannot name a control.")
            if self.max_control_attempts != 0:
                raise ValueError(f"Acceptance case '{self.case_id}' cannot allow control attempts.")
            if self.measurement_selector_id is not None:
                raise ValueError(
                    f"Acceptance case '{self.case_id}' cannot declare a selector measurement."
                )
            if self.body_case_id != self.case_id:
                raise ValueError(
                    f"Acceptance case '{self.case_id}' owns its own route and cannot "
                    "retain a discovery body witness."
                )
            if self.allowed_source_screens:
                raise ValueError(
                    f"Acceptance case '{self.case_id}' binds guarded Home, not a "
                    "control source-screen contract."
                )
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

        if self.purpose is CasePurpose.CONTROL_DISCOVERY:
            return DevelopmentalCasePurpose.CONTROL_DISCOVERY
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
    operation_id: str = BODY_ENTRY_OPERATION_ID,
    entry_effect: WorkflowEffect = WorkflowEffect.READ_ONLY,
    body_case_id: str | None = None,
    control_name: str | None = None,
    control_effect: WorkflowEffect | None = None,
    allowed_source_screens: frozenset[ScreenType] = frozenset(),
    max_control_attempts: int = 0,
    measurement_selector_id: UiElementId | None = None,
    required_preconditions: frozenset[CaseGate] | None = None,
    required_postconditions: frozenset[CaseGate],
) -> CaseSpec:
    return CaseSpec(
        case_id=case_id,
        purpose=purpose,
        target=target,
        home_city_slot=home_city_slot,
        operation_id=operation_id,
        entry_effect=entry_effect,
        released_action_id=released_action_id,
        control_name=control_name,
        control_effect=control_effect,
        allowed_source_screens=allowed_source_screens,
        max_control_attempts=max_control_attempts,
        body_case_id=body_case_id or case_id,
        measurement_selector_id=measurement_selector_id,
        required_preconditions=(
            frozenset({CaseGate.GUARDED_HOME_CITY})
            if required_preconditions is None
            else required_preconditions
        ),
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
                body_case_id="v44_bank_body_menu",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset({ScreenType.UNKNOWN, ScreenType.PNC_POPUP}),
                max_control_attempts=2,
                required_preconditions=frozenset({CaseGate.RETAINED_BODY_CONTEXT}),
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
            # The selected Watchtower stays Home-classified and shows only the
            # on-city Upgrade chip. This case measures that chip through the
            # canonical current-frame selector proof and sends it once; it does
            # not claim an upgrade endpoint or a production route.
            _spec(
                "v44_watchtower_selected_control_entry",
                purpose=CasePurpose.CONTROL_DISCOVERY,
                target=HomeCityObjectId.WATCHTOWER,
                home_city_slot=HomeCitySlotSelector(slot_index=4),
                released_action_id="v44_watchtower_selected_chip_entry",
                body_case_id="v44_watchtower_body_menu",
                control_name="open_watchtower_panel",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset({ScreenType.PNC_HOME_CITY}),
                max_control_attempts=1,
                measurement_selector_id=UiElementId.PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP,
                required_preconditions=frozenset({CaseGate.RETAINED_BODY_CONTEXT}),
                required_postconditions=frozenset({CaseGate.RAW_FOLLOW_UP_CAPTURED}),
            ),
            _spec(
                "v44_watchtower_return_home",
                purpose=CasePurpose.DEVELOPMENT_VALIDATION,
                target=HomeCityObjectId.WATCHTOWER,
                home_city_slot=HomeCitySlotSelector(slot_index=4),
                released_action_id="v44_watchtower_menu_return_home",
                body_case_id="v44_watchtower_body_menu",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset(
                    {ScreenType.PNC_WATCHTOWER, ScreenType.UNKNOWN, ScreenType.PNC_POPUP}
                ),
                max_control_attempts=2,
                required_preconditions=frozenset({CaseGate.RETAINED_BODY_CONTEXT}),
                required_postconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
            ),
            # Ordinary troop-building body entries may collect completed
            # troops, so these discovery cases declare a nonspending state
            # change instead of read-only. They discover the native panels
            # only; no production route is claimed.
            _spec(
                "v44_cavalry_body_menu",
                purpose=CasePurpose.DISCOVERY,
                target=HomeCityObjectId.CAVALRY_BARRACKS,
                home_city_slot=HomeCitySlotSelector(slot_index=6),
                released_action_id=BODY_ENTRY_OPERATION_ID,
                entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                required_postconditions=frozenset({CaseGate.RAW_FOLLOW_UP_CAPTURED}),
            ),
            _spec(
                "v44_cavalry_return_home",
                purpose=CasePurpose.DEVELOPMENT_VALIDATION,
                target=HomeCityObjectId.CAVALRY_BARRACKS,
                home_city_slot=HomeCitySlotSelector(slot_index=6),
                released_action_id="v44_cavalry_menu_return_home",
                body_case_id="v44_cavalry_body_menu",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset(
                    {
                        ScreenType.UNKNOWN,
                        ScreenType.PNC_POPUP,
                        ScreenType.PNC_CAVALRY_BARRACKS,
                    }
                ),
                max_control_attempts=2,
                required_preconditions=frozenset({CaseGate.RETAINED_BODY_CONTEXT}),
                required_postconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
            ),
            _spec(
                "v44_siege_body_menu",
                purpose=CasePurpose.DISCOVERY,
                target=HomeCityObjectId.SIEGE_FACTORY,
                home_city_slot=HomeCitySlotSelector(slot_index=8),
                released_action_id=BODY_ENTRY_OPERATION_ID,
                entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                required_postconditions=frozenset({CaseGate.RAW_FOLLOW_UP_CAPTURED}),
            ),
            _spec(
                "v44_siege_return_home",
                purpose=CasePurpose.DEVELOPMENT_VALIDATION,
                target=HomeCityObjectId.SIEGE_FACTORY,
                home_city_slot=HomeCitySlotSelector(slot_index=8),
                released_action_id="v44_siege_menu_return_home",
                body_case_id="v44_siege_body_menu",
                control_name="return_home",
                control_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                allowed_source_screens=frozenset(
                    {
                        ScreenType.UNKNOWN,
                        ScreenType.PNC_POPUP,
                        ScreenType.PNC_SIEGE_FACTORY,
                    }
                ),
                max_control_attempts=2,
                required_preconditions=frozenset({CaseGate.RETAINED_BODY_CONTEXT}),
                required_postconditions=frozenset({CaseGate.GUARDED_HOME_CITY}),
            ),
            # One frozen production route: guarded Home -> slot-4 Watchtower
            # body -> canonical Upgrade chip -> qualified Watch Tower panel ->
            # measured Back -> guarded Home. The route never confirms an
            # upgrade and never touches the panel's resource controls.
            _spec(
                "v44_watchtower_public_open_return",
                purpose=CasePurpose.ACCEPTANCE,
                target=HomeCityObjectId.WATCHTOWER,
                home_city_slot=HomeCitySlotSelector(slot_index=4),
                released_action_id="v44_watchtower_public_open_return",
                operation_id=WATCHTOWER_OPEN_RETURN_OPERATION_ID,
                entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
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


def validate_case_registry() -> None:
    """Proves every declared body dependency targets a compatible discovery case."""

    for spec in CASE_REGISTRY.values():
        if spec.body_case_id == spec.case_id:
            continue
        owner = CASE_REGISTRY.get(spec.body_case_id)
        if owner is None or owner.purpose is not CasePurpose.DISCOVERY:
            raise ValueError(
                f"Case '{spec.case_id}' declares body case '{spec.body_case_id}' "
                "which is not a frozen discovery case."
            )
        if owner.target != spec.target or owner.home_city_slot != spec.home_city_slot:
            raise ValueError(
                f"Case '{spec.case_id}' targets a different building than its "
                f"declared body case '{spec.body_case_id}'."
            )


def validate_selected_order(selected: Sequence[str]) -> None:
    """Requires each selected case's declared body case to precede it.

    A discovery case supplies its own body witness; a dependent case is only
    meaningful when its discovery case was already selected and executed.
    """

    seen: set[str] = set()
    for case_id in selected:
        spec = require_case(case_id)
        if spec.body_case_id != spec.case_id and spec.body_case_id not in seen:
            raise KeyError(
                f"Case '{case_id}' requires its discovery case "
                f"'{spec.body_case_id}' to be selected and ordered before it."
            )
        seen.add(case_id)


validate_case_registry()
