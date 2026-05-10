"""Capture and vision-pipeline tests."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.authoring.config.models import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapOverviewNavigator
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    ListEntryKind,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ObservationDebugArtifactCollector,
    ObservationService,
    PillowSelectorEngine,
)
from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher, _find_world_map_root_coordinate_line
from pnc_automation.app.pnc.vision.world_map_coordinates import parse_world_coordinate_text
from pnc_automation.app.pnc.vision.selector_catalog import (
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    write_selector_catalog_document,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.spatial_surfaces import build_world_map_spatial_surface
from pnc_automation.app.pnc.vision.selectors import (
    ClickDefinition,
    DetectionKind,
    RelativeBounds,
    Region,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
    build_default_selector_registry,
)
from pnc_automation.core.vision.template.template_matcher import PillowTemplateMatcher
from tests.test_support import FakeObservationService, FakeSession, build_logger, build_png_bytes, make_observation


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
class _CoordinateBarFilteringOcrService:
    """Returns different OCR text for raw versus blue-text-filtered coordinate-bar crops."""

    raw_text: str
    filtered_text: str

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Builds one synthetic OCR result from the requested region text."""

        lines = self.read_lines(image, region)
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns one synthetic OCR line that reflects whether the crop was prefiltered."""

        if region is None:
            raise AssertionError("Coordinate-bar filtering OCR tests require an explicit region.")
        text = self.read_text(image, region)
        return (_ocr_line(text, x=region.x, y=region.y, width=max(1, region.width), height=max(1, region.height)),)

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns the filtered OCR text only when the image was reduced to a black-on-white mask."""

        crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("L")
        colors = {value for count, value in (crop.getcolors(maxcolors=8) or []) if count > 0}
        if colors and colors.issubset({0, 255}):
            return self.filtered_text
        return self.raw_text


@dataclass(slots=True)
class _CoordinateBarFilteringFullOcrService(_CoordinateBarFilteringOcrService):
    """Returns full-screen OCR lines while preserving selector-crop filtered coordinate text."""

    full_lines: tuple[OcrLine, ...] = ()

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns full-screen lines or one synthetic region line for the requested coordinate crop."""

        if region is None:
            return self.full_lines
        return _CoordinateBarFilteringOcrService.read_lines(self, image, region)


def _materialize_chat_region(
    registry: SelectorRegistry,
    selector_id: UiElementId,
    *,
    image_size: tuple[int, int],
) -> Region:
    """Returns one materialized chat region from the canonical selector registry."""

    selector = registry.require(selector_id)
    if selector.relative_bounds is None:
        raise AssertionError(f"Expected relative bounds for selector '{selector_id.value}'.")
    return selector.relative_bounds.materialize_region(image_size=image_size)


def _make_chat_ocr_fallback_fixture(
    *,
    active_channel: ChatChannel | None,
    draft_ocr_text: str | None,
    image_size: tuple[int, int] = (900, 1600),
) -> tuple[object, SelectorRegistry, _RecordingOcrService]:
    """Builds a synthetic chat screenshot where geometry misses but OCR still proves chat."""

    registry = build_default_selector_registry()
    image = Image.new("RGB", image_size, (15, 28, 68))
    input_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_INPUT_FIELD, image_size=image_size)
    kingdom_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_KINGDOM, image_size=image_size)
    alliance_region = _materialize_chat_region(registry, UiElementId.PNC_CHAT_TAB_ALLIANCE, image_size=image_size)
    image.paste((210, 210, 210), (input_region.x, input_region.y, input_region.x + input_region.width, input_region.y + input_region.height))
    warm_color = (228, 178, 48)
    cool_color = (64, 68, 82)
    if active_channel is None:
        neutral_color = (118, 112, 106)
        image.paste(
            neutral_color,
            (kingdom_region.x, kingdom_region.y, kingdom_region.x + kingdom_region.width, kingdom_region.y + kingdom_region.height),
        )
        image.paste(
            neutral_color,
            (alliance_region.x, alliance_region.y, alliance_region.x + alliance_region.width, alliance_region.y + alliance_region.height),
        )
    else:
        active_region = kingdom_region if active_channel == ChatChannel.WORLD else alliance_region
        inactive_region = alliance_region if active_channel == ChatChannel.WORLD else kingdom_region
        image.paste(
            warm_color,
            (active_region.x, active_region.y, active_region.x + active_region.width, active_region.y + active_region.height),
        )
        image.paste(
            cool_color,
            (inactive_region.x, inactive_region.y, inactive_region.x + inactive_region.width, inactive_region.y + inactive_region.height),
        )
    lines = [
        _ocr_line("Chat", x=181, y=20, width=113, height=49),
        _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
        _ocr_line("Alliance", x=652, y=116, width=123, height=39),
    ]
    if draft_ocr_text:
        lines.append(
            _ocr_line(
                draft_ocr_text,
                x=input_region.x + 18,
                y=input_region.y + max(8, input_region.height // 5),
                width=max(40, input_region.width - 36),
                height=max(20, input_region.height // 2),
            )
        )
    screenshot = type(
        "Captured",
        (),
        {
            "image": image,
            "artifact": type("Artifact", (), {"path": Path("synthetic_chat_ocr_fallback.png"), "captured_at": None})(),
        },
    )()
    return screenshot, registry, _RecordingOcrService(lines=tuple(lines))


def _build_chat_observation_from_ocr_fallback(
    *,
    request: ObservationRequest,
    active_channel: ChatChannel | None,
    draft_ocr_text: str | None,
) -> tuple[object, _RecordingOcrService]:
    """Builds one OCR-proven chat observation from the shared geometry-miss fixture."""

    screenshot, registry, ocr_service = _make_chat_ocr_fallback_fixture(
        active_channel=active_channel,
        draft_ocr_text=draft_ocr_text,
    )
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=PillowSelectorEngine(
            template_matcher=PillowTemplateMatcher(),
            ocr_service=UnavailableOcrService(),
        ),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(
            ocr_service=ocr_service,
            selector_registry=registry,
        ),
    )
    return builder.build(screenshot, request=request), ocr_service


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

    def test_pillow_selector_engine_detects_catalog_backed_ocr_regions(self) -> None:
        """Resolves catalog-defined normalized OCR regions through the runtime selector engine."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = root / "selector_registry.yaml"
            write_selector_catalog_document(
                catalog_path,
                SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_CASH_MALL_ENTRY_TITLE_REGION",
                            screens=("PNC_CASH_MALL",),
                            status="screenshot_seeded",
                            detection_kind="ocr_region",
                            relative_bounds=SelectorCatalogRelativeBounds(
                                x_ratio=0.1,
                                y_ratio=0.2,
                                width_ratio=0.4,
                                height_ratio=0.18,
                            ),
                        ),
                    )
                ),
            )
            registry = build_default_selector_registry(catalog_path=catalog_path, template_root=root)
            selector_engine = PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
                ocr_service=_FakeOcrService(
                    lines=(
                        _ocr_line("Daily Sale", x=12, y=22, width=32, height=12),
                    )
                ),
            )

            matches = selector_engine.detect(Image.new("RGB", (100, 100), (0, 0, 0)), registry)

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].selector_id, UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION)
            self.assertEqual(matches[0].source_kind, VisibleElementSourceKind.OCR)
            self.assertEqual(matches[0].extracted_text, "Daily Sale")
            self.assertEqual(
                registry.require(UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION).relative_bounds,
                RelativeBounds(x_ratio=0.1, y_ratio=0.2, width_ratio=0.4, height_ratio=0.18),
            )

    def test_pillow_selector_engine_rejects_non_world_text_for_world_map_ocr_regions(self) -> None:
        """Does not mark world-map OCR selectors visible when their crop only contains unrelated home-city text."""

        registry = build_default_selector_registry()
        selector_engine = PillowSelectorEngine(
            template_matcher=PillowTemplateMatcher(),
            ocr_service=_FakeOcrService(
                lines=(
                    _ocr_line("Build", x=18, y=47, width=46, height=14),
                    _ocr_line("Hero", x=16, y=920, width=44, height=18),
                )
            ),
        )

        matches = selector_engine.detect(
            Image.new("RGB", (540, 960), (0, 0, 0)),
            registry,
            selector_ids=(UiElementId.PNC_WORLD_COORDINATE_BAR, UiElementId.PNC_WORLD_HOME_NAV),
        )

        self.assertEqual(matches, [])

    def test_pillow_selector_engine_prefers_blue_filtered_world_coordinate_bar_ocr(self) -> None:
        """Uses the coordinate bar's blue-text-isolated OCR path so background castle labels do not block world-map proof."""

        registry = build_default_selector_registry()
        selector_engine = PillowSelectorEngine(
            template_matcher=PillowTemplateMatcher(),
            ocr_service=_CoordinateBarFilteringOcrService(
                raw_text="X:272-kV.498",
                filtered_text="X:272 Y:498",
            ),
        )
        image = Image.new("RGB", (540, 960), (18, 24, 40))
        coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate_region is not None
        bounds = coordinate_region.materialize_region(image_size=image.size)
        for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
            for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                image.putpixel((x, y), (42, 198, 224))

        matches = selector_engine.detect(
            image,
            registry,
            selector_ids=(UiElementId.PNC_WORLD_COORDINATE_BAR,),
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].selector_id, UiElementId.PNC_WORLD_COORDINATE_BAR)
        self.assertEqual(matches[0].extracted_text, "X:272 Y:498")

    def test_observation_builder_does_not_promote_home_city_to_world_map_from_region_noise(self) -> None:
        """Keeps home-city classification when world-map OCR regions contain unrelated text instead of real world-map anchors."""

        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
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

            observation = builder.build(screenshot)
            castle_entries = observation.entries(ListEntryKind.CASTLE)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
            self.assertEqual(len(castle_entries), 1)
            self.assertEqual(castle_entries[0].title_text, "Lv.5 Hellhound")

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
            self.assertEqual(observation.require(UiElementId.PNC_LOGIN_USERNAME_FIELD).bounds.x, 60)
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
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON).bounds.x, 159)
            self.assertEqual(observation.require(UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON).bounds.width, 340)
            self.assertEqual(observation.current_pnc_account_id, "user@example.com")

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
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Chat", x=181, y=20, width=113, height=49),
                            _ocr_line("Kingdom", x=202, y=117, width=143, height=40),
                            _ocr_line("Alliance", x=652, y=116, width=123, height=39),
                        )
                    ),
                    selector_registry=build_default_selector_registry(),
                ),
            )

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
                VisibleElementSourceKind.GEOMETRY,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_TAB_ALLIANCE).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_SEND_BUTTON).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_CHAT_INPUT_FIELD).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )

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
        self.assertGreater(ocr_service.read_text_calls, 0)

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
        self.assertGreater(ocr_service.read_text_calls, 0)

    def test_observation_builder_escalates_chat_send_follow_up_to_ocr_after_a_geometry_miss(self) -> None:
        """Falls back to OCR for post-send chat confirmation when the chat geometry heuristic misses."""

        observation, ocr_service = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.chat_send_follow_up(),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="",
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(observation.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(observation.chat_draft_empty)
        self.assertEqual(ocr_service.read_result_calls, 1)
        self.assertGreater(ocr_service.read_text_calls, 0)

    def test_send_chat_message_can_type_from_an_ocr_proven_chat_observation(self) -> None:
        """Allows chat sending to continue from an OCR fallback observation because chat state is populated."""

        observation, _ = _build_chat_observation_from_ocr_fallback(
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CHAT),
            active_channel=ChatChannel.ALLIANCE,
            draft_ocr_text="Pleaseter content",
        )
        fake_session = FakeSession()
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_CHAT,
                    visible_ids=(
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                        UiElementId.PNC_CHAT_INPUT_FIELD,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    ),
                    active_chat_channel=ChatChannel.ALLIANCE,
                    chat_draft_empty=True,
                )
            ]
        )
        executor = ActionExecutor(
            session=fake_session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )

        executor.execute_actions(
            ScreenFlowPlanner().send_chat_message(
                observation,
                message="hello",
                channel=ChatChannel.ALLIANCE,
            ),
            observation,
            observe=fake_observer.observe,
        )

        self.assertEqual(fake_session.texts, ["hello"])
        self.assertEqual(fake_session.key_events, [])
        self.assertEqual(fake_observer.requests, [ObservationRequest.chat_send_follow_up()])

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
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
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
                    Path(__file__).resolve().parents[1]
                    / "artifacts"
                    / "2026-03-13"
                    / "k287_pine_cobaye_1"
                    / "20260313T134419Z_live_send_chat_helper_post_action_1.png"
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
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
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

    def test_observation_builder_strips_alliance_tag_from_lord_info_current_castle_name(self) -> None:
        """Normalizes the Lord Info castle signal so alliance tags do not break target matching."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_lord_info_tagged",
                label="lord_info_tagged",
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
                            _ocr_line("[AAS] pine cobaye 1", x=190, y=1048, width=287, height=35),
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
            target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
            roster = PncAccountCastleRosterConfig(
                pnc_account_id="user@example.com",
                castles=(target_castle,),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_LORD_INFO)
            self.assertEqual(
                observation.require(UiElementId.PNC_LORD_INFO_NAME_LABEL).extracted_text,
                "[AAS] pine cobaye 1",
            )
            self.assertEqual(observation.current_castle_name, "pine cobaye 1")
            self.assertTrue(observation.current_castle_match(target_castle, roster=roster).matches)

    def test_home_city_follow_up_still_classifies_full_screen_settings_as_more_menu(self) -> None:
        """Keeps More > Settings identifiable during home-city follow-ups from Manage Char."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k304_more_settings_follow_up",
                label="more_settings_follow_up",
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

            observation = builder.build(
                screenshot,
                request=ObservationRequest.home_city_follow_up(ScreenType.PNC_CASTLE_SELECTION),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_MORE_MENU)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))

    def test_observation_builder_does_not_misclassify_trial_challenge_as_more_menu(self) -> None:
        """Requires distinct More-menu support text so repeated event-page Rank buttons do not spoof the overlay."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="trial_challenge_live_like",
                label="trial_challenge_live_like",
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
                            _ocr_line("Trial Challenge", x=184, y=18, width=340, height=55),
                            _ocr_line("Exchange", x=227, y=147, width=158, height=45),
                            _ocr_line("Progress", x=477, y=149, width=148, height=42),
                            _ocr_line("Total Rank", x=695, y=151, width=170, height=33),
                            _ocr_line("Hero Trial", x=252, y=282, width=172, height=34),
                            _ocr_line("Rank", x=263, y=422, width=60, height=24),
                            _ocr_line("Curio Trial", x=253, y=507, width=178, height=34),
                            _ocr_line("Rank", x=265, y=647, width=57, height=25),
                            _ocr_line("Gear Trial", x=253, y=955, width=168, height=37),
                            _ocr_line("Trial", x=716, y=1066, width=75, height=37),
                            _ocr_line("Rune Trial", x=213, y=1178, width=214, height=37),
                            _ocr_line("Rank", x=263, y=1321, width=63, height=24),
                            _ocr_line("Sauroi Trial", x=254, y=1406, width=192, height=34),
                            _ocr_line("Rank", x=263, y=1545, width=61, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_TRIAL_CHALLENGE)
            self.assertTrue(observation.has(UiElementId.PNC_TRIAL_CHALLENGE_HEADER))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))

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

    def test_observation_builder_exposes_shared_building_requirement_controls_on_exact_building_screens(self) -> None:
        """Recognizes unmet upgrade prerequisites on exact building-owned screens through shared OCR controls."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_infantry_requirement",
                label="infantry_requirement",
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
                            _ocr_line("Infantry Barracks", x=88, y=16, width=240, height=30),
                            _ocr_line("Glory Level", x=588, y=142, width=154, height=32),
                            _ocr_line("Upgrade", x=734, y=308, width=120, height=40),
                            _ocr_line("Requirement", x=59, y=714, width=177, height=32),
                            _ocr_line("Recruiting Center : Lv.7", x=152, y=769, width=278, height=28),
                            _ocr_line("Go", x=732, y=766, width=47, height=31),
                            _ocr_line("Materials required", x=58, y=866, width=246, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_INFANTRY_BARRACKS)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON))
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL).extracted_text,
                "Recruiting Center : Lv.7",
            )

    def test_observation_builder_classifies_castle_screen_when_territory_overview_wraps_across_two_ocr_lines(self) -> None:
        """Keeps Castle on its exact screen when OCR splits `Territory Overview` into stacked fragments."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_castle_split_overview",
                label="castle_split_overview",
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
                            _ocr_line("Castle", x=181, y=18, width=144, height=51),
                            _ocr_line("Territory", x=691, y=129, width=108, height=32),
                            _ocr_line("Overview", x=691, y=157, width=115, height=27),
                            _ocr_line("Glory Level", x=655, y=346, width=183, height=44),
                            _ocr_line("Upgrade", x=673, y=438, width=146, height=41),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE)
            self.assertTrue(observation.has(UiElementId.PNC_CASTLE_TERRITORY_OVERVIEW_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_CASTLE_GLORY_LEVEL_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))

    def test_observation_builder_classifies_exact_building_upgrade_confirmation_layout(self) -> None:
        """Keeps the exact building screen when the shared final-confirmation layout replaces the base tiles."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_wall_upgrade_confirm",
                label="wall_upgrade_confirm",
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
                            _ocr_line("Wall", x=182, y=18, width=107, height=50),
                            _ocr_line("Glory Level", x=655, y=346, width=182, height=42),
                            _ocr_line("Upgrade", x=672, y=437, width=146, height=41),
                            _ocr_line("Upgrade Now", x=401, y=459, width=210, height=32),
                            _ocr_line("Time", x=58, y=550, width=75, height=37),
                            _ocr_line("Requirement", x=61, y=714, width=176, height=30),
                            _ocr_line("Castle: Lv.8", x=153, y=768, width=141, height=27),
                            _ocr_line("Materials required", x=60, y=866, width=242, height=30),
                            _ocr_line("Effect", x=60, y=1036, width=83, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WALL)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL))
            self.assertTrue(observation.has(UiElementId.PNC_WALL_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_HEADER))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON))

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
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

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
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)

    def test_observation_builder_classifies_busy_builder_home_city_from_help_anchor(self) -> None:
        """Treats the occupied-builder Help label as the same canonical home-city build-slot signal."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_busy_builder_home",
                label="home_city_help_anchor",
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
                            _ocr_line("Help", x=27, y=354, width=58, height=28),
                            _ocr_line("(1/1)", x=20, y=389, width=76, height=26),
                            _ocr_line("Research", x=121, y=1182, width=118, height=29),
                            _ocr_line("Hero", x=219, y=1567, width=62, height=25),
                            _ocr_line("Bag", x=455, y=1565, width=54, height=32),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("Quest", x=333, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=571, y=1568, width=57, height=24),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_RESEARCH_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_MORE))

    def test_observation_builder_exposes_home_city_active_build_timer_and_building_level(self) -> None:
        """Adds the shared home-city timer proof plus building-level enrichment used by upgrade verification."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_city_active_build",
                label="home_city_active_build",
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
                            _ocr_line("Wall", x=455, y=918, width=81, height=28),
                            _ocr_line("6", x=506, y=956, width=22, height=22),
                            _ocr_line("00:48:33", x=404, y=872, width=140, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.metadata["active_build_timer_text"], "00:48:33")
            wall = observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    metadata_key="home_city_object_id",
                    metadata_value="wall",
                )
            )
            self.assertEqual(wall.level, 6)

    def test_observation_builder_classifies_build_queue_and_extracts_active_entry(self) -> None:
        """Recognizes the build queue overlay and exposes its active upgrading row for task verification."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_build_queue",
                label="build_queue",
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
                            _ocr_line("Build Queue", x=315, y=64, width=256, height=36),
                            _ocr_line("Upgrading: Wall", x=115, y=250, width=250, height=34),
                            _ocr_line("00:48:16", x=262, y=303, width=128, height=28),
                            _ocr_line("Speedup", x=673, y=244, width=154, height=40),
                            _ocr_line("2nd Build Queue", x=101, y=420, width=278, height=32),
                            _ocr_line("Idle", x=113, y=470, width=68, height=26),
                            _ocr_line("Go", x=754, y=468, width=52, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILD_QUEUE)
            active_entries = observation.entries(ListEntryKind.BUILDING)
            self.assertEqual(len(active_entries), 1)
            self.assertEqual(active_entries[0].title_text, "Wall")
            self.assertEqual(active_entries[0].timer_text, "00:48:16")
            self.assertEqual(active_entries[0].metadata["queue_state"], "upgrading")

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr(self) -> None:
        """Recognizes the live root-map layout so root navigation does not fall back to KEYCODE_BACK."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_map",
                label="world_map_live_like",
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
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_SEARCH_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertTrue(observation.has(UiElementId.PNC_CHAT_SHORTCUT))
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.WORLD_MAP)
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))
            self.assertLess(
                observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON).action_point[0],
                observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).bounds.x,
            )

    def test_observation_builder_preserves_world_map_invalid_coordinate_status_banner(self) -> None:
        """Carries the magnifier invalid-coordinate banner with the proven world-map observation."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_map_invalid_coordinate",
                label="world_map_invalid_coordinate",
            )
            registry = build_default_selector_registry()
            ocr_service = _FakeOcrService(
                lines=(
                    _ocr_line("Invalid coordinates", x=288, y=180, width=326, height=38),
                    _ocr_line("X:253", x=73, y=67, width=71, height=24),
                    _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                    _ocr_line("Home", x=63, y=1563, width=76, height=28),
                    _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                    _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                    _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                    _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                    _ocr_line("More", x=795, y=1568, width=70, height=25),
                )
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=ocr_service,
                    selector_registry=registry,
                ),
            )

            observation = builder.build(screenshot, request=ObservationRequest.source_screen_retry(ScreenType.PNC_WORLD_MAP))

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertEqual(observation.require(UiElementId.PNC_STATUS_BANNER).extracted_text, "Invalid coordinates")
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))

    def test_observation_builder_classifies_live_like_world_coordinate_dialog(self) -> None:
        """Recognizes the inline K/X/Y world-coordinate dialog layout and parses committed field values."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="live_like_world_coordinate_dialog",
                label="world_coordinate_dialog_live_like",
            )
            registry = build_default_selector_registry()
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:", x=76, y=398, width=26, height=26),
                            _ocr_line("226", x=132, y=400, width=38, height=24),
                            _ocr_line("X:", x=202, y=398, width=31, height=28),
                            _ocr_line("262", x=257, y=400, width=41, height=24),
                            _ocr_line("Y:", x=334, y=400, width=24, height=23),
                            _ocr_line("436", x=384, y=400, width=42, height=24),
                            _ocr_line("Go", x=253, y=532, width=36, height=26),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_coordinate_dialog_follow_up(),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_COORDINATE_DIALOG)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON))
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD).text, "226")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD).text, "262")
            self.assertEqual(observation.require_text_field_state(UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD).text, "436")

    def test_observation_builder_detects_world_overview_marker_without_hint_near_map_edge(self) -> None:
        """Falls back to the border-touching warm cluster when overview opens without a prior coordinate hint."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            registry = build_default_selector_registry()
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            map_region = registry.require(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION).relative_bounds
            assert map_region is not None
            map_region_bounds = map_region.materialize_region(image_size=image.size)
            _paint_synthetic_world_overview_map(image, map_region_bounds=map_region_bounds)
            _paint_overview_false_positive_blob(
                image,
                bounds=Bounds(
                    x=map_region_bounds.x + 84,
                    y=map_region_bounds.y + 57,
                    width=47,
                    height=41,
                ),
            )
            marker_point = project_world_coordinate_to_overview_point(
                coordinate=(20, 20),
                bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
                map_region_bounds=Bounds(
                    x=map_region_bounds.x,
                    y=map_region_bounds.y,
                    width=map_region_bounds.width,
                    height=map_region_bounds.height,
                ),
            )
            _paint_overview_viewport_marker(image, marker_point=marker_point)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="synthetic_world_overview_edge_marker",
                label="synthetic_world_overview_edge_marker",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:226 Reset", x=228, y=22, width=144, height=32),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_overview_follow_up(),
            )
            context = WorldMapOverviewNavigator().parse_context(observation)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER))
            self.assertEqual(
                observation.require(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER).source_kind,
                VisibleElementSourceKind.GEOMETRY,
            )
            self.assertLessEqual(abs(context.current_viewport_coordinate[0] - 20), 4)
            self.assertLessEqual(abs(context.current_viewport_coordinate[1] - 20), 4)

    def test_observation_builder_detects_world_overview_marker_with_coordinate_hint(self) -> None:
        """Uses the expected-coordinate hint to prefer the correct interior marker over a larger unrelated warm blob."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            registry = build_default_selector_registry()
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            map_region = registry.require(UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION).relative_bounds
            assert map_region is not None
            map_region_bounds = map_region.materialize_region(image_size=image.size)
            _paint_synthetic_world_overview_map(image, map_region_bounds=map_region_bounds)
            _paint_overview_false_positive_blob(
                image,
                bounds=Bounds(
                    x=map_region_bounds.x + 83,
                    y=map_region_bounds.y + 57,
                    width=47,
                    height=41,
                ),
            )
            marker_point = project_world_coordinate_to_overview_point(
                coordinate=(256, 512),
                bounds=WorldMapCoordinateDomain.puzzles_and_conquest().bounds,
                map_region_bounds=Bounds(
                    x=map_region_bounds.x,
                    y=map_region_bounds.y,
                    width=map_region_bounds.width,
                    height=map_region_bounds.height,
                ),
            )
            _paint_overview_viewport_marker(image, marker_point=marker_point)
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="synthetic_world_overview_hinted_marker",
                label="synthetic_world_overview_hinted_marker",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("K:226 Reset", x=228, y=22, width=144, height=32),
                        )
                    ),
                    selector_registry=registry,
                ),
            )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_overview_follow_up(expected_coordinate=(256, 512)),
            )
            context = WorldMapOverviewNavigator().parse_context(observation)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP_OVERVIEW)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER))
            self.assertEqual(context.current_viewport_coordinate, (256, 512))

    def test_observation_builder_classifies_world_map_from_coordinates_and_bottom_nav_ocr_at_alternate_resolution(self) -> None:
        """Recognizes the world map from OCR at the smaller supported live resolution too."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_world_map_small",
                label="world_map_live_like_small",
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
                            _ocr_line("X:253", x=44, y=41, width=42, height=18),
                            _ocr_line("Y:447", x=102, y=41, width=42, height=18),
                            _ocr_line("Home", x=38, y=937, width=46, height=17),
                            _ocr_line("Hero", x=126, y=938, width=38, height=17),
                            _ocr_line("Quest", x=200, y=939, width=45, height=15),
                            _ocr_line("Mail", x=321, y=939, width=35, height=16),
                            _ocr_line("Alliance", x=402, y=938, width=74, height=17),
                            _ocr_line("More", x=479, y=938, width=41, height=17),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.surface_type, SpatialSurfaceType.WORLD_MAP)
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))

    def test_observation_builder_uses_filtered_coordinate_bar_for_world_map_spatial_surface(self) -> None:
        """Uses the same blue-filtered coordinate OCR for both world-map proof and viewport coordinates."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            registry = build_default_selector_registry()
            coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
            assert coordinate_region is not None
            bounds = coordinate_region.materialize_region(image_size=image.size)
            for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
                for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                    image.putpixel((x, y), (42, 198, 224))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_world_map_filtered_coordinate",
                label="world_map_filtered_coordinate",
            )
            ocr_service = _CoordinateBarFilteringFullOcrService(
                raw_text="X:230-kV.958",
                filtered_text="X:230 Y:958",
                full_lines=(
                    _ocr_line("X: 2,736,039", x=185, y=42, width=123, height=30),
                    _ocr_line("Y:958", x=286, y=89, width=55, height=18),
                    _ocr_line("Home", x=38, y=937, width=46, height=17),
                    _ocr_line("Hero", x=126, y=938, width=38, height=17),
                    _ocr_line("Quest", x=200, y=939, width=45, height=15),
                    _ocr_line("Mail", x=321, y=939, width=35, height=16),
                    _ocr_line("Alliance", x=402, y=938, width=74, height=17),
                    _ocr_line("More", x=479, y=938, width=41, height=17),
                ),
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=PillowSelectorEngine(
                    template_matcher=PillowTemplateMatcher(),
                    ocr_service=ocr_service,
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(
                    ocr_service=ocr_service,
                    selector_registry=registry,
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.require(UiElementId.PNC_WORLD_COORDINATE_BAR).extracted_text, "X:230 Y:958")
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (230, 958))
            self.assertEqual(observation.spatial_surface.metadata["coordinate_text"], "X:230 Y:958")

    def test_observation_builder_builds_world_map_spatial_surface_with_typed_objects(self) -> None:
        """Parses typed world-map scene objects with relationships instead of forcing them into selectors."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (900, 1600), (15, 28, 68))
            image.paste((40, 90, 190), box=(200, 500, 410, 535))
            image.paste((90, 190, 220), box=(455, 640, 735, 675))
            image.paste((230, 210, 70), box=(305, 720, 605, 755))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_world_map_objects",
                label="world_map_objects",
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
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                            _ocr_line("My Territory", x=210, y=505, width=180, height=24),
                            _ocr_line("[RST] Alliance Tower", x=465, y=645, width=240, height=24),
                            _ocr_line("[BAD] Enemy Castle", x=315, y=725, width=220, height=24),
                            _ocr_line("Lv.29 Enchanted Reptilian", x=420, y=860, width=270, height=24),
                            _ocr_line("Food Farm", x=160, y=920, width=140, height=24),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (253, 447))
            self_castle = observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.CASTLE,
                    name_text="My Territory",
                )
            )
            self.assertEqual(self_castle.relationship, SpatialObjectRelationship.SELF)
            self.assertEqual(self_castle.viewport_offset, (-150, -235))
            self.assertAlmostEqual(self_castle.viewport_offset_ratio[0], -150 / 900)
            self.assertAlmostEqual(self_castle.viewport_offset_ratio[1], -235 / 1184)
            self.assertEqual(self_castle.estimated_world_coordinate, (103, 212))
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.ALLIANCE_BUILDING,
                        alliance_tag="RST",
                    )
                ).relationship,
                SpatialObjectRelationship.ALLY,
            )
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.CASTLE,
                        alliance_tag="BAD",
                    )
                ).relationship,
                SpatialObjectRelationship.OTHER,
            )
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.MONSTER,
                    )
                ).level,
                29,
            )
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.WORLD_MAP,
                        kind=SpatialObjectKind.RESOURCE_NODE,
                    )
                ).metadata["resource_type"],
                "food",
            )

    def test_world_map_spatial_surface_can_scan_a_requested_viewport_section(self) -> None:
        """Builds dynamic world interactables from only the requested world-view subsection when needed."""

        image = Image.new("RGB", (900, 1600), (15, 28, 68))
        image.paste((40, 90, 190), box=(200, 500, 410, 535))
        image.paste((90, 190, 220), box=(455, 640, 735, 675))
        image.paste((230, 210, 70), box=(305, 720, 605, 755))
        surface = build_world_map_spatial_surface(
            image=image,
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("My Territory", x=210, y=505, width=180, height=24),
                _ocr_line("[RST] Alliance Tower", x=465, y=645, width=240, height=24),
                _ocr_line("Food Farm", x=160, y=920, width=140, height=24),
            ),
            selector_registry=build_default_selector_registry(),
            object_scan_bounds=Bounds(x=0, y=460, width=430, height=180),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.metadata["scan_scope"], "section")
        self.assertEqual(surface.metadata["scan_bounds"], Bounds(x=0, y=460, width=430, height=180))
        self.assertEqual(len(surface.objects), 1)
        self.assertEqual(surface.objects[0].name_text, "My Territory")
        self.assertEqual(surface.objects[0].kind, SpatialObjectKind.CASTLE)
        self.assertEqual(surface.objects[0].viewport_offset, (-150, -235))
        self.assertAlmostEqual(surface.objects[0].viewport_offset_ratio[0], -150 / 900)
        self.assertAlmostEqual(surface.objects[0].viewport_offset_ratio[1], -235 / 1184)
        self.assertEqual(surface.objects[0].estimated_world_coordinate, (103, 212))

    def test_world_map_spatial_surface_accepts_coordinate_lines_when_ocr_orders_y_before_x(self) -> None:
        """Keeps valid world-map frames parseable when OCR emits the Y line before the X line."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("Y:447", x=177, y=65, width=69, height=24),
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("My Territory", x=210, y=505, width=180, height=24),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (253, 447))
        self.assertEqual(len(surface.objects), 1)

    def test_world_map_estimated_coordinates_are_resolution_invariant_for_matching_normalized_offsets(self) -> None:
        """Keeps estimated world coordinates stable when the same normalized object placement is observed at different resolutions."""

        baseline_surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("My Territory", x=210, y=505, width=180, height=24),
            ),
            selector_registry=build_default_selector_registry(),
        )
        scaled_surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (1800, 3200), (15, 28, 68)),
            lines=(
                _ocr_line("X:253", x=146, y=134, width=142, height=48),
                _ocr_line("Y:447", x=354, y=134, width=138, height=48),
                _ocr_line("My Territory", x=420, y=1010, width=360, height=48),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(baseline_surface)
        self.assertIsNotNone(scaled_surface)
        assert baseline_surface is not None
        assert scaled_surface is not None
        baseline_castle = baseline_surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.CASTLE,
                name_text="My Territory",
            )
        )
        scaled_castle = scaled_surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.CASTLE,
                name_text="My Territory",
            )
        )

        self.assertEqual(baseline_castle.estimated_world_coordinate, (103, 212))
        self.assertEqual(scaled_castle.estimated_world_coordinate, baseline_castle.estimated_world_coordinate)

    def test_world_map_spatial_surface_accepts_noisy_coordinate_bar_text(self) -> None:
        """Parses the viewport coordinates even when OCR injects extra characters around the X/Y tokens."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("NcX:246ed) Y:450", x=361, y=148, width=207, height=29),
                _ocr_line("My Territory", x=210, y=505, width=180, height=24),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (246, 450))

    def test_world_map_spatial_surface_accepts_split_noisy_x_coordinate_without_colon(self) -> None:
        """Parses the live coordinate bar when OCR drops the X-colon but still leaves split X/Y lines in the HUD."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("KX272", x=355, y=141, width=106, height=36),
                _ocr_line("Y:498", x=483, y=148, width=86, height=28),
                _ocr_line("43km", x=596, y=297, width=76, height=29),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (272, 498))

    def test_world_map_spatial_surface_ignores_resource_text_that_looks_like_x_coordinate(self) -> None:
        """Requires a coherent coordinate-bar X/Y pair instead of mixing top-HUD resource text with the map Y coordinate."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (540, 960), (15, 28, 68)),
            lines=(
                _ocr_line("X: 2,736,039", x=185, y=42, width=123, height=30),
                _ocr_line("X:230", x=223, y=87, width=56, height=21),
                _ocr_line("Y:958", x=286, y=89, width=55, height=18),
                _ocr_line("HellFortress 22", x=145, y=255, width=110, height=18),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (230, 958))

    def test_world_map_spatial_surface_trims_spurious_fourth_x_digit_from_live_coordinate_bar(self) -> None:
        """Keeps the world-map X coordinate in the live three-digit domain when OCR fuses an extra trailing digit."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (540, 960), (15, 28, 68)),
            lines=(
                _ocr_line("X:3511 Y:587", x=220, y=110, width=140, height=24),
                _ocr_line("Hell Fortress", x=310, y=270, width=110, height=18),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (351, 587))

    def test_world_map_spatial_surface_classifies_live_kingdom_labeled_castles(self) -> None:
        """Parses the live kingdom/id world-map castle label into one typed castle sighting."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:197", x=373, y=147, width=87, height=31),
                _ocr_line("Y:407", x=483, y=145, width=84, height=31),
                _ocr_line("K2875067781632", x=376, y=996, width=157, height=17),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        castle = surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.CASTLE,
                kingdom="K287",
            )
        )
        self.assertEqual(castle.name_text, "K2875067781632")
        self.assertEqual(castle.kingdom, "K287")
        self.assertEqual(castle.metadata["castle_identifier"], "5067781632")
        self.assertEqual(castle.estimated_world_coordinate, (201, 659))

    def test_world_map_spatial_surface_merges_wrapped_alliance_castle_name(self) -> None:
        """Keeps a wrapped alliance castle label as one canonical castle object with the full player name."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:239", x=373, y=147, width=87, height=31),
                _ocr_line("Y:483", x=483, y=145, width=84, height=31),
                _ocr_line("[DON]THE NORTH", x=320, y=1110, width=220, height=20),
                _ocr_line("FACE", x=388, y=1136, width=92, height=20),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        castles = surface.objects_of_kind(SpatialObjectKind.CASTLE)
        self.assertEqual(len(castles), 1)
        self.assertEqual(castles[0].alliance_tag, "DON")
        self.assertEqual(castles[0].name_text, "THE NORTH FACE")

    def test_world_map_spatial_surface_merges_wrapped_alliance_building_name(self) -> None:
        """Prefers the merged alliance-building label over the weaker single-line castle fallback."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("[RST] Alliance", x=455, y=645, width=180, height=24),
                _ocr_line("Tower", x=505, y=673, width=92, height=22),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        buildings = surface.objects_of_kind(SpatialObjectKind.ALLIANCE_BUILDING)
        self.assertEqual(len(buildings), 1)
        self.assertEqual(buildings[0].alliance_tag, "RST")
        self.assertEqual(buildings[0].name_text, "Alliance Tower")
        self.assertEqual(len(surface.objects_of_kind(SpatialObjectKind.CASTLE)), 0)

    def test_world_map_spatial_surface_skips_unclassified_noise_without_hanging(self) -> None:
        """Advances past non-object OCR lines instead of looping forever before the next valid map object."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:253", x=73, y=67, width=71, height=24),
                _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                _ocr_line("07:41:22", x=505, y=700, width=120, height=24),
                _ocr_line("My Territory", x=210, y=1010, width=180, height=24),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        castles = surface.objects_of_kind(SpatialObjectKind.CASTLE)
        self.assertEqual(len(castles), 1)
        self.assertEqual(castles[0].name_text, "My Territory")

    def test_world_map_spatial_surface_classifies_altar_dragonia_and_hell_fortress(self) -> None:
        """Parses the remaining planned neutral world-object classes as typed spatial objects."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:320", x=73, y=67, width=71, height=24),
                _ocr_line("Y:480", x=177, y=67, width=69, height=24),
                _ocr_line("Eastern Altar", x=180, y=540, width=190, height=24),
                _ocr_line("Dragonia", x=420, y=760, width=120, height=24),
                _ocr_line("Hell Fortress", x=530, y=920, width=160, height=24),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        altar = surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.ALTAR,
                name_text="Eastern Altar",
            )
        )
        dragonia = surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.DRAGONIA,
                name_text="Dragonia",
            )
        )
        hell_fortress = surface.require_object(
            _spatial_query(
                surface_type=SpatialSurfaceType.WORLD_MAP,
                kind=SpatialObjectKind.HELL_FORTRESS,
                name_text="Hell Fortress",
            )
        )
        self.assertEqual(altar.relationship, SpatialObjectRelationship.NEUTRAL)
        self.assertEqual(dragonia.relationship, SpatialObjectRelationship.NEUTRAL)
        self.assertEqual(hell_fortress.relationship, SpatialObjectRelationship.NEUTRAL)
        self.assertEqual(altar.estimated_world_coordinate, (145, 280))
        self.assertEqual(dragonia.estimated_world_coordinate, (350, 500))
        self.assertEqual(hell_fortress.estimated_world_coordinate, (480, 660))

    def test_world_map_spatial_surface_rejects_sections_outside_the_visible_viewport(self) -> None:
        """Fails fast when a caller requests a world-map scan region that cannot see any map content."""

        with self.assertRaises(SelectorResolutionError):
            build_world_map_spatial_surface(
                image=Image.new("RGB", (900, 1600), (15, 28, 68)),
                lines=(
                    _ocr_line("X:253", x=73, y=67, width=71, height=24),
                    _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                ),
                selector_registry=build_default_selector_registry(),
                object_scan_bounds=Bounds(x=0, y=1450, width=120, height=60),
            )

    def test_observation_builder_keeps_partial_world_coordinates_unknown(self) -> None:
        """Rejects partial world-coordinate OCR instead of classifying world map from weak evidence."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_partial",
                label="world_map_partial_coordinate",
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
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertIsNone(observation.spatial_surface)

    def test_observation_builder_classifies_world_map_when_coordinate_bar_omits_the_x_colon(self) -> None:
        """Builds the exact world-map surface when OCR keeps both axes even if the X token loses its colon."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_world_root",
                label="world_map_root_like",
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
                            _ocr_line("X292Y:540", x=346, y=140, width=223, height=39),
                            _ocr_line("[LFG]Mr_Zero", x=249, y=307, width=126, height=23),
                            _ocr_line("18km", x=594, y=296, width=77, height=31),
                            _ocr_line("Home", x=63, y=1563, width=76, height=28),
                            _ocr_line("Hero", x=213, y=1567, width=62, height=25),
                            _ocr_line("Quest", x=331, y=1571, width=69, height=20),
                            _ocr_line("Mail", x=533, y=1568, width=55, height=24),
                            _ocr_line("Alliance", x=666, y=1567, width=100, height=26),
                            _ocr_line("More", x=795, y=1568, width=70, height=25),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            self.assertTrue(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
            self.assertTrue(observation.has(UiElementId.PNC_BOTTOM_NAV_HOME))

    def test_world_coordinate_parser_accepts_fullwidth_colons_for_exact_world_map_proof(self) -> None:
        """Keeps fullwidth-colon OCR variants on the canonical coordinate parser path."""

        self.assertEqual(parse_world_coordinate_text("X\uff1a253 Y\uff1a987"), (253, 987))

    def test_world_map_root_coordinate_detection_uses_canonical_coordinate_parser(self) -> None:
        """Uses the same coordinate grammar for coarse root evidence, including omitted X colons."""

        image = Image.new("RGB", (900, 1600), (15, 28, 68))
        coordinate_line = _ocr_line("X253 Y\uff1a987", x=73, y=67, width=160, height=24)

        self.assertIs(
            _find_world_map_root_coordinate_line(
                image=image,
                lines=(coordinate_line,),
            ),
            coordinate_line,
        )

    def test_observation_builder_builds_home_city_spatial_surface_objects(self) -> None:
        """Parses home-city buildings and empty slots as spatial objects rather than list rows."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_objects",
                label="home_city_objects",
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=310, y=610, width=120, height=28),
                            _ocr_line("Academy", x=520, y=690, width=150, height=28),
                            _ocr_line("Build", x=450, y=840, width=90, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertIsNotNone(observation.spatial_surface)
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                        kind=SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                    )
                ).metadata["home_city_object_id"],
                "castle",
            )
            self.assertEqual(
                observation.require_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                        kind=SpatialObjectKind.HOME_BUILDING,
                        name_text="Academy",
                    )
                ).metadata["home_city_object_id"],
                "institute",
            )
            self.assertIsNotNone(
                observation.find_spatial_object(
                    _spatial_query(
                        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                        kind=SpatialObjectKind.HOME_EMPTY_SLOT,
                    )
                )
            )

    def test_home_city_spatial_objects_rebuild_from_each_viewport_observation(self) -> None:
        """Rebuilds home-city building targets from current OCR geometry instead of any fixed building coordinate."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=310, y=610, width=120, height=28),
                        )
                    )
                ),
            )
            shifted_builder = ObservationBuilder(
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
                            _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                            _ocr_line("More", x=740, y=1500, width=74, height=32),
                            _ocr_line("Castle", x=528, y=744, width=120, height=28),
                        )
                    )
                ),
            )
            initial_screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_viewport_initial",
                label="home_city_initial",
            )
            shifted_screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_home_viewport_shifted",
                label="home_city_shifted",
            )

            initial_observation = builder.build(initial_screenshot)
            shifted_observation = shifted_builder.build(shifted_screenshot)
            initial_castle = initial_observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                )
            )
            shifted_castle = shifted_observation.require_spatial_object(
                _spatial_query(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                )
            )

            self.assertNotEqual(initial_castle.bounds, shifted_castle.bounds)
            self.assertNotEqual(initial_castle.action_point, shifted_castle.action_point)
            self.assertEqual(initial_castle.viewport_offset, (-80, -176))
            self.assertAlmostEqual(initial_castle.viewport_offset_ratio[0], -80 / 900)
            self.assertAlmostEqual(initial_castle.viewport_offset_ratio[1], -176 / 1600)
            self.assertEqual(shifted_castle.viewport_offset, (138, -42))
            self.assertAlmostEqual(shifted_castle.viewport_offset_ratio[0], 138 / 900)
            self.assertAlmostEqual(shifted_castle.viewport_offset_ratio[1], -42 / 1600)
            self.assertEqual(initial_castle.metadata["home_city_object_id"], "castle")
            self.assertEqual(shifted_castle.metadata["home_city_object_id"], "castle")

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

    def test_observation_builder_classifies_research_queue_overlay_as_blocking_popup(self) -> None:
        """Recognizes the in-game research queue overlay as a popup so bootstrap stays inside the game."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_research_queue_popup",
                label="research_queue_popup",
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
                            _ocr_line("Research Queue", x=288, y=427, width=328, height=45),
                            _ocr_line("1st Research Queue", x=213, y=544, width=265, height=30),
                            _ocr_line("Go", x=700, y=573, width=50, height=35),
                            _ocr_line("Idle", x=208, y=596, width=58, height=33),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertTrue(observation.blocking_popup)

    def test_observation_builder_classifies_google_play_games_profile_prompt_as_blocking_popup(self) -> None:
        """Treats the external Google Play Games profile prompt as a recoverable popup instead of bootstrap unknown."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_google_play_games_popup",
                label="google_play_games_popup",
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
                            _ocr_line("Google Play Games", x=369, y=440, width=214, height=27),
                            _ocr_line("Create a Play Games profile", x=233, y=960, width=424, height=30),
                            _ocr_line("No profile", x=154, y=1097, width=109, height=30),
                            _ocr_line("Cancel", x=59, y=1529, width=78, height=24),
                            _ocr_line("Next", x=782, y=1530, width=56, height=22),
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

    def test_observation_builder_classifies_vip_daily_reset_popup_from_ocr(self) -> None:
        """Recognizes the VIP daily-reset popup as a dedicated blocking screen with a tappable Close button."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (384, 633), (15, 28, 68)))),
                artifact_directory="vip_daily_reset_popup",
                label="vip_daily_reset_popup",
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
                            _ocr_line("VIP", x=176, y=222, width=43, height=24),
                            _ocr_line("Log in every day to get VIP pts.", x=98, y=246, width=208, height=22),
                            _ocr_line("Gain VIP pts: 96", x=113, y=278, width=160, height=24),
                            _ocr_line("Consec. login days: 2", x=93, y=312, width=190, height=22),
                            _ocr_line("Pts to gain tomorrow: 112", x=90, y=339, width=205, height=20),
                            _ocr_line("Close", x=155, y=407, width=75, height=28),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_VIP_DAILY_RESET)
            self.assertTrue(observation.blocking_popup)
            self.assertTrue(observation.has(UiElementId.PNC_VIP_DAILY_RESET_HEADER))
            self.assertTrue(observation.has(UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_POPUP_CLOSE_BUTTON))

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

    def test_observation_builder_classifies_daily_to_do_from_live_like_ocr(self) -> None:
        """Recognizes the Daily To-Do overlay and exposes its canonical header anchor."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (400, 800), (15, 28, 68)))),
                artifact_directory="k157_daily_to_do",
                label="daily_to_do_live_like",
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
                            _ocr_line("Daily To-Do", x=110, y=93, width=160, height=28),
                            _ocr_line("Camp", x=17, y=150, width=55, height=21),
                            _ocr_line("Daily Quest", x=21, y=386, width=95, height=22),
                            _ocr_line("Go", x=251, y=179, width=37, height=20),
                            _ocr_line("Go", x=251, y=244, width=37, height=20),
                            _ocr_line("Tap to close", x=131, y=716, width=112, height=22),
                        )
                    )
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_DAILY_TO_DO)
            self.assertTrue(observation.has(UiElementId.PNC_DAILY_TO_DO_HEADER))

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

            self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
            self.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
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
                            CastleIdentity(kingdom="K230", castle_name="Lv.5 Hellhound", castle_level=8),
                            CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=10),
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
                        castles=(CastleIdentity(kingdom="K999", castle_name="Other Castle", castle_level=1),),
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
        """Keeps the last validated current castle on home-adjacent screens across Lord Info and Manage Char."""

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
                            current_castle=CastleIdentity(kingdom="K313", castle_name="K313alpha"),
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
            self.assertEqual(post_switch_home.current_castle_name, "K313alpha")

    def test_observation_service_carries_selected_manage_char_castle_back_to_home_adjacent_screens(self) -> None:
        """Keeps exact Manage Char castle selection on home-adjacent screens until a new switch flow starts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            selected_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_CASTLE_SELECTION, current_castle=selected_castle),
                        make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,)),
                        make_observation(ScreenType.PNC_MORE_MENU, visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,)),
                        make_observation(ScreenType.PNC_WORLD_MAP),
                    ]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="k287_manage_char_validation",
            )

            castle_selection = service.observe("castle_selection")
            home_city = service.observe("home_city")
            more_menu = service.observe("more_menu")
            world_map = service.observe("world_map")

            self.assertEqual(castle_selection.current_castle, selected_castle)
            self.assertEqual(home_city.current_castle, selected_castle)
            self.assertEqual(more_menu.current_castle, selected_castle)
            self.assertIsNone(world_map.current_castle)

    def test_observation_service_skips_routine_artifact_persistence_in_light_mode(self) -> None:
        """Leaves routine observations ephemeral in light mode so idle scheduler runs do not flood artifacts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[make_observation(ScreenType.PNC_HOME_CITY)]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="light_mode_test",
                mode=ObservationMode.LIGHT,
            )

            observation = service.observe("light_scan")

            self.assertIsNone(observation.artifact_path)
            self.assertFalse(any((root / "artifacts").rglob("*.png")))

    def test_observation_service_honors_explicit_artifact_requests_in_light_mode(self) -> None:
        """Still persists explicitly requested archive-grade captures while the runtime stays in light mode."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=_SequencedObservationBuilder(
                    observations=[make_observation(ScreenType.PNC_MAIL_THREAD)]
                ),
                session=_FakeScreenshotSession(payload),
                artifact_directory="light_mode_test",
                mode=ObservationMode.LIGHT,
            )

            capture = service.capture_observation("mail_thread_scan", request=ObservationRequest.mail_thread_observation())

            self.assertIsNotNone(capture.screenshot.artifact_path)
            self.assertTrue(any((root / "artifacts").rglob("*.png")))

    def test_observation_service_persists_unidentified_ocr_sidecars_only_in_debug_mode(self) -> None:
        """Writes a debug-only OCR sidecar for unmatched lines without changing normal light-mode behavior."""

        for mode, persist_request, expect_artifact, expect_sidecar in (
            (ObservationMode.DEBUG, None, True, True),
            (ObservationMode.LIGHT, None, False, False),
            (ObservationMode.LIGHT, ObservationRequest.mail_thread_observation(), True, False),
        ):
            with self.subTest(mode=mode, explicit_request=persist_request is not None):
                root = Path.cwd() / ".tmp_test_artifacts" / f"debug_sidecar_{mode.value}_{persist_request is not None}"
                if root.exists():
                    shutil.rmtree(root)
                root.mkdir(parents=True, exist_ok=True)
                try:
                    screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                    payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
                    registry = build_default_selector_registry()
                    ocr_service = _FakeOcrService(
                        lines=(
                            _ocr_line("X:253", x=73, y=67, width=71, height=24),
                            _ocr_line("Y:447", x=177, y=67, width=69, height=24),
                            _ocr_line("My Territory", x=210, y=505, width=180, height=24),
                            _ocr_line("Mystery Badge", x=640, y=820, width=140, height=24),
                            _ocr_line("Home", x=50, y=1564, width=90, height=24),
                            _ocr_line("Hero", x=215, y=1564, width=90, height=24),
                            _ocr_line("Quest", x=330, y=1569, width=90, height=24),
                            _ocr_line("Mail", x=570, y=1568, width=90, height=24),
                            _ocr_line("Alliance", x=665, y=1566, width=120, height=24),
                            _ocr_line("More", x=794, y=1567, width=90, height=24),
                        )
                    )
                    builder = ObservationBuilder(
                        selector_registry=registry,
                        selector_engine=PillowSelectorEngine(
                            template_matcher=PillowTemplateMatcher(),
                            ocr_service=UnavailableOcrService(),
                        ),
                        screen_classifier=ScreenClassifier(),
                        enricher=PncObservationEnricher(
                            ocr_service=ocr_service,
                            selector_registry=registry,
                        ),
                        debug_artifact_collector=ObservationDebugArtifactCollector(ocr_service=ocr_service),
                    )
                    service = ObservationService(
                        screenshot_service=screenshot_service,
                        observation_builder=builder,
                        session=_FakeScreenshotSession(payload),
                        artifact_directory="debug_sidecar_test",
                        mode=mode,
                    )

                    capture = service.capture_observation("world_scan", request=persist_request)

                    expected_screen_type = ScreenType.UNKNOWN if persist_request is not None else ScreenType.PNC_WORLD_MAP
                    self.assertEqual(capture.observation.screen_type, expected_screen_type)
                    if expect_artifact:
                        self.assertIsNotNone(capture.screenshot.artifact_path)
                    else:
                        self.assertIsNone(capture.screenshot.artifact_path)
                    artifact_files = tuple((root / "artifacts").rglob("*.png"))
                    self.assertEqual(bool(artifact_files), expect_artifact)
                    sidecar_files = tuple((root / "artifacts").rglob("*_unidentified_ocr.json"))
                    self.assertEqual(bool(sidecar_files), expect_sidecar)
                    if not expect_sidecar:
                        continue
                    document = json.loads(sidecar_files[0].read_text(encoding="utf-8"))
                    unidentified_texts = [entry["text"] for entry in document["unidentified_ocr_lines"]]
                    self.assertIn("Mystery Badge", unidentified_texts)
                    self.assertNotIn("My Territory", unidentified_texts)
                finally:
                    if root.exists():
                        shutil.rmtree(root)

    def test_chat_transcript_observation_uses_the_shared_artifact_mode_policy(self) -> None:
        """Keeps transcript captures ephemeral in light mode while preserving them in debug mode through the shared policy."""

        for mode, expect_artifact in (
            (ObservationMode.LIGHT, False),
            (ObservationMode.DEBUG, True),
        ):
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as temp_directory:
                    root = Path(temp_directory)
                    screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                    payload = _encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))
                    service = ObservationService(
                        screenshot_service=screenshot_service,
                        observation_builder=_SequencedObservationBuilder(
                            observations=[make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD)]
                        ),
                        session=_FakeScreenshotSession(payload),
                        artifact_directory="chat_transcript_mode_test",
                        mode=mode,
                    )

                    capture = service.capture_observation(
                        "chat_transcript_scan",
                        request=ObservationRequest.chat_transcript_observation(),
                    )

                    self.assertEqual(capture.observation.screen_type, ScreenType.PNC_CHAT)
                    if expect_artifact:
                        self.assertIsNotNone(capture.screenshot.artifact_path)
                        self.assertTrue(any((root / "artifacts").rglob("*.png")))
                    else:
                        self.assertIsNone(capture.screenshot.artifact_path)
                        self.assertFalse(any((root / "artifacts").rglob("*.png")))


def _ocr_line(text: str, *, x: int, y: int, width: int, height: int) -> OcrLine:
    """Builds one deterministic OCR line for tests."""

    return OcrLine(text=text, bounds=Region(x=x, y=y, width=width, height=height), confidence=0.99)


def _spatial_query(
    *,
    surface_type: SpatialSurfaceType,
    kind: SpatialObjectKind,
    relationship: SpatialObjectRelationship | None = None,
    name_text: str | None = None,
    alliance_tag: str | None = None,
    kingdom: str | None = None,
    level: int | None = None,
    metadata_key: str | None = None,
    metadata_value: object | None = None,
) -> SpatialObjectQuery:
    """Builds one typed spatial-object query for observation assertions."""

    return SpatialObjectQuery(
        surface_type=surface_type,
        kind=kind,
        relationship=relationship,
        name_text=name_text,
        alliance_tag=alliance_tag,
        kingdom=kingdom,
        level=level,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )


def _paint_synthetic_world_overview_map(image: Image.Image, *, map_region_bounds: Bounds) -> None:
    """Paints one simple parchment-like overview map body inside the calibrated selector bounds."""

    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (
            map_region_bounds.x,
            map_region_bounds.y,
            map_region_bounds.x + map_region_bounds.width,
            map_region_bounds.y + map_region_bounds.height,
        ),
        fill=(156, 138, 101),
    )
    draw.rectangle(
        (
            map_region_bounds.x + 2,
            map_region_bounds.y + 2,
            map_region_bounds.x + map_region_bounds.width - 2,
            map_region_bounds.y + map_region_bounds.height - 2,
        ),
        outline=(86, 74, 56),
        width=2,
    )


def _paint_overview_false_positive_blob(image: Image.Image, *, bounds: Bounds) -> None:
    """Paints one unrelated warm blob that the detector must ignore when a better marker candidate exists."""

    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (
            bounds.x,
            bounds.y,
            bounds.x + bounds.width,
            bounds.y + bounds.height,
        ),
        fill=(198, 115, 34),
    )


def _paint_overview_viewport_marker(image: Image.Image, *, marker_point: tuple[int, int]) -> None:
    """Paints one stylized orange overview viewport marker around the requested point."""

    draw = ImageDraw.Draw(image)
    warm = (255, 170, 52)
    glow = (218, 118, 30)
    half_width = 18
    half_height = 14
    arm = 10
    thickness = 3
    left = marker_point[0] - half_width
    right = marker_point[0] + half_width
    top = marker_point[1] - half_height
    bottom = marker_point[1] + half_height
    for offset in range(thickness):
        draw.line((left, top + offset, left + arm, top + offset), fill=warm, width=1)
        draw.line((left + offset, top, left + offset, top + arm), fill=warm, width=1)
        draw.line((right - arm, top + offset, right, top + offset), fill=warm, width=1)
        draw.line((right - offset, top, right - offset, top + arm), fill=warm, width=1)
        draw.line((left, bottom - offset, left + arm, bottom - offset), fill=warm, width=1)
        draw.line((left + offset, bottom - arm, left + offset, bottom), fill=warm, width=1)
        draw.line((right - arm, bottom - offset, right, bottom - offset), fill=warm, width=1)
        draw.line((right - offset, bottom - arm, right - offset, bottom), fill=warm, width=1)
    draw.rectangle(
        (
            marker_point[0] - 3,
            marker_point[1] - 3,
            marker_point[0] + 3,
            marker_point[1] + 3,
        ),
        fill=glow,
    )


def _encode_png(image: Image.Image) -> bytes:
    """Encodes one PIL image into PNG bytes for screenshot tests."""

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
