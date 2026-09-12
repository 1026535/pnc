"""Research observation: verifies the named internal boundary with offline fixtures."""

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
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ResearchObservationTests(unittest.TestCase):
    """Proves research observation."""

    def test_observation_builder_classifies_research_tree_from_live_like_ocr(self) -> None:
        """Recognizes the live research grid so flows can back out to home safely."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_live_research_tree",
                label="research_tree_live_like",
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
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Troop Size I", x=229, y=340, width=90, height=20),
                            _ocr_line("March Speed", x=221, y=714, width=103, height=19),
                            _ocr_line("0/3", x=106, y=425, width=25, height=14),
                            _ocr_line("0/5", x=230, y=615, width=27, height=16),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)

    def test_observation_builder_classifies_institute_overview_from_live_like_ocr(self) -> None:
        """Recognizes the live institute overview and exposes a safe back target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_live_academy",
                label="academy_live_like",
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
                            _ocr_line("Institute", x=108, y=12, width=115, height=29),
                            _ocr_line("Upgrade", x=404, y=263, width=88, height=25),
                            _ocr_line("Development", x=41, y=335, width=111, height=20),
                            _ocr_line("Economy", x=304, y=333, width=79, height=24),
                            _ocr_line("Military", x=38, y=412, width=67, height=24),
                            _ocr_line("Fortification", x=306, y=415, width=99, height=17),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
            self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON))

    def test_observation_builder_rejects_academy_title_without_upgrade_and_categories(self) -> None:
        """Keeps isolated academy-like titles unknown when the overview structure is absent."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_academy_probe",
                label="academy_near_match",
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
                            _ocr_line("Institute", x=108, y=12, width=115, height=29),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_rejects_research_tree_header_without_grid_evidence(self) -> None:
        """Keeps isolated research-like headers unknown when the node-grid evidence is absent."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_research_tree_probe",
                label="research_tree_near_match",
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
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_rejects_bottom_nav_only_non_home_screens(self) -> None:
        """Keeps bag, quest, hero, and mail OCR fixtures unknown without city-only anchors."""

        cases = (
            (
                "bag",
                (
                    _ocr_line("Inventory", x=360, y=240, width=110, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "quest",
                (
                    _ocr_line("Quest", x=360, y=240, width=92, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "hero",
                (
                    _ocr_line("Hero", x=360, y=240, width=80, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "mail",
                (
                    _ocr_line("Mail", x=360, y=240, width=80, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
        )

        for label, lines in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_directory:
                root = Path(temp_directory)
                screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                screenshot = screenshot_service.capture(
                    _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                    artifact_directory="k230_probe",
                    label=label,
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
                            lines=lines,
                        )
                    )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertFalse(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
