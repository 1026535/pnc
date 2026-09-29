"""Navigation core campaign tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_home import (
    camera_home_frame,
    measured_building_object,
    qualified_pan_step,
)
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_campaign_endpoint_opens_after_fresh_target_reacquisition(self):
        target = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(78, 225, 90, 42),
            action_point=(121, 247),
            action_bounds=Bounds(114, 241, 13, 13),
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter((
            camera_home_frame((target,), translation=(-1882, -709), captured_at=now),
            camera_home_frame((target,), translation=(-1882, -709), captured_at=now + timedelta(seconds=1)),
        ))
        destination_frames = iter(
            replace(observation(screen), captured_at=now + timedelta(seconds=index))
            for index, screen in enumerate((
                ScreenType.PNC_LOADING, ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_MAP,
            ), start=2)
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(destination_frames), reviewed_navigation_edges(),
            sleep=lambda _: None,
        )

        opened = core.open_building(
            HomeCityObjectId.CAMPAIGN, observe_content=lambda _: next(content_frames),
        )

        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, opened.screen_type)
        self.assertEqual(now + timedelta(seconds=4), opened.captured_at)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual(target.action_point, actuator.actions[0].target_point)
        self.assertIsNone(next(content_frames, None))


    def test_campaign_stage_routes_through_chapter_and_map_to_home(self):
        controls = {
            ScreenType.PNC_CAMPAIGN_STAGE: UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
            ScreenType.PNC_CAMPAIGN_CHAPTER: UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
            ScreenType.PNC_CAMPAIGN_MAP: UiElementId.PNC_CAMPAIGN_HOME_PORTAL,
        }
        screens = (
            ScreenType.PNC_CAMPAIGN_STAGE, ScreenType.PNC_CAMPAIGN_STAGE,
            ScreenType.PNC_CAMPAIGN_CHAPTER, ScreenType.PNC_CAMPAIGN_CHAPTER,
            ScreenType.PNC_CAMPAIGN_CHAPTER,
            ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_MAP,
            ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_LOADING,
            ScreenType.PNC_HOME_CITY, ScreenType.PNC_HOME_CITY,
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = []
        for index, screen in enumerate(screens):
            selector = controls.get(screen)
            visible = {} if selector is None else {
                selector: VisibleElement(
                    selector, Bounds(450, 200, 50, 50), 1.0,
                    source_kind=VisibleElementSourceKind.TEMPLATE,
                ),
            }
            frames.append(replace(
                observation(screen), visible_elements=visible,
                captured_at=now + timedelta(seconds=index),
            ))
        pending = iter(frames)
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(pending), reviewed_navigation_edges(), sleep=lambda _: None,
        )

        returned = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertIs(frames[-1], returned)
        self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
        self.assertEqual(list(controls.values()), [action.selector_id for action in actuator.actions])
        self.assertIsNone(next(pending, None))


    def test_formation_preparation_routes_back_through_stage_to_home(self):
        """One owned preparation Back reaches the typed stage, then the reviewed chain to Home."""
        controls = {
            ScreenType.PNC_HERO_FORMATION: UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
            ScreenType.PNC_CAMPAIGN_STAGE: UiElementId.PNC_CAMPAIGN_CLOSE_BUTTON,
            ScreenType.PNC_CAMPAIGN_CHAPTER: UiElementId.PNC_CAMPAIGN_BACK_BUTTON,
            ScreenType.PNC_CAMPAIGN_MAP: UiElementId.PNC_CAMPAIGN_HOME_PORTAL,
        }
        screens = (
            ScreenType.PNC_HERO_FORMATION, ScreenType.PNC_HERO_FORMATION,
            ScreenType.PNC_CAMPAIGN_STAGE, ScreenType.PNC_CAMPAIGN_STAGE,
            ScreenType.PNC_CAMPAIGN_STAGE,
            ScreenType.PNC_CAMPAIGN_CHAPTER, ScreenType.PNC_CAMPAIGN_CHAPTER,
            ScreenType.PNC_CAMPAIGN_CHAPTER,
            ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_MAP,
            ScreenType.PNC_CAMPAIGN_MAP,
            ScreenType.PNC_HOME_CITY, ScreenType.PNC_HOME_CITY,
        )
        now = datetime(2026, 9, 29, tzinfo=UTC)
        frames = []
        for index, screen in enumerate(screens):
            selector = controls.get(screen)
            visible = {} if selector is None else {
                selector: VisibleElement(
                    selector, Bounds(14, 4, 48, 42), 1.0,
                    source_kind=VisibleElementSourceKind.TEMPLATE,
                ),
            }
            frames.append(replace(
                observation(screen), visible_elements=visible,
                captured_at=now + timedelta(seconds=index),
            ))
        pending = iter(frames)
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(pending), reviewed_navigation_edges(), sleep=lambda _: None,
        )

        returned = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertIs(frames[-1], returned)
        self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
        self.assertEqual(list(controls.values()), [action.selector_id for action in actuator.actions])
        self.assertIsNone(next(pending, None))


    def test_formation_without_preparation_back_refuses_navigation(self):
        """SaveForm-like and control-less formations never reach the actuator."""
        variants = (
            {
                UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON: VisibleElement(
                    UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON, Bounds(350, 1490, 200, 40), 1.0,
                    source_kind=VisibleElementSourceKind.GEOMETRY,
                ),
            },
            {},
        )
        for visible in variants:
            with self.subTest(visible=list(visible)):
                pending = iter((
                    replace(
                        observation(ScreenType.PNC_HERO_FORMATION),
                        visible_elements=visible,
                    ),
                    replace(
                        observation(ScreenType.PNC_HERO_FORMATION),
                        visible_elements=visible,
                    ),
                ))
                actuator = Actuator()
                core = NavigationCore(
                    actuator, lambda _: next(pending), reviewed_navigation_edges(),
                    sleep=lambda _: None,
                )
                with self.assertRaises(RuntimeError):
                    core.navigate(ScreenType.PNC_HOME_CITY)
                self.assertEqual([], actuator.actions)


    def test_formation_preparation_back_rejects_an_unexpected_destination(self):
        """A post-Back screen outside the reviewed destination stops after one tap."""
        back = {
            UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON: VisibleElement(
                UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON, Bounds(14, 4, 48, 42), 1.0,
                source_kind=VisibleElementSourceKind.TEMPLATE,
            ),
        }
        now = datetime(2026, 9, 29, tzinfo=UTC)
        pending = iter((
            replace(
                observation(ScreenType.PNC_HERO_FORMATION), visible_elements=back,
                captured_at=now,
            ),
            replace(
                observation(ScreenType.PNC_HERO_FORMATION), visible_elements=back,
                captured_at=now + timedelta(seconds=1),
            ),
            replace(
                observation(ScreenType.PNC_MAIL_HUB),
                captured_at=now + timedelta(seconds=2),
            ),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(pending), reviewed_navigation_edges(), sleep=lambda _: None,
        )

        with self.assertRaises(RuntimeError) as failure:
            core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertIn("unexpected screen", str(failure.exception))
        self.assertEqual(
            [UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON],
            [action.selector_id for action in actuator.actions],
        )


    def test_campaign_measured_open_descends_to_corridor_before_horizontal_pan(self):
        """Northern Home first descends to the measured corridor, then pans east."""
        target = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(78, 225, 90, 42),
            action_point=(121, 247),
            action_bounds=Bounds(114, 241, 13, 13),
        )
        now = datetime(2026, 9, 16, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame(translation=(-532, 222), captured_at=now),
                camera_home_frame(translation=(-532, 222), captured_at=now + timedelta(seconds=1)),
                camera_home_frame(translation=(-532, -709), captured_at=now + timedelta(seconds=2)),
                camera_home_frame((target,), translation=(-1882, -709), captured_at=now + timedelta(seconds=3)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_CAMPAIGN_MAP),
                observation(ScreenType.PNC_CAMPAIGN_MAP),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=5),
            sleep=lambda _: None,
        )
        steps = (
            qualified_pan_step(
                "up", axis="y", goal_atlas=(982, 1700),
                reason="pan_home_city_camera_campaign_y",
            ),
            qualified_pan_step(
                "left", axis="x", goal_atlas=(2400, 1509),
                reason="pan_home_city_camera_campaign_x",
            ),
        )
        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            side_effect=list(steps),
        ) as planner:
            result = core.open_building(
                HomeCityObjectId.CAMPAIGN,
                observe_content=lambda _: next(content_frames),
            )

        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, result.screen_type)
        self.assertEqual(2, planner.call_count)
        self.assertEqual(3, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertEqual("up", actuator.actions[0].direction)
        self.assertEqual("pan_home_city_camera_campaign_y", actuator.actions[0].reason)
        self.assertIsInstance(actuator.actions[1], SwipeAction)
        self.assertEqual("left", actuator.actions[1].direction)
        self.assertEqual("pan_home_city_camera_campaign_x", actuator.actions[1].reason)
        self.assertIsInstance(actuator.actions[2], TapSpatialObjectAction)
        self.assertEqual((121, 247), actuator.actions[2].target_point)


    def test_campaign_measured_open_pans_above_band_body_before_tap(self):
        """A body matched above the HUD-safe band gets one vertical pan, never a blind tap."""
        above_band = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(353, 145, 90, 42),
            action_point=(395, 167),
            action_bounds=Bounds(389, 161, 13, 13),
        )
        in_band = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(280, 225, 90, 42),
            action_point=(323, 247),
            action_bounds=Bounds(316, 241, 13, 13),
        )
        now = datetime(2026, 9, 16, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((above_band,), translation=(-1423, -843), captured_at=now),
                camera_home_frame((above_band,), translation=(-1423, -843), captured_at=now + timedelta(seconds=1)),
                camera_home_frame((in_band,), translation=(-1423, -730), captured_at=now + timedelta(seconds=2)),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_CAMPAIGN_MAP),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "down", axis="y", goal_atlas=(1873, 1200),
            reason="pan_home_city_camera_campaign_y",
        )
        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ) as planner:
            result = core.open_building(
                HomeCityObjectId.CAMPAIGN,
                observe_content=lambda _: next(content_frames),
            )

        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, result.screen_type)
        self.assertEqual(1, planner.call_count)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertEqual("down", actuator.actions[0].direction)
        self.assertEqual("pan_home_city_camera_campaign_y", actuator.actions[0].reason)
        self.assertIsInstance(actuator.actions[1], TapSpatialObjectAction)
        self.assertEqual((323, 247), actuator.actions[1].target_point)


    def test_campaign_measured_stalled_corridor_pan_fails_closed_before_tap(self):
        """A corridor descent that produced no camera motion cannot reach a tap."""
        target = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(78, 225, 90, 42),
            action_point=(121, 247),
            action_bounds=Bounds(114, 241, 13, 13),
        )
        now = datetime(2026, 9, 16, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame(translation=(-532, 222), captured_at=now),
                camera_home_frame(translation=(-532, 222), captured_at=now + timedelta(seconds=1)),
                camera_home_frame(
                    (target,), translation=(-532, 222), captured_at=now + timedelta(seconds=2),
                ),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_CAMPAIGN_MAP),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1700),
            reason="pan_home_city_camera_campaign_y",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            side_effect=[step, SelectorResolutionError("no qualified lane remains")],
        ):
            with self.assertRaisesRegex(RuntimeError, "no camera movement"):
                core.open_building(
                    HomeCityObjectId.CAMPAIGN,
                    observe_content=lambda _: next(content_frames),
                )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_campaign_measured_wrong_destination_does_not_repeat_tap(self):
        """A portal tap that does not reach the Campaign map is not repeated."""
        target = measured_building_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(78, 225, 90, 42),
            action_point=(121, 247),
            action_bounds=Bounds(114, 241, 13, 13),
        )
        now = datetime(2026, 9, 16, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((target,), translation=(-1882, -709), captured_at=now),
                camera_home_frame((target,), translation=(-1882, -709), captured_at=now + timedelta(seconds=1)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_CASTLE),
                observation(ScreenType.PNC_CASTLE),
                observation(ScreenType.PNC_CASTLE),
                observation(ScreenType.PNC_CASTLE),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            core.open_building(
                HomeCityObjectId.CAMPAIGN,
                observe_content=lambda _: next(content_frames),
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
