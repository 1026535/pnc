"""Captured Home/Institute publication through both production observers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.automation.engine.navigation_core import (
    _is_hud_safe_building_point,
    _resolve_observed_building_target,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    ListEntryKind,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    compile_screen_content_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds as ImageBounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, RapidOcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
MOTIVATING_FIXTURE = "home_city_development_research_institute.png"
RESOURCE_AUTO_USE_FIXTURE = "development_research_resource_auto_use_popup.png"
ACTIVE_RESEARCH_FIXTURE = "development_research_speed_active.png"


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Run actual RapidOCR while rejecting unbounded frame reads."""

    delegate: RapidOcrService
    capture_size: tuple[int, int] | None = None
    calls: list[ImageBounds | None] = field(default_factory=list)

    def bind(self, image_size: tuple[int, int]) -> None:
        """Bind one source frame and clear its backend-call accounting."""

        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: ImageBounds | None = None) -> OcrResult:
        """Reject full-frame OCR and delegate every strict crop to RapidOCR."""

        self.calls.append(region)
        whole = None if self.capture_size is None else ImageBounds(0, 0, *self.capture_size)
        if region is None or region == whole:
            raise AssertionError("Home content OCR must use a strict named crop.")
        return self.delegate.read_result(image, region)

    def read_lines(
        self, image: Image.Image, region: ImageBounds | None = None
    ) -> tuple[OcrLine, ...]:
        """Expose the bounded OCR protocol for selector consumers."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: ImageBounds) -> str:
        """Expose bounded text reads for selector consumers."""

        return "\n".join(line.text for line in self.read_lines(image, region))


def _capture(name: str, *, session_id: str) -> CapturedScreenshot:
    """Load a tracked frame and attach one explicit source FrameRef."""

    with Image.open(FIXTURES / name) as source:
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


def _wire(ocr: _BoundedRapidOcrService) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire the canonical builder and independent navigation perception path."""

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
        ocr_backend_revision="package-01-home-institute-rapidocr",
    )
    return builder, NavigationPerception(
        recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )


def _home_object(observation, object_id: str):
    """Resolve one canonical Home object through the consumer metadata query."""

    return observation.require_spatial_object(
        SpatialObjectQuery(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            kind=SpatialObjectKind.HOME_BUILDING,
            metadata_key="home_city_object_id",
            metadata_value=object_id,
        )
    )


class HomeDevelopmentResearchCapturedTests(unittest.TestCase):
    """Require exact Home object publication from both production observers."""

    def test_motivating_home_frame_publishes_institute_and_neighbors_from_bounded_ocr(self) -> None:
        """The saved missing-object regression now publishes all supported labels."""

        capture = _capture(MOTIVATING_FIXTURE, session_id="package-01-motivating-home")
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY)
        plans = compile_screen_content_ocr_region_plans(
            resolved_screen=ScreenType.PNC_HOME_CITY,
            request=request,
            image_size=capture.image.size,
        )
        self.assertEqual(
            tuple(plan.bounds for plan in plans),
            (
                Bounds(0, 0, 900, 104),
                Bounds(0, 304, 153, 352),
                Bounds(90, 288, 720, 400),
                Bounds(90, 672, 720, 352),
                Bounds(0, 1480, 900, 120),
            ),
        )
        self.assertEqual(
            tuple(plan.required_fact for plan in plans),
            (
                "screen_header",
                "home_queue_status",
                "home_building_nameplates_upper",
                "home_building_nameplates_lower",
                "home_navigation",
            ),
        )

        ocr.bind(capture.image.size)
        builder_observation = builder.build(capture, request=request)
        builder_calls = tuple(ocr.calls)
        ocr.bind(capture.image.size)
        navigation_observation = navigation.build(capture, include_content=True)
        navigation_calls = tuple(ocr.calls)

        for observation, calls in (
            (builder_observation, builder_calls),
            (navigation_observation, navigation_calls),
        ):
            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertEqual(observation.decision.guard.value, "clear")
            self.assertEqual(observation.decision.layout_id, "home_city")
            self.assertEqual(observation.frame_ref, capture.frame_ref)
            self.assertEqual(observation.require_spatial_surface().surface_type, SpatialSurfaceType.HOME_CITY_SURFACE)
            institute = _home_object(observation, "institute")
            self.assertEqual(institute.bounds, Bounds(420, 843, 69, 19))
            self.assertEqual(institute.action_point, (454, 852))
            self.assertEqual(
                _resolve_observed_building_target(
                    observation,
                    target=HomeCityObjectId.INSTITUTE,
                ),
                (institute, (454, 852)),
            )
            self.assertTrue(
                _is_hud_safe_building_point(
                    institute.action_point,
                    image_size=capture.image.size,
                )
            )
            self.assertEqual(
                {
                    object_.metadata.get("home_city_object_id")
                    for object_ in observation.spatial_surface.objects
                },
                {"castle", "warehouse", "institute", "goddess_statue", "trap_workshop"},
            )
            self.assertEqual(
                len(
                    [
                        object_
                        for object_ in observation.spatial_surface.objects
                        if object_.metadata.get("home_city_object_id") == "institute"
                    ]
                ),
                1,
            )
            self.assertTrue(calls)
            whole = ImageBounds(0, 0, *capture.image.size)
            self.assertTrue(all(region is not None and region != whole for region in calls))

    def test_independent_panned_home_group_publishes_institute_in_both_paths(self) -> None:
        """A separate 540x960 capture group retains exact Institute identity and a safe point."""

        capture = _capture("home_city_panned_core.png", session_id="package-01-panned-home")
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY)

        ocr.bind(capture.image.size)
        builder_observation = builder.build(capture, request=request)
        ocr.bind(capture.image.size)
        navigation_observation = navigation.build(capture, include_content=True)

        for observation in (builder_observation, navigation_observation):
            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            institute = _home_object(observation, "institute")
            self.assertEqual(institute.bounds, Bounds(247, 506, 46, 11))
            self.assertEqual(institute.action_point, (270, 511))
            self.assertTrue(
                _is_hud_safe_building_point(
                    institute.action_point,
                    image_size=capture.image.size,
                )
            )
            self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_independent_development_grid_binds_numeric_progress_to_each_node(self) -> None:
        """Real bounded OCR publishes non-max progression through both observers."""

        capture = _capture(
            "research_tree_development.png",
            session_id="package-01-development-progress",
        )
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_RESEARCH_TREE)

        observations = []
        for operation in (
            lambda: builder.build(capture, request=request),
            lambda: navigation.build(capture, include_content=True),
        ):
            ocr.bind(capture.image.size)
            observation = operation()
            calls = tuple(ocr.calls)
            observations.append(observation)
            whole = ImageBounds(0, 0, *capture.image.size)
            self.assertTrue(calls)
            self.assertTrue(all(region is not None and region != whole for region in calls))

        expected = {
            "Construction I": (2, 5, "available"),
            "Troop Load I": (1, 5, "available"),
            "Storage I": (1, 5, "available"),
            "Infirmary Cap": (1, 5, "locked"),
        }
        for observation in observations:
            self.assertEqual(ScreenType.PNC_RESEARCH_TREE, observation.screen_type)
            rows = {
                row.title_text: row
                for row in observation.entries(ListEntryKind.RESEARCH)
            }
            for title, (current, limit, access_state) in expected.items():
                self.assertEqual("incomplete", rows[title].metadata["research_progress_state"])
                self.assertEqual(current, rows[title].metadata["research_progress_current"])
                self.assertEqual(limit, rows[title].metadata["research_progress_limit"])
                self.assertEqual(access_state, rows[title].metadata["research_access_state"])

    def test_live_shifted_development_detail_publishes_only_normal_start_in_both_paths(self) -> None:
        """The current tall Development detail binds its measured blue Research control."""

        capture = _capture(
            "development_research_troop_load_detail_idle.png",
            session_id="package-01-shifted-development-detail",
        )
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_RESEARCH_TREE)

        observations = []
        for operation in (
            lambda: builder.build(capture, request=request),
            lambda: navigation.build(capture, include_content=True),
        ):
            ocr.bind(capture.image.size)
            observation = operation()
            calls = tuple(ocr.calls)
            observations.append(observation)
            whole = ImageBounds(0, 0, *capture.image.size)
            self.assertTrue(calls)
            self.assertTrue(all(region is not None and region != whole for region in calls))
            self.assertIn(ImageBounds(36, 392, 828, 960), calls)

        for observation in observations:
            self.assertEqual(ScreenType.PNC_RESEARCH_TREE, observation.screen_type)
            self.assertEqual("research_tree_development", observation.decision.layout_id)
            self.assertEqual("clear", observation.decision.guard.value)
            self.assertIn(
                "visual_anchor:research_tree_node_detail",
                {evidence.reason for evidence in observation.decision.evidence},
            )
            start = observation.require(UiElementId.PNC_RESEARCH_START_BUTTON)
            self.assertEqual(VisibleElementSourceKind.TEMPLATE, start.source_kind)
            self.assertEqual(Bounds(507, 702, 225, 81), start.bounds)
            self.assertEqual((619, 742), start.action_point)
            self.assertTrue(start.bounds.contains_point(start.action_point))
            self.assertEqual(capture.frame_ref, start.frame_ref)
            self.assertFalse(observation.research_start_resources_sufficient)
            self.assertIsNone(observation.research_start_queue_available)

    def test_live_resource_auto_use_popup_is_task_owned_in_both_paths(self) -> None:
        """The exact live popup publishes its measured task-owned controls."""

        capture = _capture(
            RESOURCE_AUTO_USE_FIXTURE,
            session_id="package-01-research-resource-auto-use",
        )
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)

        observations = []
        for operation in (
            lambda: builder.build(capture),
            lambda: navigation.build(capture, include_content=True),
        ):
            ocr.bind(capture.image.size)
            observation = operation()
            calls = tuple(ocr.calls)
            observations.append(observation)
            whole = ImageBounds(0, 0, *capture.image.size)
            self.assertTrue(calls)
            self.assertTrue(
                all(region is not None and region != whole for region in calls)
            )
            self.assertIn(ImageBounds(27, 224, 846, 976), calls)

        for observation in observations:
            self.assertEqual(ScreenType.PNC_POPUP, observation.screen_type)
            self.assertTrue(observation.blocking_popup)
            self.assertEqual("blocked", observation.decision.guard.value)
            cancel = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
            self.assertIn(
                cancel.source_kind,
                {VisibleElementSourceKind.OCR, VisibleElementSourceKind.GEOMETRY},
            )
            self.assertTrue(cancel.bounds.contains_point(cancel.action_point))
            confirm = observation.require(
                UiElementId.PNC_RESEARCH_RESOURCE_CONFIRM_BUTTON
            )
            self.assertEqual(VisibleElementSourceKind.OCR, confirm.source_kind)
            self.assertEqual(Bounds(563, 1170, 139, 29), confirm.bounds)
            self.assertEqual((632, 1184), confirm.action_point)
            self.assertEqual(capture.frame_ref, confirm.frame_ref)
            self.assertIsNotNone(observation.popup_overlay)
            assert observation.popup_overlay is not None
            self.assertEqual(
                "research_resource_auto_use",
                observation.popup_overlay.layout_id,
            )
            self.assertIsNotNone(
                observation.popup_overlay.candidate(
                    PopupControlKind.RESEARCH_RESOURCE_CONFIRM
                )
            )

    def test_live_shifted_active_detail_is_proved_in_both_paths(self) -> None:
        """The correlated post-Start frame is active even while alliance Help is available."""

        capture = _capture(
            ACTIVE_RESEARCH_FIXTURE,
            session_id="package-01-research-active-reconciliation",
        )
        ocr = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(ocr)
        request = ObservationRequest.source_screen_retry(ScreenType.PNC_RESEARCH_TREE)

        observations = []
        for operation in (
            lambda: builder.build(capture, request=request),
            lambda: navigation.build(capture, include_content=True),
        ):
            ocr.bind(capture.image.size)
            observation = operation()
            calls = tuple(ocr.calls)
            observations.append(observation)
            whole = ImageBounds(0, 0, *capture.image.size)
            self.assertTrue(calls)
            self.assertTrue(
                all(region is not None and region != whole for region in calls)
            )

        for observation in observations:
            self.assertEqual(ScreenType.PNC_RESEARCH_TREE, observation.screen_type)
            self.assertEqual("clear", observation.decision.guard.value)
            self.assertIn(
                "visual_anchor:research_tree_node_detail_active",
                {evidence.reason for evidence in observation.decision.evidence},
            )
            self.assertFalse(
                observation.has(UiElementId.PNC_RESEARCH_START_BUTTON)
            )
            self.assertFalse(observation.research_start_queue_available)
            self.assertEqual(capture.frame_ref, observation.frame_ref)


if __name__ == "__main__":
    unittest.main()
