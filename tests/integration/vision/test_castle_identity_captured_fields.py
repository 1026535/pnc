"""Selected-castle identity qualification against sanitized Manage Char captures."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageStat

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    ListEntryKind,
    Observation,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_diagnostics import ObservationDebugArtifactCollector
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import Region, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrRequiredFieldStatus,
    OcrResult,
    OcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession, make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import (
    _require_rapid_ocr_service,
)


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition" / "castle_identity_variants"
FIXTURES = ("castle_identity_0042.png", "castle_identity_0108.png")
BOTTOM_FIXTURE = "castle_identity_3xx_holdout.png"
VIEWPORT = (900, 1600)
SCALED_VIEWPORT = (540, 960)
ROSTER_REGION = Bounds(180, 112, 558, 1472)
TARGET_NAME = "0 sticker NPC"
UNSTABLE_NAME = "0 stickerNPC"
NAME_REGION = Bounds(190, 522, 217, 75)
TARGET_NAME_BOUNDS = Bounds(201, 545, 165, 29)
TARGET_ROW_BOUNDS = Bounds(0, 497, 900, 126)
BOTTOM_NAME = "K3033849ba8778"
BOTTOM_KINGDOM = "K303"
BOTTOM_LEVEL = 5
BOTTOM_KINGDOM_BOUNDS = Bounds(205, 1427, 195, 28)
BOTTOM_NAME_BOUNDS = Bounds(207, 1471, 199, 20)
BOTTOM_LEVEL_BOUNDS = Bounds(206, 1507, 164, 27)
BOTTOM_ROW_BOUNDS = Bounds(0, 1419, 900, 127)


def _load_fixture(name: str) -> Image.Image:
    """Load one native-size sanitized Manage Char capture."""

    path = FIXTURE_ROOT / name
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != VIEWPORT:
        raise AssertionError(f"Castle identity fixture {path} has unexpected size {image.size}.")
    return image


def _capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach immutable frame provenance to one fixture image."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _line(text: str, bounds: Bounds) -> OcrLine:
    """Build one localized OCR line in native capture coordinates."""

    return OcrLine(text=text, bounds=bounds, confidence=1.0)


_ROSTER_LINES = (
    _line("K314 Kingdom", Bounds(205, 139, 196, 27)),
    _line("Other castle one", Bounds(207, 181, 170, 21)),
    _line("Castle Level 1", Bounds(207, 219, 161, 25)),
    _line("K289 Kingdom", Bounds(203, 320, 198, 33)),
    _line("Other castle two", Bounds(206, 363, 170, 28)),
    _line("Castle Level 7", Bounds(206, 401, 164, 28)),
    _line("K157 Kingdom", Bounds(205, 505, 195, 29)),
    _line(UNSTABLE_NAME, Bounds(205, 547, 157, 25)),
    _line("Castle Level 15", Bounds(206, 589, 177, 22)),
)


@dataclass(slots=True)
class _RosterOcrService:
    """Return crop-owned roster lines while rejecting whole-frame OCR."""

    refined_mode: str = "exact"
    missing_name_region_y: int | None = None
    calls: list[Bounds | None] = field(default_factory=list)
    roster_pass_names: list[str] = field(default_factory=list)
    authoritative_names: list[str] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Return lines contained by the requested crop and track ownership stages."""

        self.calls.append(region)
        whole_frame = Bounds(0, 0, *image.size)
        if region is None or region == whole_frame:
            raise AssertionError("Castle identity OCR must use strict screenshot crops.")

        if region == ROSTER_REGION:
            self.roster_pass_names.append(UNSTABLE_NAME)
            lines = _ROSTER_LINES
        elif self.missing_name_region_y is not None and region.y == self.missing_name_region_y:
            lines = ()
        elif region == NAME_REGION:
            if self.refined_mode == "exact":
                lines = (_line(TARGET_NAME, TARGET_NAME_BOUNDS),)
                self.authoritative_names.append(TARGET_NAME)
            elif self.refined_mode == "old_spelling":
                lines = (_line(UNSTABLE_NAME, TARGET_NAME_BOUNDS),)
                self.authoritative_names.append(UNSTABLE_NAME)
            elif self.refined_mode == "fragmented":
                lines = (
                    _line("0 sticker", Bounds(201, 545, 86, 29)),
                    _line("NPC", Bounds(292, 545, 50, 29)),
                )
            elif self.refined_mode == "unknown":
                lines = ()
            else:
                raise AssertionError(f"Unknown refined mode {self.refined_mode!r}.")
        else:
            lines = _ROSTER_LINES
        contained = tuple(line for line in lines if region.contains_bounds(line.bounds))
        return OcrResult(
            lines=contained,
            words=tuple(word for line in contained for word in line.words),
        )

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Expose the bounded line protocol through the same result read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Expose the bounded text protocol through the same result read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _scale_bounds(bounds: Bounds, image_size: tuple[int, int]) -> Bounds:
    """Scale native captured OCR bounds to one of the reviewed viewport sizes."""

    scale_x = image_size[0] / VIEWPORT[0]
    scale_y = image_size[1] / VIEWPORT[1]
    return Bounds(
        round(bounds.x * scale_x),
        round(bounds.y * scale_y),
        round(bounds.width * scale_x),
        round(bounds.height * scale_y),
    )


@dataclass(slots=True)
class _BottomRosterOcrService:
    """Serve only the selected bottom row through bounded, scale-aware crops."""

    calls: list[Bounds | None] = field(default_factory=list)

    def _lines(self, image: Image.Image) -> tuple[OcrLine, ...]:
        return tuple(
            _line(text, _scale_bounds(bounds, image.size))
            for text, bounds in (
                ("+ Manage Char.", Bounds(0, 0, 900, 104)),
                (f"{BOTTOM_KINGDOM} Kingdom", BOTTOM_KINGDOM_BOUNDS),
                (BOTTOM_NAME, BOTTOM_NAME_BOUNDS),
                (f"Castle Level {BOTTOM_LEVEL}", BOTTOM_LEVEL_BOUNDS),
            )
        )

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Return selected-row lines contained by the requested strict crop."""

        self.calls.append(region)
        whole_frame = Bounds(0, 0, *image.size)
        if region is None or region == whole_frame:
            raise AssertionError("Bottom castle identity OCR must use strict screenshot crops.")
        lines = tuple(line for line in self._lines(image) if region.contains_bounds(line.bounds))
        return OcrResult(
            lines=lines,
            words=tuple(word for line in lines for word in line.words),
        )

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Expose the bounded line protocol."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Expose the bounded text protocol."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Keep optional captured RapidOCR replay from falling back to full-frame reads."""

    delegate: OcrService
    calls: list[Bounds | None] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Read one strict crop with the installed RapidOCR backend."""

        self.calls.append(region)
        whole_frame = Bounds(0, 0, *image.size)
        if region is None or region == whole_frame:
            raise AssertionError("Captured castle replay must use strict screenshot crops.")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Expose the bounded line protocol."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Expose the bounded text protocol."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _wire(
    ocr: _RosterOcrService | _BottomRosterOcrService | _BoundedRapidOcrService,
) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production perception paths with the controlled crop-aware backend."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    recognizer = load_visual_screen_recognizer(matcher=matcher)
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        visual_recognizer=recognizer,
        ocr_service=ocr,
        ocr_backend_revision="castle-identity-captured-qualification",
    )
    navigation = NavigationPerception(
        recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return builder, navigation


def _assert_bounded(test: unittest.TestCase, ocr: _RosterOcrService) -> None:
    """Require every backend call to name a strict native screenshot crop."""

    test.assertTrue(ocr.calls)
    test.assertTrue(all(region is not None for region in ocr.calls))
    test.assertTrue(all(region != Bounds(0, 0, *VIEWPORT) for region in ocr.calls))
    test.assertIn(ROSTER_REGION, ocr.calls)
    test.assertIn(NAME_REGION, ocr.calls)


def _assert_rapid_bounded(
    test: unittest.TestCase,
    ocr: _BoundedRapidOcrService,
    image_size: tuple[int, int],
) -> None:
    """Require actual replay to use the reviewed roster and name crops only."""

    whole_frame = Bounds(0, 0, *image_size)
    test.assertTrue(ocr.calls)
    test.assertTrue(all(region is not None and region != whole_frame for region in ocr.calls))
    test.assertIn(_scale_bounds(ROSTER_REGION, image_size), ocr.calls)


def _assert_common_observation(
    test: unittest.TestCase,
    observation: Observation,
    capture: CapturedScreenshot,
    *,
    viewport: tuple[int, int] = VIEWPORT,
) -> None:
    """Require independent Manage Char identity and frame-local provenance."""

    test.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
    test.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
    test.assertEqual(observation.decision.layout_id, "manage_char")
    test.assertEqual(observation.frame_ref, capture.frame_ref)
    test.assertEqual(observation.image_size, viewport)
    test.assertTrue(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
    back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
    test.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
    for element in observation.visible_elements.values():
        test.assertEqual(element.frame_ref, capture.frame_ref)
        test.assertEqual(element.source_screen, ScreenType.PNC_CASTLE_SELECTION)
        test.assertEqual(element.source_layout_id, "manage_char")


class CastleIdentityCapturedFieldTests(unittest.TestCase):
    """Keep selected-castle identity exact across both OCR consumers."""

    def test_sanitized_captures_preserve_manage_char_and_source_background_trigger(self) -> None:
        """Sanitized fixtures retain the visual layout, checkmark, and gray/blue row change."""

        recognizer = load_visual_screen_recognizer()
        first_row_pixels = []
        for name in FIXTURES:
            image = _load_fixture(name)
            result = recognizer.recognize(image)
            self.assertEqual(result.profile_ids, ("manage_char",))
            self.assertEqual(
                {control.selector_id for control in result.controls},
                {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
            )
            first_row_pixels.append(image.getpixel((500, 180)))
            green_checkmark_pixels = sum(
                1
                for y in range(
                    TARGET_ROW_BOUNDS.y,
                    TARGET_ROW_BOUNDS.y + TARGET_ROW_BOUNDS.height,
                )
                for x in range(int(VIEWPORT[0] * 0.82), VIEWPORT[0])
                if (
                    (pixel := image.getpixel((x, y)))[1] >= 140
                    and pixel[1] >= pixel[0] + 35
                    and pixel[1] >= pixel[2] + 35
                )
            )
            self.assertGreater(green_checkmark_pixels, 24)
            for bounds in (Bounds(195, 173, 253, 38), Bounds(195, 355, 247, 43)):
                crop = image.crop(
                    (bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height),
                )
                self.assertLessEqual(
                    max(channel_max for _channel_min, channel_max in ImageStat.Stat(crop).extrema),
                    100,
                )

        gray, blue = first_row_pixels
        self.assertLessEqual(max(gray) - min(gray), 15)
        self.assertGreater(blue[2] - blue[0], 25)
        self.assertNotEqual(gray, blue)

    def test_authoritative_owned_name_overrides_unstable_roster_pass_in_both_paths(self) -> None:
        """The exact padded row read publishes selected K157 without normalization."""

        expected = CastleIdentity(kingdom="K157", castle_name=TARGET_NAME, castle_level=15)
        for fixture_name in FIXTURES:
            with self.subTest(fixture=fixture_name):
                capture = _capture(_load_fixture(fixture_name), session_id=f"castle:{fixture_name}")
                for producer in ("builder", "navigation"):
                    with self.subTest(producer=producer):
                        ocr = _RosterOcrService(refined_mode="exact")
                        builder, navigation = _wire(ocr)
                        observation = (
                            builder.build(
                                capture,
                                request=ObservationRequest.source_screen_retry(
                                    ScreenType.PNC_CASTLE_SELECTION,
                                ),
                            )
                            if producer == "builder"
                            else navigation.build(capture, include_content=True)
                        )
                        _assert_common_observation(self, observation, capture)
                        entries = observation.entries(ListEntryKind.CASTLE)
                        self.assertEqual(len(entries), 3)
                        entry = next(entry for entry in entries if entry.selected)
                        self.assertEqual(entry.title_text, TARGET_NAME)
                        self.assertNotEqual(entry.title_text, UNSTABLE_NAME)
                        self.assertEqual(entry.bounds, TARGET_ROW_BOUNDS)
                        self.assertEqual(entry.metadata["name_bounds"], (201, 545, 165, 29))
                        self.assertTrue(entry.selected)
                        self.assertEqual(entry.frame_ref, capture.frame_ref)
                        self.assertEqual(entry.source_screen, ScreenType.PNC_CASTLE_SELECTION)
                        self.assertEqual(entry.source_layout_id, "manage_char")
                        self.assertEqual(observation.current_castle, expected)
                        self.assertEqual(
                            observation.current_castle_evidence,
                            CurrentCastleEvidenceKind.EXACT,
                        )
                        _assert_bounded(self, ocr)
                        self.assertEqual(ocr.roster_pass_names, [UNSTABLE_NAME])
                        self.assertEqual(ocr.authoritative_names, [TARGET_NAME])

    def test_missing_earlier_row_name_is_retained_when_later_rows_are_present(self) -> None:
        """The artifact sidecar keeps a missing first row distinct from later successes."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = _load_fixture(FIXTURES[0])
            screenshot = ScreenshotService(
                artifact_store=ArtifactStore(root=root / "artifacts"),
            ).capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="castle_row_name_gap",
                label="castle_row_name_gap",
            )
            ocr = _RosterOcrService(missing_name_region_y=160)
            builder, _ = _wire(ocr)
            builder.debug_artifact_collector = ObservationDebugArtifactCollector()
            context = builder.create_ocr_context(screenshot)
            observation = builder.build(
                screenshot,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_CASTLE_SELECTION),
                ocr_context=context,
            )

            selected = next(entry for entry in observation.entries(ListEntryKind.CASTLE) if entry.selected)
            self.assertEqual(selected.title_text, TARGET_NAME)
            row_diagnostics = tuple(
                diagnostic
                for diagnostic in context.required_field_diagnostics
                if diagnostic.required_fact.startswith("castle_row_name[")
            )
            self.assertEqual(
                [(diagnostic.region.y, diagnostic.status) for diagnostic in row_diagnostics],
                [
                    (160, OcrRequiredFieldStatus.MISSING),
                    (335, OcrRequiredFieldStatus.PRESENT),
                    (522, OcrRequiredFieldStatus.PRESENT),
                ],
            )
            row_reads = tuple(
                read for read in context.read_diagnostics
                if read.required_fact is not None
                and read.required_fact.startswith("castle_row_name[")
            )
            self.assertEqual(
                {read.required_fact for read in row_reads},
                {diagnostic.required_fact for diagnostic in row_diagnostics},
            )

            assert screenshot.artifact_path is not None
            sidecar = screenshot.artifact_path.with_name(
                f"{screenshot.artifact_path.stem}_recognition_gap.json",
            )
            document = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(
                [field["region"]["y"] for field in document["missing_required_fields"]],
                [160],
            )

    def test_captured_bottom_selected_identity_survives_full_roster_crop_and_scale(self) -> None:
        """The complete selected eighth card remains associated at native and reviewed scale."""

        expected = CastleIdentity(
            kingdom=BOTTOM_KINGDOM,
            castle_name=BOTTOM_NAME,
            castle_level=BOTTOM_LEVEL,
        )
        expected_rows = {
            VIEWPORT: BOTTOM_ROW_BOUNDS,
            # The parser's scale-local minimum row height keeps the tap region
            # usable after the 0.6x review resize.
            SCALED_VIEWPORT: Bounds(0, 848, 540, 96),
        }
        for size, row_bounds in expected_rows.items():
            with self.subTest(size=size):
                source = _load_fixture(BOTTOM_FIXTURE)
                image = source if size == VIEWPORT else source.resize(size, Image.Resampling.LANCZOS)
                capture = _capture(image, session_id=f"castle:bottom:{size[0]}")
                expected_name_bounds = _scale_bounds(BOTTOM_NAME_BOUNDS, size)
                expected_level_bounds = _scale_bounds(BOTTOM_LEVEL_BOUNDS, size)
                for producer in ("builder", "navigation"):
                    with self.subTest(producer=producer):
                        ocr = _BottomRosterOcrService()
                        builder, navigation = _wire(ocr)
                        observation = (
                            builder.build(
                                capture,
                                request=ObservationRequest.source_screen_retry(
                                    ScreenType.PNC_CASTLE_SELECTION,
                                ),
                            )
                            if producer == "builder"
                            else navigation.build(capture, include_content=True)
                        )
                        _assert_common_observation(self, observation, capture, viewport=size)
                        entries = observation.entries(ListEntryKind.CASTLE)
                        self.assertEqual(len(entries), 1)
                        selected = entries[0]
                        self.assertTrue(selected.selected)
                        self.assertEqual(selected.title_text, BOTTOM_NAME)
                        self.assertEqual(selected.subtitle_text, f"{BOTTOM_KINGDOM} Kingdom")
                        self.assertEqual(selected.bounds, row_bounds)
                        self.assertEqual(
                            selected.metadata["name_bounds"],
                            (
                                expected_name_bounds.x,
                                expected_name_bounds.y,
                                expected_name_bounds.width,
                                expected_name_bounds.height,
                            ),
                        )
                        self.assertEqual(selected.metadata["kingdom"], BOTTOM_KINGDOM)
                        self.assertEqual(selected.metadata["castle_level"], BOTTOM_LEVEL)
                        self.assertEqual(observation.current_castle, expected)
                        self.assertEqual(
                            observation.current_castle_evidence,
                            CurrentCastleEvidenceKind.EXACT,
                        )
                        self.assertTrue(
                            any(
                                region is not None
                                and region.y <= _scale_bounds(BOTTOM_KINGDOM_BOUNDS, size).y
                                and region.y + region.height >= expected_level_bounds.y + expected_level_bounds.height
                                for region in ocr.calls
                            )
                        )
                        self.assertTrue(
                            all(region is not None and region != Bounds(0, 0, *size) for region in ocr.calls)
                        )

    def test_real_rapidocr_replay_associates_bottom_identity_both_paths(self) -> None:
        """Actual offline OCR keeps the selected bottom card's fields together."""

        for size in (VIEWPORT, SCALED_VIEWPORT):
            with self.subTest(size=size):
                source = _load_fixture(BOTTOM_FIXTURE)
                image = source if size == VIEWPORT else source.resize(size, Image.Resampling.LANCZOS)
                capture = _capture(image, session_id=f"castle:bottom:rapid:{size[0]}")
                for producer in ("builder", "navigation"):
                    with self.subTest(producer=producer):
                        ocr = _BoundedRapidOcrService(
                            _require_rapid_ocr_service(self)
                        )
                        builder, navigation = _wire(ocr)
                        observation = (
                            builder.build(
                                capture,
                                request=ObservationRequest.source_screen_retry(
                                    ScreenType.PNC_CASTLE_SELECTION,
                                ),
                            )
                            if producer == "builder"
                            else navigation.build(capture, include_content=True)
                        )
                        _assert_common_observation(self, observation, capture, viewport=size)
                        entries = observation.entries(ListEntryKind.CASTLE)
                        self.assertEqual(len(entries), 1)
                        selected = entries[0]
                        self.assertTrue(selected.selected)
                        self.assertEqual(selected.title_text, BOTTOM_NAME)
                        self.assertEqual(
                            selected.subtitle_text.replace(" ", ""),
                            f"{BOTTOM_KINGDOM}Kingdom",
                        )
                        self.assertEqual(selected.metadata["kingdom"], BOTTOM_KINGDOM)
                        self.assertEqual(selected.metadata["castle_level"], BOTTOM_LEVEL)
                        self.assertEqual(observation.current_castle, CastleIdentity(
                            kingdom=BOTTOM_KINGDOM,
                            castle_name=BOTTOM_NAME,
                            castle_level=BOTTOM_LEVEL,
                        ))
                        name_bounds = Bounds(*selected.metadata["name_bounds"])
                        self.assertTrue(selected.bounds.contains_bounds(name_bounds))
                        self.assertTrue(selected.bounds.contains_point(selected.action_point))
                        _assert_rapid_bounded(self, ocr, size)


    def test_authoritative_old_spelling_remains_distinct_from_requested_target(self) -> None:
        """A no-space authoritative crop stays a different castle name under exact matching."""

        capture = _capture(_load_fixture(FIXTURES[0]), session_id="castle:old-spelling")
        ocr = _RosterOcrService(refined_mode="old_spelling")
        builder, _navigation = _wire(ocr)
        observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_CASTLE_SELECTION),
        )
        selected = next(
            entry for entry in observation.entries(ListEntryKind.CASTLE) if entry.selected
        )
        self.assertEqual(selected.title_text, UNSTABLE_NAME)
        self.assertNotEqual(selected.title_text, TARGET_NAME)
        self.assertIsNotNone(observation.current_castle)
        assert observation.current_castle is not None
        self.assertEqual(observation.current_castle.castle_name, UNSTABLE_NAME)
        self.assertNotEqual(observation.current_castle, CastleIdentity("K157", TARGET_NAME, 15))
        _assert_bounded(self, ocr)

    def test_unknown_or_fragmented_owned_name_omits_row_but_keeps_screen_and_back(self) -> None:
        """An unusable refined name cannot create selected identity or a partial row."""

        capture = _capture(_load_fixture(FIXTURES[0]), session_id="castle:missing-name")
        for mode in ("unknown", "fragmented"):
            with self.subTest(mode=mode):
                for producer in ("builder", "navigation"):
                    with self.subTest(producer=producer):
                        ocr = _RosterOcrService(refined_mode=mode)
                        builder, navigation = _wire(ocr)
                        observation = (
                            builder.build(
                                capture,
                                request=ObservationRequest.source_screen_retry(
                                    ScreenType.PNC_CASTLE_SELECTION,
                                ),
                            )
                            if producer == "builder"
                            else navigation.build(capture, include_content=True)
                        )
                        _assert_common_observation(self, observation, capture)
                        entries = observation.entries(ListEntryKind.CASTLE)
                        self.assertEqual(len(entries), 2)
                        self.assertTrue(all(not entry.selected for entry in entries))
                        self.assertNotIn(TARGET_NAME, {entry.title_text for entry in entries})
                        self.assertIsNone(observation.current_castle)
                        self.assertIsNone(observation.current_castle_evidence)
                        self.assertFalse(observation.has(UiElementId.PNC_CASTLE_LIST_ENTRY))
                        self.assertFalse(observation.has(UiElementId.PNC_CASTLE_SELECTED_CHECKMARK))
                        _assert_bounded(self, ocr)
                        self.assertEqual(ocr.roster_pass_names, [UNSTABLE_NAME])
                        self.assertEqual(ocr.authoritative_names, [])

    def test_foreign_frame_ocr_context_is_rejected_before_reading(self) -> None:
        """A context owned by one capture cannot be reused for another frame."""

        first = _capture(_load_fixture(FIXTURES[0]), session_id="castle:context-first")
        second = _capture(_load_fixture(FIXTURES[1]), session_id="castle:context-second")
        ocr = _RosterOcrService(refined_mode="exact")
        builder, _navigation = _wire(ocr)
        context = builder.create_ocr_context(first)
        with self.assertRaisesRegex(ValueError, "different from its captured frame"):
            builder.build(
                second,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_CASTLE_SELECTION),
                ocr_context=context,
            )
        self.assertEqual(ocr.calls, [])


if __name__ == "__main__":
    unittest.main()
