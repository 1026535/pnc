"""Shared immutable action policy for read-only visual probes."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    KeyEventAction,
    LaunchAppAction,
    SwipeAction,
    TapAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError


@dataclass(frozen=True, slots=True)
class ReadOnlyProbePolicy:
    """Defines the exact source states and actions a probe may dispatch."""

    enabled: bool = False
    allowed_selectors: frozenset[UiElementId] = frozenset()
    allowed_selector_screens: tuple[tuple[UiElementId, frozenset[ScreenType]], ...] = ()
    allow_launch: bool = False
    allow_swipe: bool = False
    allowed_back_screens: frozenset[ScreenType] = frozenset()
    allowed_swipe_screens: frozenset[ScreenType] = frozenset()
    allowed_launch_screens: frozenset[ScreenType] = frozenset()
    max_wait_ms: int = 1000

    def __post_init__(self) -> None:
        """Rejects invalid probe wait budgets."""

        if self.max_wait_ms < 0:
            raise ValueError("Read-only wait budget cannot be negative.")

    def selector_allowed_on_screen(self, selector_id: UiElementId, screen_type: ScreenType) -> bool:
        """Returns whether one allowlisted selector is reviewed for this source screen."""

        return any(
            allowed_id == selector_id and screen_type in screens
            for allowed_id, screens in self.allowed_selector_screens
        )

    def validate(self, action: ActionRequest, observation: Observation) -> None:
        """Rejects any action outside this policy before input dispatch."""

        if not self.enabled:
            return
        if (
            isinstance(action, TapAction)
            and action.selector_id in self.allowed_selectors
            and self.selector_allowed_on_screen(action.selector_id, observation.screen_type)
        ):
            return
        if (
            isinstance(action, KeyEventAction)
            and action.key_code == "KEYCODE_BACK"
            and observation.screen_type in self.allowed_back_screens
        ):
            return
        if isinstance(action, WaitAction) and 0 <= action.milliseconds <= self.max_wait_ms:
            return
        if (
            isinstance(action, LaunchAppAction)
            and self.allow_launch
            and observation.screen_type in self.allowed_launch_screens
        ):
            return
        if (
            isinstance(action, SwipeAction)
            and self.allow_swipe
            and observation.screen_type in self.allowed_swipe_screens
        ):
            return
        raise SelectorResolutionError(
            "Read-only probe rejected an action outside its explicit safety policy.",
            action_type=type(action).__name__,
            selector_id=getattr(action, "selector_id", None),
            screen_type=observation.screen_type,
        )
