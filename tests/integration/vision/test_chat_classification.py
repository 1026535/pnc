"""Chat classification: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Bounds, VisibleElementSourceKind
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

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.build_chat_observation_from_ocr_fallback import (
    _build_chat_observation_from_ocr_fallback,
)
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ChatClassificationTests(unittest.TestCase):
    """Proves chat classification."""

    def test_observation_builder_classifies_chat_from_live_like_ocr(self) -> None:
        """Recognizes chat from OCR and materializes the shared draft-input geometry."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_chat",
                label="chat_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                    selector_registry=build_default_selector_registry(),
                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Chat", x=181, y=20, width=113, height=49),
                            _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
                            _ocr_line("Alliance", x=652, y=116, width=123, height=39),
                        )
                    ))

            observation = builder.build(
                screenshot,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_HEADER))
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_TAB_KINGDOM))
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_TAB_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_SEND_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_INPUT_FIELD))
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_HEADER).source_kind,
                VisibleElementSourceKind.OCR,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM).source_kind,
                VisibleElementSourceKind.OCR,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE).source_kind,
                VisibleElementSourceKind.OCR,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM).bounds,
                Bounds(x=202, y=117, width=143, height=40),
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE).bounds,
                Bounds(x=652, y=116, width=123, height=39),
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_SEND_BUTTON).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_INPUT_FIELD).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )

    def test_observation_builder_classifies_compact_chat_and_uses_ocr_tab_bounds(self) -> None:
        """Recognizes the current compact chat layout and avoids stale tab geometry."""

        image_size = (540, 960)
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", image_size, (15, 28, 68)),
                "artifact": type("Artifact", (), {"path": Path("synthetic_compact_chat.png"), "captured_at": None})(),
            },
        )()
        registry = build_default_selector_registry()
        ocr_service = _FakeOcrService(
            lines=(
                _ocr_line("Chat", x=111, y=16, width=75, height=28),
                _ocr_line("Kingdom", x=64, y=64, width=82, height=26),
                _ocr_line("Alliance", x=219, y=64, width=91, height=27),
            )
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
                ocr_service=UnavailableOcrService(),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(selector_registry=registry),
            ocr_service=ocr_service,
        )

        observation = builder.build(
            screenshot,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        kingdom = observation.require(UiElementId.PNC_CHAT_TAB_KINGDOM)
        alliance = observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE)
        self.assertEqual(kingdom.source_kind, VisibleElementSourceKind.OCR)
        self.assertEqual(alliance.source_kind, VisibleElementSourceKind.OCR)
        self.assertEqual(kingdom.bounds, Bounds(x=64, y=64, width=82, height=26))
        self.assertEqual(alliance.bounds, Bounds(x=219, y=64, width=91, height=27))

    def test_observation_builder_extracts_chat_state_after_ocr_chat_fallback(self) -> None:
        """Carries active-channel and draft state through the OCR fallback path once chat is proven."""

        observation, ocr_service = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="Pleaseter content",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(observation.chat_draft_empty)
        self.assertIsNone(observation.chat_draft_text)
        self.assertEqual(ocr_service.read_result_calls, 1)
        self.assertEqual(ocr_service.read_text_calls, 0)

    def test_observation_builder_leaves_active_chat_channel_unknown_when_tab_colors_are_ambiguous(self) -> None:
        """Keeps OCR-proven chat observations fail-safe when the highlighted tab cannot be trusted."""

        observation, ocr_service = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=None,
            draft_ocr_text="Pleaseter content",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertIsNone(observation.active_chat_channel)
        self.assertTrue(observation.chat_draft_empty)
        self.assertIsNone(observation.chat_draft_text)
        self.assertEqual(ocr_service.read_result_calls, 1)
        self.assertEqual(ocr_service.read_text_calls, 0)

    def test_observation_builder_escalates_chat_send_follow_up_to_ocr_after_a_geometry_miss(self) -> None:
        """Falls back to OCR for post-send chat confirmation when the chat geometry heuristic misses."""

        observation, ocr_service = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.chat_send_follow_up(),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertIsNone(observation.chat_draft_empty)
        self.assertEqual(ocr_service.read_result_calls, 2)
        self.assertEqual(ocr_service.read_text_calls, 0)
