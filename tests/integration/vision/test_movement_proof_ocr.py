"""Movement proof ocr: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
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

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.coordinate_bar_top_hud_fallback_ocr_service import (
    _CoordinateBarTopHudFallbackOcrService,
)
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class MovementProofOcrTests(unittest.TestCase):
    """Proves movement proof ocr."""

    def test_world_map_movement_proof_uses_coordinate_only_ocr_without_full_viewport_analysis(self) -> None:
        """Keeps movement proof cheap by parsing only the coordinate bar instead of full-frame world-map objects."""

        registry = build_default_selector_registry()
        image = Image.new("RGB", (540, 960), (15, 28, 68))
        coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate_region is not None
        bounds = coordinate_region.materialize_region(image_size=image.size)
        for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
            for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                image.putpixel((x, y), (42, 198, 224))
        screenshot = type(
            "Captured",
            (),
            {
                "image": image,
            "artifact": type("Artifact", (), {"path": Path("synthetic.png"), "captured_at": None})(),
            "frame_ref": make_captured_frame(b"").frame_ref,
            },
        )()
        ocr_service = _RecordingOcrService(
            lines=(
                _ocr_line("X:230 Y:958", x=bounds.x + 4, y=bounds.y + 4, width=100, height=18),
                _ocr_line("Lv.36 Monster", x=180, y=400, width=120, height=18),
            )
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),

            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(

                selector_registry=registry,
            ),
            ocr_service=ocr_service)

        observation = builder.build(screenshot, request=ObservationRequest.world_map_movement_proof_follow_up())

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(ocr_service.read_result_calls, 1)
        self.assertEqual(ocr_service.read_text_calls, 0)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (230, 958))
        self.assertEqual(observation.spatial_surface.objects, ())
        self.assertEqual(observation.spatial_surface.metadata["scan_scope"], "coordinate_only")

    def test_world_map_movement_proof_falls_back_to_bounded_top_hud_coordinate_ocr(self) -> None:
        """Replays the live movement-proof miss where selector-crop OCR failed but top-HUD OCR saw coordinates."""

        fixture_path = require_local_fixture_artifact(
            "world_map_coordinate_only_top_hud_live_20260617",
            default_repo_relative_path="tests/data/world_map/world_map_coordinate_only_top_hud_live_20260617.png",
        )
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.open(fixture_path).convert("RGB")
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(image)),
                artifact_directory="world_map_coordinate_only_top_hud",
                label="world_map_coordinate_only_top_hud",
            )
            registry = build_default_selector_registry()
            ocr_service = _CoordinateBarTopHudFallbackOcrService(
                top_hud_lines=(
                    _ocr_line("X:370Y:510", x=373, y=146, width=199, height=33),
                    _ocr_line("Hell Fortress", x=421, y=423, width=123, height=26),
                )
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                    selector_registry=registry,
                ),
            ocr_service=ocr_service)

            observation = builder.build(screenshot, request=ObservationRequest.world_map_movement_proof_follow_up())

            self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
            self.assertIsNotNone(observation.spatial_surface)
            assert observation.spatial_surface is not None
            self.assertEqual(observation.spatial_surface.viewport.coordinate, (370, 510))
            self.assertEqual(observation.spatial_surface.objects, ())
            self.assertEqual(ocr_service.read_text_calls, 0)
            self.assertTrue(any(region is not None and region.x == 0 for region in ocr_service.read_lines_regions))
