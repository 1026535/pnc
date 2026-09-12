"""World spatial coordinates."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.vision.spatial_surfaces import build_world_map_spatial_surface
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.spatial_query import _spatial_query


class WorldSpatialCoordinatesTests(unittest.TestCase):
    """Proves world spatial coordinates."""

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

    def test_world_map_spatial_surface_trims_spurious_fourth_y_digit_from_live_coordinate_bar(self) -> None:
        """Keeps the live Y coordinate stable when OCR absorbs one unrelated trailing digit beside the bar."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (540, 960), (15, 28, 68)),
            lines=(
                _ocr_line("X:104 Y:7268", x=220, y=110, width=150, height=24),
                _ocr_line("Hell Fortress", x=310, y=270, width=110, height=18),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (104, 726))

    def test_world_map_spatial_surface_recovers_noisy_merged_coordinate_bar_digits(self) -> None:
        """Recovers a real viewport coordinate when OCR prefixes the X digits and appends extra Y digits on one line."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:99287Y:707414", x=371, y=141, width=222, height=38),
                _ocr_line("Venom Spider", x=447, y=379, width=135, height=25),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (287, 707))

    def test_world_map_spatial_surface_recovers_whitespace_split_live_coordinate_fragment(self) -> None:
        """Recovers the live coordinate bar when OCR inserts a whitespace-split stray digit inside the X fragment."""

        surface = build_world_map_spatial_surface(
            image=Image.new("RGB", (900, 1600), (15, 28, 68)),
            lines=(
                _ocr_line("X:101 4Y:695", x=371, y=146, width=197, height=30),
                _ocr_line("Enchanted Reptilian", x=194, y=582, width=192, height=25),
            ),
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(surface)
        assert surface is not None
        self.assertEqual(surface.viewport.coordinate, (101, 695))
