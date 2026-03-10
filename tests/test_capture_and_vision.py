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
from pnc_automation.vision.ocr_service import OcrLine, OcrResult, UnavailableOcrService
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

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns pre-seeded OCR output with line and word-level data."""

        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

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

    def test_observation_builder_rejects_upgrade_like_non_building_screens(self) -> None:
        """Keeps ambiguous upgrade screens unknown when the building evidence is incomplete."""

        cases = (
            (
                "hero_detail_upgrade",
                (
                    _ocr_line("Hero", x=120, y=18, width=120, height=30),
                    _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                    _ocr_line("Enhance", x=118, y=210, width=160, height=34),
                    _ocr_line("Evolve", x=585, y=1220, width=160, height=40),
                ),
            ),
            (
                "generic_modal_upgrade",
                (
                    _ocr_line("Rewards", x=310, y=40, width=180, height=30),
                    _ocr_line("Upgrade", x=682, y=308, width=120, height=40),
                    _ocr_line("Claim Available", x=160, y=440, width=220, height=30),
                ),
            ),
        )

        for label, lines in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_directory:
                root = Path(temp_directory)
                screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                screenshot = screenshot_service.capture(
                    _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                    artifact_directory="k313_probe",
                    label=label,
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
                            lines=lines,
                        )
                    ),
                )

                observation = builder.build(screenshot)

                self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))

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
                            _ocr_line("Build", x=120, y=1180, width=90, height=30),
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
            self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))

    def test_observation_builder_classifies_live_like_home_city_when_build_anchor_is_left_aligned(self) -> None:
        """Recognizes home city when the live Build button sits on the left rail instead of the lower action band."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_live_like_home",
                label="home_city_left_build",
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
                            _ocr_line("Build", x=27, y=354, width=65, height=28),
                            _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                            _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Build", x=27, y=354, width=65, height=28),
                            _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                            _ocr_line("Cancel", x=378, y=888, width=115, height=40),
                            _ocr_line("Join/Apply", x=607, y=888, width=178, height=44),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_observation_builder_classifies_promotional_hero_offer_popup_from_ocr(self) -> None:
        """Recognizes the observed monetized hero-offer modal as a blocking popup with a close target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_offer_popup",
                label="hero_offer_popup",
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
                            _ocr_line("5 Hero", x=27, y=65, width=138, height=35),
                            _ocr_line("Savannah", x=68, y=113, width=94, height=22),
                            _ocr_line("$6.99", x=240, y=805, width=60, height=25),
                            _ocr_line("One-time", x=230, y=854, width=81, height=21),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_observation_builder_rejects_hero_offer_near_match_without_price_and_one_time(self) -> None:
        """Keeps the screen unknown when the hero-offer popup evidence is incomplete."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_offer_probe",
                label="hero_offer_near_match",
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
                            _ocr_line("5 Hero", x=27, y=65, width=138, height=35),
                            _ocr_line("Savannah", x=68, y=113, width=94, height=22),
                            _ocr_line("1100", x=236, y=443, width=98, height=44),
                            _ocr_line("3900%", x=410, y=397, width=87, height=68),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.blocking_popup)
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

    def test_observation_builder_classifies_bag_from_live_like_ocr(self) -> None:
        """Recognizes the live bag inventory layout when template matches are unavailable."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_live_bag",
                label="bag_live_like",
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
                            _ocr_line("Bag", x=177, y=16, width=100, height=64),
                            _ocr_line("Bag", x=184, y=123, width=82, height=52),
                            _ocr_line("Diamond Shop", x=545, y=125, width=259, height=44),
                            _ocr_line("Resource", x=22, y=220, width=139, height=35),
                            _ocr_line("Use", x=725, y=327, width=64, height=37),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BAG)
            self.assertTrue(observation.has(UiElementId.PNC_BAG_MAIN_TAB_BAG))
            self.assertTrue(observation.has(UiElementId.PNC_BAG_USE_BUTTON))

    def test_observation_builder_classifies_alliance_join_from_live_like_ocr(self) -> None:
        """Recognizes the join-alliance landing when the account has no alliance yet."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k313_live_alliance_join",
                label="alliance_join_live_like",
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
                            _ocr_line("Join Alliance", x=300, y=627, width=305, height=49),
                            _ocr_line("Join", x=642, y=1198, width=78, height=39),
                            _ocr_line("Create Alliance", x=131, y=1218, width=259, height=36),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_ALLIANCE_JOIN)

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Troop Size I", x=229, y=340, width=90, height=20),
                            _ocr_line("March Speed", x=221, y=714, width=103, height=19),
                            _ocr_line("0/3", x=106, y=425, width=25, height=14),
                            _ocr_line("0/5", x=230, y=615, width=27, height=16),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)

    def test_observation_builder_classifies_academy_overview_from_live_like_ocr(self) -> None:
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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
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
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_ACADEMY)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Institute", x=108, y=12, width=115, height=29),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                ),
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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_rejects_bottom_nav_only_non_home_screens(self) -> None:
        """Keeps bag, quest, hero, and mail OCR fixtures unknown without city-only anchors."""

        cases = (
            (
                "bag",
                (
                    _ocr_line("Bag", x=360, y=240, width=72, height=28),
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
                    selector_registry=SelectorRegistry(selectors=()),
                    selector_engine=PillowSelectorEngine(
                        template_matcher=PillowTemplateMatcher(),
                        ocr_service=UnavailableOcrService(),
                    ),
                    screen_classifier=ScreenClassifier(),
                    enricher=PncObservationEnricher(
                        ocr_service=_FakeOcrService(
                            lines=lines,
                        )
                    ),
                )

                observation = builder.build(screenshot)

                self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
                self.assertFalse(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))

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
