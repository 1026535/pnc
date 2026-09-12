"""Event observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class EventObservationTests(unittest.TestCase):
    """Proves event observation."""

    def test_observation_builder_classifies_vip_from_live_like_ocr(self) -> None:
        """Recognizes the VIP benefits screen from its header and support text."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_vip",
                label="vip_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("VIP", x=180, y=19, width=83, height=48),
                            _ocr_line("Get Pts", x=741, y=254, width=108, height=31),
                            _ocr_line("Current", x=177, y=409, width=98, height=29),
                            _ocr_line("Next Level", x=612, y=410, width=128, height=27),
                            _ocr_line("VIP 1", x=180, y=460, width=89, height=36),
                            _ocr_line("VIP 2", x=625, y=457, width=101, height=41),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_VIP)
            self.assertTrue(observation.has(UiElementId.PNC_VIP_HEADER))

    def test_observation_builder_exposes_gold_back_for_might_rank_recovery(self) -> None:
        """Materializes the non-OCR gold back geometry needed to leave a live Might Rank screen safely."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="might_rank_recovery",
                label="might_rank_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Rank", x=330, y=30, width=80, height=30),
                            _ocr_line("free cookies", x=80, y=500, width=180, height=30),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_MIGHT_RANK)
            self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_observation_builder_classifies_event_center_from_live_like_ocr(self) -> None:
        """Recognizes Event Center rows so safe-root recovery does not treat the surface as unknown."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="event_center_recovery",
                label="event_center_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Event Center", x=112, y=15, width=170, height=25),
                            _ocr_line("Regular Events", x=7, y=70, width=174, height=24),
                            _ocr_line("Holiday Events", x=185, y=70, width=175, height=22),
                            _ocr_line("About to start", x=369, y=69, width=162, height=24),
                            _ocr_line("Banner Brawl", x=32, y=239, width=165, height=22),
                            _ocr_line("Time left: 5d 10:28:21", x=31, y=287, width=196, height=19),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_EVENT_CENTER)
            self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_EVENT_CENTER_EVENT_ROW))
            self.assertEqual("Banner Brawl", observation.entries(ListEntryKind.EVENT_ENTRY)[0].title_text)

    def test_observation_builder_classifies_improve_might_from_live_like_ocr(self) -> None:
        """Recognizes the Improve Might prompt from its title and explanatory guidance."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_improve_might",
                label="improve_might_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Improve Might", x=296, y=352, width=307, height=49),
                            _ocr_line("Improve", x=685, y=494, width=122, height=37),
                            _ocr_line("Can also train units, research techs, upgrade buildings,", x=86, y=1164, width=729, height=36),
                            _ocr_line("or craft traps to improve Might.", x=236, y=1196, width=426, height=30),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_IMPROVE_MIGHT)
            self.assertTrue(observation.has(UiElementId.PNC_IMPROVE_MIGHT_HEADER))

    def test_observation_builder_rejects_reconnect_without_loading_support(self) -> None:
        """Keeps isolated reconnect text unknown so bootstrap recovery stays conservative."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_loading_probe",
                label="reconnect_near_match",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Rewards", x=210, y=112, width=90, height=24),
                            _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))
