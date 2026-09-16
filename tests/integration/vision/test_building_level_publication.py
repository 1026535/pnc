"""Building-level publication remains frame-local when OCR identity is noisy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionPreprocessing,
    OcrRegionPurpose,
    compile_guard_ocr_region_plans,
    compile_screen_content_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds, Region
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrService,
    OcrRequiredFieldStatus,
    OcrResult,
    RapidOcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
BUILDING_FIXTURES = FIXTURES / "building_variants"


def _capture(
    path: str,
    *,
    session_id: str,
    size: tuple[int, int] | None = None,
) -> CapturedScreenshot:
    """Attach fresh canonical provenance to one committed visual fixture."""

    with Image.open(FIXTURES / path) as source:
        image = source.convert("RGB")
    if size is not None:
        image = image.resize(size, Image.Resampling.LANCZOS)
    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(tz=UTC),
        frame_ref=frame.frame_ref,
    )


def _farm_capture(
    *, session_id: str, name: str = "farm_level_one_detail.png",
) -> CapturedScreenshot:
    """Load one reviewed Farm detail capture at its native 900x1600 size."""

    with Image.open(BUILDING_FIXTURES / name) as source:
        image = source.convert("RGB")
    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(tz=UTC),
        frame_ref=frame.frame_ref,
    )


def _farm_lines(*, title: str | None = "Farm", level: str | None = "1/45") -> tuple[OcrLine, ...]:
    """Return crop-filterable OCR facts for the reviewed Farm detail."""

    lines = [
        OcrLine("Where Food is produced. Upgrade", Bounds(471, 245, 415, 26), 1.0),
        OcrLine("Upgrade", Bounds(671, 440, 147, 37), 1.0),
        OcrLine("Time", Bounds(59, 552, 71, 29), 1.0),
        OcrLine("Requirement", Bounds(62, 713, 177, 27), 1.0),
        OcrLine("Materials required", Bounds(61, 865, 251, 26), 1.0),
        OcrLine("Effect", Bounds(60, 1035, 83, 31), 1.0),
    ]
    if title is not None:
        lines.insert(0, OcrLine(title, Bounds(180, 23, 123, 46), 1.0))
    if level is not None:
        lines.insert(2, OcrLine(level, Bounds(201, 408, 68, 31), 1.0))
    return tuple(lines)


def _farm_requirement_lines(*, include_target: bool) -> tuple[OcrLine, ...]:
    """Return actual Farm-detail OCR plus the visible unmet target when present."""

    lines = list(_farm_lines())
    if include_target:
        lines.append(OcrLine("Castle: Lv.8", Bounds(154, 768, 147, 24), 1.0))
    return tuple(lines)


def _institute_lines(*, title: str = "Institute", level: str | None = "8/45") -> tuple[OcrLine, ...]:
    """Return crop-filterable OCR facts for the reviewed Institute detail."""

    lines = [
        OcrLine(title, Bounds(110, 15, 120, 28), 1.0),
        OcrLine("Glory Level", Bounds(397, 220, 137, 30), 1.0),
        OcrLine("Upgrade", Bounds(404, 254, 104, 40), 1.0),
        OcrLine("Development", Bounds(41, 337, 125, 20), 1.0),
        OcrLine("Economy", Bounds(305, 337, 107, 20), 1.0),
        OcrLine("Military", Bounds(41, 417, 101, 20), 1.0),
        OcrLine("Fortification", Bounds(305, 417, 139, 20), 1.0),
    ]
    if level is not None:
        lines.insert(1, OcrLine(level, Bounds(122, 245, 45, 23), 1.0))
    return tuple(lines)


@dataclass(slots=True)
class _CropHonoringOcrService(_RecordingOcrService):
    """Reject accidental unbounded backend calls while filtering lines by ROI."""

    regions: list[Region] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Require every backend request to identify a strict screenshot region."""

        if region is None or region == Bounds(0, 0, image.width, image.height):
            raise AssertionError("Building-level OCR must receive a bounded region.")
        self.regions.append(region)
        return _RecordingOcrService.read_result(self, image, region)


@dataclass(slots=True)
class _CastleRapidOcrService:
    """Allow backend ``None`` only for the prepared Castle level field."""

    delegate: RapidOcrService
    capture_size: tuple[int, int] | None = None
    field_bounds: Bounds | None = None
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)

    def bind(self, *, capture_size: tuple[int, int], field_bounds: Bounds) -> None:
        """Bind one captured frame and its native Castle field."""

        self.capture_size = capture_size
        self.field_bounds = field_bounds
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Reject full-capture reads while permitting only the reference-sized input."""

        self.calls.append((region, image.size))
        if self.capture_size is None or self.field_bounds is None:
            raise AssertionError("Castle RapidOCR spy was used before binding a frame")
        whole = Bounds(0, 0, *self.capture_size)
        if region == whole:
            raise AssertionError("Castle OCR reached RapidOCR with a whole-capture region")
        prepared_size = (291, 120)
        if region is None and image.size != prepared_size:
            raise AssertionError(
                "Castle OCR allowed None only for the prepared level field: "
                f"got image size {image.size}, expected {prepared_size}"
            )
        if region is not None and image.size == prepared_size:
            raise AssertionError("Castle prepared level field unexpectedly retained a region")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Expose the backend line protocol through the same guarded read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Expose the backend text protocol through the same guarded read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _wire(
    lines: tuple[OcrLine, ...],
    *,
    ocr_service: OcrService | None = None,
) -> tuple[ObservationBuilder, NavigationPerception, list[ObservationOcrContext]]:
    """Wire both production perception paths and retain their OCR contexts."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    ocr = _CropHonoringOcrService(lines=lines) if ocr_service is None else ocr_service
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=ocr,
    )
    contexts: list[ObservationOcrContext] = []

    def create_context(screenshot: CapturedScreenshot) -> ObservationOcrContext:
        context = builder.create_ocr_context(screenshot)
        contexts.append(context)
        return context

    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        create_context,
    )
    return builder, navigation, contexts


def _level_region(builder: ObservationBuilder, screen: ScreenType, image_size: tuple[int, int]) -> Bounds:
    """Return the canonical bounded crop that owns the building level fact."""

    plans = compile_screen_content_ocr_region_plans(
        resolved_screen=screen,
        request=ObservationRequest.source_screen_retry(screen),
        image_size=image_size,
    )
    return next(plan.bounds for plan in plans if plan.purpose == OcrRegionPurpose.BUILDING_LEVEL)


class BuildingLevelPublicationTests(unittest.TestCase):
    """Keep content labels independent from OCR screen identity and controls."""

    def _assert_level(self, observation, capture: CapturedScreenshot, expected: str) -> None:
        self.assertEqual(observation.screen_type, observation.decision.effective_screen)
        level = observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
        self.assertEqual(level.extracted_text, expected)
        self.assertEqual(level.source_kind, VisibleElementSourceKind.OCR)
        self.assertFalse(level.identity_evidence)
        self.assertIsNone(level.action_point)
        self.assertEqual(level.frame_ref, capture.frame_ref)
        self.assertEqual(level.source_screen, observation.screen_type)
        self.assertEqual(level.source_layout_id, observation.decision.layout_id)

    def _assert_required_diagnostic(self, context, status: OcrRequiredFieldStatus, region: Bounds) -> None:
        diagnostics = [
            item
            for item in context.required_field_diagnostics
            if item.required_fact == "building_level"
        ]
        self.assertTrue(diagnostics)
        self.assertTrue(all(item.status == status for item in diagnostics))
        self.assertTrue(all(item.region == region for item in diagnostics))

    def test_available_farm_prerequisite_text_does_not_claim_an_unmet_requirement(self) -> None:
        """The saved frame has prerequisite text without an unmet Go row."""

        capture = _farm_capture(session_id="farm-prerequisite", name="farm_upgrade_available.png")
        builder, navigation, _contexts = _wire(_farm_requirement_lines(include_target=True))
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS)
        for observation in (builder.build(capture, request=request),
                            navigation.build(capture, include_content=True)):
            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            for selector in (UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
                             UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
                             UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON):
                self.assertFalse(observation.has(selector))

    def test_malformed_ocr_titles_do_not_displace_valid_level_or_controls(self) -> None:
        """Visual identity keeps valid frame-local labels when OCR titles are corrupted."""

        cases = (
            (
                "farm",
                _farm_capture(
                    name="farm_upgrade_available.png",
                    session_id="building-level-farm-title-corrupt",
                ),
                _farm_lines(title="Farm0", level="7/45"),
                ScreenType.PNC_BUILDING_DETAILS,
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
            ),
            (
                "institute",
                _capture("institute_audit.png", session_id="building-level-institute-title-corrupt"),
                _institute_lines(title="Insttute0", level="8/45"),
                ScreenType.PNC_INSTITUTE,
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
            ),
        )
        for name, capture, lines, screen, control_id in cases:
            with self.subTest(name=name):
                builder, navigation, contexts = _wire(lines)
                request = ObservationRequest.source_screen_retry(screen)
                builder_context = builder.create_ocr_context(capture)
                builder_observation = builder.build(capture, request=request, ocr_context=builder_context)
                navigation_observation = navigation.build(capture, include_content=True)

                for observation in (builder_observation, navigation_observation):
                    self._assert_level(observation, capture, "7/45" if name == "farm" else "8/45")
                    control = observation.require(control_id)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(control.frame_ref, capture.frame_ref)
                    self.assertEqual(control.source_screen, screen)
                    self.assertEqual(control.source_layout_id, observation.decision.layout_id)
                self.assertTrue(contexts)

    def test_captured_base_profiles_keep_level_and_back_without_body_ocr(self) -> None:
        """Warehouse and Goddess publish level/Back from only owned OCR and visual evidence."""

        cases = (
            (
                "warehouse_audit.png",
                ScreenType.PNC_WAREHOUSE,
                "Warehouse",
                "9/45",
                Bounds(97, 0, 389, 53),
            ),
            (
                "goddess_statue_audit.png",
                ScreenType.PNC_GODDESS_STATUE,
                "Goddess Statue",
                "1/45",
                Bounds(0, 0, 540, 62),
            ),
        )
        level_bounds = Bounds(11, 192, 518, 134)
        guard_bounds = Bounds(16, 240, 508, 480)

        for name, screen, title, expected_level, header_bounds in cases:
            with self.subTest(name=name):
                lines = (
                    OcrLine(title, Bounds(105, 10, 150, 30), 1.0),
                    OcrLine(expected_level, Bounds(122, 246, 40, 17), 1.0),
                )
                capture = _capture(name, session_id=f"base-profile:{name}")
                builder, navigation, contexts = _wire(lines)
                request = ObservationRequest.source_screen_retry(screen)

                builder_context = builder.create_ocr_context(capture)
                observations = [
                    builder.build(capture, request=request, ocr_context=builder_context),
                ]
                observations.append(navigation.build(capture, include_content=True))
                contexts_by_path = (builder_context, contexts[-1])

                expected_diagnostics = (
                    ("plan:screen_header", header_bounds),
                    ("plan:building_level_and_actions", level_bounds),
                )
                for observation, context in zip(observations, contexts_by_path, strict=True):
                    self.assertEqual(observation.screen_type, screen)
                    self.assertEqual(observation.frame_ref, capture.frame_ref)
                    self.assertEqual(
                        set(observation.visible_elements),
                        {
                            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                            UiElementId.PNC_BUILDING_LEVEL_LABEL,
                        },
                    )
                    back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
                    self.assertEqual(back.source_kind, VisibleElementSourceKind.TEMPLATE)
                    self.assertEqual(back.frame_ref, capture.frame_ref)
                    self.assertEqual(back.source_screen, screen)
                    self.assertEqual(back.source_layout_id, observation.decision.layout_id)
                    self._assert_level(observation, capture, expected_level)
                    self.assertEqual(
                        tuple((item.detail, item.region) for item in context.read_diagnostics),
                        expected_diagnostics,
                    )
                    self.assertNotIn("plan:castle_fields", [item.detail for item in context.read_diagnostics])
                    self.assertNotIn("plan:storage_fields", [item.detail for item in context.read_diagnostics])
                    self.assertNotIn("plan:goddess_fields", [item.detail for item in context.read_diagnostics])

    def test_captured_castle_profile_uses_reference_sized_level_field_in_both_paths(self) -> None:
        """RapidOCR reads the real Castle level at both supported native resolutions."""

        delegate = _require_rapid_ocr_service(self)
        for size in ((540, 960), (900, 1600)):
            with self.subTest(size=size):
                capture = _capture("castle_audit.png", session_id=f"castle-rgb-reference-3x:{size}", size=size)
                field_bounds = Bounds(
                    round(97 * size[0] / 540),
                    round(235 * size[1] / 960),
                    round(97 * size[0] / 540),
                    round(40 * size[1] / 960),
                )
                header_bounds = Bounds(
                    round(size[0] * 0.18),
                    0,
                    round(size[0] * 0.72),
                    round(size[1] * 0.055),
                )
                guard_bounds = Bounds(
                    round(size[0] * 0.03),
                    round(size[1] * 0.25),
                    round(size[0] * 0.94),
                    round(size[1] * 0.50),
                )
                plans = compile_screen_content_ocr_region_plans(
                    resolved_screen=ScreenType.PNC_CASTLE,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_CASTLE),
                    image_size=size,
                )
                level_plan = next(plan for plan in plans if plan.purpose == OcrRegionPurpose.BUILDING_LEVEL)
                self.assertEqual(level_plan.bounds, field_bounds)
                self.assertEqual(level_plan.preprocessing, OcrRegionPreprocessing.RGB_REFERENCE_3X)

                ocr = _CastleRapidOcrService(delegate)
                ocr.bind(capture_size=size, field_bounds=field_bounds)
                builder, navigation, contexts = _wire((), ocr_service=ocr)
                request = ObservationRequest.source_screen_retry(ScreenType.PNC_CASTLE)
                builder_context = builder.create_ocr_context(capture)
                builder_observation = builder.build(
                    capture,
                    request=request,
                    ocr_context=builder_context,
                )
                navigation_observation = navigation.build(capture, include_content=True)
                observations = (builder_observation, navigation_observation)
                contexts_by_path = (builder_context, contexts[-1])

                expected_diagnostics = (
                    ("plan:screen_header", header_bounds),
                    ("plan:building_level", field_bounds),
                )
                expected_calls = (
                    (header_bounds, size),
                    (None, (291, 120)),
                )
                self.assertEqual(ocr.calls, list(expected_calls) + list(expected_calls))
                for observation, context in zip(observations, contexts_by_path, strict=True):
                    self._assert_level(observation, capture, "17/45")
                    self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE)
                    self.assertEqual(observation.frame_ref, capture.frame_ref)
                    self.assertEqual(
                        set(observation.visible_elements),
                        {
                            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                            UiElementId.PNC_BUILDING_LEVEL_LABEL,
                        },
                    )
                    back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
                    self.assertEqual(back.frame_ref, capture.frame_ref)
                    level = observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL)
                    self.assertTrue(field_bounds.contains_bounds(level.bounds))
                    self.assertEqual(
                        tuple((item.detail, item.region) for item in context.read_diagnostics),
                        expected_diagnostics,
                    )

    def test_missing_or_invalid_level_keeps_visual_controls_and_records_owned_diagnostic(self) -> None:
        """Missing and malformed level OCR omits only the label and records its bounded parser outcome."""

        cases = (
            (
                "farm",
                _farm_capture(session_id="building-level-farm-miss"),
                _farm_lines(level=None),
                ScreenType.PNC_BUILDING_DETAILS,
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
            ),
            (
                "farm-invalid",
                _farm_capture(session_id="building-level-farm-invalid"),
                _farm_lines(level="7/xx"),
                ScreenType.PNC_BUILDING_DETAILS,
                UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
            ),
            (
                "institute",
                _capture("institute_audit.png", session_id="building-level-institute-miss"),
                _institute_lines(level=None),
                ScreenType.PNC_INSTITUTE,
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
            ),
            (
                "institute-invalid",
                _capture("institute_audit.png", session_id="building-level-institute-invalid"),
                _institute_lines(level="7/xx"),
                ScreenType.PNC_INSTITUTE,
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
            ),
        )
        for name, capture, lines, screen, control_id in cases:
            with self.subTest(name=name):
                builder, navigation, contexts = _wire(lines)
                request = ObservationRequest.source_screen_retry(screen)
                level_region = _level_region(builder, screen, capture.image.size)
                builder_context = builder.create_ocr_context(capture)
                builder_observation = builder.build(capture, request=request, ocr_context=builder_context)
                navigation_observation = navigation.build(capture, include_content=True)
                status = (
                    OcrRequiredFieldStatus.INVALID
                    if "invalid" in name
                    else OcrRequiredFieldStatus.MISSING
                )

                for observation in (builder_observation, navigation_observation):
                    self.assertEqual(observation.screen_type, screen)
                    self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))
                    control = observation.require(control_id)
                    self.assertEqual(control.source_kind, VisibleElementSourceKind.TEMPLATE)
                self._assert_required_diagnostic(builder_context, status, level_region)
                self._assert_required_diagnostic(contexts[0], status, level_region)

    def test_missing_title_keeps_visual_identity_level_and_upgrade_control(self) -> None:
        """A title crop miss cannot discard independently proved level or Upgrade evidence."""

        capture = _farm_capture(
            session_id="building-level-farm-title-miss",
            name="farm_upgrade_available.png",
        )
        builder, navigation, _contexts = _wire(_farm_lines(title=None, level="7/45"))
        builder_observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
        )
        navigation_observation = navigation.build(capture, include_content=True)

        for observation in (builder_observation, navigation_observation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_BUILDING_DETAILS)
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_LEVEL_LABEL).extracted_text,
                "7/45",
            )
            self.assertEqual(
                observation.require(UiElementId.PNC_BUILDING_UPGRADE_BUTTON).source_kind,
                VisibleElementSourceKind.TEMPLATE,
            )

    def test_blocked_or_wrong_visual_screen_never_fabricates_building_level(self) -> None:
        """A valid OCR level cannot cross a popup or independently identified screen boundary."""

        blocked_lines = (
            *_institute_lines(level="8/45"),
            OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        blocked_capture = _capture("update_over_bag.png", session_id="building-level-blocked")
        builder, navigation, _contexts = _wire(blocked_lines)
        blocked_builder = builder.build(
            blocked_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE),
        )
        blocked_navigation = navigation.build(blocked_capture, include_content=True)
        for observation in (blocked_builder, blocked_navigation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

        wrong_capture = _capture("home_negative.png", session_id="building-level-wrong-screen")
        builder, navigation, _contexts = _wire(_institute_lines(level="8/45"))
        wrong_builder = builder.build(
            wrong_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_INSTITUTE),
        )
        wrong_navigation = navigation.build(wrong_capture, include_content=True)
        for observation in (wrong_builder, wrong_navigation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))


if __name__ == "__main__":
    unittest.main()
