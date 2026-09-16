"""Typed BuildingDetail acceptance on reviewed captures through both publishers.

The shared producer must answer which building owns the frame, which panel
phase is displayed, and what the measured level/requirement rows contain —
without ever turning a primary entry control into the mutation surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.building_details import BuildingDetailPhase
from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.vision.building_details import BuildingContentProducer
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.paths import TEST_DATA_ROOT


FIXTURES = TEST_DATA_ROOT / "screen_recognition"
BUILDING_FIXTURES = FIXTURES / "building_variants"
ROUTE_FIXTURES = FIXTURES / "building_routes"
QUEUE_FIXTURES = FIXTURES / "build_queue_variants"


def _capture(path, *, session_id: str) -> CapturedScreenshot:
    """Attach explicit frame provenance to one committed capture fixture."""

    with Image.open(path) as source:
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


def _wire(ocr) -> tuple[ObservationBuilder, NavigationPerception]:
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
    )
    navigation = NavigationPerception(
        recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return builder, navigation


class BuildingDetailFactTests(unittest.TestCase):
    """Real-OCR acceptance for the shared building detail packet."""

    def _observations(self, capture: CapturedScreenshot, screen: ScreenType):
        builder, navigation = _wire(self.ocr)
        built = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(screen),
            ocr_context=builder.create_ocr_context(capture),
        )
        perceived = navigation.build(capture, include_content=True)
        return built, perceived

    def _assert_detail_provenance(self, observation, capture, screen, layout_id):
        detail = observation.building_detail
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.frame_ref, capture.frame_ref)
        self.assertEqual(detail.source_screen, screen)
        self.assertEqual(detail.source_layout_id, layout_id)
        return detail

    def setUp(self) -> None:
        self.ocr = _require_rapid_ocr_service(self)

    def test_farm_upgrade_detail_publishes_typed_owner_phase_level_and_requirement(self) -> None:
        """The saved Farm upgrade panel proves owner, phase, N/M, and a satisfied row."""

        capture = _capture(
            BUILDING_FIXTURES / "farm_upgrade_available.png",
            session_id="building-detail-farm-upgrade",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_BUILDING_DETAILS)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation, capture, ScreenType.PNC_BUILDING_DETAILS, "building_detail_farm",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.FARM)
            self.assertEqual(detail.phase, BuildingDetailPhase.UPGRADE)
            self.assertEqual((detail.current_level, detail.max_level), (7, 45))
            self.assertEqual(detail.level_text, "7/45")
            self.assertIsNotNone(detail.original_time_text)
            self.assertIsNotNone(detail.actual_time_text)
            self.assertTrue(detail.costs)
            self.assertIsNotNone(detail.requirement)
            assert detail.requirement is not None
            self.assertEqual(detail.requirement.target_building, HomeCityObjectId.CASTLE)
            self.assertEqual(detail.requirement.target_level, 8)
            # The saved row is satisfied: no measured Go exists to invent.
            self.assertIsNone(detail.requirement.go_bounds)
            self.assertEqual(detail.requirement.frame_ref, capture.frame_ref)
            self.assertEqual(detail.requirement.source_screen, ScreenType.PNC_BUILDING_DETAILS)
            self.assertEqual(detail.requirement.source_layout_id, "building_detail_farm")
            # The proved UPGRADE phase owns the mutation surface, never the entry.
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_farm_primary_publishes_entry_without_mutation_surface(self) -> None:
        """The saved Farm stats panel is PRIMARY: entry measured, no spending control."""

        capture = _capture(
            BUILDING_FIXTURES / "farm_level_one_detail.png",
            session_id="building-detail-farm-primary",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_BUILDING_DETAILS)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation, capture, ScreenType.PNC_BUILDING_DETAILS, "building_detail_farm",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.FARM)
            self.assertEqual(detail.phase, BuildingDetailPhase.PRIMARY)
            self.assertEqual((detail.current_level, detail.max_level), (1, 45))
            self.assertIsNone(detail.requirement)
            self.assertTrue(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_institute_blocked_detail_keeps_row_owned_measured_go(self) -> None:
        """The blocked Institute panel binds the unmet row to its own measured Go."""

        capture = _capture(
            BUILDING_FIXTURES / "institute_upgrade_blocked.png",
            session_id="building-detail-institute-blocked",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_INSTITUTE)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation, capture, ScreenType.PNC_INSTITUTE, "institute_upgrade_detail",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.INSTITUTE)
            self.assertEqual(detail.phase, BuildingDetailPhase.UPGRADE)
            self.assertEqual((detail.current_level, detail.max_level), (22, 45))
            self.assertEqual("4d08:36:48", detail.original_time_text.replace(" ", ""))
            self.assertEqual("2d17:10:46", detail.actual_time_text.replace(" ", ""))
            self.assertEqual("19,714", detail.premium_cost_text)
            self.assertIn((87085, 10777363), [(cost.available, cost.required) for cost in detail.costs])
            self.assertIn((38797, 594597), [(cost.available, cost.required) for cost in detail.costs])
            self.assertIsNotNone(detail.requirement)
            assert detail.requirement is not None
            self.assertEqual(detail.requirement.target_building, HomeCityObjectId.CASTLE)
            self.assertEqual(detail.requirement.target_level, 23)
            self.assertIsNotNone(detail.requirement.go_bounds)
            # The blocked panel's red Upgrade is not the qualified mutation
            # surface; the row-owned Go is the only published action.
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_institute_primary_proves_phase_through_category_grid(self) -> None:
        """The saved Institute primary proves PRIMARY from measured categories."""

        capture = _capture(
            FIXTURES / "institute_audit.png",
            session_id="building-detail-institute-primary",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_INSTITUTE)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation, capture, ScreenType.PNC_INSTITUTE, "institute",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.INSTITUTE)
            self.assertEqual(detail.phase, BuildingDetailPhase.PRIMARY)
            self.assertEqual((detail.current_level, detail.max_level), (8, 45))
            # The proved primary keeps its named entry; the generic pair is absent.
            self.assertTrue(observation.has(UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_farm_construction_publishes_construction_phase_facts(self) -> None:
        """The construction surface keeps its own phase, level pair, and cost row."""

        capture = _capture(
            BUILDING_FIXTURES / "farm_construction_available.png",
            session_id="building-detail-farm-construction",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_BUILDING_CONSTRUCTION)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation,
                capture,
                ScreenType.PNC_BUILDING_CONSTRUCTION,
                "building_construction_farm",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.FARM)
            self.assertEqual(detail.phase, BuildingDetailPhase.CONSTRUCTION)
            self.assertEqual((detail.current_level, detail.max_level), (0, 45))
            self.assertTrue(detail.costs)
            self.assertIsNotNone(detail.requirement)
            assert detail.requirement is not None
            self.assertEqual(detail.requirement.target_building, HomeCityObjectId.CASTLE)
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_named_primary_publishes_proven_owner_with_unproved_phase(self) -> None:
        """Blacksmith keeps typed identity while its phase stays honestly unknown."""

        capture = _capture(
            ROUTE_FIXTURES / "blacksmith_reference_20260914.png",
            session_id="building-detail-blacksmith-primary",
        )
        built, perceived = self._observations(capture, ScreenType.PNC_BLACKSMITH)

        for observation in (built, perceived):
            detail = self._assert_detail_provenance(
                observation, capture, ScreenType.PNC_BLACKSMITH, "building_blacksmith",
            )
            self.assertEqual(detail.building_id, HomeCityObjectId.BLACKSMITH)
            self.assertIsNone(detail.phase)
            self.assertIsNone(detail.current_level)
            # The unproved frame keeps its named entry control and no generic ones.
            self.assertTrue(observation.has(UiElementId.PNC_BLACKSMITH_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON))
            self.assertFalse(observation.has(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON))
        self.assertEqual(built.building_detail, perceived.building_detail)

    def test_non_detail_surfaces_publish_no_building_detail(self) -> None:
        """Queue, Home, and warning frames never fabricate a building detail."""

        cases = (
            (QUEUE_FIXTURES / "build_queue_idle.png", ScreenType.PNC_BUILD_QUEUE),
            (FIXTURES / "home_city_core.png", ScreenType.PNC_HOME_CITY),
        )
        for path, screen in cases:
            with self.subTest(path=path.name):
                capture = _capture(path, session_id=f"building-detail-absent:{path.name}")
                built, perceived = self._observations(capture, screen)
                self.assertIsNone(built.building_detail)
                self.assertIsNone(perceived.building_detail)


class BuildingMeasuredProofTests(unittest.TestCase):
    """Keep unproved numeric values and non-template action evidence unknown."""

    def test_partly_unreadable_cost_keeps_known_half_without_guessing_grouping(self) -> None:
        detail = BuildingContentProducer().detail(
            image=Image.new("RGB", (900, 1600)),
            screen_type=ScreenType.PNC_INSTITUTE,
            layout_id="institute_upgrade_detail",
            lines=(OcrLine("57.998/3,764,841", Bounds(150, 1210, 220, 30), 0.72),),
            measured_elements={}, content_elements={},
        )
        self.assertEqual(1, len(detail.costs))
        self.assertIsNone(detail.costs[0].available)
        self.assertEqual(3764841, detail.costs[0].required)

    def test_ocr_category_elements_do_not_establish_primary_phase(self) -> None:
        image = Image.new("RGB", (900, 1600))
        elements = {
            selector: VisibleElement(
                selector, Bounds(10 + index * 250, 500, 200, 100), .99,
                source_kind=VisibleElementSourceKind.OCR,
            )
            for index, selector in enumerate((
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON,
            ))
        }
        phase = BuildingContentProducer().phase_for(
            image=image, screen_type=ScreenType.PNC_INSTITUTE, layout_id="institute",
            lines=(), measured_elements=elements,
        )
        self.assertIsNone(phase)

    def test_ocr_go_keeps_requirement_text_without_action_bounds(self) -> None:
        selector = UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON
        bounds = Bounds(700, 780, 100, 40)
        detail = BuildingContentProducer().detail(
            image=Image.new("RGB", (900, 1600)),
            lines=(
                OcrLine("Requirement", Bounds(60, 700, 170, 30), .99),
                OcrLine("Castle: Lv.8", Bounds(150, 780, 300, 30), .99),
                OcrLine("Go", bounds, .99),
            ),
            screen_type=ScreenType.PNC_INSTITUTE, layout_id="institute_upgrade_detail",
            measured_elements={selector: VisibleElement(selector, bounds, .99, source_kind=VisibleElementSourceKind.OCR)},
            content_elements={},
        )
        self.assertEqual("Castle: Lv.8", detail.requirement.target_text)
        self.assertIsNone(detail.requirement.go_bounds)


if __name__ == "__main__":
    unittest.main()
