"""Synthetic make_coordinate_dialog_observation fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Observation, ObservedTextFieldState
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation



def _make_coordinate_dialog_observation(
    kingdom: int,
    x: int,
    y: int,
    *,
    status_banner_text: str | None = None,
) -> Observation:
    """Builds one synthetic coordinate-dialog observation with committed field state."""

    visible_ids = [
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
        UiElementId.PNC_WORLD_COORDINATE_DIALOG_KEYBOARD_OK_BUTTON,
    ]
    if status_banner_text is not None:
        visible_ids.append(UiElementId.PNC_STATUS_BANNER)
    visible_texts = {} if status_banner_text is None else {UiElementId.PNC_STATUS_BANNER: status_banner_text}
    return make_observation(
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        visible_ids=tuple(visible_ids),
        visible_texts=visible_texts,
        text_field_states={
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
                text=str(kingdom),
                empty=False,
            ),
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                text=str(x),
                empty=False,
            ),
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD: ObservedTextFieldState(
                selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
                text=str(y),
                empty=False,
            ),
        },
    )
