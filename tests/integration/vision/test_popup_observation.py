"""Popup observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_reconnect_popup_additions,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class PopupObservationTests(unittest.TestCase):
    """Proves popup observation."""

    def test_observation_builder_classifies_blocking_popup_over_home_city_from_ocr(self) -> None:
        """Promotes centered modal cancel buttons into the canonical blocking-popup selector."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_live_popup",
                label="home_city_popup",
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
                            _ocr_line("Build", x=27, y=354, width=65, height=28),
                            _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                            _ocr_line("Join our alliance and get strong together!", x=240, y=690, width=420, height=44),
                            _ocr_line("Cancel", x=378, y=888, width=115, height=40),
                            _ocr_line("Join/Apply", x=607, y=888, width=178, height=44),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_observation_builder_classifies_exit_game_popup_when_cancel_is_right_aligned(self) -> None:
        """Replays the live exit-game modal whose safe Cancel action sits to the right of Confirm."""

        fixture_path = require_local_fixture_artifact(
            "world_map_exit_game_cancel_right_live_20260617",
            default_repo_relative_path="tests/data/world_map/world_map_exit_game_cancel_right_live_20260617.png",
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_exit_game_popup",
                label="exit_game_cancel_right",
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
                            _ocr_line("Exit the game?", x=59, y=385, width=134, height=22),
                            _ocr_line("Confirm", x=122, y=536, width=73, height=20),
                            _ocr_line("Cancel", x=351, y=533, width=63, height=23),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            close_button = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            self.assertEqual(close_button.extracted_text, "Cancel")
            self.assertGreater(close_button.bounds.center()[0], image.width // 2)

    def test_observation_builder_classifies_live_disconnect_reconnect_popup(self) -> None:
        """Replays the live disconnect modal as the shared recoverable blocking-popup contract."""

        fixture_path = require_local_fixture_artifact(
            "world_map_disconnect_popup_live_20260615",
            default_repo_relative_path="tests/data/world_map/world_map_disconnect_popup_live_20260615.png",
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="live_disconnect_popup",
                label="world_map_disconnect_popup",
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
                            _ocr_line("Disconnected. Reconnect now?[-10013]", x=47, y=382, width=422, height=35),
                            _ocr_line("Confirm", x=231, y=533, width=107, height=34),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            close_button = observation.require(UiElementId.PNC_RECONNECT_CONFIRM_BUTTON)
            self.assertEqual(close_button.extracted_text, "Confirm")
            self.assertEqual(close_button.action_point, (284, 550))
            additions = _build_reconnect_popup_additions(
                image=image,
                lines=(
                    _ocr_line("Disconnected. Reconnect now?[-10013]", x=47, y=382, width=422, height=35),
                    _ocr_line("Confirm", x=231, y=533, width=107, height=34),
                ),
            )
            self.assertIsNotNone(additions)
            assert additions is not None
            self.assertEqual("ocr_reconnect_popup", additions.screen_evidence[0].reason)
