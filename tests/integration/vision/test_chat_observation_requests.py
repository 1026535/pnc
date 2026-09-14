"""Chat observation requests: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.integration.vision.test_chat_mail_captured_content import (
    CHAT_BODY_REGION,
    _ControlledOcrService,
    _assert_bounded,
    _builder,
    _capture,
    _line,
)
from tests.support.pnc.capture_vision.materialize_chat_region import _materialize_chat_region
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.mail.build_observation import _build_observation


class ChatObservationRequestsTests(unittest.TestCase):
    """Proves chat observation requests."""

    def test_observation_builder_treats_common_empty_chat_placeholder_ocr_variants_as_empty(self) -> None:
        """Accepts the observed placeholder OCR variants instead of clearing a field that is already empty."""

        for placeholder_text in ("Pleaseter content", "Please enter conteni"):
            with self.subTest(placeholder_text=placeholder_text):
                image_size = (900, 1600)
                registry = build_default_selector_registry()
                input_region = _materialize_chat_region(
                    registry,
                    UiElementId.PNC_CHAT_INPUT_FIELD,
                    image_size=image_size,
                )
                observation = _build_observation(
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                    accepted_screen=ScreenType.PNC_CHAT,
                    image_size=image_size,
                    lines=(
                        _ocr_line(
                            placeholder_text,
                            x=input_region.x + 18,
                            y=input_region.y + max(8, input_region.height // 5),
                            width=max(40, input_region.width - 36),
                            height=max(20, input_region.height // 2),
                        ),
                    ),
                )

                self.assertTrue(observation.chat_draft_empty)
                self.assertIsNone(observation.chat_draft_text)

    def test_observation_builder_uses_geometry_first_chat_follow_up_without_full_frame_ocr(self) -> None:
        """Recognizes chat from the shared tab/footer geometry during narrow chat follow-up observations."""

        registry = build_default_selector_registry()
        ocr_service = _RecordingOcrService(lines=())
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),

            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(

                selector_registry=registry,
            ),
            ocr_service=ocr_service)
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.open(
                    require_local_fixture_artifact(
                        "chat_follow_up_geometry_first",
                        default_repo_relative_path=(
                            "artifacts/2026-03-13/k287_pine_cobaye_1/"
                            "20260313T134419Z_live_send_chat_helper_post_action_1.png"
                        ),
                    )
                ),
                "artifact": type("Artifact", (), {"path": Path("chat.png"), "captured_at": None})(),
                "frame_ref": make_captured_frame(b"").frame_ref,
            },
        )()

        observation = builder.build(
            screenshot,
            request=ObservationRequest.chat_send_follow_up(),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(observation.chat_draft_empty)
        self.assertEqual(ocr_service.read_result_calls, 1)
        self.assertEqual(ocr_service.read_text_calls, 0)

    def test_chat_transcript_observation_still_runs_ocr_after_geometry_proves_chat(self) -> None:
        """Keeps transcript extraction on the measured body crop after captured Chat identity is proven."""

        capture = _capture("chat_kingdom.png", session_id="captured-chat-transcript-request")
        ocr_service = _ControlledOcrService(
            (
                _line("Chat", x=105, y=9, width=76, height=35),
                _line("Kingdom", x=62, y=69, width=89, height=26),
                _line("Alliance", x=217, y=70, width=77, height=20),
                _line("Enemy Bob", x=108, y=145, width=150, height=20),
                _line("Hello there", x=108, y=177, width=180, height=22),
            )
        )
        builder = _builder(ocr_service)
        ocr_service.bind(capture.image.size)
        context = builder.create_ocr_context(capture)
        observation = builder.build(
            capture,
            request=ObservationRequest.chat_transcript_observation(),
            ocr_context=context,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.WORLD)
        self.assertEqual(len(observation.entries(ListEntryKind.CHAT_MESSAGE)), 1)
        self.assertEqual(observation.entries(ListEntryKind.CHAT_MESSAGE)[0].title_text, "Enemy Bob")
        _assert_bounded(self, ocr_service, capture.image.size)
        self.assertTrue(any(region == CHAT_BODY_REGION for region, _ in ocr_service.calls))
