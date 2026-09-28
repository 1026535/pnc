"""Shared core frames doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.emulator.provenance import FrameRef


class Actuator:
    def __init__(self):
        self.actions = []

    def execute_action(self, action, observation):
        self.actions.append(action)
        return True


def observation(screen, *, geometry=False, blocked=False):
    return Observation(
        decision=ScreenDecision(
            base_screen=screen,
            effective_screen=screen,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
        ),
        visible_elements={UiElementId.PNC_HOME_WORLD_SWITCH: VisibleElement(
            UiElementId.PNC_HOME_WORLD_SWITCH, Bounds(10, 20, 30, 40), 0.99,
            source_kind=VisibleElementSourceKind.GEOMETRY if geometry else VisibleElementSourceKind.TEMPLATE,
        )},
    )


def _frame_ref(label: str) -> FrameRef:
    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )
