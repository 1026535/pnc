"""Action tap targets."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    TapAction,
    TapListEntryAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_entry, make_observation, make_visible
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)


class ActionTapTargetsTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves action tap targets."""

    def test_tap_actions_prefer_visible_element_action_points(self) -> None:
        """Uses selector-specific action points when OCR-derived bounds are not the real touch target."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = Observation(
            screen_type=ScreenType.PNC_HOME_CITY,
            visible_elements={
                UiElementId.PNC_BOTTOM_NAV_BAG: make_visible(
                    UiElementId.PNC_BOTTOM_NAV_BAG,
                    x=440,
                    y=1560,
                    width=54,
                    height=33,
                    action_point=(482, 1529),
                )
            },
        )

        executor.execute_action(
            TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_BAG),
            observation,
        )

        self.assertEqual(executor.session.taps, [(482, 1529)])

    def test_tap_list_entry_action_matches_castle_titles_with_spacing_only_ocr_drift(self) -> None:
        """Resolves castle-row taps through the shared OCR-tolerant castle-name matcher."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="please bgentle",
                    metadata={"kingdom": "K226", "castle_level": 12},
                    action_point=(240, 872),
                ),
            ),
        )

        executor.execute_action(
            TapListEntryAction(
                entry_kind=ListEntryKind.CASTLE,
                title_text="please b gentle",
                metadata_key="kingdom",
                metadata_value="K226",
                use_action_point=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(240, 872)])

    def test_tap_spatial_object_actions_use_current_viewport_action_points(self) -> None:
        """Uses the live spatial-object action point from the current viewport instead of any fixed building coordinate."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(167, 241),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                    metadata_key="home_city_object_id",
                    metadata_value="castle",
                )
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(167, 241)])

    def test_tap_spatial_object_actions_preserve_duplicate_target_points(self) -> None:
        """Uses the concrete target point captured during planning instead of re-resolving duplicate semantic matches."""

        executor = ActionExecutor(
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(55, 66),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(155, 166),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                    name_text="Food Farm",
                    metadata_key="resource_type",
                    metadata_value="food",
                ),
                target_point=(155, 166),
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(155, 166)])
