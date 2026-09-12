"""World spatial objects."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.vision.spatial_surfaces import build_world_map_spatial_surface
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query


class WorldSpatialObjectsTests(unittest.TestCase):
    """Proves world spatial objects."""

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
