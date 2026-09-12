"""Synthetic make_incomplete_coordinate_dialog_observation fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Observation, ObservedTextFieldState
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation



def _make_incomplete_coordinate_dialog_observation(
    kingdom: int | None,
    *,
    x: int | None,
    y: int | None,
) -> Observation:
    """Builds a classified coordinate dialog while omitting selected field states."""

    text_field_states: dict[UiElementId, ObservedTextFieldState] = {}
    if kingdom is not None:
        text_field_states[UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD] = ObservedTextFieldState(
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
            text=str(kingdom),
            empty=False,
        )
    if x is not None:
        text_field_states[UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD] = ObservedTextFieldState(
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
            text=str(x),
            empty=False,
        )
    if y is not None:
        text_field_states[UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD] = ObservedTextFieldState(
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            text=str(y),
            empty=False,
        )
    return make_observation(
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        visible_ids=(
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_KEYBOARD_OK_BUTTON,
        ),
        text_field_states=text_field_states,
    )
