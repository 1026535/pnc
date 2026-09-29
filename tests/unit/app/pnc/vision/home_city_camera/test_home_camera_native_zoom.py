"""Home camera native zoom tests."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)

from tests.support.pnc.home_city_camera.fixtures import (
    _CAMERA_FIXTURES,
    _localizer,
)


class HomeCityCameraNativeZoomTests(unittest.TestCase):
    """The first verified native game-zoom captures pin the production path.

    2026-09-22 157_farm live wheel evidence (client 5.0.204/235): wheel -1
    produced the sampled scene scale ~1.072 and the inverse wheel +1
    restored scale 1.0 without restoring the original camera pose. Unlike
    the resampled fixtures in ``HomeCityCameraRealPixelZoomTests`` — which
    manufacture scene zoom by resizing pixels — these are the game's own
    rendered zoom states at unchanged native 900x1600, so they pin the real
    OpenCV matcher and fitter end to end. Only the two sampled scales are
    qualified; no continuous zoom interval is claimed.
    """

    _BASELINE = "home_city_native_zoom_baseline_20260922.png"
    _HOLDOUT = "home_city_native_zoom_holdout_20260922.png"
    _RESTORED = "home_city_native_zoom_restored_20260922.png"

    def _native_fixture(self, name: str) -> Image.Image:
        """Preserves the emulator capture mode through the production entry point."""
        with Image.open(_CAMERA_FIXTURES / name) as source:
            image = source.copy()
        self.assertEqual(("RGBA", (900, 1600)), (image.mode, image.size))
        return image

    def _localize(self, name: str) -> HomeCityCameraProof:
        return _localizer().localize(self._native_fixture(name))

    def test_native_baseline_localizes_at_the_reference_pose(self) -> None:
        """The unzoomed native frame reproduces the authored camera."""
        proof = self._localize(self._BASELINE)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual(1.0, proof.zoom)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual((900, 1600), proof.frame_size)
        self.assertEqual(11, len(proof.evidence))
        self.assertEqual(6, len(proof.matched_group_ids))
        self.assertTrue(all(item.residual <= 1.0 for item in proof.evidence))

    def test_native_zoomed_holdout_recovers_measured_off_grid_scale(self) -> None:
        """Wheel -1 sampled scene zoom 1.071989179 at atlas (-603, 78).

        The measured scale sits >0.02 from every 0.05 grid value, so a
        snapped grid hypothesis cannot satisfy this bound; only the fitted
        pair-fit zoom explains the independent group positions.
        """
        proof = self._localize(self._HOLDOUT)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.071989179, proof.zoom, delta=0.005)
        for actual, expected in zip(proof.translation, (-603, 78), strict=True):
            self.assertLessEqual(abs(actual - expected), 2)
        self.assertEqual((900, 1600), proof.frame_size)
        self.assertGreaterEqual(len(proof.evidence), 3)
        self.assertEqual(9, len(proof.evidence))
        self.assertGreaterEqual(len(proof.matched_group_ids), 2)
        self.assertEqual(6, len(proof.matched_group_ids))
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_native_inverse_projection_is_scene_consistent_across_zooms(self) -> None:
        """Fixed scene features inverse-project to the same atlas position.

        The eight landmarks visible in all three captures must agree in
        atlas space regardless of each frame's measured zoom and pose; this
        is the inverse-projection check the zoomed transform must satisfy.
        """
        proofs = {
            name: self._localize(name)
            for name in (self._BASELINE, self._HOLDOUT, self._RESTORED)
        }
        shared = {
            item.landmark_id for item in proofs[self._BASELINE].evidence
        } & {
            item.landmark_id for item in proofs[self._HOLDOUT].evidence
        } & {
            item.landmark_id for item in proofs[self._RESTORED].evidence
        }
        self.assertGreaterEqual(len(shared), 3)
        for landmark_id in shared:
            atlas_points = []
            for proof in proofs.values():
                evidence = next(
                    item for item in proof.evidence if item.landmark_id == landmark_id
                )
                center = (
                    evidence.bounds.x + evidence.bounds.width / 2,
                    evidence.bounds.y + evidence.bounds.height / 2,
                )
                atlas_points.append(proof.project_reference_to_atlas(center))
            with self.subTest(landmark=landmark_id):
                for axis in (0, 1):
                    values = [point[axis] for point in atlas_points]
                    self.assertLessEqual(max(values) - min(values), 2.0)

    def test_native_zoom_restoration_does_not_restore_camera_pose(self) -> None:
        """Inverse wheel +1 restored scale 1.0 at a different translation.

        The final frame localizes at zoom 1.0 with atlas translation
        (-532, 73) — not the baseline (-532, 222). Zoom restoration must
        never be read as restoration of the original camera pose.
        """
        proof = self._localize(self._RESTORED)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual(1.0, proof.zoom)
        self.assertEqual((-532, 73), proof.translation)
        self.assertNotEqual((-532, 222), proof.translation)
        self.assertEqual(11, len(proof.evidence))
        self.assertEqual(6, len(proof.matched_group_ids))

    def test_native_zoomed_frame_keeps_institute_unmatched(self) -> None:
        """At the zoomed pose the Institute body crop stays unmatched.

        p6_path_right — the camera-qualified Institute body landmark — does
        not match at scale 1.072. The independently qualified Goddess body,
        Castle body, and slot-5 Infantry Barracks body remain visible
        without weakening the Institute match contract.
        Baseline and restored views qualify Institute at their measured poses.
        """
        localizer = _localizer()
        target = localizer.catalog.target_for(HomeCityObjectId.INSTITUTE)

        zoomed = localizer.prepare_frame(self._native_fixture(self._HOLDOUT))
        zoomed_proof = localizer.localize(zoomed)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, zoomed_proof.status)
        self.assertIsNone(localizer.match_target(zoomed, target, proof=zoomed_proof))
        objects = localizer.matched_target_objects(zoomed, proof=zoomed_proof)
        self.assertEqual(
            [
                HomeCityObjectId.GODDESS_STATUE.value,
                HomeCityObjectId.CASTLE.value,
                HomeCityObjectId.INFANTRY_BARRACKS.value,
            ],
            [item.metadata["home_city_object_id"] for item in objects],
        )
        self.assertEqual(1, objects[1].home_city_slot.slot_index)
        self.assertEqual((583, 649), objects[1].action_point)
        self.assertEqual(5, objects[2].home_city_slot.slot_index)
        self.assertEqual((68, 965), objects[2].action_point)

        for name, action_point in (
            (self._BASELINE, (724, 1253)),
            (self._RESTORED, (724, 1104)),
        ):
            with self.subTest(fixture=name):
                frame = localizer.prepare_frame(self._native_fixture(name))
                proof = localizer.localize(frame)
                match = localizer.match_target(frame, target, proof=proof)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(action_point, match.action_point)
                self.assertTrue(match.action_bounds.contains_point(match.action_point))
