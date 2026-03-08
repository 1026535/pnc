"""Capture and vision-pipeline tests."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from pnc_automation.capture.artifact_store import ArtifactStore
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import PncAccountCastleRosterConfig, SelectedCastleConfig
from pnc_automation.pnc.observation import ListEntryKind
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ObservationService,
    PillowSelectorEngine,
)
from pnc_automation.vision.ocr_service import OcrLine, UnavailableOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier
from pnc_automation.vision.selectors import (
    ClickDefinition,
    DetectionKind,
    Region,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
)
from pnc_automation.vision.template_matcher import PillowTemplateMatcher
from tests.test_support import build_png_bytes


class _FakeScreenshotSession:
    """Returns a fixed screenshot payload."""

    def __init__(self, payload: bytes) -> None:
        """Stores the screenshot bytes returned by capture."""

        self._payload = payload

    def capture_screenshot_bytes(self) -> bytes:
        """Returns the pre-seeded screenshot bytes."""

        return self._payload


@dataclass(slots=True)
class _FakeOcrService:
    """Returns deterministic OCR lines for castle-selection parsing tests."""

    lines: tuple[OcrLine, ...]

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns pre-seeded OCR lines, optionally restricted to a region."""

        del image
        if region is None:
            return self.lines
        filtered: list[OcrLine] = []
        for line in self.lines:
            if line.bounds.x < region.x or line.bounds.y < region.y:
                continue
            if line.bounds.x + line.bounds.width > region.x + region.width:
                continue
            if line.bounds.y + line.bounds.height > region.y + region.height:
                continue
            filtered.append(line)
        return tuple(filtered)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))


class CaptureAndVisionTests(unittest.TestCase):
    """Validates screenshot persistence and synthetic vision classification."""

    def test_screenshot_service_persists_valid_png(self) -> None:
        """Captures a screenshot, validates it, and writes it to disk."""

        with tempfile.TemporaryDirectory() as temp_directory:
            service = ScreenshotService(artifact_store=ArtifactStore(root=Path(temp_directory)))
            screenshot = service.capture(
                _FakeScreenshotSession(build_png_bytes(size=(12, 14))),
                artifact_directory="k313_main_castle",
                label="home_scan",
            )

            self.assertTrue(screenshot.artifact.path.is_file())
            self.assertEqual(screenshot.image.size, (12, 14))
            self.assertEqual(screenshot.artifact.path.parent.name, "k313_main_castle")

    def test_observation_builder_classifies_home_city_from_templates(self) -> None:
        """Builds a home-city observation from synthetic template anchors."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_path = root / "screen.png"
            world_switch_template = root / "world_switch.png"
            character_panel_template = root / "character_panel.png"
            build_button_template = root / "build_button.png"

            screen = Image.new("RGBA", (30, 20), (255, 255, 255, 255))
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(world_switch_template)
            Image.new("RGBA", (4, 4), (0, 255, 0, 255)).save(character_panel_template)
            Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(build_button_template)
            screen.paste(Image.open(world_switch_template), (2, 2))
            screen.paste(Image.open(character_panel_template), (10, 2))
            screen.paste(Image.open(build_button_template), (18, 2))
            screen.save(screenshot_path)

            registry = SelectorRegistry(
                selectors=(
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=world_switch_template,
                        click=ClickDefinition(),
                    ),
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=character_panel_template,
                        click=ClickDefinition(),
                    ),
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=build_button_template,
                        click=ClickDefinition(),
                    ),
                )
            )

            with screenshot_path.open("rb") as handle:
                payload = handle.read()
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            captured = screenshot_service.capture(
                _FakeScreenshotSession(payload),
                artifact_directory="k230_main_castle",
                label="synthetic",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=DefaultObservationEnricher(),
            )

            observation = builder.build(captured)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_WORLD_SWITCH))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_CHARACTER_PANEL))

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
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

    def test_observation_builder_classifies_building_detail_and_exposes_back_click_target(self) -> None:
        """Recognizes a building-detail screen from OCR and surfaces tappable controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_colddukeofthenorth",
                label="building_detail",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Castle", x=88, y=16, width=120, height=30),
                            _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                            _ocr_line("ColdDukeOfTheNorth", x=101, y=465, width=256, height=32),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))

    def test_observation_builder_classifies_home_city_from_bottom_nav_ocr(self) -> None:
        """Recognizes home city from bottom navigation OCR when templates are unavailable."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home",
                label="home_city",
            )
            builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_service_syncs_castle_roster_cache_from_castle_selection(self) -> None:
        """Persists discovered castle rosters when the Manage Char screen is observed."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (480, 854), (15, 28, 68))
            for x in range(410, 470):
                for y in range(520, 590):
                    image.putpixel((x, y), (40, 200, 70))
            observation_builder = ObservationBuilder(
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
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
                            _ocr_line("K226 Kingdom", x=98, y=603, width=128, height=18),
                            _ocr_line("please b gentle", x=99, y=630, width=150, height=19),
                            _ocr_line("Castle Level 11", x=98, y=657, width=132, height=18),
                        )
                    )
                ),
            )
            roster_store = CastleRosterStore(
                path=root / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(SelectedCastleConfig(kingdom="K230", castle_name="Lv.5 Hellhound", castle_level=8),),
                    ),
                ),
            )
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=observation_builder,
                session=_FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_lv_5_hellhound",
                pnc_account_id="inline_user",
                castle_roster_store=roster_store,
            )

            service.observe("scan")

            persisted = (root / "castles.yaml").read_text(encoding="utf-8")
            self.assertIn("inline_user", persisted)
            self.assertIn("Lv.5 Hellhound", persisted)
            self.assertIn("castle_level: 9", persisted)
            self.assertIn("please b gentle", persisted)
            self.assertIn("castle_level: 11", persisted)


def _ocr_line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one deterministic OCR line for tests."""

    return OcrLine(text=text, bounds=Region(x=x, y=y, width=width, height=height), confidence=0.99)


def _encode_png(image: Image.Image) -> bytes:
    """Encodes one PIL image into PNG bytes for screenshot tests."""

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
