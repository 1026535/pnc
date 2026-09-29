"""Home camera zoom tests."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectSourceKind
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    HOME_CITY_HUD_SAFE_MAX_Y_RATIO,
)
from pnc_automation.app.pnc.vision.home_city_camera.models import (
    HomeCityCameraLandmark,
)
from pnc_automation.app.pnc.vision.home_city_camera.localization import (
    HomeCityCameraLocalizer,
)
from pnc_automation.app.pnc.vision.home_city_camera.catalog import (
    load_home_city_camera_catalog,
)
from pnc_automation.core.infra.diagnostics.performance import (
    PerformanceReportWriter,
    performance_run_scope,
)
from pnc_automation.core.vision.image.models import TemplateMatch

from tests.support.pnc.home_city_camera.doubles import (
    _ScaleAwareScriptedMatcher,
    _ZoomScriptedMatcher,
    _zoomed_localizer,
)
from tests.support.pnc.home_city_camera.fixtures import (
    _CAMERA_FIXTURES,
    _fixture,
    _localizer,
)


class HomeCityCameraZoomTests(unittest.TestCase):
    """Zoom-aware localization must recover the measured transform honestly."""

    _FIXED_FOUR = {
        "p2_institute_facade.png",
        "p3_institute_base_left.png",
        "p4_garden_terrace.png",
        "t5_barracks_roofs.png",
    }

    def test_zoomed_scene_recovers_the_measured_zoom(self) -> None:
        """Content rendered at grid zoom 1.25 fits and publishes that zoom."""
        localizer = _zoomed_localizer(
            {name: (1.25, (-200, -300)) for name in self._FIXED_FOUR}
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.25, proof.zoom, places=2)
        # Published translation is the combined z*offset + image translation:
        # (-200,-300) + 1.25*(-532,+222) = (-865,-22.5).
        self.assertAlmostEqual(-865, proof.translation[0], delta=1)
        self.assertAlmostEqual(-22.5, proof.translation[1], delta=1)
        self.assertTrue(
            {"institute_structure", "garden_terrace", "barracks_roofs"}
            <= proof.matched_group_ids
        )

    def test_zoom_sweep_spans_keep_worker_identity_and_localize_parent(self) -> None:
        """Opt-in localization reports every concurrent scale under its frame span."""
        localizer = _zoomed_localizer(
            {name: (1.25, (-200, -300)) for name in self._FIXED_FOUR}
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            writer = PerformanceReportWriter(Path(temporary_directory))
            with performance_run_scope(writer, "home_camera_fixture"):
                proof = localizer.localize(Image.new("RGB", (900, 1600)))

            self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
            report_path = next(Path(temporary_directory).glob("*.json"))
            report = json.loads(report_path.read_text(encoding="utf-8"))
            localize = next(
                span for span in report["spans"] if span["name"] == "home_camera.localize"
            )
            hypotheses = [
                span for span in report["spans"]
                if span["name"] == "home_camera.zoom_hypothesis"
            ]
            self.assertEqual(15, len(hypotheses))
            self.assertEqual(
                {localize["span_id"]},
                {span["parent_id"] for span in hypotheses},
            )
            self.assertTrue(all(span["thread_id"] != localize["thread_id"] for span in hypotheses))
            self.assertEqual(
                15,
                len({span["attributes"]["zoom_scale"] for span in hypotheses}),
            )

    def test_off_grid_zoom_fits_positions_instead_of_quantizing(self) -> None:
        """A scene at zoom 1.275 fits from landmark pairs, not the 0.05 grid."""
        localizer = _zoomed_localizer(
            {name: (1.275, (-50, -60)) for name in self._FIXED_FOUR}
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # 1.275 is >0.02 from both adjacent grid values; the published zoom
        # must be the fitted measurement, not a snapped grid hypothesis.
        self.assertAlmostEqual(1.275, proof.zoom, delta=0.01)
        # Center correspondences carry integer-bounds quantization (<=0.5px
        # per vote) which the least-squares zoom term can amplify at the
        # centroid; a grid-snapped 1.25/1.30 hypothesis would still miss
        # translation by ~12px, so this bound keeps the same discrimination.
        self.assertAlmostEqual(-50 + 1.275 * -532, proof.translation[0], delta=2)
        self.assertAlmostEqual(-60 + 1.275 * 222, proof.translation[1], delta=2)

    def test_contradictory_zoom_hypotheses_are_ambiguous(self) -> None:
        """Two multi-group sets disagreeing in zoom reject as ambiguous."""
        localizer = _zoomed_localizer(
            {
                "p2_institute_facade.png": (0.90, (10, -20)),
                "p3_institute_base_left.png": (0.90, (10, -20)),
                "p4_garden_terrace.png": (0.90, (10, -20)),
                "t5_barracks_roofs.png": (0.75, (900, 700)),
                "east_aqueduct.png": (0.75, (900, 700)),
                "east_parapet.png": (0.75, (900, 700)),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.AMBIGUOUS, proof.status)
        self.assertEqual("conflicting_zoom_hypotheses", proof.reason)
        self.assertIsNone(proof.translation)

    def test_different_sized_neighbor_scale_matches_stay_consistent(self) -> None:
        """Neighbor template scales crop the same features at different sizes.

        Regression for live010: every evaluated scale returns a differently
        sized match whose center stays on the same physical feature while its
        top-left carries a bias proportional to that landmark's own size.
        Correspondences must use the scale-invariant centers so every
        hypothesis converges on the true transform; fitted top-lefts instead
        leave residuals proportional to each crop's size and split weak
        neighboring hypotheses into false rivals.
        """
        catalog = load_home_city_camera_catalog()
        bounds_by_file = {
            item.file_name: item.reference_bounds for item in catalog.landmarks
        }
        # Deliberately mixed crop sizes (60..157px) across independent groups:
        # the top-left bias is proportional to each landmark's own size.
        placements = {
            name: (1.0, (-5.0, -624.0))
            for name in (
                "tower_of_trial_body.png",
                "t5_barracks_roofs.png",
                "p2_institute_facade.png",
                "p4_garden_terrace.png",
                "castle_tower.png",
                "plaza_ring.png",
            )
        }
        localizer = HomeCityCameraLocalizer(
            matcher=_ScaleAwareScriptedMatcher(placements, bounds_by_file),
            catalog=catalog,
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.01)
        for actual, expected in zip(
            proof.translation, (-537, -402), strict=True
        ):
            self.assertLessEqual(abs(actual - expected), 2)
        self.assertEqual(6, len(proof.evidence))
        self.assertTrue(all(item.residual <= 1.0 for item in proof.evidence))

    def test_fast_path_scale_must_not_hide_a_contradictory_zoom(self) -> None:
        """A qualifying zoom-1.0 hypothesis cannot skip evaluating rivals.

        Regression for the removed 1.0 fast path: the first fixed-landmark
        set qualifies at the former fast-path scale while an equally valid
        fixed set sits at zoom 1.25 -- the contract requires ambiguity, not
        publication of the first qualifying transform found.
        """
        localizer = _zoomed_localizer(
            {
                **{name: (1.0, (10, -20)) for name in self._FIXED_FOUR},
                "east_aqueduct.png": (1.25, (200, 150)),
                "east_parapet.png": (1.25, (200, 150)),
                "east_cliff_rock.png": (1.25, (200, 150)),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.AMBIGUOUS, proof.status)
        self.assertEqual("conflicting_zoom_hypotheses", proof.reason)
        self.assertIsNone(proof.translation)

    def test_pair_fitted_zoom_cannot_escape_the_search_domain(self) -> None:
        """Votes whose positions imply zoom >1.40 cannot publish a transform.

        The scripted matches are visible only at evaluated scale 1.40, but
        their positions carry scale 1.5: every pair fit lands outside the
        supported domain, so no qualifying transform may be formed.
        """
        catalog = load_home_city_camera_catalog()
        bounds_by_file = {
            landmark.file_name: landmark.reference_bounds
            for landmark in catalog.landmarks
        }
        matches: dict[str, TemplateMatch | None] = {}
        zoom_by_file: dict[str, float] = {}
        for name in self._FIXED_FOUR:
            bounds = bounds_by_file[name]
            matches[name] = TemplateMatch(
                bounds=Bounds(
                    x=round(1.5 * bounds.x - 50),
                    y=round(1.5 * bounds.y - 60),
                    width=round(1.5 * bounds.width),
                    height=round(1.5 * bounds.height),
                ),
                confidence=0.95,
            )
            zoom_by_file[name] = 1.4
        localizer = HomeCityCameraLocalizer(
            matcher=_ZoomScriptedMatcher(matches, zoom_by_file=zoom_by_file),
            catalog=catalog,
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_zoomed_projection_scales_atlas_points(self) -> None:
        """Forward and inverse projection must divide/multiply by zoom."""
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=(-765, 78),
            zoom=1.25,
            frame_size=(900, 1600),
        )

        # Castle nameplate anchor: 1.25*(991,625) + (-765,78) = (473.75,859.25).
        self.assertEqual((474, 859), proof.project_to_frame((991, 625)))
        self.assertEqual(
            (991, 625), proof.project_reference_to_atlas((473.75, 859.25))
        )

    def test_zoomed_target_match_scales_action_geometry(self) -> None:
        """Body action geometry derives from the zoomed match, not reference size."""
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=(-765, 78),
            zoom=1.25,
            frame_size=(900, 1600),
        )
        # Image translation = published - z*offset = (-100,-199.5); the body
        # origin lands at 1.25*(700,1240) + (-100,-199.5) = (775,1350.5).
        matcher = _ZoomScriptedMatcher(
            {
                "p6_path_right.png": TemplateMatch(
                    bounds=Bounds(775, 1350, 100, 93),
                    confidence=0.95,
                )
            },
            zoom_by_file={"p6_path_right.png": 1.25},
        )
        localizer = HomeCityCameraLocalizer(matcher=matcher, catalog=catalog)
        frame = matcher.prepare_frame(None)

        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 1.0)
        # Action point = match origin + 1.25*(724,1253)-(700,1240) offset.
        self.assertEqual((805, 1366), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))

    def test_zoomed_target_match_rejects_foreign_scale_content(self) -> None:
        """A body rendered at zoom 1 must not publish under a 1.25 proof."""
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=(-765, 78),
            zoom=1.25,
            frame_size=(900, 1600),
        )
        matcher = _ZoomScriptedMatcher(
            {
                "p6_path_right.png": TemplateMatch(
                    bounds=Bounds(775, 1350, 80, 75),
                    confidence=0.95,
                )
            },
            zoom_by_file={"p6_path_right.png": 1.0},
        )
        localizer = HomeCityCameraLocalizer(matcher=matcher, catalog=catalog)
        frame = matcher.prepare_frame(None)

        self.assertIsNone(localizer.match_target(frame, target, proof=proof))

    def test_tight_landmark_span_cannot_establish_scale(self) -> None:
        """Two groups with a <100px authored span stay insufficient."""
        catalog = replace(
            load_home_city_camera_catalog(),
            landmarks=(
                HomeCityCameraLandmark(
                    id="close_a",
                    group_id="g1",
                    file_name="close_a.png",
                    reference_bounds=Bounds(100, 100, 50, 50),
                    min_score=0.5,
                ),
                HomeCityCameraLandmark(
                    id="close_b",
                    group_id="g2",
                    file_name="close_b.png",
                    reference_bounds=Bounds(140, 120, 50, 50),
                    min_score=0.5,
                ),
                HomeCityCameraLandmark(
                    id="close_c",
                    group_id="g1",
                    file_name="close_c.png",
                    reference_bounds=Bounds(160, 150, 50, 50),
                    min_score=0.5,
                ),
            ),
        )
        localizer = _zoomed_localizer(
            {
                "close_a.png": (1.0, (10, -20)),
                "close_b.png": (1.0, (10, -20)),
                "close_c.png": (1.0, (10, -20)),
            },
            catalog=catalog,
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_scale_separation", proof.reason)

    def test_movable_landmarks_neither_establish_nor_contradict(self) -> None:
        """Slot occupants attach only as residual-verified evidence."""
        base = {name: (1.0, (10, -20)) for name in self._FIXED_FOUR}

        # A Blacksmith placement that disagrees with the fixed transform must
        # be dropped without vetoing the qualified fixed cluster.
        localizer = _zoomed_localizer(
            {**base, "blacksmith_structure.png": (1.0, (400, 500))}
        )
        proof = localizer.localize(Image.new("RGB", (900, 1600)))
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertNotIn(
            "blacksmith_structure", {item.landmark_id for item in proof.evidence}
        )

        # Fixed votes from a single group plus an agreeing movable landmark
        # still cannot establish the camera.
        localizer = _zoomed_localizer(
            {
                "p2_institute_facade.png": (1.0, (10, -20)),
                "p3_institute_base_left.png": (1.0, (10, -20)),
                "p6_path_right.png": (1.0, (10, -20)),
                "blacksmith_structure.png": (1.0, (10, -20)),
            }
        )
        proof = localizer.localize(Image.new("RGB", (900, 1600)))
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)

    def test_northeast_holdout_localizes_through_fixed_groups(self) -> None:
        """The 2026-09-23 northeast view localizes through the new fixed crops."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_northeast_holdout_20260923.png")
        )

        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual(1.0, proof.zoom)
        for actual, expected in zip(proof.translation, (-1251, 139), strict=True):
            self.assertLessEqual(abs(actual - expected), 1)
        self.assertTrue(
            {"sauroi_lair_structure", "east_fortification"}
            <= set(proof.matched_group_ids)
        )
        self.assertGreaterEqual(len(proof.evidence), 3)
        # Warehouse is visible in this native view. Its body may publish, but
        # the measured action point remains below the HUD-safe tap band.
        objects = localizer.matched_target_objects(prepared, proof=proof)
        self.assertEqual(1, len(objects))
        warehouse = objects[0]
        self.assertEqual(
            HomeCityObjectId.WAREHOUSE,
            home_city_object_id_from_metadata(warehouse.metadata),
        )
        self.assertEqual(SpatialObjectSourceKind.TEMPLATE, warehouse.source_kind)
        self.assertEqual(HomeCitySlotSelector(3), warehouse.home_city_slot)
        self.assertEqual((250, 1038), warehouse.action_point)
        self.assertGreater(
            warehouse.action_point[1], int(HOME_CITY_HUD_SAFE_MAX_Y_RATIO * 1600),
        )

    def test_northeast_moat_pair_alone_cannot_establish_the_camera(self) -> None:
        """The correlated moat crops share east_fortification and cannot localize."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_northeast_holdout_20260923.png")
        # Mask the matched Sauroi pier region and the region the new
        # campaign_left_pedestal landmark covers in this view, so only the
        # moat pair can vote: every remaining fixed crop shares one physical
        # group, which can never satisfy the two-group minimum.
        image.paste((0, 0, 0), (635, 865, 740, 1010))
        image.paste((0, 0, 0), (647, 1130, 746, 1282))
        prepared = localizer.prepare_frame(image)

        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_wall_corridor_localizes_through_campaign_pedestal(self) -> None:
        """The failed-Wall live view localizes through the new fixed crop.

        The 2026-09-23 turn003 corridor frame (post-pan Wall view, frame
        0064) previously offered only east_fortification: the movable
        Alliance Hall cannot establish the camera and Sauroi is behind the
        top HUD. The fixed campaign_left_pedestal landmark -- sharing the
        campaign_portal group with the existing portal body -- supplies the
        second independent group. This is a regression frame derived from a
        diagnosed live view, not an unseen holdout.
        """
        localizer = _localizer()
        prepared = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_wall_corridor_regression_20260923.png")
        )

        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual(1.0, proof.zoom)
        for actual, expected in zip(proof.translation, (-1298, -645), strict=True):
            self.assertLessEqual(abs(actual - expected), 1)
        self.assertTrue(
            {"campaign_portal", "east_fortification"}
            <= set(proof.matched_group_ids)
        )
        # The movable Alliance Hall corroborates the fitted transform but
        # cannot establish it.
        self.assertIn("alliance_hall_structure", proof.matched_group_ids)
        # The existing Wall slot-2 body qualifies under this transform; no
        # new target or tap geometry is invented.
        matches = localizer.matched_target_objects(prepared, proof=proof)
        self.assertEqual(
            {HomeCityObjectId.WALL},
            {home_city_object_id_from_metadata(item.metadata) for item in matches},
        )
        self.assertEqual(HomeCitySlotSelector(2), matches[0].home_city_slot)
        self.assertEqual((456, 1057), matches[0].action_point)
        self.assertTrue(matches[0].action_bounds.contains_point(matches[0].action_point))

    def test_wall_corridor_pedestal_masked_cannot_establish_the_camera(self) -> None:
        """Masking the new pedestal leaves only east_fortification to vote."""
        localizer = _localizer()
        image = _fixture(_CAMERA_FIXTURES / "home_city_wall_corridor_regression_20260923.png")
        # Mask the matched Campaign pedestal region so only the fortification
        # crops can vote; the movable Alliance Hall cannot count, so the
        # camera must fail closed exactly as it did live.
        image.paste((0, 0, 0), (600, 348, 697, 497))
        prepared = localizer.prepare_frame(image)

        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)
        self.assertIsNone(proof.zoom)
        self.assertFalse(localizer.matched_target_objects(prepared, proof=proof))
