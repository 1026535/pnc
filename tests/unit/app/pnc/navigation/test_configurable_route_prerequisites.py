"""Typed configurable occupants; reviewed edges still require fresh body evidence."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationEdge,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError
from pnc_automation.core.errors import SelectorResolutionError
from tests.support.pnc.navigation.core_frames import observation
from tests.support.pnc.navigation.core_home import camera_home_frame, measured_building_object


_NOW = datetime(2026, 9, 29, tzinfo=UTC)


def _body(target: HomeCityObjectId, slot: int, *, x: int = 200):
    return replace(
        measured_building_object(
            target, bounds=Bounds(x - 20, 380, 40, 40), action_point=(x, 400),
            action_bounds=Bounds(x - 5, 395, 10, 10),
        ),
        home_city_slot=HomeCitySlotSelector(slot),
    )


def _controlled_hall_core():
    """Model a Hall endpoint only in this fake to isolate acquisition mechanics."""
    actions = []
    frames = iter(replace(observation(ScreenType.PNC_ALLIANCE_HALL),
                          captured_at=_NOW + timedelta(seconds=i)) for i in (10, 11))
    core = NavigationCore(
        SimpleNamespace(execute_action=lambda action, before: actions.append(action) or True),
        lambda _: next(frames),
        (NavigationEdge(ScreenType.PNC_ALLIANCE_HALL, UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        frozenset({ScreenType.PNC_HOME_CITY})),),
        NavigationPolicy(max_observations=4), sleep=lambda _: None,
    )
    return core, actions


def _hall_live_pose(objects=(), *, second: int, image_size=(900, 1600)):
    """Model the saved 0054/0055 endpoint pose with independently supplied bodies."""
    return camera_home_frame(
        objects, translation=(-628, -401), zoom=0.74, image_size=image_size,
        captured_at=_NOW + timedelta(seconds=second),
    )


def _hall_slot13_body():
    return replace(
        measured_building_object(
            HomeCityObjectId.ALLIANCE_HALL,
            bounds=Bounds(658, 582, 120, 133), action_point=(707, 675),
            action_bounds=Bounds(699, 668, 15, 15),
        ),
        home_city_slot=HomeCitySlotSelector(13),
    )


class ConfigurableRoutePrerequisiteTests(unittest.TestCase):
    def test_hall_reacquisition_uses_reference_band_for_scaled_frame(self) -> None:
        core, actions = _controlled_hall_core()
        body = replace(
            _hall_slot13_body(), bounds=Bounds(395, 349, 72, 80),
            action_point=(424, 405), action_bounds=Bounds(419, 400, 9, 9),
        )
        observed = Mock(side_effect=(
            _hall_live_pose((body,), second=0, image_size=(540, 960)),
            _hall_live_pose(second=1, image_size=(540, 960)),
            _hall_live_pose((body,), second=2, image_size=(540, 960)),
        ))
        core.open_building(
            HomeCityObjectId.ALLIANCE_HALL, observe_content=observed,
            home_city_slot=HomeCitySlotSelector(13),
        )
        self.assertEqual(3, observed.call_count)
        self.assertEqual(1, len(actions))
        self.assertEqual((424, 405), actions[0].target_point)

    def test_hall_exact_slot_reacquires_current_body_after_endpoint_overlay(self) -> None:
        core, actions = _controlled_hall_core()
        observed = Mock(side_effect=(
            _hall_live_pose((_hall_slot13_body(),), second=0),
            _hall_live_pose(second=1),
            _hall_live_pose((_hall_slot13_body(),), second=2),
        ))
        core.open_building(
            HomeCityObjectId.ALLIANCE_HALL, observe_content=observed,
            home_city_slot=HomeCitySlotSelector(13),
        )
        self.assertEqual(3, observed.call_count)
        self.assertEqual(1, len(actions))
        self.assertEqual((707, 675), actions[0].target_point)
        self.assertEqual(HomeCitySlotSelector(13), actions[0].expected_object.home_city_slot)

    def test_hall_exact_slot_still_refuses_when_body_remains_absent(self) -> None:
        core, actions = _controlled_hall_core()
        observed = Mock(side_effect=(
            _hall_live_pose((_hall_slot13_body(),), second=0),
            _hall_live_pose(second=1),
            _hall_live_pose(second=2),
        ))
        with self.assertRaisesRegex(HomeCityScanError, "No qualified pan remains"):
            core.open_building(
                HomeCityObjectId.ALLIANCE_HALL, observe_content=observed,
                home_city_slot=HomeCitySlotSelector(13),
            )
        self.assertEqual(3, observed.call_count)
        self.assertEqual([], actions)

    def test_hall_exact_slot_does_not_reacquire_over_other_measured_occupant(self) -> None:
        core, actions = _controlled_hall_core()
        other = replace(_hall_slot13_body(), metadata={
            "home_city_object_id": HomeCityObjectId.MARKET.value,
        })
        observed = Mock(side_effect=(
            _hall_live_pose((_hall_slot13_body(),), second=0),
            _hall_live_pose((other,), second=1),
        ))
        with self.assertRaisesRegex(HomeCityScanError, "No qualified pan remains"):
            core.open_building(
                HomeCityObjectId.ALLIANCE_HALL, observe_content=observed,
                home_city_slot=HomeCitySlotSelector(13),
            )
        self.assertEqual(2, observed.call_count)
        self.assertEqual([], actions)

    def test_hall_reacquisition_refuses_changed_endpoint(self) -> None:
        core, actions = _controlled_hall_core()
        reacquired = _hall_live_pose((_hall_slot13_body(),), second=2)
        changed = replace(
            reacquired,
            spatial_surface=replace(
                reacquired.spatial_surface,
                home_city_view=replace(
                    reacquired.spatial_surface.home_city_view,
                    calibration_id="other_endpoint",
                ),
            ),
        )
        observed = Mock(side_effect=(
            _hall_live_pose((_hall_slot13_body(),), second=0),
            _hall_live_pose(second=1),
            changed,
        ))
        with self.assertRaisesRegex(HomeCityScanError, "normalized endpoint"):
            core.open_building(
                HomeCityObjectId.ALLIANCE_HALL, observe_content=observed,
                home_city_slot=HomeCitySlotSelector(13),
            )
        self.assertEqual(3, observed.call_count)
        self.assertEqual([], actions)

    def test_reviewed_routes_admit_public_entries_that_fail_closed_on_body(self) -> None:
        """The reviewed edges qualify both types; missing fresh body evidence still refuses.

        Route review now passes for Market and Alliance Hall, so the measured
        scan alone decides: a frame carrying neither occupant stops typed
        without any input on either public entry.
        """
        for target in (HomeCityObjectId.ALLIANCE_HALL, HomeCityObjectId.MARKET):
            for method in ("open_building", "open_visible_building"):
                with self.subTest(target=target, method=method):
                    actuator = Mock()
                    content = Mock(side_effect=(
                        camera_home_frame(captured_at=_NOW + timedelta(seconds=index))
                        for index in range(6)
                    ))
                    observer = Mock()
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
                        with self.assertRaisesRegex(HomeCityScanError, message):
                            getattr(core, method)(
                                target, observe_content=content,
                                home_city_slot=HomeCitySlotSelector(11),
                            )
                    actuator.execute_action.assert_not_called()
                    observer.assert_not_called()

    def test_slot11_hall_uses_fresh_identity_and_point_among_other_occupants(self) -> None:
        core, actions = _controlled_hall_core()
        bodies = (_body(HomeCityObjectId.ALLIANCE_HALL, 11),
                  _body(HomeCityObjectId.BLACKSMITH, 12, x=250),
                  _body(HomeCityObjectId.MARKET, 13, x=300))
        fresh = (_body(HomeCityObjectId.ALLIANCE_HALL, 11, x=220), *bodies[1:])
        frames = iter((
            camera_home_frame(bodies, captured_at=_NOW),
            camera_home_frame(fresh, captured_at=_NOW + timedelta(seconds=1)),
        ))
        core.open_building(HomeCityObjectId.ALLIANCE_HALL, observe_content=lambda _: next(frames),
                           home_city_slot=HomeCitySlotSelector(11))
        self.assertEqual(1, len(actions))
        self.assertEqual((220, 400), actions[0].target_point)
        self.assertEqual(HomeCitySlotSelector(11), actions[0].expected_object.home_city_slot)
        self.assertEqual("alliance_hall", actions[0].expected_object.metadata["home_city_object_id"])

    def test_same_slot_changed_occupant_refuses_after_callback_without_tap(self) -> None:
        core, actions = _controlled_hall_core()
        bodies = (_body(HomeCityObjectId.ALLIANCE_HALL, 11),)
        frames = iter((
            camera_home_frame(bodies, captured_at=_NOW),
            camera_home_frame(bodies, captured_at=_NOW + timedelta(seconds=1)),
            camera_home_frame((_body(HomeCityObjectId.MARKET, 11),),
                              captured_at=_NOW + timedelta(seconds=2)),
        ))
        acquired = []
        with self.assertRaisesRegex(RuntimeError, "absent or ambiguous"):
            core.open_building(HomeCityObjectId.ALLIANCE_HALL, observe_content=lambda _: next(frames),
                               on_target_acquired=acquired.append)
        self.assertEqual(HomeCitySlotSelector(11), acquired[0].home_city_slot)
        self.assertEqual([], actions)
