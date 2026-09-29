"""Scoped endpoint probing keeps unrestricted camera localization available."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore, NavigationPolicy, _HomeCityOperation, reviewed_navigation_edges,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId, home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraScanMode,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.home_city_scan import HomeCityScanError, HomeCityScanStopReason
from pnc_automation.app.pnc.vision.home_city_camera import home_city_camera_target
from pnc_automation.app.pnc.vision.home_city_camera.localization import (
    HomeCityCameraLocalizer,
    _CameraHypothesis,
)
from pnc_automation.app.pnc.vision.observation_provenance import bind_spatial_surface
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher
from tests.support.pnc.home_city_camera.fixtures import _CAMERA_FIXTURES
from tests.support.pnc.navigation.core_frames import Actuator
from tests.support.pnc.navigation.core_home import camera_home_frame


_SLOT_BODY_FIXTURES = Path(_CAMERA_FIXTURES).parent / "home_city_slot_bodies"
_CAPTURED_AT = datetime(2026, 9, 29, tzinfo=UTC)


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

    @staticmethod
    def _native_home(
        image: Image.Image, camera: HomeCityCameraLocalizer, sequence: int,
    ):
        """Publish a real native camera/anchor result on a distinct Home capture."""
        captured_at = _CAPTURED_AT + timedelta(seconds=sequence)
        frame_ref = FrameRef("native-endpoint-regression", 1, sequence, sequence - 1, captured_at)
        surface = build_home_city_spatial_surface(
            image=image, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.ENDPOINT_PROBE,
        )
        frame = camera_home_frame(image_size=image.size, captured_at=captured_at)
        return replace(
            frame, frame_ref=frame_ref,
            spatial_surface=bind_spatial_surface(
                surface, frame_ref=frame_ref, source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id=frame.decision.layout_id,
            ),
        )

    @staticmethod
    def _native_operation(frames, *, max_zoom_inputs: int):
        observations = iter(frames)
        actuator = Actuator()
        core = NavigationCore(
            actuator, lambda _: next(observations), reviewed_navigation_edges(),
            policy=NavigationPolicy(max_home_zoom_inputs=max_zoom_inputs),
            sleep=lambda _: None, clock=lambda: 0.0,
        )
        operation = _HomeCityOperation(
            core, (home_city_camera_target(HomeCityObjectId.WAREHOUSE),),
            lambda _: next(observations), "native_endpoint_regression", 0.0,
        )
        return operation, actuator

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

    def test_native_within_run_anchor_shrink_authorizes_next_wheel(self) -> None:
        """Each pair is an observed trajectory segment, never a stitched endpoint run."""
        for before_name, after_name in (
            ("home_city_fountain_935_20260927.png", "home_city_fountain_879_20260927.png"),
            ("home_city_zoom_mid_871_20260925.png", "home_city_zoom_mid_824_20260925.png"),
        ):
            with self.subTest(before=before_name, after=after_name):
                camera = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
                before = self._native_home(self._native(before_name), camera, 1)
                after = self._native_home(self._native(after_name), camera, 2)
                before_view = before.spatial_surface.home_city_view
                after_view = after.spatial_surface.home_city_view
                self.assertIsNotNone(before_view.zoom_anchor)
                self.assertIsNotNone(after_view.zoom_anchor)
                self.assertEqual(
                    before_view.zoom_anchor.qualification_id,
                    after_view.zoom_anchor.qualification_id,
                )
                self.assertLess(after_view.zoom_anchor.bounds.width, before_view.zoom_anchor.bounds.width)
                self.assertLess(after_view.zoom_anchor.bounds.height, before_view.zoom_anchor.bounds.height)
                operation, actuator = self._native_operation((before, after), max_zoom_inputs=1)
                with self.assertRaises(HomeCityScanError) as error:
                    operation.normalize()
                self.assertIs(
                    HomeCityScanStopReason.ZOOM_BUDGET_EXHAUSTED,
                    error.exception.result.stop_reason,
                )
                self.assertEqual(1, operation.state.zoom_inputs)
                self.assertEqual(1, len(actuator.actions))

    def test_same_native_nonendpoint_frame_cannot_forge_progress(self) -> None:
        """Fresh captures with unchanged native pixels never earn a second detent."""
        camera = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
        image = self._native("home_city_zoom_rung_20260925.png")
        frames = tuple(self._native_home(image, camera, index) for index in range(1, 5))
        for frame in frames:
            self.assertEqual(
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                frame.spatial_surface.home_city_view.zoom_status,
            )
        operation, actuator = self._native_operation(frames, max_zoom_inputs=2)
        with self.assertRaises(HomeCityScanError) as error:
            operation.normalize()
        self.assertIs(HomeCityScanStopReason.ZOOM_INEFFECTIVE, error.exception.result.stop_reason)
        self.assertEqual(1, operation.state.zoom_inputs)
        self.assertEqual(1, len(actuator.actions))

    def test_native_changed_pose_fixed_reacquisition_agrees_with_unrestricted(self) -> None:
        """A saved post-pan endpoint body keeps its identity and point at fixed scale."""
        camera = HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())
        source = self._native("home_city_zoom_endpoint_20260925.png")
        with Image.open(_SLOT_BODY_FIXTURES / "home_city_warehouse_slot3_0047_20260929.png") as fixture:
            post_pan = fixture.copy()
        source_proof = camera.localize_endpoint(source)
        fixed = build_home_city_spatial_surface(
            image=post_pan, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.NORMALIZED_ENDPOINT,
        )
        unrestricted = build_home_city_spatial_surface(
            image=post_pan, lines=(), selector_registry=None, camera=camera,
            camera_mode=HomeCityCameraScanMode.UNRESTRICTED,
        )
        self.assertEqual(HomeCityZoomStatus.AT_ENDPOINT, fixed.home_city_view.zoom_status)
        self.assertTrue(source_proof.localized)
        self.assertEqual(
            HomeCityZoomStatus.AT_ENDPOINT,
            camera.analyze_view(source, camera_proof=source_proof).zoom_status,
        )
        self.assertTrue(fixed.camera_proof.localized)
        self.assertTrue(unrestricted.camera_proof.localized)
        self.assertNotEqual(source_proof.translation, fixed.camera_proof.translation)
        for observed, expected in zip(
            fixed.camera_proof.translation, unrestricted.camera_proof.translation, strict=True,
        ):
            self.assertLessEqual(abs(observed - expected), 2)
        bodies = []
        for surface in (fixed, unrestricted):
            warehouse = [
                item for item in surface.objects
                if home_city_object_id_from_metadata(item.metadata) is HomeCityObjectId.WAREHOUSE
            ]
            self.assertEqual(1, len(warehouse))
            self.assertEqual(3, warehouse[0].home_city_slot.slot_index)
            self.assertEqual((330, 718), warehouse[0].action_point)
            bodies.append(warehouse[0])
        self.assertEqual(bodies[0].bounds, bodies[1].bounds)
        self.assertEqual(bodies[0].action_bounds, bodies[1].action_bounds)


if __name__ == "__main__":
    unittest.main()
