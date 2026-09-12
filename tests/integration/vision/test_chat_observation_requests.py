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
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.build_chat_observation_from_ocr_fallback import (
    _build_chat_observation_from_ocr_fallback,
)
from tests.support.pnc.capture_vision.materialize_chat_region import _materialize_chat_region
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ChatObservationRequestsTests(unittest.TestCase):
    """Proves chat observation requests."""

    def test_observation_builder_treats_common_empty_chat_placeholder_ocr_variants_as_empty(self) -> None:
        """Accepts the observed placeholder OCR variants instead of clearing a field that is already empty."""

        for placeholder_text in ("Pleaseter content", "Please enter conteni"):
            with self.subTest(placeholder_text=placeholder_text):
                observation, _ = _build_chat_observation_from_ocr_fallback(
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
                    active_channel=ChatChannel.WORLD,
                    draft_ocr_text=placeholder_text,
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
                ocr_service=ocr_service,
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=ocr_service,
                selector_registry=registry,
            ),
        )
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
            },
        )()

        observation = builder.build(
            screenshot,
            request=ObservationRequest.chat_send_follow_up(),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(observation.chat_draft_empty)
        self.assertEqual(ocr_service.read_result_calls, 0)
        self.assertGreater(ocr_service.read_text_calls, 0)

    def test_chat_transcript_observation_still_runs_ocr_after_geometry_proves_chat(self) -> None:
        """Keeps transcript-row extraction enabled for chat transcript polls even when geometry already proves chat."""

        registry = build_default_selector_registry()
        image_size = (900, 1600)
        image = Image.new("RGB", image_size, (15, 28, 68))
        input_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_INPUT_FIELD, image_size=image_size)
        kingdom_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_KINGDOM, image_size=image_size)
        alliance_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_ALLIANCE, image_size=image_size)
        image.paste((20, 20, 20), (input_region.x, input_region.y, input_region.x + input_region.width, input_region.y + input_region.height))
        image.paste((228, 178, 48), (kingdom_region.x, kingdom_region.y, kingdom_region.x + kingdom_region.width, kingdom_region.y + kingdom_region.height))
        image.paste((64, 68, 82), (alliance_region.x, alliance_region.y, alliance_region.x + alliance_region.width, alliance_region.y + alliance_region.height))
        ocr_service = _RecordingOcrService(
            lines=(
                _ocr_line("Chat", x=181, y=20, width=113, height=49),
                _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
                _ocr_line("Alliance", x=652, y=116, width=123, height=39),
                _ocr_line("Enemy Bob", x=120, y=260, width=180, height=24),
                _ocr_line("Hello there", x=160, y=292, width=200, height=24),
            )
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
                ocr_service=UnavailableOcrService(),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=ocr_service,
                selector_registry=registry,
            ),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": image,
                "artifact": type("Artifact", (), {"path": Path("chat_transcript.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot, request=ObservationRequest.chat_transcript_observation())

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.WORLD)
        self.assertEqual(len(observation.entries(ListEntryKind.CHAT_MESSAGE)), 1)
        self.assertEqual(observation.entries(ListEntryKind.CHAT_MESSAGE)[0].title_text, "Enemy Bob")
        self.assertEqual(ocr_service.read_result_calls, 1)
