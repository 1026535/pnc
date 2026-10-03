"""Navigation core buildings tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeAction,
    TapAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityZoomStatus
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectSourceKind,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    home_city_scan_step_budget,
    home_city_scan_steps,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_home import (
    camera_home_frame,
    home_building_frame,
    measured_building_object,
    qualified_pan_step,
)
from tests.support.pnc.navigation.core_mail import mail_frame
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_trial_building_opens_category_list_and_has_measured_return(self):
        target = measured_building_object(
            HomeCityObjectId.TOWER_OF_TRIAL,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime.now(UTC)
        content_frames = iter(
            camera_home_frame((target,), captured_at=now + timedelta(seconds=index))
            for index in (1, 2)
        )
        frames = iter(
            mail_frame(ScreenType.PNC_TRIAL_CHALLENGE, captured_at=now + timedelta(seconds=index))
            for index in (3, 4)
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(frames), reviewed_navigation_edges(), sleep=lambda _: None,
        )
        result = core.open_visible_building(
            HomeCityObjectId.TOWER_OF_TRIAL,
            observe_content=lambda _: next(content_frames),
        )
        self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertEqual(target.action_point, actuator.actions[0].target_point)


    def test_building_uses_observed_point_and_rejects_absent_or_duplicate_target(self):
        target = measured_building_object(
            HomeCityObjectId.GODDESS_STATUE,
            bounds=Bounds(220, 470, 110, 110),
            action_point=(275, 524),
            action_bounds=Bounds(269, 518, 12, 12),
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            camera_home_frame((target,), captured_at=now + timedelta(seconds=index))
            for index in (1, 2)
        )
        core, actuator, _ = self.make_core([
            observation(ScreenType.PNC_GODDESS_STATUE), observation(ScreenType.PNC_GODDESS_STATUE),
        ])
        core.open_visible_building(
            HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: next(content_frames))
        self.assertEqual(len(actuator.actions), 1)
        self.assertEqual(actuator.actions[0].target_point, (275, 524))
        for bodies in ((), (target, target)):
            core, actuator, _ = self.make_core([])
            frames = iter(
                camera_home_frame(bodies, captured_at=now + timedelta(seconds=index))
                for index in (1, 2)
            )
            with self.assertRaisesRegex(RuntimeError, 'absent or ambiguous'):
                core.open_visible_building(
                    HomeCityObjectId.GODDESS_STATUE, observe_content=lambda _: next(frames))
            self.assertEqual(actuator.actions, [])


    def test_castle_building_opens_from_observed_point_and_returns_home_by_template_back(self):
        target = measured_building_object(
            HomeCityObjectId.CASTLE,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)

        def castle_frame(captured_at: datetime) -> Observation:
            return replace(
                observation(ScreenType.PNC_CASTLE),
                visible_elements={
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT: VisibleElement(
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        Bounds(22, 8, 58, 38),
                        0.99,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    ),
                },
                image_size=(540, 960),
                captured_at=captured_at,
            )

        def home_frame(captured_at: datetime) -> Observation:
            return replace(
                observation(ScreenType.PNC_HOME_CITY),
                image_size=(540, 960),
                captured_at=captured_at,
            )

        content_frames = iter(
            camera_home_frame((target,), captured_at=now + timedelta(seconds=index))
            for index in (1, 2)
        )
        frames = iter(
            (
                castle_frame(now + timedelta(seconds=3)),
                castle_frame(now + timedelta(seconds=4)),
                castle_frame(now + timedelta(seconds=5)),
                castle_frame(now + timedelta(seconds=6)),
                home_frame(now + timedelta(seconds=7)),
                home_frame(now + timedelta(seconds=8)),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        opened = core.open_visible_building(
            HomeCityObjectId.CASTLE,
            observe_content=lambda _: next(content_frames),
        )
        returned = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertEqual(ScreenType.PNC_CASTLE, opened.screen_type)
        self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((270, 520), actuator.actions[0].target_point)
        self.assertEqual(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, actuator.actions[1].selector_id)


    def test_public_home_scan_sequence_and_budget_match_canonical_navigator(self):
        steps = home_city_scan_steps()

        self.assertEqual(6, len(steps))
        self.assertEqual(18, home_city_scan_step_budget())
        self.assertEqual(
            (0.45, 0.54, 0.45, 0.26),
            (steps[-1].start_x_ratio, steps[-1].start_y_ratio, steps[-1].end_x_ratio, steps[-1].end_y_ratio),
        )


    def test_reviewed_public_entry_preserves_exact_slot_and_returns_home(self) -> None:
        """Reviewed routes compose public body acquisition with the measured return.

        A fresh qualified Home capture -> a measured typed body at the exact
        requested slot -> one observed-point tap. A separate navigation call
        follows the reviewed typed Back edge to Home. Support slots 11/12/13
        interchange Blacksmith, Market and Alliance Hall; the current
        observed occupant binds identity per request, never a global mapping.
        """
        for method in ("open_building", "open_visible_building"):
            for target, slot, screen in (
                (HomeCityObjectId.INFANTRY_BARRACKS, 5, ScreenType.PNC_INFANTRY_BARRACKS),
                (HomeCityObjectId.RANGED_BARRACKS, 7, ScreenType.PNC_RANGED_BARRACKS),
                (HomeCityObjectId.HALL_OF_WAR, 14, ScreenType.PNC_HALL_OF_WAR),
                (HomeCityObjectId.BLACKSMITH, 12, ScreenType.PNC_BLACKSMITH),
                (HomeCityObjectId.MARKET, 11, ScreenType.PNC_MARKET),
                (HomeCityObjectId.MARKET, 12, ScreenType.PNC_MARKET),
                (HomeCityObjectId.MARKET, 13, ScreenType.PNC_MARKET),
                (HomeCityObjectId.ALLIANCE_HALL, 11, ScreenType.PNC_ALLIANCE_HALL),
                (HomeCityObjectId.ALLIANCE_HALL, 12, ScreenType.PNC_ALLIANCE_HALL),
                (HomeCityObjectId.ALLIANCE_HALL, 13, ScreenType.PNC_ALLIANCE_HALL),
            ):
                with self.subTest(method=method, target=target):
                    selector = HomeCitySlotSelector(slot)
                    body = replace(
                        measured_building_object(
                            target,
                            bounds=Bounds(220, 470, 100, 100),
                            action_point=(270, 520),
                            action_bounds=Bounds(264, 514, 12, 12),
                        ),
                        home_city_slot=selector,
                    )
                    now = datetime(2026, 9, 29, tzinfo=UTC)
                    content_frames = iter(
                        camera_home_frame((body,), captured_at=now + timedelta(seconds=index))
                        for index in (1, 2)
                    )
                    back = VisibleElement(
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        Bounds(22, 8, 58, 38),
                        0.99,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    )
                    endpoint = replace(
                        observation(screen),
                        visible_elements={UiElementId.PNC_BACK_BUTTON_TOP_LEFT: back},
                        image_size=(540, 960),
                    )
                    frames = iter(
                        [replace(endpoint, captured_at=now + timedelta(seconds=index))
                         for index in (3, 4, 5, 6)]
                        + [replace(observation(ScreenType.PNC_HOME_CITY),
                                   captured_at=now + timedelta(seconds=index))
                           for index in (7, 8)]
                    )
                    actuator = Actuator()
                    core = NavigationCore(
                        actuator, lambda _: next(frames), reviewed_navigation_edges(),
                        NavigationPolicy(max_observations=4), sleep=lambda _: None,
                    )

                    opened = getattr(core, method)(
                        target, home_city_slot=selector,
                        observe_content=lambda _: next(content_frames),
                        entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                    )
                    returned = core.navigate(ScreenType.PNC_HOME_CITY)

                    self.assertEqual(screen, opened.screen_type)
                    self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
                    self.assertEqual(2, len(actuator.actions))
                    self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
                    self.assertEqual(body, actuator.actions[0].expected_object)
                    self.assertEqual(selector, actuator.actions[0].expected_object.home_city_slot)
                    self.assertEqual(body.action_point, actuator.actions[0].target_point)
                    self.assertEqual(UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                                     actuator.actions[1].selector_id)


    def test_open_building_visible_target_uses_no_scan_gesture(self):
        """Hero Hall retains the direct-visible route: a current measured body needs no pan."""
        target = measured_building_object(
            HomeCityObjectId.HERO_HALL,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((target,), captured_at=now),
                camera_home_frame((target,), captured_at=now + timedelta(seconds=1)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_HERO_HALL),
                observation(ScreenType.PNC_HERO_HALL),
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

        result = core.open_building(
            HomeCityObjectId.HERO_HALL,
            observe_content=lambda _: next(content_frames),
        )

        self.assertEqual(ScreenType.PNC_HERO_HALL, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((270, 520), actuator.actions[0].target_point)


    def test_unqualified_offscreen_building_does_not_replay_the_old_scan(self):
        core, actuator, _ = self.make_core([])
        now = datetime(2026, 9, 12, tzinfo=UTC)
        capture = Mock(side_effect=(
            camera_home_frame(captured_at=now),
            camera_home_frame(captured_at=now + timedelta(seconds=1)),
        ))
        with self.assertRaisesRegex(RuntimeError, "no qualified offscreen"):
            core.open_building(HomeCityObjectId.HERO_HALL, observe_content=capture)
        self.assertEqual(2, capture.call_count)
        self.assertEqual([], actuator.actions)


    def test_direct_visible_building_loss_before_reacquisition_sends_no_input(self):
        target = measured_building_object(
            HomeCityObjectId.HERO_HALL,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime(2026, 9, 22, tzinfo=UTC)
        frames = iter((camera_home_frame((target,), captured_at=now),
                       camera_home_frame(captured_at=now + timedelta(seconds=1))))
        core, actuator, _ = self.make_core([])
        with self.assertRaisesRegex(RuntimeError, "no qualified offscreen"):
            core.open_building(HomeCityObjectId.HERO_HALL,
                               observe_content=lambda _: next(frames))
        self.assertEqual([], actuator.actions)


    def test_unqualified_building_in_fixed_hud_region_sends_no_input(self):
        target = measured_building_object(
            HomeCityObjectId.HERO_HALL,
            bounds=Bounds(380, 620, 120, 100),
            action_point=(434, 654),
            action_bounds=Bounds(428, 648, 12, 12),
        )
        now = datetime(2026, 9, 12, tzinfo=UTC)
        frames = iter((camera_home_frame((target,), captured_at=now),
                       camera_home_frame((target,), captured_at=now + timedelta(seconds=1))))
        core, actuator, _ = self.make_core([])
        with self.assertRaisesRegex(RuntimeError, "no qualified offscreen"):
            core.open_building(HomeCityObjectId.HERO_HALL,
                               observe_content=lambda _: next(frames))
        self.assertEqual([], actuator.actions)


    def test_open_building_fails_closed_for_unsafe_scan_frames_without_swipe(self):
        """Malformed current body evidence on the normalized frame stops before any input."""
        now = datetime(2026, 9, 12, tzinfo=UTC)
        no_point = replace(
            measured_building_object(HomeCityObjectId.HERO_HALL),
            action_point=None,
            action_bounds=None,
        )
        out_of_image = replace(
            measured_building_object(HomeCityObjectId.HERO_HALL),
            action_point=(540, 520),
            action_bounds=None,
        )
        malformed = replace(
            measured_building_object(HomeCityObjectId.HERO_HALL),
            action_point=("bad", 520),  # type: ignore[arg-type]
            action_bounds=None,
        )
        second = measured_building_object(
            HomeCityObjectId.HERO_HALL,
            bounds=Bounds(60, 470, 80, 80),
            action_point=(100, 500),
            action_bounds=Bounds(94, 494, 12, 12),
        )
        cases = (
            (camera_home_frame(captured_at=now, image_size=None), "image dimensions"),
            (camera_home_frame((no_point,), captured_at=now), "action point"),
            (camera_home_frame((out_of_image,), captured_at=now), "out-of-image"),
            (camera_home_frame((malformed,), captured_at=now), "malformed"),
            (camera_home_frame((measured_building_object(HomeCityObjectId.HERO_HALL), second), captured_at=now), "ambiguous"),
        )
        for defect, message in cases:
            with self.subTest(message=message):
                frames = iter((camera_home_frame(captured_at=now - timedelta(seconds=1)), defect))
                actuator = Actuator()
                core = NavigationCore(
                    actuator,
                    lambda _: observation(ScreenType.PNC_HERO_HALL),
                    reviewed_navigation_edges(),
                    NavigationPolicy(max_observations=4),
                    sleep=lambda _: None,
                )
                with self.assertRaisesRegex(RuntimeError, message):
                    core.open_building(
                        HomeCityObjectId.HERO_HALL,
                        observe_content=lambda _: next(frames),
                    )
                self.assertEqual([], actuator.actions)


    def test_open_building_stops_scan_on_unknown_popup_or_stale_follow_up(self):
        now = datetime(2026, 9, 12, tzinfo=UTC)
        for follow_up in (
            Observation(screen_type=ScreenType.UNKNOWN, visible_elements={}, captured_at=now + timedelta(seconds=2)),
            Observation(screen_type=ScreenType.PNC_BAG, visible_elements={}, captured_at=now + timedelta(seconds=2)),
            home_building_frame(captured_at=now, blocked=False),
            home_building_frame(captured_at=now + timedelta(seconds=2), blocked=True),
        ):
            with self.subTest(screen=follow_up.screen_type, blocked=follow_up.blocking_popup):
                actuator = Actuator()
                content_frames = iter((
                    camera_home_frame(captured_at=now),
                    camera_home_frame(captured_at=now + timedelta(seconds=1)),
                    follow_up,
                ))
                core = NavigationCore(
                    actuator,
                    lambda _: observation(ScreenType.PNC_INSTITUTE),
                    reviewed_navigation_edges(),
                    NavigationPolicy(max_observations=4),
                    sleep=lambda _: None,
                )
                step = qualified_pan_step(
                    "up", axis="y", goal_atlas=(982, 1800),
                    reason="pan_home_city_camera_institute_y",
                )
                with patch(
                    "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
                    return_value=step,
                ):
                    with self.assertRaises(RuntimeError):
                        core.open_building(
                            HomeCityObjectId.INSTITUTE,
                            observe_content=lambda _: next(content_frames),
                        )
                self.assertEqual(1, len(actuator.actions))
                self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_read_only_collecting_entry_refuses_before_observation(self) -> None:
        """An authored body and route cannot waive a read-only effect."""
        for target in (
            HomeCityObjectId.TRAP_WORKSHOP,
            HomeCityObjectId.FARM,
            HomeCityObjectId.LUMBER_CAMP,
            HomeCityObjectId.MOON_WELL,
            HomeCityObjectId.IRON_MINE,
            HomeCityObjectId.GOLD_MINE,
            HomeCityObjectId.INFANTRY_BARRACKS,
            HomeCityObjectId.CAVALRY_BARRACKS,
            HomeCityObjectId.RANGED_BARRACKS,
            HomeCityObjectId.SIEGE_FACTORY,
        ):
            for method in ("open_building", "open_visible_building"):
                with self.subTest(target=target, method=method):
                    observed = Mock()
                    actuator = Actuator()
                    core = NavigationCore(
                        actuator, observed, reviewed_navigation_edges(),
                        NavigationPolicy(max_observations=4), sleep=lambda _: None,
                    )
                    with self.assertRaisesRegex(PermissionError, "automatically collect completed output"):
                        getattr(core, method)(target, observe_content=observed)
                    observed.assert_not_called()
                    self.assertEqual([], actuator.actions)

    def test_nonspending_military_entry_keeps_measured_body_and_exact_endpoint(self) -> None:
        target = measured_building_object(
            HomeCityObjectId.RANGED_BARRACKS,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime.now(UTC)
        content_frames = iter(
            camera_home_frame((target,), captured_at=now + timedelta(seconds=index))
            for index in (1, 2)
        )
        destination_frames = iter(
            mail_frame(ScreenType.PNC_RANGED_BARRACKS, captured_at=now + timedelta(seconds=index))
            for index in (3, 4)
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(destination_frames), reviewed_navigation_edges(),
            sleep=lambda _: None,
        )

        result = core.open_visible_building(
            HomeCityObjectId.RANGED_BARRACKS,
            observe_content=lambda _: next(content_frames),
            entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
        )

        self.assertEqual(ScreenType.PNC_RANGED_BARRACKS, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual(target.action_point, actuator.actions[0].target_point)

    def test_open_building_rejects_unsupported_route_before_observation(self) -> None:
        """An unqualified endpoint cannot dispatch its potentially mutating body tap."""
        for target in (
            HomeCityObjectId.BANK,
            HomeCityObjectId.CAVALRY_BARRACKS,
            HomeCityObjectId.SIEGE_FACTORY,
            HomeCityObjectId.FARM,
            HomeCityObjectId.LUMBER_CAMP,
            HomeCityObjectId.MOON_WELL,
            HomeCityObjectId.IRON_MINE,
            HomeCityObjectId.GOLD_MINE,
            HomeCityObjectId.TRAP_WORKSHOP,
            HomeCityObjectId.CAVALRY_BARRACKS,
            HomeCityObjectId.SIEGE_FACTORY,
        ):
            for method in ("open_building", "open_visible_building"):
                with self.subTest(target=target, method=method):
                    observed = Mock()
                    actuator = Actuator()
                    core = NavigationCore(
                        actuator, observed, reviewed_navigation_edges(),
                        NavigationPolicy(max_observations=4), sleep=lambda _: None,
                    )

                    with self.assertRaisesRegex(ValueError, "return route"):
                        getattr(core, method)(
                            target, observe_content=observed,
                            entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                        )

                    observed.assert_not_called()
                    self.assertEqual([], actuator.actions)


    def test_reviewed_support_routes_refuse_wrong_occupant_or_slot_without_input(self) -> None:
        """A foreign occupant or a wrong exact slot never authorizes a body tap.

        Slots 11/12/13 interchange Blacksmith, Market and Alliance Hall; only
        the requested type's measured body on the selected slot qualifies.
        """
        for method in ("open_building", "open_visible_building"):
            for target, occupant, occupant_slot, selector in (
                (HomeCityObjectId.MARKET, HomeCityObjectId.BLACKSMITH, 11, None),
                (HomeCityObjectId.ALLIANCE_HALL, HomeCityObjectId.BLACKSMITH, 11, None),
                (HomeCityObjectId.MARKET, HomeCityObjectId.MARKET, 11,
                 HomeCitySlotSelector(12)),
                (HomeCityObjectId.MARKET, HomeCityObjectId.BLACKSMITH, 11,
                 HomeCitySlotSelector(11)),
            ):
                with self.subTest(method=method, target=target, occupant=occupant,
                                  selector=selector):
                    body = replace(
                        measured_building_object(
                            occupant,
                            bounds=Bounds(220, 470, 100, 100),
                            action_point=(270, 520),
                            action_bounds=Bounds(264, 514, 12, 12),
                        ),
                        home_city_slot=HomeCitySlotSelector(occupant_slot),
                    )
                    now = datetime(2026, 9, 30, tzinfo=UTC)
                    content_frames = iter(
                        camera_home_frame((body,), captured_at=now + timedelta(seconds=index))
                        for index in range(6)
                    )
                    observer = Mock()
                    actuator = Actuator()
                    core = NavigationCore(
                        actuator, observer, reviewed_navigation_edges(),
                        NavigationPolicy(max_observations=4), sleep=lambda _: None,
                    )
                    message = ("No qualified pan remains" if method == "open_building"
                               else "absent or ambiguous")
                    with patch(
                        "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
                        side_effect=SelectorResolutionError("no qualified lane remains"),
                    ):
                        with self.assertRaisesRegex(RuntimeError, message):
                            getattr(core, method)(
                                target,
                                observe_content=lambda _: next(content_frames),
                                home_city_slot=selector,
                            )
                    self.assertEqual([], actuator.actions)
                    observer.assert_not_called()


    def test_institute_measured_open_taps_body_verified_target_without_queue_detour(self):
        """A localized, body-verified in-band Institute opens with one tap and no focus detour."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        acquired: list[DetectedSpatialObject] = []
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((target,), captured_at=now),
                camera_home_frame((target,), captured_at=now + timedelta(seconds=1)),
                camera_home_frame((target,), captured_at=now + timedelta(seconds=2)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_INSTITUTE),
                observation(ScreenType.PNC_INSTITUTE),
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

        result = core.open_building(
            HomeCityObjectId.INSTITUTE,
            observe_content=lambda _: next(content_frames),
            on_target_acquired=acquired.append,
        )

        self.assertEqual(ScreenType.PNC_INSTITUTE, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((154, 193), actuator.actions[0].target_point)
        self.assertEqual([target], acquired)


    def test_open_building_measured_pans_once_then_reacquires_and_taps(self):
        """An out-of-band camera target produces one measured pan, fresh proof, then one tap."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame(captured_at=now),
                camera_home_frame(captured_at=now + timedelta(seconds=1)),
                camera_home_frame((target,), translation=(-1000, -710), captured_at=now + timedelta(seconds=2)),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_INSTITUTE),
                observation(ScreenType.PNC_INSTITUTE),
            )
        )
        records: list[dict[str, object]] = []
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
            record=records.append,
        )

        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1800),
            reason="pan_home_city_camera_institute_y",
        )
        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ) as planner:
            result = core.open_building(
                HomeCityObjectId.INSTITUTE,
                observe_content=lambda _: next(content_frames),
            )

        self.assertEqual(ScreenType.PNC_INSTITUTE, result.screen_type)
        self.assertEqual(1, planner.call_count)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertEqual("pan_home_city_camera_institute_y", actuator.actions[0].reason)
        self.assertIsInstance(actuator.actions[1], TapSpatialObjectAction)
        self.assertEqual((154, 193), actuator.actions[1].target_point)
        self.assertIn("pending_building_pan", {event["event"] for event in records})


    def test_open_building_measured_replans_after_partial_pan_before_single_tap(self):
        """A partial first movement requires another measured pan before acquisition."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        frames = iter((
            camera_home_frame(captured_at=now),
            camera_home_frame(captured_at=now + timedelta(seconds=1)),
            camera_home_frame(translation=(-732, -78), captured_at=now + timedelta(seconds=2)),
            camera_home_frame((target,), translation=(-1000, -710), captured_at=now + timedelta(seconds=3)),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_INSTITUTE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1800),
            reason="pan_home_city_camera_institute_y",
        )
        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            side_effect=[step, step],
        ) as planner:
            result = core.open_building(
                HomeCityObjectId.INSTITUTE, observe_content=lambda _: next(frames)
            )
        self.assertEqual(ScreenType.PNC_INSTITUTE, result.screen_type)
        self.assertEqual(2, planner.call_count)
        self.assertEqual(3, len(actuator.actions))
        self.assertTrue(all(isinstance(action, SwipeAction) for action in actuator.actions[:2]))
        self.assertIsInstance(actuator.actions[2], TapSpatialObjectAction)
        self.assertEqual((154, 193), actuator.actions[2].target_point)


    def test_open_building_measured_lost_localization_after_pan_stops_without_tap(self):
        """An unlocalized pose after a dispatched pan gets bounded passive recovery, never a tap."""
        now = datetime(2026, 9, 15, tzinfo=UTC)
        observed = Mock(side_effect=(
            camera_home_frame(captured_at=now),
            camera_home_frame(captured_at=now + timedelta(seconds=1)),
            camera_home_frame(localized=False, captured_at=now + timedelta(seconds=2)),
            camera_home_frame(localized=False, captured_at=now + timedelta(seconds=3)),
            camera_home_frame(localized=False, captured_at=now + timedelta(seconds=4)),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_INSTITUTE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1800),
            reason="pan_home_city_camera_institute_y",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ):
            with self.assertRaisesRegex(RuntimeError, "could not be reacquired"):
                core.open_building(HomeCityObjectId.INSTITUTE, observe_content=observed)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_open_building_measured_never_taps_ocr_only_targets(self):
        """A correctly spelled label without a current-frame body match cannot authorize a tap."""
        label_only = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            source_kind=SpatialObjectSourceKind.OCR,
            metadata={"home_city_object_id": HomeCityObjectId.INSTITUTE.value},
        )
        core, actuator, _ = self.make_core([])
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content = iter((
            camera_home_frame((label_only,), captured_at=now),
            camera_home_frame((label_only,), captured_at=now + timedelta(seconds=1)),
        ))

        with self.assertRaisesRegex(RuntimeError, "no current-frame match|absent or ambiguous"):
            core.open_visible_building(
                HomeCityObjectId.INSTITUTE,
                observe_content=lambda _: next(content),
                require_measured=True,
            )
        self.assertEqual(actuator.actions, [])


    def test_open_building_measured_stalled_pan_fails_closed_before_tap(self):
        """A post-pan frame with the same translation proves no camera motion and blocks the tap."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame(captured_at=now),
                camera_home_frame(captured_at=now + timedelta(seconds=1)),
                camera_home_frame(
                    (target,), translation=(-532, 222), captured_at=now + timedelta(seconds=2),
                ),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_INSTITUTE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1800),
            reason="pan_home_city_camera_institute_y",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            side_effect=[step, SelectorResolutionError("no qualified lane remains")],
        ):
            with self.assertRaisesRegex(RuntimeError, "no camera movement"):
                core.open_building(
                    HomeCityObjectId.INSTITUTE,
                    observe_content=lambda _: next(content_frames),
                )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_open_building_zoom_change_after_pan_stops_without_replan_or_tap(self):
        """A measured zoom departure after normalization stops the scan; nothing is replayed."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame(captured_at=now),
                camera_home_frame(captured_at=now + timedelta(seconds=1)),
                camera_home_frame(
                    (target,), translation=(-778, 78), zoom=1.25,
                    captured_at=now + timedelta(seconds=2),
                ),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_INSTITUTE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(982, 1800),
            reason="pan_home_city_camera_institute_y",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ) as planner:
            with self.assertRaisesRegex(RuntimeError, "scale changed after normalization"):
                core.open_building(
                    HomeCityObjectId.INSTITUTE, observe_content=lambda _: next(content_frames),
                )
        self.assertEqual(1, planner.call_count)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_open_building_measured_small_zoom_drift_keeps_pan_progress(self):
        """A moved view center with zoom drift inside tolerance still passes the stall check."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        # View center moves from atlas (982, 578) toward the target while zoom
        # drifts to 1.01 — inside the 0.02 departure tolerance, so the pan is
        # judged on its measured movement, not the incidental scale noise.
        content_frames = iter(
            (
                camera_home_frame(captured_at=now),
                camera_home_frame(captured_at=now + timedelta(seconds=1)),
                camera_home_frame(
                    (target,), translation=(-878, -22), zoom=1.01,
                    captured_at=now + timedelta(seconds=2),
                ),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_INSTITUTE),
            reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "right", axis="x", goal_atlas=(1500, 778),
            reason="pan_home_city_camera_institute_x",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ):
            result = core.open_building(
                HomeCityObjectId.INSTITUTE, observe_content=lambda _: next(content_frames)
            )
        self.assertEqual(ScreenType.PNC_INSTITUTE, result.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)
        self.assertIsInstance(actuator.actions[1], TapSpatialObjectAction)
        self.assertEqual((154, 193), actuator.actions[1].target_point)


    def test_open_building_measured_wrong_destination_does_not_repeat_tap(self):
        """A tap that reaches a different screen is not repeated."""
        target = measured_building_object(HomeCityObjectId.INSTITUTE)
        now = datetime(2026, 9, 15, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((target,), captured_at=now),
                camera_home_frame((target,), captured_at=now + timedelta(seconds=1)),
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
                HomeCityObjectId.INSTITUTE,
                observe_content=lambda _: next(content_frames),
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)


_CHIP = UiElementId.PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP


def _provenanced_home_frame(
    objects: tuple = (),
    *,
    captured_at: datetime,
    capture_sequence: int,
    input_sequence: int = 0,
    chip: bool = False,
    chip_frame_ref: FrameRef | None = None,
    chip_source_screen: ScreenType | None = ScreenType.PNC_HOME_CITY,
    chip_source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE,
    calibration_id: str = "test_endpoint",
    zoom_status: HomeCityZoomStatus = HomeCityZoomStatus.AT_ENDPOINT,
) -> Observation:
    """Build one Home frame whose view/proof/element provenance is consistent."""

    ref = FrameRef(
        session_id="watchtower-test",
        session_epoch=1,
        capture_sequence=capture_sequence,
        input_sequence=input_sequence,
        captured_at=captured_at,
    )
    frame = camera_home_frame(objects, captured_at=captured_at, zoom_status=zoom_status)
    surface = frame.spatial_surface
    elements = {}
    if chip:
        elements[_CHIP] = VisibleElement(
            _CHIP, Bounds(624, 474, 78, 62), 0.99,
            source_kind=chip_source_kind,
            frame_ref=ref if chip_frame_ref is None else chip_frame_ref,
            source_screen=chip_source_screen,
            source_layout_id=frame.decision.layout_id,
        )
    return replace(
        frame,
        frame_ref=ref,
        visible_elements=elements,
        spatial_surface=replace(
            surface,
            camera_proof=replace(surface.camera_proof, frame_ref=ref),
            home_city_view=replace(
                surface.home_city_view, frame_ref=ref, calibration_id=calibration_id,
            ),
        ),
    )


class WatchtowerTwoHopTests(RecordedFramesCore, unittest.TestCase):
    """The Watchtower body tap only selects; a fresh chip frame authorizes entry."""

    def _body(self) -> DetectedSpatialObject:
        return replace(
            measured_building_object(
                HomeCityObjectId.WATCHTOWER,
                bounds=Bounds(220, 470, 100, 100),
                action_point=(270, 520),
                action_bounds=Bounds(264, 514, 12, 12),
            ),
            home_city_slot=HomeCitySlotSelector(4),
        )

    def _open(self, content_frames, destination_frames, *, slot=HomeCitySlotSelector(4)):
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(destination_frames), reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4), sleep=lambda _: None,
        )
        return core, actuator, core.open_building(
            HomeCityObjectId.WATCHTOWER,
            observe_content=lambda _: next(content_frames),
            home_city_slot=slot,
        )

    def test_body_tap_then_fresh_chip_opens_watchtower_panel(self) -> None:
        """Qualified body tap -> fresh selected Home -> measured chip -> stable panel."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=1, chip=True),
        ))
        destination_frames = iter((
            replace(observation(ScreenType.PNC_WATCHTOWER),
                    captured_at=now + timedelta(seconds=3)),
            replace(observation(ScreenType.PNC_WATCHTOWER),
                    captured_at=now + timedelta(seconds=4)),
        ))

        core, actuator, result = self._open(content_frames, destination_frames)

        self.assertEqual(ScreenType.PNC_WATCHTOWER, result.screen_type)
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual(body, actuator.actions[0].expected_object)
        self.assertEqual((270, 520), actuator.actions[0].target_point)
        self.assertIsInstance(actuator.actions[1], TapAction)
        self.assertEqual(_CHIP, actuator.actions[1].selector_id)

    def test_missing_chip_stops_after_body_tap_only(self) -> None:
        """A selected Home frame without the chip never authorizes a dependent tap."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=1),
        ))
        _, actuator, error = self._failing_open(content_frames)
        self.assertIsNotNone(error)
        self.assertRegex(str(error), "qualified current-frame Upgrade chip")
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)

    def _failing_open(self, content_frames):
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: observation(ScreenType.PNC_WATCHTOWER),
            reviewed_navigation_edges(), NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        error = None
        try:
            core.open_building(
                HomeCityObjectId.WATCHTOWER,
                observe_content=lambda _: next(content_frames),
                home_city_slot=HomeCitySlotSelector(4),
            )
        except RuntimeError as caught:
            error = caught
        return core, actuator, error

    def test_intervening_input_breaks_chip_authorization(self) -> None:
        """A foreign input between body tap and selected frame voids the chip."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=2, chip=True),
        ))
        _, actuator, error = self._failing_open(content_frames)
        self.assertIsNotNone(error)
        self.assertRegex(str(error), "intervening input")
        self.assertEqual(1, len(actuator.actions))

    def test_changed_calibration_rejects_chip_frame(self) -> None:
        """A changed Home calibration after the body tap stops the chip hop."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=1, chip=True,
                                    calibration_id="other_calibration"),
        ))
        _, actuator, error = self._failing_open(content_frames)
        self.assertIsNotNone(error)
        self.assertRegex(str(error), "normalized endpoint pose")
        self.assertEqual(1, len(actuator.actions))

    def test_off_endpoint_chip_frame_stops_before_chip_tap(self) -> None:
        """A non-endpoint zoom verdict on the selected frame stops the chip hop."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=1, chip=True,
                                    zoom_status=HomeCityZoomStatus.NOT_AT_ENDPOINT),
        ))
        _, actuator, error = self._failing_open(content_frames)
        self.assertIsNotNone(error)
        self.assertRegex(str(error), "scale changed")
        self.assertEqual(1, len(actuator.actions))

    def test_foreign_chip_provenance_stops_before_chip_tap(self) -> None:
        """Stale-frame or foreign-screen chip elements never authorize the tap."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        stale_ref = FrameRef(
            session_id="watchtower-test", session_epoch=1, capture_sequence=2,
            input_sequence=0, captured_at=now + timedelta(seconds=1),
        )
        for kwargs in (
            {"chip_frame_ref": stale_ref},
            {"chip_source_screen": ScreenType.PNC_WATCHTOWER},
            {"chip_source_kind": VisibleElementSourceKind.OCR},
        ):
            with self.subTest(defect=sorted(kwargs)):
                content_frames = iter((
                    _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
                    _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                            capture_sequence=2),
                    _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                            capture_sequence=3, input_sequence=1,
                                            chip=True, **kwargs),
                ))
                _, actuator, error = self._failing_open(content_frames)
                self.assertIsNotNone(error)
                self.assertRegex(str(error), "qualified current-frame Upgrade chip")
                self.assertEqual(1, len(actuator.actions))
                self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)

    def test_unexpected_destination_after_chip_raises(self) -> None:
        """An unexpected post-chip screen raises without replaying either tap."""
        body = self._body()
        now = datetime(2026, 10, 3, tzinfo=UTC)
        content_frames = iter((
            _provenanced_home_frame((body,), captured_at=now, capture_sequence=1),
            _provenanced_home_frame((body,), captured_at=now + timedelta(seconds=1),
                                    capture_sequence=2),
            _provenanced_home_frame((), captured_at=now + timedelta(seconds=2),
                                    capture_sequence=3, input_sequence=1, chip=True),
        ))
        destination_frames = iter((
            replace(observation(ScreenType.PNC_CASTLE),
                    captured_at=now + timedelta(seconds=3)),
            replace(observation(ScreenType.PNC_CASTLE),
                    captured_at=now + timedelta(seconds=4)),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(destination_frames), reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4), sleep=lambda _: None,
        )
        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            core.open_building(
                HomeCityObjectId.WATCHTOWER,
                observe_content=lambda _: next(content_frames),
                home_city_slot=HomeCitySlotSelector(4),
            )
        self.assertEqual(2, len(actuator.actions))
        self.assertIsInstance(actuator.actions[1], TapAction)

    def test_watchtower_returns_home_through_reviewed_back_edge(self) -> None:
        """The qualified Watchtower Back edge returns to Home like other buildings."""
        now = datetime(2026, 10, 3, tzinfo=UTC)
        back = VisibleElement(
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT, Bounds(33, 7, 104, 73), 0.99,
            source_kind=VisibleElementSourceKind.TEMPLATE,
        )

        def panel(captured_at: datetime) -> Observation:
            return replace(
                observation(ScreenType.PNC_WATCHTOWER),
                visible_elements={UiElementId.PNC_BACK_BUTTON_TOP_LEFT: back},
                captured_at=captured_at,
            )

        frames = iter((
            panel(now), panel(now + timedelta(seconds=1)),
            replace(observation(ScreenType.PNC_HOME_CITY),
                    captured_at=now + timedelta(seconds=2)),
            replace(observation(ScreenType.PNC_HOME_CITY),
                    captured_at=now + timedelta(seconds=3)),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(frames), reviewed_navigation_edges(),
            NavigationPolicy(max_observations=4), sleep=lambda _: None,
        )

        returned = core.navigate(ScreenType.PNC_HOME_CITY)

        self.assertEqual(ScreenType.PNC_HOME_CITY, returned.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertEqual(UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                         actuator.actions[0].selector_id)
