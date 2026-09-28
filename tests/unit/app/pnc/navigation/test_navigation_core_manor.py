"""Navigation core manor tests."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch
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
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_home import (
    _MANOR_RETURN_EDGE,
    camera_home_frame,
    measured_building_object,
    qualified_pan_step,
)
from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_manor_measured_open_taps_body_verified_target(self):
        """A localized, body-verified in-band Manor opens with one measured tap."""
        # Native PW02 body geometry scaled to 540x960: verified tap (511,722).
        target = measured_building_object(
            HomeCityObjectId.ILLUSORY_BEAST_MANOR,
            bounds=Bounds(271, 385, 79, 67),
            action_point=(307, 433),
            action_bounds=Bounds(301, 427, 12, 12),
        )
        acquired: list[DetectedSpatialObject] = []
        now = datetime(2026, 9, 21, tzinfo=UTC)
        content_frames = iter(
            (
                camera_home_frame((target,), translation=(-521, -1346), captured_at=now),
                camera_home_frame(
                    (target,), translation=(-521, -1346), captured_at=now + timedelta(seconds=1)
                ),
                camera_home_frame(
                    (target,), translation=(-521, -1346), captured_at=now + timedelta(seconds=2)
                ),
            )
        )
        destination_frames = iter(
            (
                observation(ScreenType.PNC_ILLUSORY_BEAST_MANOR),
                observation(ScreenType.PNC_ILLUSORY_BEAST_MANOR),
            )
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: next(destination_frames),
            (*reviewed_navigation_edges(), _MANOR_RETURN_EDGE),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )

        result = core.open_building(
            HomeCityObjectId.ILLUSORY_BEAST_MANOR,
            observe_content=lambda _: next(content_frames),
            on_target_acquired=acquired.append,
        )

        self.assertEqual(ScreenType.PNC_ILLUSORY_BEAST_MANOR, result.screen_type)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual((307, 433), actuator.actions[0].target_point)
        self.assertEqual([target], acquired)


    def test_manor_measured_lost_localization_after_pan_stops_without_tap(self):
        """The Manor is camera-qualified: a post-pan frame that cannot localize never reaches a tap."""
        now = datetime(2026, 9, 21, tzinfo=UTC)
        observed = Mock(side_effect=(
            camera_home_frame(translation=(-521, -1346), captured_at=now),
            camera_home_frame(translation=(-521, -1346), captured_at=now + timedelta(seconds=1)),
            camera_home_frame(
                translation=(-521, -1346), localized=False, captured_at=now + timedelta(seconds=2),
            ),
            camera_home_frame(
                translation=(-521, -1346), localized=False, captured_at=now + timedelta(seconds=3),
            ),
            camera_home_frame(
                translation=(-521, -1346), localized=False, captured_at=now + timedelta(seconds=4),
            ),
        ))
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_ILLUSORY_BEAST_MANOR),
            (*reviewed_navigation_edges(), _MANOR_RETURN_EDGE),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        step = qualified_pan_step(
            "up", axis="y", goal_atlas=(971, 1900),
            reason="pan_home_city_camera_illusory_beast_manor_y",
        )

        with patch(
            "pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step",
            return_value=step,
        ):
            with self.assertRaisesRegex(RuntimeError, "could not be reacquired"):
                core.open_building(HomeCityObjectId.ILLUSORY_BEAST_MANOR, observe_content=observed)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], SwipeAction)


    def test_manor_measured_never_taps_ocr_only_label(self):
        """A correctly spelled Manor label without a current-frame body cannot authorize a tap."""
        label_only = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(280, 470, 140, 30),
            action_point=(307, 433),
            source_kind=SpatialObjectSourceKind.OCR,
            metadata={"home_city_object_id": HomeCityObjectId.ILLUSORY_BEAST_MANOR.value},
        )
        actuator = Actuator()
        core = NavigationCore(
            actuator,
            lambda _: observation(ScreenType.PNC_ILLUSORY_BEAST_MANOR),
            (*reviewed_navigation_edges(), _MANOR_RETURN_EDGE),
            NavigationPolicy(max_observations=4),
            sleep=lambda _: None,
        )
        now = datetime(2026, 9, 21, tzinfo=UTC)
        content = iter((
            camera_home_frame((label_only,), translation=(-521, -1346), captured_at=now),
            camera_home_frame(
                (label_only,), translation=(-521, -1346), captured_at=now + timedelta(seconds=1),
            ),
        ))

        with self.assertRaisesRegex(RuntimeError, "no current-frame match|absent or ambiguous"):
            core.open_visible_building(
                HomeCityObjectId.ILLUSORY_BEAST_MANOR,
                observe_content=lambda _: next(content),
                require_measured=True,
            )
        self.assertEqual(actuator.actions, [])
