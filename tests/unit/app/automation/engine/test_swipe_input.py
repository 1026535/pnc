"""Swipe input."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeGesturePrimitive,
    SwipeAction,
    SwipeInputSource,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class SwipeInputTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves swipe input."""

    def test_action_executor_uses_explicit_swipe_ratios_when_present(self) -> None:
        """Resolves selector-independent swipe geometry from explicit normalized start/end ratios when provided."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="down",
                start_x_ratio=0.5,
                start_y_ratio=0.25,
                end_x_ratio=0.5,
                end_y_ratio=0.75,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(executor.session.swipes, [(100, 25, 100, 75, 500)])

    def test_action_executor_preserves_swipe_input_source(self) -> None:
        """Forwards the requested swipe input source so profile-level gesture calibration survives execution."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="right",
                input_source=SwipeInputSource.DEFAULT,
                start_x_ratio=0.4,
                start_y_ratio=0.5,
                end_x_ratio=0.6,
                end_y_ratio=0.5,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(executor.session.swipe_input_sources, [SwipeInputSource.DEFAULT])

    def test_action_executor_preserves_swipe_gesture_primitive(self) -> None:
        """Forwards the requested drag primitive so callers can opt into motion-event gestures."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="right",
                gesture_primitive=SwipeGesturePrimitive.PRESS_MOVE_RELEASE,
                start_x_ratio=0.4,
                start_y_ratio=0.5,
                end_x_ratio=0.6,
                end_y_ratio=0.5,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(
            executor.session.swipe_gesture_primitives,
            [SwipeGesturePrimitive.PRESS_MOVE_RELEASE],
        )
