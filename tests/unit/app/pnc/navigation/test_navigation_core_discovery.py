"""Navigation core qualified building-body discovery tests."""

from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationPolicy,
    reviewed_navigation_edges,
)
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_home import (
    camera_home_frame,
    measured_building_object,
)


def _core(actuator: Actuator) -> NavigationCore:
    return NavigationCore(
        actuator,
        lambda _: observation(ScreenType.PNC_HOME_CITY),
        reviewed_navigation_edges(),
        NavigationPolicy(max_observations=6),
        sleep=lambda _: None,
    )


def _frames(targets, *, start: datetime, count: int = 4):
    """Yields increasing endpoint-localized Home frames carrying the objects."""

    return iter(
        camera_home_frame(targets, captured_at=start + timedelta(seconds=index))
        for index in range(count)
    )


class BuildingBodyDiscoveryTests(unittest.TestCase):
    def test_bank_body_entry_sends_one_measured_tap_and_returns_raw_follow_up(self):
        target = measured_building_object(
            HomeCityObjectId.BANK,
            bounds=Bounds(220, 470, 100, 100),
            action_point=(270, 520),
            action_bounds=Bounds(264, 514, 12, 12),
        )
        now = datetime(2026, 10, 1, tzinfo=UTC)
        content_frames = _frames((target,), start=now)
        follow_up = observation(ScreenType.UNKNOWN)
        prepared: list = []
        actuator = Actuator()
        source, action, after = _core(actuator).enter_building_body_for_discovery(
            HomeCityObjectId.BANK,
            entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
            observe_content=lambda _: next(content_frames),
            on_body_prepared=lambda src, act: prepared.append((src, act)),
            capture_follow_up=lambda _: follow_up,
        )
        self.assertEqual(1, len(prepared))
        self.assertIs(prepared[0][0], source)
        self.assertIs(prepared[0][1], action)
        self.assertIsInstance(action, TapSpatialObjectAction)
        self.assertEqual((270, 520), action.target_point)
        self.assertEqual("developmental_building_body_entry", action.reason)
        self.assertTrue(action.exact_geometry)
        self.assertEqual(1, len(actuator.actions))
        self.assertIs(actuator.actions[0], action)
        self.assertIs(after, follow_up)
        self.assertEqual(ScreenType.UNKNOWN, after.screen_type)

    def test_watchtower_body_entry_uses_the_direct_visible_qualification(self):
        target = measured_building_object(
            HomeCityObjectId.WATCHTOWER,
            bounds=Bounds(300, 400, 90, 90),
            action_point=(345, 445),
            action_bounds=Bounds(339, 439, 12, 12),
        )
        now = datetime(2026, 10, 1, tzinfo=UTC)
        content_frames = _frames((target,), start=now)
        follow_up = observation(ScreenType.UNKNOWN)
        actuator = Actuator()
        _source, action, after = _core(actuator).enter_building_body_for_discovery(
            HomeCityObjectId.WATCHTOWER,
            entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
            observe_content=lambda _: next(content_frames),
            on_body_prepared=lambda *_: None,
            capture_follow_up=lambda _: follow_up,
        )
        self.assertEqual((345, 445), action.target_point)
        self.assertEqual(1, len(actuator.actions))
        self.assertIs(after, follow_up)

    def test_collecting_building_entry_rejects_read_only_effect_before_input(self):
        actuator = Actuator()
        with self.assertRaises(PermissionError):
            _core(actuator).enter_building_body_for_discovery(
                HomeCityObjectId.FARM,
                entry_effect=WorkflowEffect.READ_ONLY,
                observe_content=lambda _: observation(ScreenType.PNC_HOME_CITY),
                on_body_prepared=lambda *_: None,
                capture_follow_up=lambda _: observation(ScreenType.PNC_HOME_CITY),
            )
        self.assertEqual([], actuator.actions)

    def test_absent_body_sends_no_tap(self):
        now = datetime(2026, 10, 1, tzinfo=UTC)
        content_frames = _frames((), start=now)
        actuator = Actuator()
        with self.assertRaisesRegex(HomeCityScanError, "no qualified"):
            _core(actuator).enter_building_body_for_discovery(
                HomeCityObjectId.WATCHTOWER,
                entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                observe_content=lambda _: next(content_frames),
                on_body_prepared=lambda *_: None,
                capture_follow_up=lambda _: observation(ScreenType.PNC_HOME_CITY),
            )
        self.assertEqual([], actuator.actions)

    def test_unlocalized_frame_sends_no_tap(self):
        target = measured_building_object(HomeCityObjectId.BANK)
        now = datetime(2026, 10, 1, tzinfo=UTC)
        content_frames = iter(
            camera_home_frame((target,), localized=False, captured_at=now + timedelta(seconds=index))
            for index in range(4)
        )
        actuator = Actuator()
        with self.assertRaises(HomeCityScanError):
            _core(actuator).enter_building_body_for_discovery(
                HomeCityObjectId.BANK,
                entry_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
                observe_content=lambda _: next(content_frames),
                on_body_prepared=lambda *_: None,
                capture_follow_up=lambda _: observation(ScreenType.PNC_HOME_CITY),
            )
        self.assertEqual([], actuator.actions)


if __name__ == "__main__":
    unittest.main()
