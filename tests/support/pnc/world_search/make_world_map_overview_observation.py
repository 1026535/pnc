"""Synthetic make_world_map_overview_observation fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_visible
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame



def _make_world_map_overview_observation(
    *,
    marker_point: tuple[int, int] | None,
    header_text: str = "K:157 Shadow Realm",
    recenter_region_bounds: tuple[int, int, int, int] = (10, 30, 180, 140),
) -> Observation:
    """Builds one synthetic overview observation with a map region and viewport marker."""

    visible_elements = {
        UiElementId.PNC_WORLD_OVERVIEW_HEADER: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_HEADER,
            x=20,
            y=10,
            width=120,
            height=20,
            extracted_text=header_text,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
            x=180,
            y=10,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
            x=20,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON,
            x=90,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON,
            x=150,
            y=180,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
            x=20,
            y=40,
            width=160,
            height=120,
        ),
        UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION: make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION,
            x=recenter_region_bounds[0],
            y=recenter_region_bounds[1],
            width=recenter_region_bounds[2],
            height=recenter_region_bounds[3],
        ),
    }
    if marker_point is not None:
        visible_elements[UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER] = make_visible(
            UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER,
            x=marker_point[0],
            y=marker_point[1],
            width=6,
            height=6,
            action_point=marker_point,
        )
    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_WORLD_MAP_OVERVIEW,
            effective_screen=ScreenType.PNC_WORLD_MAP_OVERVIEW,
            guard=GuardVerdict.CLEAR,
            evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_OVERVIEW, "test"),),
        ),
        visible_elements=visible_elements,
        image_size=(200, 200),
        frame_ref=make_captured_frame(b"overview").frame_ref,
    )
