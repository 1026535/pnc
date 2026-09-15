"""Offline tests for direct Home City Hero Hall entry."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.connected_hero_hall import (
    ConnectedHeroHallSession,
)
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface


class ConnectedHeroHallEntryTests(unittest.TestCase):
    """Protects the Hero Hall canary from regressing to Daily-Go navigation."""

    def setUp(self) -> None:
        """Builds a session with a mocked shared Home City flow planner."""

        self.flows = Mock()
        self.session = ConnectedHeroHallSession(
            runner=Mock(),
            observation_service=Mock(),
            action_executor=Mock(),
            flows=self.flows,
        )

    def test_dispatch_requires_current_free_template_and_positive_attempts(self) -> None:
        """Uses only the distinct current-frame free selector for one dispatch."""

        observation = make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=(
                UiElementId.PNC_HERO_HALL_RECRUIT_BANNER,
                UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,
            ),
            visible_texts={UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: "Daily attempts: 5"},
        )
        self.session.observation_service.observe.return_value = observation
        self.session.action_executor.recover_interruption_if_required.return_value = None
        self.session.action_executor.execute_action.return_value = True

        self.session.recruit_free_single()

        action = self.session.action_executor.execute_action.call_args.args[0]
        self.assertEqual(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON, action.selector_id)
        self.assertEqual("hero_hall_free_single", action.reason)

    def test_generic_only_control_is_rejected_before_dispatch(self) -> None:
        """Does not use the generic Recruit 1x geometry as a free action proof."""

        observation = make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=(
                UiElementId.PNC_HERO_HALL_RECRUIT_BANNER,
                UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON,
            ),
            visible_texts={UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: "Daily attempts: 5"},
        )
        self.session.observation_service.observe.return_value = observation
        self.session.action_executor.recover_interruption_if_required.return_value = None

        with self.assertRaisesRegex(SelectorResolutionError, "free 1x recruit control"):
            self.session.recruit_free_single()
        self.session.action_executor.execute_action.assert_not_called()

    def test_missing_attempts_is_rejected_before_dispatch(self) -> None:
        """Does not dispatch a visible free control when the attempt counter is absent."""

        observation = make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,),
        )
        self.session.observation_service.observe.return_value = observation
        self.session.action_executor.recover_interruption_if_required.return_value = None

        with self.assertRaisesRegex(SelectorResolutionError, "positive observed daily attempts"):
            self.session.recruit_free_single()
        self.session.action_executor.execute_action.assert_not_called()

    def test_false_action_result_is_rejected_without_retry(self) -> None:
        """Treats a rejected low-level action as failure and does not replay it."""

        observation = make_observation(
            ScreenType.PNC_HERO_HALL,
            visible_ids=(
                UiElementId.PNC_HERO_HALL_RECRUIT_BANNER,
                UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,
            ),
            visible_texts={UiElementId.PNC_HERO_HALL_RECRUIT_BANNER: "Daily attempts: 5"},
        )
        self.session.observation_service.observe.return_value = observation
        self.session.action_executor.recover_interruption_if_required.return_value = None
        self.session.action_executor.execute_action.return_value = False

        with self.assertRaisesRegex(RuntimeError, "was not executed"):
            self.session.recruit_free_single()
        self.assertEqual(1, self.session.action_executor.execute_action.call_count)

    def test_visible_hero_hall_uses_exact_home_city_object_tap(self) -> None:
        """Taps the observed Hero Hall object and never asks a Daily flow for entry."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Hero Hall",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.HERO_HALL),
                        action_point=(91, 37),
                    ),
                ),
            ),
        )
        planned = [TapSpatialObjectAction(reason="test_hero_hall_tap", target_point=(91, 37))]
        self.flows.open_visible_home_city_object.return_value = planned

        actions = self.session._plan_open(observation)

        self.assertEqual(planned, actions)
        self.flows.open_visible_home_city_object.assert_called_once()
        self.flows.focus_home_city_object.assert_not_called()

    def test_missing_hero_hall_requests_home_city_focus_only(self) -> None:
        """Focuses the camera when Hero Hall is not visible instead of using a blind tap."""

        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE),
        )
        planned = [SwipeAction(direction="left", reason="focus_hero_hall")]
        self.flows.focus_home_city_object.return_value = planned

        actions = self.session._plan_open(observation)

        self.assertEqual(planned, actions)
        self.flows.focus_home_city_object.assert_called_once()
        self.flows.open_visible_home_city_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
