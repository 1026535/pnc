"""Home camera view tests."""

from __future__ import annotations

from dataclasses import replace
import threading
import unittest
from unittest import mock

from PIL import Image

from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraEvidence,
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.home_city_camera import localization as home_camera_module
from pnc_automation.app.pnc.vision.home_city_camera.localization import (
    HomeCityCameraLocalizer,
)
from pnc_automation.app.pnc.vision.observation_provenance import bind_spatial_surface
from pnc_automation.app.pnc.vision.spatial_surfaces import (
    build_home_city_spatial_surface,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.home_city_camera.doubles import (
    _AnchorScriptedMatcher,
    _PrepareCountingMatcher,
    _ZoomScriptedMatcher,
    _anchor_hit,
    _view_on_scripted_matcher,
)
from tests.support.pnc.home_city_camera.fixtures import (
    _CAMERA_FIXTURES,
    _fixture,
    _frame_ref,
    _localizer,
)


class HomeCityViewAnalysisTests(unittest.TestCase):
    """analyze_view publishes the measured zoom class plus a qualified anchor."""

    def test_native_endpoint_view_reports_endpoint_with_qualified_anchor(self) -> None:
        """P1: a calibrated endpoint view publishes the endpoint and its anchor."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_zoom_endpoint_20260925.png")

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertTrue(proof.localized)
        self.assertEqual(HomeCityZoomStatus.AT_ENDPOINT, view.zoom_status)
        self.assertEqual("measured_zoom_at_endpoint", view.reason)
        self.assertEqual("home_zoom_endpoint_20260925", view.calibration_id)
        self.assertEqual((900, 1600), view.frame_size)
        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        self.assertEqual("northeast_moat_slope_wheel_20260925", anchor.qualification_id)
        self.assertEqual((270, 704), anchor.point)
        self.assertEqual(Bounds(190, 650, 170, 200), anchor.bounds)
        self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_nearest_rung_is_not_endpoint_despite_snapped_published_zoom(self) -> None:
        """P2: the closest zoom rung is separated only by the raw refit."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_zoom_rung_20260925.png")

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertTrue(proof.localized)
        # The published consensus zoom is grid-snapped to 0.75 -- the same value
        # endpoint views publish -- so only the fixed-landmark refit can classify.
        self.assertAlmostEqual(0.75, proof.zoom, places=6)
        self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
        self.assertEqual("measured_zoom_closer_than_endpoint", view.reason)
        self.assertEqual("home_zoom_endpoint_20260925", view.calibration_id)
        # The moat patch is offscreen at this pose; the castle-fountain patch is
        # the qualified wheel anchor visible here.
        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual("castle_fountain_wheel_20260927", anchor.qualification_id)
        self.assertEqual((450, 558), anchor.point)
        self.assertEqual(Bounds(425, 543, 64, 52), anchor.bounds)
        self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_default_start_view_publishes_the_fountain_wheel_anchor(self) -> None:
        """The observed default Castle start publishes the wheel-qualified patch.

        The 2026-09-27 turn-002 start frame verified Home at zoom 1.0 / atlas
        (-532,+222) while the northeast-moat patch was off-screen; the fountain
        patch supplies the pose-independent wheel anchor there.
        """
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_default_start_20260927.png")

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertTrue(proof.localized)
        self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual("castle_fountain_wheel_20260927", anchor.qualification_id)
        self.assertEqual((450, 895), anchor.point)
        self.assertEqual(Bounds(417, 875, 85, 70), anchor.bounds)
        self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_native_fountain_intermediate_sizes_keep_current_patch_anchor(self) -> None:
        """The recorded wheel trajectory must not lose a visible fountain."""
        localizer = _localizer()
        for name, expected_point in (
            ("home_city_fountain_935_20260927.png", (450, 699)),
            ("home_city_fountain_879_20260927.png", (450, 657)),
        ):
            with self.subTest(fixture=name):
                image = _fixture(_CAMERA_FIXTURES / name)
                view = localizer.analyze_view(image, camera_proof=localizer.localize(image))
                self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
                anchor = view.zoom_anchor
                self.assertIsNotNone(anchor)
                assert anchor is not None
                self.assertEqual("castle_fountain_wheel_20260927", anchor.qualification_id)
                self.assertEqual(expected_point, anchor.point)
                self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_closer_native_views_are_not_endpoint(self) -> None:
        """P2: zoom-1.0 and zoom-1.072 holdouts measure closer than the endpoint."""
        localizer = _localizer()

        for name, expected_point, expected_bounds in (
            (
                "home_city_native_zoom_baseline_20260922.png",
                (450, 895),
                Bounds(417, 875, 85, 70),
            ),
            (
                "home_city_native_zoom_holdout_20260922.png",
                (450, 800),
                Bounds(415, 779, 90, 74),
            ),
            (
                "home_city_native_zoom_restored_20260922.png",
                (450, 746),
                Bounds(417, 726, 85, 70),
            ),
        ):
            with self.subTest(fixture=name):
                image = _fixture(_CAMERA_FIXTURES / name)
                view = localizer.analyze_view(
                    image, camera_proof=localizer.localize(image)
                )
                self.assertEqual(
                    HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status
                )
                self.assertEqual("measured_zoom_closer_than_endpoint", view.reason)
                self.assertEqual(
                    "home_zoom_endpoint_20260925", view.calibration_id
                )
                anchor = view.zoom_anchor
                self.assertIsNotNone(anchor)
                assert anchor is not None
                self.assertEqual(
                    "castle_fountain_wheel_20260927", anchor.qualification_id
                )
                self.assertEqual(expected_point, anchor.point)
                self.assertEqual(expected_bounds, anchor.bounds)
                self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_pre_normalization_anchor_is_pose_independent(self) -> None:
        """P5: a non-endpoint view still publishes the qualified scenery patch."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_northeast_holdout_20260923.png")

        view = localizer.analyze_view(image, camera_proof=localizer.localize(image))

        self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        self.assertEqual("northeast_moat_slope_wheel_20260925", anchor.qualification_id)
        self.assertEqual((571, 1019), anchor.point)
        self.assertEqual(Bounds(463, 946, 230, 270), anchor.bounds)
        self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_anchor_survives_retained_intermediate_zoom_steps(self) -> None:
        """P5: the observed zoom-out trajectory retains a current ground point."""
        for rung, expected_point in (
            ("779", (261, 699)),
            ("824", (250, 693)),
            ("871", (239, 687)),
        ):
            with self.subTest(rung=rung):
                localizer = _localizer()
                image = _fixture(
                    _CAMERA_FIXTURES / f"home_city_zoom_mid_{rung}_20260925.png"
                )
                proof = localizer.localize(image)
                view = localizer.analyze_view(image, camera_proof=proof)

                self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
                anchor = view.zoom_anchor
                self.assertIsNotNone(anchor)
                assert anchor is not None
                self.assertTrue(anchor.bounds.contains_point(anchor.point))
                self.assertAlmostEqual(expected_point[0], anchor.point[0], delta=3)
                self.assertAlmostEqual(expected_point[1], anchor.point[1], delta=3)

    def test_insufficient_fixed_groups_leave_zoom_unresolved(self) -> None:
        """P4: one physical group plus a movable occupant cannot classify zoom."""
        localizer = _localizer()
        image = _fixture(
            _CAMERA_FIXTURES / "home_city_pw_manor_negative_20260922.png"
        )

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual(HomeCityZoomStatus.UNRESOLVED, view.zoom_status)
        self.assertEqual(
            "insufficient_independent_landmark_groups", view.reason
        )
        self.assertIsNone(view.zoom_anchor)

    def test_movable_only_scale_evidence_cannot_classify(self) -> None:
        """P4: a localized verdict built only on movable occupants stays unresolved."""
        evidence = (
            HomeCityCameraEvidence(
                landmark_id="blacksmith_structure",
                group_id="blacksmith_structure",
                bounds=Bounds(100, 900, 120, 130),
                reference_bounds=Bounds(640, 1845, 120, 130),
                score=0.95,
                translation=(-540, -945),
                residual=0.0,
                zoom=1.0,
            ),
            HomeCityCameraEvidence(
                landmark_id="alliance_hall_structure",
                group_id="alliance_hall_structure",
                bounds=Bounds(300, 800, 140, 80),
                reference_bounds=Bounds(1197, 1675, 140, 80),
                score=0.95,
                translation=(-897, -875),
                residual=0.0,
                zoom=1.0,
            ),
        )
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="scripted movable-only cluster",
            translation=(-540, -945),
            zoom=1.0,
            frame_size=(900, 1600),
            evidence=evidence,
            matched_group_ids=frozenset(
                item.group_id for item in evidence
            ),
        )

        view = _view_on_scripted_matcher(
            _ZoomScriptedMatcher({}, zoom_by_file={}), proof=proof
        )

        self.assertEqual(HomeCityZoomStatus.UNRESOLVED, view.zoom_status)
        self.assertEqual("insufficient_fixed_scale_evidence", view.reason)

    def test_unsupported_layout_reports_unsupported(self) -> None:
        """P2: a layout the matcher cannot normalize publishes unsupported evidence."""
        localizer = _localizer()
        image = Image.new("RGB", (900, 900), (20, 30, 40))

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertEqual(HomeCityCameraStatus.UNSUPPORTED, proof.status)
        self.assertIsNone(proof.translation)
        self.assertIsNone(proof.zoom)
        self.assertEqual(HomeCityZoomStatus.UNSUPPORTED, view.zoom_status)
        self.assertEqual("unsupported_frame_layout", view.reason)
        self.assertIsNone(view.calibration_id)
        self.assertIsNone(view.zoom_anchor)
        self.assertEqual((900, 900), view.frame_size)

    def test_resized_capture_is_unsupported_but_proof_still_measures(self) -> None:
        """P3/R2: a 540x960 capture is unqualified for view calibration only."""
        localizer = _localizer()
        image = _fixture(
            _CAMERA_FIXTURES / "home_city_zoom_endpoint_20260925.png"
        ).resize((540, 960), Image.Resampling.LANCZOS)

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        # The camera proof keeps its full transform/body geometry -- only the
        # view verdict is gated, because calibration evidence exists solely
        # for native 900x1600 captures.
        self.assertTrue(proof.localized)
        self.assertEqual((540, 960), proof.frame_size)
        self.assertEqual(HomeCityZoomStatus.UNSUPPORTED, view.zoom_status)
        self.assertEqual("unsupported_capture_size", view.reason)
        self.assertEqual("home_zoom_endpoint_20260925", view.calibration_id)
        self.assertIsNone(view.zoom_anchor)
        self.assertEqual((540, 960), view.frame_size)

    def test_upscaled_capture_is_also_unsupported(self) -> None:
        """R2: a same-aspect 1800x3200 capture is equally unqualified input."""
        localizer = _localizer()
        image = _fixture(
            _CAMERA_FIXTURES / "home_city_zoom_endpoint_20260925.png"
        ).resize((1800, 3200), Image.Resampling.LANCZOS)

        proof = localizer.localize(image)
        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertTrue(proof.localized)
        self.assertEqual(HomeCityZoomStatus.UNSUPPORTED, view.zoom_status)
        self.assertEqual("unsupported_capture_size", view.reason)
        self.assertIsNone(view.zoom_anchor)

    def test_native_size_gate_precedes_classification(self) -> None:
        """R2: the capture-size gate fires even before zoom evidence is read."""
        localizer = _localizer()
        image = Image.new("RGB", (450, 800))
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.INSUFFICIENT,
            reason="scripted non-native frame",
            frame_size=(450, 800),
        )

        view = localizer.analyze_view(image, camera_proof=proof)

        self.assertEqual(HomeCityZoomStatus.UNSUPPORTED, view.zoom_status)
        self.assertEqual("unsupported_capture_size", view.reason)
        self.assertEqual("home_zoom_endpoint_20260925", view.calibration_id)
        self.assertIsNone(view.zoom_anchor)

    def test_foreign_frame_proof_is_rejected(self) -> None:
        """P8: a proof produced on a different frame cannot stamp this frame."""
        localizer = _localizer()
        image = Image.new("RGB", (900, 1600))
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="foreign frame",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(540, 960),
        )

        with self.assertRaises(SelectorResolutionError):
            localizer.analyze_view(image, camera_proof=foreign_proof)

    def test_foreign_reference_proof_is_rejected(self) -> None:
        """P8: a proof measured at a different reference size is contradictory."""
        localizer = _localizer()
        image = Image.new("RGB", (900, 1600))
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="foreign reference",
            translation=(-532, 222),
            zoom=1.0,
            reference_size=(450, 800),
            frame_size=(900, 1600),
        )

        with self.assertRaises(SelectorResolutionError):
            localizer.analyze_view(image, camera_proof=foreign_proof)

    def test_anchor_publishes_only_when_scale_hits_agree(self) -> None:
        """P5/R1: agreeing patch hits publish the calibrated interior point."""
        hits = {
            ("northeast_moat_slope_wheel.png", scale): _anchor_hit(
                (275, 750), scale=scale, score=0.95 if scale != 1.0 else 0.96
            )
            for scale in (0.98, 1.0, 1.02)
        }
        view = _view_on_scripted_matcher(_AnchorScriptedMatcher(hits))

        self.assertEqual(HomeCityZoomStatus.UNRESOLVED, view.zoom_status)
        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        self.assertEqual("northeast_moat_slope_wheel_20260925", anchor.qualification_id)
        # The point is read off the winning patch itself: origin + scale*offset.
        self.assertEqual((270, 704), anchor.point)
        self.assertEqual(Bounds(190, 650, 170, 200), anchor.bounds)
        self.assertTrue(anchor.bounds.contains_point(anchor.point))

    def test_anchor_scale_sweep_runs_bounded_and_keeps_scale_pairs(self) -> None:
        """The moat spec's eight scales share the bounded capacity and stay paired."""
        moat_scales = (0.98, 1.0, 1.02, 1.05, 1.11, 1.17, 1.35, 1.4)
        matcher = _AnchorScriptedMatcher(
            {
                ("northeast_moat_slope_wheel.png", scale): _anchor_hit(
                    (275, 750), scale=scale, score=0.95 if scale != 1.0 else 0.96
                )
                for scale in moat_scales
            }
        )
        barrier = threading.Barrier(2)
        rendezvous = {
            ("northeast_moat_slope_wheel.png", scale) for scale in moat_scales[:2]
        }
        rendezvous_calls: list[tuple[str, float]] = []
        overlapped = threading.Event()
        calls: list[tuple[str, float]] = []
        original = matcher.find_best_match

        def recorded(*args, **kwargs):
            key = (args[1].name, kwargs.get("template_scale", 1.0))
            calls.append(key)
            if key in rendezvous:
                rendezvous_calls.append(key)
                try:
                    barrier.wait(timeout=10)
                except threading.BrokenBarrierError:
                    pass
                else:
                    overlapped.set()
            return original(*args, **kwargs)

        created: list[int] = []
        original_executor = home_camera_module.ThreadPoolExecutor

        def factory(*args, **kwargs):
            created.append(kwargs.get("max_workers", args[0] if args else None))
            return original_executor(*args, **kwargs)

        with (
            mock.patch.object(matcher, "find_best_match", side_effect=recorded),
            mock.patch.object(
                home_camera_module, "ThreadPoolExecutor", side_effect=factory
            ),
        ):
            view = _view_on_scripted_matcher(matcher)

        anchor = view.zoom_anchor
        self.assertIsNotNone(anchor)
        assert anchor is not None
        self.assertEqual("northeast_moat_slope_wheel_20260925", anchor.qualification_id)
        self.assertEqual((270, 704), anchor.point)
        self.assertEqual(Bounds(190, 650, 170, 200), anchor.bounds)
        self.assertTrue(overlapped.is_set())
        self.assertEqual(2, len(rendezvous_calls))
        self.assertEqual(rendezvous, set(rendezvous_calls))
        self.assertEqual([8], created)
        self.assertEqual(
            set(moat_scales),
            {
                scale
                for name, scale in calls
                if name == "northeast_moat_slope_wheel.png"
            },
        )

    def test_anchor_is_none_when_scale_hits_disagree(self) -> None:
        """P6: contradictory hit neighborhoods publish no fallback anchor."""
        hits = {
            ("northeast_moat_slope_wheel.png", 0.98): _anchor_hit(
                (275, 750), scale=0.98
            ),
            ("northeast_moat_slope_wheel.png", 1.0): _anchor_hit(
                (600, 750), scale=1.0
            ),
        }
        view = _view_on_scripted_matcher(_AnchorScriptedMatcher(hits))

        self.assertIsNone(view.zoom_anchor)

    def test_anchor_is_none_when_point_enters_hud(self) -> None:
        """P6: a patch projecting its point into the HUD rail is rejected."""
        hits = {
            ("northeast_moat_slope_wheel.png", 1.0): _anchor_hit((140, 750)),
        }
        view = _view_on_scripted_matcher(_AnchorScriptedMatcher(hits))

        self.assertIsNone(view.zoom_anchor)

    def test_anchor_is_none_when_patch_leaves_viewport(self) -> None:
        """P6: a patch projecting offscreen is rejected rather than clamped."""
        hits = {
            ("northeast_moat_slope_wheel.png", 1.0): _anchor_hit((-89, 750)),
        }
        view = _view_on_scripted_matcher(_AnchorScriptedMatcher(hits))

        self.assertIsNone(view.zoom_anchor)

    def test_occluded_point_patch_publishes_no_fallback(self) -> None:
        """P6/R1: occluding the patch that contains the point drops the anchor."""
        from PIL import ImageDraw

        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_zoom_endpoint_20260925.png")
        proof = localizer.localize(image)
        occluded = image.copy()
        # Obscure only the ground point's neighborhood, preserving the remote
        # shaft pixels that used to qualify a projected point incorrectly.
        ImageDraw.Draw(occluded).rectangle([260, 640, 309, 717], fill=(0, 0, 0))

        view = localizer.analyze_view(occluded, camera_proof=proof)

        self.assertEqual(HomeCityZoomStatus.AT_ENDPOINT, view.zoom_status)
        self.assertIsNone(view.zoom_anchor)

    def test_occluded_fountain_patch_publishes_no_fallback(self) -> None:
        """Covering the fountain's own patch drops its anchor on the default view."""
        from PIL import ImageDraw

        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_default_start_20260927.png")
        proof = localizer.localize(image)
        occluded = image.copy()
        # Blank the fountain patch itself, not a distant landmark.
        ImageDraw.Draw(occluded).rectangle([405, 860, 515, 955], fill=(0, 0, 0))

        view = localizer.analyze_view(occluded, camera_proof=proof)

        self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
        self.assertIsNone(view.zoom_anchor)

    def test_fountain_anchor_is_none_when_its_point_enters_hud(self) -> None:
        """P6: a fountain match projecting its point into the HUD is rejected."""
        hits = {
            ("castle_fountain.png", 1.0): _anchor_hit((89.5, 580), size=(85, 70)),
        }
        view = _view_on_scripted_matcher(_AnchorScriptedMatcher(hits))

        self.assertIsNone(view.zoom_anchor)

    def test_anchor_is_none_when_no_qualified_patch_is_visible(self) -> None:
        """A localized view where both wheel patches are offscreen publishes none."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_west_holdout_20260916.png")

        view = localizer.analyze_view(image, camera_proof=localizer.localize(image))

        self.assertEqual(HomeCityZoomStatus.NOT_AT_ENDPOINT, view.zoom_status)
        self.assertIsNone(view.zoom_anchor)

    def test_shared_producer_publishes_proof_and_view_from_one_frame(self) -> None:
        """P7: one prepared frame feeds the camera proof and the view verdict."""
        matcher = _PrepareCountingMatcher()
        localizer = HomeCityCameraLocalizer(matcher=matcher)
        image = _fixture(_CAMERA_FIXTURES / "home_city_zoom_endpoint_20260925.png")

        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=localizer,
        )

        self.assertEqual(1, matcher.prepare_frame_calls)
        self.assertEqual(1, matcher.prepare_proposal_frame_calls)
        self.assertIsNotNone(surface.camera_proof)
        self.assertTrue(surface.camera_proof.localized)
        self.assertIsNotNone(surface.home_city_view)
        self.assertEqual(
            HomeCityZoomStatus.AT_ENDPOINT, surface.home_city_view.zoom_status
        )
        self.assertEqual(
            surface.camera_proof.frame_size, surface.home_city_view.frame_size
        )
        self.assertIsNotNone(surface.home_city_view.zoom_anchor)

        frame_ref = _frame_ref("endpoint-surface")
        bound = bind_spatial_surface(
            surface,
            frame_ref=frame_ref,
            source_screen=ScreenType.PNC_HOME_CITY,
            source_layout_id="layout-a",
        )
        for fact in (bound.camera_proof, bound.home_city_view):
            self.assertEqual(frame_ref, fact.frame_ref)
            self.assertEqual(ScreenType.PNC_HOME_CITY, fact.source_screen)
            self.assertEqual("layout-a", fact.source_layout_id)

        foreign = replace(
            bound,
            home_city_view=replace(
                bound.home_city_view, frame_ref=_frame_ref("stale")
            ),
        )
        with self.assertRaises(SelectorResolutionError):
            bind_spatial_surface(
                foreign,
                frame_ref=frame_ref,
                source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id="layout-a",
            )

    def test_proposal_cache_reuses_only_the_same_prepared_frame(self) -> None:
        """Proposal pixels are reused per frame and invalidated on replacement."""

        matcher = _PrepareCountingMatcher()
        localizer = HomeCityCameraLocalizer(matcher=matcher)
        image = Image.new("RGB", (900, 1600))
        first = localizer.prepare_frame(image)
        second = localizer.prepare_frame(image)
        assert first is not None
        assert second is not None
        self.assertIsNot(first, second)

        first_proposal = localizer._proposal_frame(first)
        self.assertIs(first_proposal, localizer._proposal_frame(first))
        self.assertIsNot(first_proposal, localizer._proposal_frame(second))
        self.assertEqual(2, matcher.prepare_proposal_frame_calls)
