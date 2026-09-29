"""Scoped endpoint probing keeps unrestricted camera localization available."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraScanMode,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.vision.home_city_camera.localization import (
    HomeCityCameraLocalizer,
    _CameraHypothesis,
)
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.pnc.home_city_camera.fixtures import _CAMERA_FIXTURES


class EndpointProbeShapeTests(unittest.TestCase):
    """Cheap static/fake checks do not invoke native image matching."""

    def test_endpoint_probe_evaluates_one_calibrated_scale(self) -> None:
        localizer = HomeCityCameraLocalizer(matcher=Mock())
        frame = SimpleNamespace(original_size=(900, 1600))
        empty = _CameraHypothesis(.75, .75, (0.0, 0.0), (), (), frozenset(), 0.0)
        with (
            patch.object(localizer, "_coerce_frame", return_value=frame),
            patch.object(localizer, "_proposal_frame", return_value=frame),
            patch.object(localizer, "_evaluate_zoom", return_value=empty) as evaluate,
        ):
            proof = localizer.localize_endpoint(Image.new("RGB", (1, 1)))
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual(1, evaluate.call_count)
        self.assertEqual(.75, evaluate.call_args.args[-1])

    def test_probe_withholds_bodies_until_normalized_mode_and_current_endpoint(self) -> None:
        camera = Mock(spec=HomeCityCameraLocalizer)
        camera.prepare_frame.return_value = object()
        camera.localize_endpoint.return_value = HomeCityCameraProof(
            HomeCityCameraStatus.LOCALIZED, "test", translation=(-288, 44),
            zoom=.75, frame_size=(900, 1600),
        )
        camera.analyze_view.return_value = HomeCityViewEvidence(
            HomeCityZoomStatus.AT_ENDPOINT, "test", "test_endpoint", None, (900, 1600),
        )
        camera.matched_target_objects.return_value = ()
        image = Image.new("RGB", (900, 1600))

        build_home_city_spatial_surface(
            image=image, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.ENDPOINT_PROBE,
        )
        camera.localize.assert_not_called()
        camera.localize_endpoint.assert_called_once()
        camera.matched_target_objects.assert_not_called()

        build_home_city_spatial_surface(
            image=image, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.NORMALIZED_ENDPOINT,
        )
        camera.matched_target_objects.assert_called_once()

        camera.matched_target_objects.reset_mock()
        camera.analyze_view.return_value = HomeCityViewEvidence(
            HomeCityZoomStatus.NOT_AT_ENDPOINT, "test", "test_endpoint", None, (900, 1600),
        )
        build_home_city_spatial_surface(
            image=image, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.NORMALIZED_ENDPOINT,
        )
        camera.matched_target_objects.assert_not_called()


class EndpointProbeNativeTests(unittest.TestCase):
    """Run only when native matching CPU is released by the coordinator."""

    @staticmethod
    def _native(name: str) -> Image.Image:
        with Image.open(Path(_CAMERA_FIXTURES) / name) as source:
            return source.copy()

    def test_native_endpoint_probe_agrees_with_full_certification(self) -> None:
        localizer = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
        image = self._native("home_city_zoom_endpoint_20260925.png")
        probe = localizer.localize_endpoint(image)
        certified = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=probe)
        self.assertTrue(probe.localized)
        self.assertEqual(HomeCityZoomStatus.AT_ENDPOINT, view.zoom_status)
        self.assertTrue(certified.localized)
        for observed, expected in zip(probe.translation, certified.translation, strict=True):
            self.assertLessEqual(abs(observed - expected), 2)

    def test_closer_rung_and_default_start_do_not_publish_endpoint_bodies(self) -> None:
        localizer = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
        for name in (
            "home_city_zoom_rung_20260925.png",
            "home_city_default_start_20260927.png",
        ):
            with self.subTest(name=name):
                image = self._native(name)
                surface = build_home_city_spatial_surface(
                    image=image, lines=(), selector_registry=None, camera=localizer,
                    camera_mode=HomeCityCameraScanMode.ENDPOINT_PROBE,
                )
                self.assertNotEqual(HomeCityZoomStatus.AT_ENDPOINT, surface.home_city_view.zoom_status)
                self.assertEqual((), surface.objects)


if __name__ == "__main__":
    unittest.main()
