"""Event observation: semantic parsers under explicit screen decisions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_event_center_additions,
    _build_improve_might_additions,
    _build_vip_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.build_observation_from_ocr_lines import (
    _build_observation_from_ocr_lines,
)
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class EventObservationTests(unittest.TestCase):
    """Proves event semantic parsing and classifier abstention."""

    def test_explicit_screen_decision_publishes_vip_semantics(self) -> None:
        """Publishes VIP semantics after the caller accepts the screen identity."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("VIP", x=180, y=19, width=83, height=48),
                _ocr_line("Get Pts", x=741, y=254, width=108, height=31),
                _ocr_line("Current", x=177, y=409, width=98, height=29),
                _ocr_line("Next Level", x=612, y=410, width=128, height=27),
                _ocr_line("VIP 1", x=180, y=460, width=89, height=36),
                _ocr_line("VIP 2", x=625, y=457, width=101, height=41),
            ),
            accepted_screen=ScreenType.PNC_VIP,
            semantic_parser=lambda image, lines: _build_vip_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_VIP)
        self.assertTrue(observation.has(UiElementId.PNC_VIP_HEADER))

    def test_explicit_screen_decision_publishes_might_rank_recovery_surface(self) -> None:
        """Publishes the accepted Might Rank surface while keeping an unproved back tap absent."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Rank", x=330, y=30, width=80, height=30),
                _ocr_line("free cookies", x=80, y=500, width=180, height=30),
            ),
            accepted_screen=ScreenType.PNC_MIGHT_RANK,
            materialize_geometry=False,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_MIGHT_RANK)
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

    def test_explicit_screen_decision_publishes_event_center_rows(self) -> None:
        """Publishes Event Center rows after the caller accepts the screen identity."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Event Center", x=112, y=15, width=170, height=25),
                _ocr_line("Regular Events", x=7, y=70, width=174, height=24),
                _ocr_line("Holiday Events", x=185, y=70, width=175, height=22),
                _ocr_line("About to start", x=369, y=69, width=162, height=24),
                _ocr_line("Banner Brawl", x=32, y=239, width=165, height=22),
                _ocr_line("Time left: 5d 10:28:21", x=31, y=287, width=196, height=19),
            ),
            accepted_screen=ScreenType.PNC_EVENT_CENTER,
            semantic_parser=lambda image, lines: _build_event_center_additions(image=image, lines=lines),
            materialize_geometry=False,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_EVENT_CENTER)
        self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
        self.assertTrue(observation.has(UiElementId.PNC_EVENT_CENTER_EVENT_ROW))
        self.assertEqual("Banner Brawl", observation.entries(ListEntryKind.EVENT_ENTRY)[0].title_text)

    def test_explicit_screen_decision_publishes_improve_might_semantics(self) -> None:
        """Publishes the Improve Might prompt after the caller accepts its identity."""

        observation = _build_observation_from_ocr_lines(
            (
                _ocr_line("Improve Might", x=296, y=352, width=307, height=49),
                _ocr_line("Improve", x=685, y=494, width=122, height=37),
                _ocr_line(
                    "Can also train units, research techs, upgrade buildings,",
                    x=86,
                    y=1164,
                    width=729,
                    height=36,
                ),
                _ocr_line("or craft traps to improve Might.", x=236, y=1196, width=426, height=30),
            ),
            accepted_screen=ScreenType.PNC_IMPROVE_MIGHT,
            semantic_parser=lambda image, lines: _build_improve_might_additions(image=image, lines=lines),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_IMPROVE_MIGHT)
        self.assertTrue(observation.has(UiElementId.PNC_IMPROVE_MIGHT_HEADER))

    def test_screen_classifier_rejects_reconnect_without_loading_support(self) -> None:
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
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Rewards", x=210, y=112, width=90, height=24),
                        _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))


if __name__ == "__main__":
    unittest.main()
