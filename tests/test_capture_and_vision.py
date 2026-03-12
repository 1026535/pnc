"""Capture and vision-pipeline tests."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from pnc_automation.capture.artifact_store import ArtifactStore
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.models import PncAccountCastleRosterConfig, SelectedCastleConfig
from pnc_automation.pnc.observation import ListEntryKind, VisibleElementSourceKind
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ObservationService,
    PillowSelectorEngine,
)
from pnc_automation.vision.image_models import SelectorMatch
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.ocr_service import OcrLine, OcrResult, UnavailableOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier
from pnc_automation.vision.selectors import (
    ClickDefinition,
    DetectionKind,
    RelativeBounds,
    Region,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
    build_default_selector_registry,
)
from pnc_automation.vision.template_matcher import PillowTemplateMatcher
from tests.test_support import build_png_bytes, make_observation


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


@dataclass(slots=True)
class _RecordingOcrService(_FakeOcrService):
    """Counts OCR calls so staged-observation tests can assert cost control."""

    read_result_calls: int = 0
    read_text_calls: int = 0

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Records full-image OCR requests before returning deterministic lines."""

        self.read_result_calls += 1
        return _FakeOcrService.read_result(self, image, region)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Records region OCR reads before returning deterministic text."""

        self.read_text_calls += 1
        return _FakeOcrService.read_text(self, image, region)


@dataclass(slots=True)
class _SequencedObservationBuilder:
    """Returns a pre-seeded sequence of built observations."""

    observations: list

    def build(self, screenshot: object, *, request: ObservationRequest | None = None) -> object:
        """Returns the next queued observation for one capture request."""

        del screenshot, request
        if not self.observations:
            raise AssertionError("No observation queued for ObservationService.")
        return self.observations.pop(0)


@dataclass(slots=True)
class _RecordingSelectorEngine:
    """Records selector-engine requests so observation scans stay scoped."""

    responses: list[tuple[SelectorMatch, ...]]
    requested_selector_ids: list[tuple[UiElementId, ...]] = field(default_factory=list)

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: tuple[UiElementId, ...] | None = None,
    ) -> tuple[SelectorMatch, ...]:
        """Records one selector request and returns the queued response."""

        del image, registry
        self.requested_selector_ids.append(()) if selector_ids is None else self.requested_selector_ids.append(tuple(selector_ids))
        if not self.responses:
            raise AssertionError("No selector-engine response queued.")
        return self.responses.pop(0)


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
                selector_registry=build_default_selector_registry(),
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

    def test_observation_builder_classifies_login_from_live_like_ocr(self) -> None:
        """Recognizes the credential form from OCR and exposes the actionable login controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_login",
                label="login_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Email", x=80, y=225, width=70, height=26),
                            _ocr_line("user@example.com", x=92, y=276, width=188, height=22),
                            _ocr_line("Password", x=82, y=365, width=110, height=26),
                            _ocr_line("Log In", x=211, y=566, width=105, height=30),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOGIN)
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_USERNAME_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_PASSWORD_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_LOGIN_SUBMIT_BUTTON))
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_USERNAME_FIELD).bounds.x, 59)
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_PASSWORD_FIELD).bounds.y, 352)
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON).bounds.width, 210)
            self.assertEqual(observation.current_pnc_account_id, "user@example.com")

    def test_observation_builder_classifies_account_switch_from_live_like_ocr(self) -> None:
        """Recognizes account-switch UI and exposes the verified-account continuation controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_account_switch",
                label="account_switch_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Switch Account", x=134, y=42, width=180, height=28),
                            _ocr_line("user@example.com", x=116, y=292, width=188, height=22),
                            _ocr_line("Continue", x=210, y=576, width=102, height=28),
                            _ocr_line("Change Account", x=165, y=654, width=170, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_ACCOUNT_SWITCH)
            self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON))
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON).bounds.x, 158)
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON).bounds.width, 340)
            self.assertEqual(observation.current_pnc_account_id, "user@example.com")

    def test_observation_builder_classifies_loading_reconnect_from_live_like_ocr(self) -> None:
        """Recognizes reconnect prompts as loading-state bootstrap screens."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_loading",
                label="loading_reconnect_live_like",
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
                            _ocr_line("Connecting", x=188, y=108, width=116, height=28),
                            _ocr_line("Network unstable", x=142, y=342, width=170, height=24),
                            _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
            self.assertTrue(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))

    def test_observation_builder_classifies_loading_splash_from_live_like_ocr(self) -> None:
        """Recognizes the branded game splash as a loading transition during castle switching or launch."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_loading_splash",
                label="loading_splash_live_like",
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
                            _ocr_line("CONQUEST", x=310, y=41, width=190, height=34),
                            _ocr_line("8%", x=430, y=1390, width=42, height=20),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))

    def test_observation_builder_classifies_more_menu_and_exposes_requested_actions(self) -> None:
        """Recognizes More-related overlays and exposes both the footer Settings action and direct menu entries."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_more_menu",
                label="more_menu_live_like",
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
                            _ocr_line("Manage Char", x=78, y=1330, width=178, height=34),
                            _ocr_line("Lord Info", x=315, y=1332, width=154, height=34),
                            _ocr_line("VIP", x=562, y=1333, width=58, height=34),
                            _ocr_line("Improve Might", x=690, y=1330, width=184, height=34),
                            _ocr_line("Rank", x=105, y=1444, width=72, height=31),
                            _ocr_line("Friend", x=318, y=1444, width=88, height=31),
                            _ocr_line("Guides", x=520, y=1444, width=91, height=31),
                            _ocr_line("Settings", x=742, y=1444, width=112, height=31),
                            _ocr_line("More", x=794, y=1567, width=71, height=27),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_MORE_MENU)
            self.assertTrue(observation.has(UiElementId.PNC_MORE_SETTINGS))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_LORD_INFO))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_VIP))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_IMPROVE_MIGHT))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_classifies_more_settings_submenu_with_top_left_back(self) -> None:
        """Recognizes the full-screen Settings submenu and exposes the canonical back target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k304_more_settings_menu",
                label="more_settings_menu_live_like",
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
                            _ocr_line("Settings", x=112, y=20, width=128, height=28),
                            _ocr_line("Account", x=120, y=94, width=102, height=24),
                            _ocr_line("Manage Char.", x=304, y=94, width=134, height=24),
                            _ocr_line("Search", x=122, y=188, width=88, height=24),
                            _ocr_line("Rank", x=344, y=188, width=64, height=24),
                            _ocr_line("Blacklist", x=320, y=374, width=104, height=24),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_MORE_MENU)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
            self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_classifies_lord_info_and_extracts_displayed_name(self) -> None:
        """Recognizes the Lord Info screen and exposes the OCR-backed displayed lord name."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k304_lord_info",
                label="lord_info_live_like",
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
                            _ocr_line("Lord Info", x=184, y=20, width=208, height=48),
                            _ocr_line("Gear", x=52, y=111, width=83, height=42),
                            _ocr_line("K304554ca2797", x=240, y=1048, width=210, height=27),
                            _ocr_line("Talent", x=68, y=1560, width=82, height=28),
                            _ocr_line("Lord Info", x=220, y=1559, width=114, height=30),
                            _ocr_line("Boost Info", x=386, y=1561, width=124, height=27),
                            _ocr_line("Alliance Info", x=561, y=1561, width=120, height=26),
                            _ocr_line("Achievements", x=731, y=1567, width=115, height=17),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LORD_INFO)
            self.assertTrue(observation.has(UiElementId.PNC_LORD_INFO_HEADER))
            self.assertEqual(
                observation.require(UiElementId.PNC_LORD_INFO_NAME_LABEL).extracted_text,
                "K304554ca2797",
            )
            self.assertEqual(observation.current_castle_name, "K304554ca2797")

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
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
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_VIP)
            self.assertTrue(observation.has(UiElementId.PNC_VIP_HEADER))

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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Improve Might", x=296, y=352, width=307, height=49),
                            _ocr_line("Improve", x=685, y=494, width=122, height=37),
                            _ocr_line("Can also train units, research techs, upgrade buildings,", x=86, y=1164, width=729, height=36),
                            _ocr_line("or craft traps to improve Might.", x=236, y=1196, width=426, height=30),
                        )
                    )
                ),
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
                selector_registry=SelectorRegistry(selectors=()),
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Rewards", x=210, y=112, width=90, height=24),
                            _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))

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
                selector_registry=build_default_selector_registry(),
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
            self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_VIP_SHORTCUT))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_IMPROVE_MIGHT_SHORTCUT))

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
                selector_registry=build_default_selector_registry(),
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
            self.assertTrue(observation.has(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT))

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

    def test_observation_builder_classifies_top_up_offer_popup_from_ocr(self) -> None:
        """Recognizes the observed top-up reward modal as a blocking popup with a close target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_top_up_popup",
                label="top_up_offer_popup",
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
                            _ocr_line("Complete 1st Top-up to Obtain Yune", x=72, y=352, width=382, height=68),
                            _ocr_line("Obtain Now", x=176, y=500, width=180, height=28),
                            _ocr_line("Claim Next Day", x=160, y=612, width=210, height=30),
                            _ocr_line("Top Up", x=188, y=856, width=150, height=34),
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

    def test_observation_builder_scans_only_probes_then_current_screen_selectors(self) -> None:
        """Limits template detection to classifier probes first, then the resolved screen slice."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_BAG_SUBTAB_RESOURCE,
                    screens=(ScreenType.PNC_BAG,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
            )
        )
        selector_engine = _RecordingSelectorEngine(
            responses=[
                (
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        bounds=Region(x=10, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        bounds=Region(x=40, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        bounds=Region(x=70, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                ),
                (),
            ]
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=DefaultObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot)

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(len(selector_engine.requested_selector_ids), 2)
        self.assertIn(UiElementId.PNC_HOME_WORLD_SWITCH, selector_engine.requested_selector_ids[0])
        self.assertIn(UiElementId.PNC_BAG_MAIN_TAB_BAG, selector_engine.requested_selector_ids[0])
        self.assertNotIn(UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON, selector_engine.requested_selector_ids[0])
        self.assertIn(UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON, selector_engine.requested_selector_ids[1])
        self.assertNotIn(UiElementId.PNC_BAG_MAIN_TAB_BAG, selector_engine.requested_selector_ids[1])

    def test_observation_builder_keeps_click_only_geometry_hidden_without_detection(self) -> None:
        """Does not auto-materialize relative click regions that still require explicit visibility proof."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.PLANNED,
                    click=ClickDefinition(),
                    relative_bounds=RelativeBounds(
                        x_ratio=0.1,
                        y_ratio=0.1,
                        width_ratio=0.2,
                        height_ratio=0.2,
                    ),
                    materialize_relative_bounds=False,
                ),
            )
        )
        selector_engine = _RecordingSelectorEngine(
            responses=[
                (
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        bounds=Region(x=10, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        bounds=Region(x=40, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_RESEARCH_BUTTON,
                        bounds=Region(x=70, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                ),
                (),
            ]
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=DefaultObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot)

        self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertFalse(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))

    def test_observation_builder_skips_ocr_for_base_requests(self) -> None:
        """Leaves OCR idle when the caller requests only the cheap selector-and-geometry base pass."""

        ocr_service = _RecordingOcrService(lines=())
        builder = ObservationBuilder(
            selector_registry=SelectorRegistry(selectors=()),
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
                ocr_service=ocr_service,
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(ocr_service=ocr_service),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        builder.build(screenshot, request=ObservationRequest.base())

        self.assertEqual(ocr_service.read_result_calls, 0)
        self.assertEqual(ocr_service.read_text_calls, 0)

    def test_observation_builder_runs_ocr_when_requested(self) -> None:
        """Invokes OCR when the observation request explicitly asks for OCR-backed facts."""

        ocr_service = _RecordingOcrService(lines=())
        builder = ObservationBuilder(
            selector_registry=SelectorRegistry(selectors=()),
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
                ocr_service=ocr_service,
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(ocr_service=ocr_service),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        builder.build(screenshot, request=ObservationRequest.runtime_default())

        self.assertEqual(ocr_service.read_result_calls, 1)

    def test_observation_builder_tags_template_and_geometry_sources(self) -> None:
        """Carries template and geometry provenance onto the final visible-element map."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    click=ClickDefinition(),
                    relative_bounds=RelativeBounds(
                        x_ratio=0.70,
                        y_ratio=0.80,
                        width_ratio=0.10,
                        height_ratio=0.10,
                    ),
                ),
            )
        )
        selector_engine = _RecordingSelectorEngine(
            responses=[
                (
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        bounds=Region(x=10, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        bounds=Region(x=40, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        bounds=Region(x=70, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                ),
                (),
            ]
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=DefaultObservationEnricher(),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (100, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(screenshot, request=ObservationRequest.base())

        self.assertEqual(
            observation.require(UiElementId.PNC_HOME_WORLD_SWITCH).source_kind,
            VisibleElementSourceKind.TEMPLATE,
        )
        self.assertEqual(
            observation.require(UiElementId.PNC_BOTTOM_NAV_MORE).source_kind,
            VisibleElementSourceKind.GEOMETRY,
        )

    def test_observation_builder_tags_ocr_sources(self) -> None:
        """Keeps OCR-synthesized selectors distinct from geometry-backed visibility."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.TEMPLATE,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                    click=ClickDefinition(),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    click=ClickDefinition(),
                    relative_bounds=RelativeBounds(
                        x_ratio=0.70,
                        y_ratio=0.80,
                        width_ratio=0.10,
                        height_ratio=0.10,
                    ),
                ),
            )
        )
        selector_engine = _RecordingSelectorEngine(
            responses=[
                (
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        bounds=Region(x=10, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        bounds=Region(x=40, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                    SelectorMatch(
                        selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        bounds=Region(x=70, y=10, width=20, height=20),
                        confidence=1.0,
                    ),
                ),
                (),
            ]
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=selector_engine,
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Alliance", x=48, y=92, width=124, height=8),
                        _ocr_line("More", x=160, y=92, width=74, height=8),
                    )
                )
            ),
        )
        screenshot = type(
            "Captured",
            (),
            {
                "image": Image.new("RGB", (240, 100), (0, 0, 0)),
                "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            },
        )()

        observation = builder.build(
            screenshot,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(
            observation.require(UiElementId.PNC_BOTTOM_NAV_MORE).source_kind,
            VisibleElementSourceKind.OCR,
        )

    def test_observation_service_syncs_castle_roster_cache_only_after_account_verification(self) -> None:
        """Persists discovered castle rosters only when the visible roster matches a trusted snapshot."""

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
                        castles=(
                            SelectedCastleConfig(kingdom="K230", castle_name="Lv.5 Hellhound", castle_level=8),
                            SelectedCastleConfig(kingdom="K226", castle_name="please b gentle", castle_level=10),
                        ),
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

            observation = service.observe("scan")

            persisted = (root / "castles.yaml").read_text(encoding="utf-8")
            self.assertEqual(observation.verified_pnc_account_id, "inline_user")
            self.assertIn("inline_user", persisted)
            self.assertIn("ordering: unknown", persisted)
            self.assertIn("Lv.5 Hellhound", persisted)
            self.assertIn("castle_level: 9", persisted)
            self.assertIn("please b gentle", persisted)
            self.assertIn("castle_level: 11", persisted)

    def test_observation_service_does_not_sync_castle_roster_cache_without_account_verification(self) -> None:
        """Leaves the cache untouched when the visible castle roster cannot prove account ownership."""

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
                        )
                    )
                ),
            )
            roster_store = CastleRosterStore(
                path=root / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(SelectedCastleConfig(kingdom="K999", castle_name="Other Castle", castle_level=1),),
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

            observation = service.observe("scan")

            self.assertIsNone(observation.verified_pnc_account_id)
            self.assertFalse((root / "castles.yaml").exists())

    def test_observation_service_carries_lord_info_castle_name_back_to_home_adjacent_screens(self) -> None:
        """Keeps the last Lord Info castle name on home and More screens until the switch flow starts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="K304554ca2797"),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                        make_observation(ScreenType.PNC_MORE_MENU, visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,)),
                        make_observation(
                            ScreenType.PNC_CASTLE_SELECTION,
                            current_castle=SelectedCastleConfig(kingdom="K313", castle_name="K313alpha"),
                        ),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                    ]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="k304_validation",
            )

            lord_info = service.observe("lord_info")
            home_city = service.observe("home_city")
            more_menu = service.observe("more_menu")
            castle_selection = service.observe("castle_selection")
            post_switch_home = service.observe("post_switch_home")

            self.assertEqual(lord_info.current_castle_name, "K304554ca2797")
            self.assertEqual(home_city.current_castle_name, "K304554ca2797")
            self.assertEqual(more_menu.current_castle_name, "K304554ca2797")
            self.assertEqual(castle_selection.current_castle_name, "K313alpha")
            self.assertIsNone(post_switch_home.current_castle)


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
