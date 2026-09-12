"""Overview marker observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_world_coordinate_to_overview_point,
)
from pnc_automation.app.pnc.navigation.world_map_search import WorldMapOverviewNavigator
from pnc_automation.app.pnc.domain.observation import Bounds, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.paint_overview_false_positive_blob import (
    _paint_overview_false_positive_blob,
)
from tests.support.pnc.capture_vision.paint_overview_viewport_marker import (
    _paint_overview_viewport_marker,
)
from tests.support.pnc.capture_vision.paint_synthetic_world_overview_map import (
    _paint_synthetic_world_overview_map,
)


class OverviewMarkerObservationTests(unittest.TestCase):
    """Proves overview marker observation."""

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
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
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
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
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
