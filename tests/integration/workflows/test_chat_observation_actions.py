"""Chat observation actions: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from dataclasses import replace

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.capture_vision.build_chat_observation_from_ocr_fallback import (
    _build_chat_observation_from_ocr_fallback,
)


class ChatObservationActionsTests(unittest.TestCase):
    """Proves chat observation actions."""

    def test_send_chat_message_can_type_from_an_ocr_proven_chat_observation(self) -> None:
        """Allows chat sending to continue from an OCR fallback observation because chat state is populated."""

        observation, _ = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="Pleaseter content",
        )
        fake_session = FakeSession()
        refresh_frame = make_captured_frame(b"refresh").frame_ref
        post_frame = make_captured_frame(b"post").frame_ref
        refreshed_elements = {
            selector_id: replace(element, frame_ref=refresh_frame)
            for selector_id, element in observation.visible_elements.items()
        }
        posted_elements = {
            selector_id: replace(element, frame_ref=post_frame)
            for selector_id, element in observation.visible_elements.items()
        }
        fake_observer = FakeObservationService(
            observations=[
                replace(observation, frame_ref=refresh_frame, visible_elements=refreshed_elements),
                replace(observation, frame_ref=post_frame, visible_elements=posted_elements),
            ]
        )
        executor = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=ActionExecutor(
                selector_registry=build_default_selector_registry(),
                session=fake_session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            logger=build_logger(),
            sleep=lambda _: None,
        )

        executor.execute_actions(
            ScreenFlowPlanner().send_chat_message(
                observation,
                message="hello",
                channel=ChatChannel.ALLIANCE,
            ),
            observation,
            observe=fake_observer.observe,
        )

        self.assertEqual(fake_session.texts, ["hello"])
        self.assertEqual(fake_session.key_events, [])
        self.assertEqual(
            fake_observer.requests,
            [ObservationRequest.full_runtime_default(), ObservationRequest.chat_send_follow_up()],
        )
