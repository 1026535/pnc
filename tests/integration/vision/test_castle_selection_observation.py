"""Castle selection observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

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
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class CastleSelectionObservationTests(unittest.TestCase):
    """Proves castle selection observation."""

    def test_observation_builder_does_not_promote_home_city_to_world_map_from_region_noise(self) -> None:
        """Keeps home-city classification when world-map OCR regions contain unrelated text instead of real world-map anchors."""

        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Build", x=18, y=47, width=46, height=14),
                        _ocr_line("Hero", x=124, y=938, width=40, height=16),
                        _ocr_line("Quest", x=198, y=938, width=45, height=16),
                        _ocr_line("Mail", x=320, y=938, width=35, height=16),
                        _ocr_line("Alliance", x=401, y=938, width=73, height=16),
                        _ocr_line("More", x=478, y=938, width=40, height=16),
                    )
                ),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Build", x=18, y=47, width=46, height=14),
                        _ocr_line("Hero", x=124, y=938, width=40, height=16),
                        _ocr_line("Quest", x=198, y=938, width=45, height=16),
                        _ocr_line("Mail", x=320, y=938, width=35, height=16),
                        _ocr_line("Alliance", x=401, y=938, width=73, height=16),
                        _ocr_line("More", x=478, y=938, width=40, height=16),
                    )
                )
            ),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (540, 960), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic_home_city_noise.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot)

        self.assertNotEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
        self.assertFalse(observation.has(UiElementId.PNC_WORLD_HOME_NAV))

    def test_observation_builder_parses_castle_selection_from_manage_char_ocr(self) -> None:
        """Classifies the Manage Char screen from OCR and extracts castle rows."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (480, 854), (15, 28, 68))
            for x in range(410, 470):
                for y in range(520, 590):
                    image.putpixel((x, y), (40, 200, 70))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k304_probe",
                label="castle_selection",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                            _ocr_line("K304 Kingdom", x=99, y=97, width=127, height=18),
                            _ocr_line("K304caf8305606", x=99, y=124, width=148, height=18),
                            _ocr_line("Castle Level 4", x=98, y=151, width=125, height=18),
                            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)
            castle_entries = observation.entries(ListEntryKind.CASTLE)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
            self.assertEqual(len(castle_entries), 2)
            self.assertEqual(castle_entries[1].title_text, "Lv.5 Hellhound")
            self.assertEqual(castle_entries[1].metadata["kingdom"], "K230")
            self.assertEqual(castle_entries[1].metadata["castle_level"], 9)
            self.assertTrue(castle_entries[1].selected)
            self.assertEqual(observation.current_castle_name, "Lv.5 Hellhound")
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertEqual(
                VisibleElementSourceKind.GEOMETRY,
                observation.visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT].source_kind,
            )

    def test_observation_builder_parses_single_castle_manage_char_from_ocr(self) -> None:
        """Recognizes Manage Char even when OCR only exposes one visible castle row."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (480, 854), (15, 28, 68)))),
                artifact_directory="k230_single_castle_manage_char",
                label="single_castle_manage_char",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)
            castle_entries = observation.entries(ListEntryKind.CASTLE)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
            self.assertEqual(len(castle_entries), 1)
            self.assertEqual(castle_entries[0].title_text, "Lv.5 Hellhound")
