"""World spatial semantic projection checks using typed OCR geometry."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_world_map_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query
from tests.support.pnc.mail.build_observation import _build_observation


class WorldSpatialObservationTests(unittest.TestCase):
    """Proves typed world-map spatial projection after explicit screen acceptance."""

    def test_observation_builder_builds_world_map_spatial_surface_with_typed_objects(self) -> None:
        """Projects supplied OCR geometry into typed objects and relationships."""

        image = Image.new("RGB", (900, 1600), (15, 28, 68))
        image.paste((40, 90, 190), box=(200, 500, 410, 535))
        image.paste((90, 190, 220), box=(455, 640, 735, 675))
        image.paste((230, 210, 70), box=(305, 720, 605, 755))
        observation = _build_observation(
            request=ObservationRequest.full_runtime_default(),
            accepted_screen=ScreenType.PNC_WORLD_MAP,
            semantic_parser=_build_world_map_semantic_additions,
            image=image,
            image_size=image.size,
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
            ),
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
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
