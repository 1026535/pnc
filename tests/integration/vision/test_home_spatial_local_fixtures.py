"""Offline integration of home spatial local fixtures."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import SpatialObjectKind
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface

from tests.local_fixture_artifacts import require_local_fixture_artifact


class HomeSpatialObjectsTests(unittest.TestCase):

    def test_home_city_surface_does_not_treat_live_castle_details_as_empty_plots(self) -> None:
        """Rejects bright castle geometry from the live regression screenshot."""

        fixture_path = require_local_fixture_artifact(
            "home_city_castle_empty_slot_false_positive_20260822",
            default_repo_relative_path=(
                "artifacts/2026-08-22/testing/"
                "20260822T033821Z_building_construct_final_safe_slot_contract.png"
            ),
        )
        surface = build_home_city_spatial_surface(
            image=Image.open(fixture_path).convert("RGB"),
            lines=(),
            selector_registry=None,
        )

        self.assertEqual(surface.objects_of_kind(SpatialObjectKind.HOME_EMPTY_SLOT), ())
