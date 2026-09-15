"""Home spatial objects."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectKind
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface

from tests.local_fixture_artifacts import require_local_fixture_artifact
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class HomeSpatialObjectsTests(unittest.TestCase):
    """Proves home spatial objects."""

    def test_home_city_surface_detects_unlabeled_small_plot_geometry(self) -> None:
        """Produces a typed small-slot object for a bright foundation surrounded by darker terrain."""

        image = Image.new("RGB", (900, 1600), (74, 104, 34))
        ImageDraw.Draw(image).ellipse((395, 570, 505, 630), fill=(145, 145, 120))

        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
        )

        empty_slots = surface.objects_of_kind(SpatialObjectKind.HOME_EMPTY_SLOT)
        self.assertEqual(len(empty_slots), 1)
        self.assertEqual(empty_slots[0].metadata["home_city_object_id"], "small_territory_build_slot")
        self.assertEqual(empty_slots[0].metadata["detection_source"], "foundation_geometry")
        self.assertAlmostEqual(empty_slots[0].action_point[0], 450, delta=16)
        self.assertAlmostEqual(empty_slots[0].action_point[1], 600, delta=16)

    def test_home_city_surface_recovers_live_barracks_ocr_variants(self) -> None:
        """Maps the observed barracks OCR distortions back to their canonical building ids."""

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(
                _ocr_line("Jnfantry Barracks", x=690, y=1039, width=159, height=20),
                _ocr_line("Ranged Barrar", x=691, y=1255, width=142, height=22),
            ),
            selector_registry=None,
        )

        object_ids = {object_.metadata.get("home_city_object_id") for object_ in surface.objects}
        self.assertIn("infantry_barracks", object_ids)
        self.assertIn("ranged_barracks", object_ids)

    def test_home_city_surface_accepts_only_the_observed_institute_ocr_alias(self) -> None:
        """Maps the exact observed leading-I omission to canonical Institute metadata."""

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(
                _ocr_line("nstitute", x=420, y=843, width=69, height=19),
                _ocr_line("Instltute", x=520, y=843, width=69, height=19),
            ),
            selector_registry=None,
        )

        institute_objects = [
            object_
            for object_ in surface.objects
            if object_.metadata.get("home_city_object_id") == "institute"
        ]
        self.assertEqual(len(institute_objects), 1)
        self.assertEqual(institute_objects[0].name_text, "nstitute")
        self.assertEqual(institute_objects[0].bounds, Bounds(420, 843, 69, 19))
        self.assertEqual(institute_objects[0].action_point, (454, 852))
        self.assertEqual(
            [object_.name_text for object_ in surface.objects if object_.name_text == "Instltute"],
            [],
        )

    def test_home_city_surface_keeps_missing_institute_identity_missing(self) -> None:
        """Does not infer Institute from a known Home surface or an unrelated label."""

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(_ocr_line("Research", x=420, y=843, width=69, height=19),),
            selector_registry=None,
        )

        self.assertEqual(
            [
                object_
                for object_ in surface.objects
                if object_.metadata.get("home_city_object_id") == "institute"
            ],
            [],
        )

    def test_home_city_surface_does_not_treat_uniform_terrain_as_empty_plot(self) -> None:
        """Rejects terrain without the localized neutral foundation contrast required by geometry detection."""

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(),
            selector_registry=None,
        )

        self.assertEqual(surface.objects_of_kind(SpatialObjectKind.HOME_EMPTY_SLOT), ())
