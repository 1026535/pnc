"""Typed configurable occupants; controlled routes do not qualify native edges."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

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


class ConfigurableRoutePrerequisiteTests(unittest.TestCase):
    def test_public_routes_remain_refused_before_capture(self) -> None:
        actuator = Mock()
        capture = Mock()
        core = NavigationCore(actuator, capture, reviewed_navigation_edges())
        for target in (HomeCityObjectId.ALLIANCE_HALL, HomeCityObjectId.MARKET):
            for method in (core.open_building, core.open_visible_building):
                with self.subTest(target=target, method=method.__name__):
                    with self.assertRaisesRegex(ValueError, "no reviewed return route"):
                        method(target, observe_content=capture, home_city_slot=HomeCitySlotSelector(11))
        capture.assert_not_called()
        actuator.execute_action.assert_not_called()

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
