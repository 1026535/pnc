"""Home camera pixel zoom tests."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)

from tests.support.pnc.home_city_camera.fixtures import (
    _CAMERA_FIXTURES,
    _fixture,
    _localizer,
    _zoomed_fixture,
)


class HomeCityCameraRealPixelZoomTests(unittest.TestCase):
    """Deterministically rescaled fixtures exercise real matcher scaling.

    The scripted zoom tests prove the ambiguity/fitting logic; these run the
    actual OpenCV template scaling and correlation path on resampled pixels
    from ``home_city_pan_07.png``, which publishes ``t=(-1000,-710)`` at zoom
    1.0. A content zoom around the viewport center keeps the inverse-
    projected atlas center fixed at ``(1450, 1510)`` for every zoom.
    """

    _SOURCE = _CAMERA_FIXTURES / "home_city_pan_07.png"
    _ATLAS_CENTER = (1450.0, 1510.0)

    def _assert_atlas_center(self, proof: HomeCityCameraProof) -> None:
        center = proof.project_reference_to_atlas((450.0, 800.0))
        self.assertAlmostEqual(self._ATLAS_CENTER[0], center[0], delta=4.0)
        self.assertAlmostEqual(self._ATLAS_CENTER[1], center[1], delta=4.0)

    def test_real_pixels_recover_grid_zoom(self) -> None:
        """A 0.8x content zoom is measured, not assumed: real resized templates."""
        localizer = _localizer()

        proof = localizer.localize(_zoomed_fixture(_fixture(self._SOURCE), 0.80))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(0.80, proof.zoom, delta=0.02)
        # t' = 0.8*(-1000,-710) + 0.2*(450,800) = (-710,-408) +/- resampling.
        self.assertAlmostEqual(-710.0, proof.translation[0], delta=4.0)
        self.assertAlmostEqual(-408.0, proof.translation[1], delta=4.0)
        self._assert_atlas_center(proof)

    def test_real_pixels_recover_off_grid_zoom(self) -> None:
        """A 0.825x scene fits from positions instead of snapping to the grid."""
        localizer = _localizer()

        proof = localizer.localize(_zoomed_fixture(_fixture(self._SOURCE), 0.825))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # 0.825 sits >0.02 from both 0.80 and 0.85 grid values, so a snapped
        # grid hypothesis fails this bound.
        self.assertAlmostEqual(0.825, proof.zoom, delta=0.02)
        self._assert_atlas_center(proof)

    def test_real_pixels_zoom_in_recovers_off_grid_zoom(self) -> None:
        """A 1.275x crop of the same scene still fits the measured zoom."""
        localizer = _localizer()

        proof = localizer.localize(_zoomed_fixture(_fixture(self._SOURCE), 1.275))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.275, proof.zoom, delta=0.02)
        self._assert_atlas_center(proof)

    def test_real_pixels_outside_zoom_domain_stay_unresolved(self) -> None:
        """Scenes beyond the supported zoom domain must not publish a guess."""
        localizer = _localizer()

        for zoom in (0.60, 1.50):
            with self.subTest(zoom=zoom):
                proof = localizer.localize(
                    _zoomed_fixture(_fixture(self._SOURCE), zoom)
                )
                self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
                self.assertIsNone(proof.translation)
