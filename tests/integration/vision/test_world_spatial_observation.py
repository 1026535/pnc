"""World spatial observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query


class WorldSpatialObservationTests(unittest.TestCase):
    """Proves world spatial observation."""

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
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
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
