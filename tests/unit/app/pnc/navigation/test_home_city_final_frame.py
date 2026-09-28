"""Final Home body input uses the latest qualified frame without a redundant scan."""

import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.navigation_core import NavigationCore, reviewed_navigation_edges
from pnc_automation.app.pnc.domain.action_requests import TapSpatialObjectAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError
from tests.unit.app.pnc.navigation.test_home_city_normalization import (
    _BODY, _TARGET, frame, home, operation,
)
from tests.support.pnc.navigation.core_frames import Actuator


class HomeFinalFrameTests(unittest.TestCase):
    def test_normalized_current_body_is_tapped_without_a_third_content_capture(self):
        source = home(1, objects=(_BODY,))
        content = Mock(side_effect=[home(0, objects=(_BODY,)), source])
        destinations = iter([
            frame(ScreenType.PNC_ILLUSORY_BEAST_MANOR, captured_at=home(2).captured_at),
            frame(ScreenType.PNC_ILLUSORY_BEAST_MANOR, captured_at=home(3).captured_at),
        ])
        actuator = Actuator()
        core = NavigationCore(actuator, lambda _: next(destinations), reviewed_navigation_edges(),
                              sleep=lambda _: None)
        result = core.open_building(_TARGET, observe_content=content)
        self.assertEqual(ScreenType.PNC_ILLUSORY_BEAST_MANOR, result.screen_type)
        self.assertEqual(2, content.call_count)
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapSpatialObjectAction)
        self.assertEqual(_BODY, actuator.actions[0].expected_object)

    def test_fresh_post_pan_frame_can_finish_inside_existing_deadline(self):
        # Live turn009 had its usable final post-pan frame at40.14s. A gratuitous
        # 5.26s content scan expired45s. Reusing that frame leaves confirmation time.
        clock = [40.14]
        op = operation([], clock=lambda: clock[0])
        op.started = 0.0
        op.calibration_id = "test_endpoint"
        op.state.gestures = 4
        content = Mock(side_effect=AssertionError("redundant final content capture"))
        op.observe_content = content
        ticks = iter((home(2).captured_at, home(3).captured_at))

        def destination(_):
            clock[0] += 1.0
            return frame(ScreenType.PNC_ILLUSORY_BEAST_MANOR, captured_at=next(ticks))

        op.core.observe = destination
        result = op.core._open_reacquired_building(
            target=_TARGET, source=home(1, objects=(_BODY,)), operation=op,
            on_target_acquired=None,
        )
        self.assertEqual(ScreenType.PNC_ILLUSORY_BEAST_MANOR, result.screen_type)
        content.assert_not_called()
        self.assertLess(clock[0], 45.0)
        self.assertEqual(4, op.state.gestures)

    def test_callback_requires_new_body_and_never_uses_the_old_point(self):
        op = operation([home(2)])  # target vanished after callback
        op.calibration_id = "test_endpoint"
        callback = Mock()
        with self.assertRaises(HomeCityScanError):
            op.core._open_reacquired_building(
                target=_TARGET, source=home(1, objects=(_BODY,)), operation=op,
                on_target_acquired=callback,
            )
        callback.assert_called_once_with(_BODY)
        self.assertEqual([], op.core.actuator.actions)

    def test_callback_returning_same_capture_is_rejected(self):
        source = home(1, objects=(_BODY,))
        op = operation([source])
        op.calibration_id = "test_endpoint"
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            op.core._open_reacquired_building(
                target=_TARGET, source=source, operation=op, on_target_acquired=lambda _: None,
            )
        self.assertEqual([], op.core.actuator.actions)

    def test_source_without_current_body_is_not_tapped(self):
        op = operation([])
        op.calibration_id = "test_endpoint"
        with self.assertRaises(HomeCityScanError):
            op.core._open_reacquired_building(
                target=_TARGET, source=home(1), operation=op, on_target_acquired=None,
            )
        self.assertEqual([], op.core.actuator.actions)

    def test_dispatch_provenance_rejection_is_not_retried(self):
        class RejectingActuator:
            calls = 0

            def execute_action(self, action, before):
                self.calls += 1
                raise RuntimeError("stale session input proof")

        actuator = RejectingActuator()
        op = operation([], actuator=actuator)
        op.calibration_id = "test_endpoint"
        with self.assertRaisesRegex(RuntimeError, "stale session input proof"):
            op.core._open_reacquired_building(
                target=_TARGET, source=home(1, objects=(_BODY,)), operation=op,
                on_target_acquired=None,
            )
        self.assertEqual(1, actuator.calls)
