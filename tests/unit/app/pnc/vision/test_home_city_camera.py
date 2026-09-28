"""Home-city camera localization from authored scene landmarks."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraEvidence,
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectSourceKind,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    home_city_object_definition_for_label,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.vision.home_city_camera import (
    HOME_CITY_CAMERA_REFERENCE_SIZE,
    HomeCityCameraCatalog,
    HomeCityCameraLandmark,
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
    merge_camera_target_objects,
)
from pnc_automation.app.pnc.vision.observation_provenance import bind_spatial_surface
from pnc_automation.app.pnc.vision.spatial_surfaces import build_home_city_spatial_surface
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)
from datetime import UTC, datetime

from tests.support.paths import TEST_DATA_ROOT


_SCREEN_RECOGNITION = TEST_DATA_ROOT / "screen_recognition"
_CAMERA_FIXTURES = TEST_DATA_ROOT / "home_city_camera"


def _fixture(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return image.convert("RGB")


def _localizer() -> HomeCityCameraLocalizer:
    return HomeCityCameraLocalizer(matcher=OpenCvTemplateMatcher())


class _ZoomScriptedMatcher:
    """Matcher stub that simulates scene content rendered at a true zoom.

    A hit is returned only while the evaluated ``template_scale`` stays within
    ``tolerance`` of that file's true scene zoom, and the scripted position
    always carries the true scale -- like a real resized-template correlation.
    """

    _TOLERANCE = 0.04

    def __init__(
        self,
        matches: dict[str, TemplateMatch | None],
        *,
        zoom_by_file: dict[str, float],
    ) -> None:
        self._matches = matches
        self._zoom_by_file = zoom_by_file

    def prepare_frame(self, image: Image.Image, *, reference_size=None) -> PreparedFrame:
        del image
        return PreparedFrame(
            pixels=np.zeros((1600, 900, 3), dtype=np.uint8),
            original_size=(900, 1600),
            reference_size=(900, 1600),
        )

    def prepare_proposal_frame(self, frame: PreparedFrame) -> PreparedFrame:
        return frame

    def find_best_match_coarse_to_fine(
        self,
        frame,
        proposal_frame,
        template_path: Path,
        *,
        threshold: float,
        **kwargs,
    ):
        del proposal_frame
        return self.find_best_match(
            frame, template_path, threshold=threshold, **kwargs
        )

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        true_zoom = self._zoom_by_file.get(template_path.name)
        if true_zoom is None or abs(scale - true_zoom) > self._TOLERANCE:
            return None
        return self._matches.get(template_path.name)


class _ScaleAwareScriptedMatcher(_ZoomScriptedMatcher):
    """Matcher stub returning evaluated-scale bounds anchored on the feature.

    A real resized template is ``evaluated_scale * reference`` sized while
    its correlation peak keeps the crop center on the same physical feature
    at ``true_zoom * reference_center + offset``.  Neighboring scales
    therefore return differently sized matches whose centers agree and whose
    top-lefts carry a size-dependent bias -- the live010 false-conflict
    geometry.
    """

    _TOLERANCE = 0.35

    def __init__(
        self,
        placements: dict[str, tuple[float, tuple[float, float]]],
        bounds_by_file: dict[str, Bounds],
        *,
        score: float = 0.95,
    ) -> None:
        self._placements = placements
        self._bounds_by_file = bounds_by_file
        self._score = score

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        placement = self._placements.get(template_path.name)
        if placement is None or abs(scale - placement[0]) > self._TOLERANCE:
            return None
        true_zoom, offset = placement
        bounds = self._bounds_by_file[template_path.name]
        width = int(round(scale * bounds.width))
        height = int(round(scale * bounds.height))
        center_x = true_zoom * (bounds.x + bounds.width / 2) + offset[0]
        center_y = true_zoom * (bounds.y + bounds.height / 2) + offset[1]
        return TemplateMatch(
            bounds=Bounds(
                x=int(round(center_x - width / 2)),
                y=int(round(center_y - height / 2)),
                width=width,
                height=height,
            ),
            confidence=self._score,
        )


def _scripted_localizer(
    placements: dict[str, tuple[int, int] | None],
    *,
    score: float = 0.95,
) -> HomeCityCameraLocalizer:
    """Builds a localizer over zoom-1.0 content at reference position + offset."""

    catalog = load_home_city_camera_catalog()
    matches: dict[str, TemplateMatch | None] = {}
    zoom_by_file: dict[str, float] = {}
    for landmark in catalog.landmarks:
        offset = placements.get(landmark.id)
        if offset is None:
            matches[landmark.file_name] = None
            continue
        zoom_by_file[landmark.file_name] = 1.0
        matches[landmark.file_name] = TemplateMatch(
            bounds=replace(
                landmark.reference_bounds,
                x=landmark.reference_bounds.x + offset[0],
                y=landmark.reference_bounds.y + offset[1],
            ),
            confidence=score,
        )
    return HomeCityCameraLocalizer(
        matcher=_ZoomScriptedMatcher(matches, zoom_by_file=zoom_by_file),
        catalog=catalog,
    )


def _zoomed_localizer(
    placements: dict[str, tuple[float, tuple[int, int]]],
    *,
    score: float = 0.95,
    catalog: HomeCityCameraCatalog | None = None,
) -> HomeCityCameraLocalizer:
    """Builds a localizer over content rendered at per-file ``(zoom, offset)``.

    ``placements`` maps a template file name to its true scene zoom and image
    translation; the scripted match lands at ``zoom * reference + offset``.
    """

    catalog = catalog or load_home_city_camera_catalog()
    bounds_by_file = {
        item.file_name: item.reference_bounds
        for item in (*catalog.landmarks, *catalog.targets)
    }
    matches: dict[str, TemplateMatch | None] = {}
    zoom_by_file: dict[str, float] = {}
    for file_name, bounds in bounds_by_file.items():
        placement = placements.get(file_name)
        if placement is None:
            matches[file_name] = None
            continue
        zoom, offset = placement
        zoom_by_file[file_name] = zoom
        # Center-anchored bounds mimic a real match: the resized template's
        # correlation peaks with its center on the physical feature at
        # ``zoom * reference_center + offset``, independent of crop size.
        width = int(round(zoom * bounds.width))
        height = int(round(zoom * bounds.height))
        matches[file_name] = TemplateMatch(
            bounds=Bounds(
                x=int(round(zoom * (bounds.x + bounds.width / 2) + offset[0] - width / 2)),
                y=int(round(zoom * (bounds.y + bounds.height / 2) + offset[1] - height / 2)),
                width=width,
                height=height,
            ),
            confidence=score,
        )
    return HomeCityCameraLocalizer(
        matcher=_ZoomScriptedMatcher(matches, zoom_by_file=zoom_by_file),
        catalog=catalog,
    )


def _frame_ref(label: str) -> FrameRef:
    return FrameRef(
        session_id=label,
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
    )


class HomeCityCameraCatalogTests(unittest.TestCase):
    """The packaged landmark catalog must stay self-consistent and small."""

    def test_catalog_loads_reviewed_landmarks_targets_and_anchor_basis(self) -> None:
        catalog = load_home_city_camera_catalog()

        self.assertEqual((900, 1600), catalog.reference_size)
        self.assertEqual((-532, 222), catalog.atlas_to_reference_offset)
        self.assertEqual(
            (HomeCityObjectId.CASTLE, HomeCityObjectId.INFANTRY_BARRACKS),
            catalog.anchor_object_ids,
        )
        self.assertEqual(30, len(catalog.landmarks))
        self.assertEqual(7, len(catalog.targets))
        groups = {landmark.group_id for landmark in catalog.landmarks}
        self.assertEqual(
            {
                "institute_structure",
                "garden_terrace",
                "plaza_low",
                "barracks_roofs",
                "tower_structure",
                "blacksmith_structure",
                "southern_courtyard",
                "castle_structure",
                "courtyard_garden",
                "east_fortification",
                "east_cliff",
                "alliance_hall_structure",
                "sanctum_structure",
                "campaign_portal",
                "illusory_beast_manor_structure",
                "sauroi_lair_structure",
            },
            groups,
        )
        # Institute-correlated crops share one group so they cannot outvote
        # independent contradictory evidence.
        institute_votes = [
            landmark.id
            for landmark in catalog.landmarks
            if landmark.group_id == "institute_structure"
        ]
        self.assertEqual(
            {"p2_institute_facade", "p3_institute_base_left", "p6_path_right"},
            set(institute_votes),
        )
        # Correlated eastern wall/cliff crops are grouped honestly for the same reason.
        by_group = {}
        for landmark in catalog.landmarks:
            by_group.setdefault(landmark.group_id, set()).add(landmark.id)
        self.assertEqual(
            {
                "east_aqueduct",
                "east_parapet",
                "ridge_wall",
                "northeast_moat_cap",
                "northeast_moat_shaft",
            },
            by_group["east_fortification"],
        )
        # The Sauroi Lair pier is a new independent fixed structure; the two
        # moat parts above join east_fortification and never vote apart.
        self.assertEqual({"northeast_sauroi_pier"}, by_group["sauroi_lair_structure"])
        # The portal body and its left pedestal are two measured regions of
        # the same fixed Campaign structure; they share one group and can
        # never vote as independent scene proof.
        self.assertEqual(
            {"campaign_portal_body", "campaign_left_pedestal"},
            by_group["campaign_portal"],
        )
        self.assertEqual({"east_cliff_rock", "east_rock_trees"}, by_group["east_cliff"])
        self.assertEqual({"tower_of_trial_body", "west_trial_wall"}, by_group["tower_structure"])
        # Castle keep crops share one structure group; the statue monument and
        # courtyard gardens are genuinely independent scene regions.
        self.assertEqual(
            {
                "castle_fountain",
                "castle_tower",
            },
            by_group["castle_structure"],
        )
        self.assertEqual(
            {"statue_wings", "plaza_ring", "p5_plaza_low", "t6_plaza_south"},
            by_group["plaza_low"],
        )
        self.assertEqual({"garden_west"}, by_group["courtyard_garden"])
        # Two distinct parts of one Manor share one group so the structure can
        # supply only one group's identity correspondences, not an extra vote.
        self.assertEqual(
            {"illusory_beast_manor_owl_head", "illusory_beast_manor_right_tower"},
            by_group["illusory_beast_manor_structure"],
        )
        for item in (*catalog.landmarks, *catalog.targets):
            self.assertTrue(catalog.template_path(item.file_name).is_file())
        self.assertIs(
            catalog.target_for(HomeCityObjectId.INSTITUTE),
            catalog.targets[0],
        )
        campaign = catalog.target_for(HomeCityObjectId.CAMPAIGN)
        self.assertIsNotNone(campaign)
        self.assertEqual((2083, 1121), campaign.atlas_action_point())
        blacksmith = catalog.target_for(HomeCityObjectId.BLACKSMITH)
        self.assertIsNotNone(blacksmith)
        self.assertEqual(
            HomeCitySlotSelector(12),
            blacksmith.reference_slot,
        )
        manor = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        self.assertIsNotNone(manor)
        # The Manor is a fixed camera target: it publishes no slot candidate.
        self.assertIsNone(manor.reference_slot)
        self.assertEqual((1032, 2068), manor.atlas_action_point())
        self.assertIsNone(catalog.target_for(HomeCityObjectId.CASTLE))
        # An unrelated nearby "Manor" label is not the Illusory Beast Manor and
        # must never resolve to it.
        self.assertIsNone(home_city_object_definition_for_label("Manor"))


class HomeCityCameraLocalizationTests(unittest.TestCase):
    """Measured translations must reproduce the calibrated tour evidence."""

    def test_reference_layout_localizes_at_the_authored_origin(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "home_city_core.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual((540, 960), proof.frame_size)
        self.assertEqual((900, 1600), proof.reference_size)
        self.assertGreaterEqual(len(proof.evidence), 5)
        self.assertGreaterEqual(len(proof.matched_group_ids), 3)
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_live_hud_occlusion_keeps_camera_but_does_not_invent_institute_body(self) -> None:
        """The live offer rail hides Institute; independent regions still locate Home."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_hud_occluded_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertEqual(
            frozenset(
                {
                    "plaza_low",
                    "garden_terrace",
                    "barracks_roofs",
                    "castle_structure",
                    "courtyard_garden",
                }
            ),
            proof.matched_group_ids,
        )
        self.assertFalse(localizer.matched_target_objects(prepared, proof=proof))

    def test_live_tower_pan_localizes_after_northern_landmarks_leave_view(self) -> None:
        """The qualified Tower body extends camera proof beyond the Institute region."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(_fixture(_CAMERA_FIXTURES / "home_city_tower_lower_20260916.png"))
        proof = localizer.localize(prepared)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -843), proof.translation)
        self.assertIn("tower_structure", proof.matched_group_ids)
        target = localizer.catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)
        match = localizer.match_target(prepared, target, proof=proof)
        self.assertIsNotNone(match)
        self.assertEqual((179, 389), match.action_point)

    def test_pan_pair_localizes_at_the_measured_image_translation(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_pan_07.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Image translation -468,-931 relative to the authored reference view,
        # combined with the -532,+222 atlas offset.
        self.assertEqual((-1000, -710), proof.translation)
        self.assertIn("institute_structure", proof.matched_group_ids)
        self.assertIn("plaza_low", proof.matched_group_ids)

    def test_west_live_holdout_localizes_at_both_supported_sizes(self) -> None:
        """Independent west capture retains three votes from two actual structures."""
        native = _fixture(_CAMERA_FIXTURES / "home_city_west_holdout_20260916.png")
        for size in ((900, 1600), (540, 960)):
            with self.subTest(size=size):
                proof = _localizer().localize(native.resize(size, Image.Resampling.LANCZOS))
                self.assertTrue(proof.localized)
                # Projecting integer 540px matches back to the 900px atlas
                # quantizes the vertical offset by one reference pixel.
                for actual, expected in zip(proof.translation, (-74, -812), strict=True):
                    self.assertLessEqual(abs(actual - expected), 1)
                self.assertEqual(frozenset({"tower_structure", "sanctum_structure"}), proof.matched_group_ids)
                self.assertEqual(3, len(proof.evidence))
                self.assertTrue(all(item.residual <= 1 for item in proof.evidence))

    def test_west_tower_crops_alone_do_not_supply_independent_scene_proof(self) -> None:
        """Two correlated Tower crops cannot replace the missing Sanctum evidence."""
        image = _fixture(_CAMERA_FIXTURES / "home_city_west_holdout_20260916.png")
        image.paste((0, 0, 0), (500, 960, 595, 1085))
        proof = _localizer().localize(image)
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_tower_view_localizes_at_the_measured_image_translation(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, -638), proof.translation)
        self.assertIn("barracks_roofs", proof.matched_group_ids)

    def test_different_castle_appearance_still_localizes(self) -> None:
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_mega_castle.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_live_castle_holdout_localizes_through_three_courtyard_groups(self) -> None:
        """The 2026-09-21 panned castle view agrees on three independent regions."""
        localizer = _localizer()
        prepared = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_castle_holdout_20260921.png")
        )
        proof = localizer.localize(prepared)

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-545, 149), proof.translation)
        self.assertEqual(1.0, proof.zoom)
        self.assertTrue(
            {"castle_structure", "plaza_low", "courtyard_garden"}
            <= proof.matched_group_ids
        )
        self.assertFalse(localizer.matched_target_objects(prepared, proof=proof))

    def test_live_castle_default_view_localizes_at_the_reference_camera(self) -> None:
        """A different account's castle at the authored camera position localizes."""
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_castle_default_20260921.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-532, 222), proof.translation)
        self.assertTrue(
            {"castle_structure", "plaza_low"} <= proof.matched_group_ids
        )

    def test_live_institute_pretap_frame_localizes_past_the_false_zoom_conflict(self) -> None:
        """The live010 Institute pre-tap frame refused a false scale conflict.

        Weak 0.95/1.05 matches of the same scene features disagreed with
        one another by over the 10px rival bound under top-left
        correspondences; center correspondences converge on the measured
        image translation (-5,-624), atlas (-537,-402).
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_institute_pretap_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.02)
        for actual, expected in zip(proof.translation, (-537, -402), strict=True):
            self.assertLessEqual(abs(actual - expected), 4)
        self.assertTrue(
            {"institute_structure", "plaza_low", "barracks_roofs"}
            <= proof.matched_group_ids
        )
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_live_tower_pretap_frame_localizes_past_the_false_zoom_conflict(self) -> None:
        """The live008 Tower pre-tap frame carried the same false conflict.

        Center correspondences converge on image translation (-2,-594),
        atlas (-534,-372), at the measured zoom 1.0.
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_tower_pretap_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertAlmostEqual(1.0, proof.zoom, delta=0.02)
        for actual, expected in zip(proof.translation, (-534, -372), strict=True):
            self.assertLessEqual(abs(actual - expected), 4)
        self.assertTrue(
            {"tower_structure", "plaza_low", "barracks_roofs"}
            <= proof.matched_group_ids
        )
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_castle_structure_crops_alone_do_not_supply_independent_scene_proof(self) -> None:
        """Correlated Castle patches still require an independent region."""
        image = _fixture(_CAMERA_FIXTURES / "home_city_castle_holdout_20260921.png")
        image.paste((0, 0, 0), (100, 560, 540, 960))
        proof = _localizer().localize(image)

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_statue_and_base_cannot_supply_independent_scene_proof(self) -> None:
        """Real statue and plaza matches cannot pretend to be separate structures."""
        catalog = load_home_city_camera_catalog()
        catalog = replace(
            catalog,
            landmarks=tuple(
                item for item in catalog.landmarks
                if item.id in {"statue_wings", "plaza_ring", "p5_plaza_low", "t6_plaza_south"}
            ),
        )
        localizer = HomeCityCameraLocalizer(
            matcher=OpenCvTemplateMatcher(), catalog=catalog,
        )
        proof = localizer.localize(
            _fixture(_CAMERA_FIXTURES / "home_city_hud_occluded_20260916.png")
        )
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertGreaterEqual(len(proof.evidence), 3)
        self.assertIsNone(proof.translation)

    def test_tracked_panned_fixture_localizes_at_its_measured_translation(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "home_city_panned_core.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-822, -260), proof.translation)

    def test_bridge_t1_localizes_through_southern_corridor_landmarks(self) -> None:
        """The first live bridge pan lands on the measured corridor camera."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1009, -843), proof.translation)
        self.assertIn("blacksmith_structure", proof.matched_group_ids)
        self.assertIn("southern_courtyard", proof.matched_group_ids)

    def test_bridge_t2_localizes_through_eastern_landmarks(self) -> None:
        """The second live bridge pan lands on the eastern landmark groups."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_bridge_t2_20260916.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1423, -843), proof.translation)
        self.assertTrue({"east_fortification", "east_cliff"} <= proof.matched_group_ids)

    def test_campaign_post_pan_hud_occlusion_localizes_through_fixed_groups(self) -> None:
        """The HUD-covered eastern view keeps two independent fixed groups.

        East-fortification aqueduct/ridge-wall and the scene-fixed Campaign
        portal body survive the HUD occlusion. Alliance Hall also matches but
        is a player-chosen slot occupant: it corroborates the fitted transform
        as attached evidence without counting toward the qualifying groups.
        """
        localizer = _localizer()
        frame = localizer.prepare_frame(
            _fixture(_CAMERA_FIXTURES / "home_city_campaign_hud_occluded_20260916.png")
        )
        proof = localizer.localize(frame)
        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-1423, -485), proof.translation)
        self.assertEqual(1.0, proof.zoom)
        fixed_groups = {
            evidence.group_id
            for evidence in proof.evidence
            if evidence.landmark_id != "alliance_hall_structure"
        }
        self.assertTrue({"east_fortification", "campaign_portal"} <= fixed_groups)
        self.assertIn("alliance_hall_structure", proof.matched_group_ids)
        match = localizer.match_target(
            frame,
            localizer.catalog.target_for(HomeCityObjectId.CAMPAIGN),
            proof=proof,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual((395, 382), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))

    def test_campaign_view_localizes_at_the_globally_calibrated_translation(self) -> None:
        """The c45 portal view resolves through the bridge-calibrated eastern crops."""
        proof = _localizer().localize(_fixture(_CAMERA_FIXTURES / "home_city_campaign_portal_20260915.png"))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Accepted measurement is (-1882,-709); the 540x960 fixture rounds to (-1881,-710).
        self.assertEqual((-1881, -710), proof.translation)
        self.assertEqual(
            frozenset({"east_fortification", "east_cliff", "campaign_portal"}),
            proof.matched_group_ids,
        )

    def test_manor_view_localizes_through_its_structure_parts(self) -> None:
        """The PW02 Home frame localizes only once the Manor structure is authored."""
        proof = _localizer().localize(
            _fixture(
                _SCREEN_RECOGNITION
                / "building_routes"
                / "home_city_illusory_beast_manor_20260921.png"
            )
        )

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Accepted PW02 measurement; the same frame was INSUFFICIENT before the
        # two Manor regions were authored because no second group was present.
        self.assertEqual((-521, -1346), proof.translation)
        self.assertIn("illusory_beast_manor_structure", proof.matched_group_ids)

    def test_manor_masked_body_cannot_supply_independent_scene_proof(self) -> None:
        """Masking the Manor structure leaves two votes that cannot localize."""
        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        image.paste((0, 0, 0), (440, 630, 590, 760))
        proof = _localizer().localize(image)
        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)

    def test_manor_structure_alone_cannot_establish_the_camera(self) -> None:
        """The PW006 hopium_growth view keeps Manor plus Blacksmith insufficient.

        Both Manor landmarks score well but share one structure group, and the
        movable Blacksmith is excluded from independent votes, so the native
        RGBA frame publishes no translation or zoom.  This is the reviewed
        ``insufficient_independent_landmark_groups`` outcome; it must never be
        turned positive by lowering the group requirement.
        """
        proof = _localizer().localize(
            _fixture(_CAMERA_FIXTURES / "home_city_pw_manor_negative_20260922.png")
        )

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertIsNone(proof.translation)
        self.assertIsNone(proof.zoom)
        self.assertEqual(
            {"illusory_beast_manor_owl_head", "illusory_beast_manor_right_tower"},
            {item.landmark_id for item in proof.evidence},
        )
        self.assertEqual(
            frozenset({"illusory_beast_manor_structure"}),
            {item.group_id for item in proof.evidence},
        )

    def test_world_map_is_the_true_camera_negative(self) -> None:
        proof = _localizer().localize(_fixture(_SCREEN_RECOGNITION / "world_map_core.png"))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertIsNone(proof.translation)
        self.assertEqual("no_landmark_correspondences", proof.reason)

    def test_unsupported_aspect_returns_unsupported_not_a_guess(self) -> None:
        image = Image.new("RGB", (640, 960), (30, 40, 20))

        proof = _localizer().localize(image)

        self.assertEqual(HomeCityCameraStatus.UNSUPPORTED, proof.status)
        self.assertIsNone(proof.translation)
        self.assertEqual((640, 960), proof.frame_size)

    def test_projection_is_scale_normalized_into_frame_pixels(self) -> None:
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(540, 960),
        )

        # Castle nameplate anchor: atlas (991,625) + T -> reference (459,847)
        # -> 540x960 frame pixels (275,508).
        self.assertEqual((275, 508), proof.project_to_frame((991, 625)))
        # The same proof at the reference size projects without scaling.
        at_reference = replace(proof, frame_size=(900, 1600))
        self.assertEqual((459, 847), at_reference.project_to_frame((991, 625)))

    def test_projection_requires_localization(self) -> None:
        proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.INSUFFICIENT,
            reason="test",
            frame_size=(540, 960),
        )

        with self.assertRaises(SelectorResolutionError):
            proof.project_to_frame((991, 625))

    def test_proof_validation_rejects_inconsistent_transforms(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.LOCALIZED,
                reason="missing translation",
                frame_size=(540, 960),
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason="carries translation",
                translation=(0, 0),
                frame_size=(540, 960),
            )
        with self.assertRaises(SelectorResolutionError):
            HomeCityCameraProof(
                status=HomeCityCameraStatus.LOCALIZED,
                reason="missing zoom",
                translation=(-532, 222),
                frame_size=(540, 960),
            )


class HomeCityCameraConsensusTests(unittest.TestCase):
    """Consensus fitting must qualify independent groups and reject conflicts."""

    def test_no_correspondences_is_insufficient(self) -> None:
        localizer = _scripted_localizer({})

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("no_landmark_correspondences", proof.reason)

    def test_single_group_cannot_localize_even_with_three_votes(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_independent_landmark_groups", proof.reason)
        self.assertIsNone(proof.translation)

    def test_two_groups_with_too_few_votes_is_insufficient(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "t5_barracks_roofs": (10, -20),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.INSUFFICIENT, proof.status)
        self.assertEqual("insufficient_landmark_correspondences", proof.reason)

    def test_agreeing_groups_fit_the_consensus_translation(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (11, -20),
                "t5_barracks_roofs": (9, -21),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        # Consensus image translation (10,-20) plus the (-532,+222) atlas offset.
        self.assertEqual((-522, 202), proof.translation)
        self.assertEqual(5, len(proof.evidence))
        self.assertTrue(all(item.residual <= 3.0 for item in proof.evidence))

    def test_outlier_votes_do_not_pollute_the_consensus_cluster(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p3_institute_base_left": (10, -20),
                "p6_path_right": (10, -20),
                "p4_garden_terrace": (10, -19),
                "t5_barracks_roofs": (400, 500),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.LOCALIZED, proof.status)
        self.assertEqual((-522, 202), proof.translation)
        self.assertNotIn("t5_barracks_roofs", {item.landmark_id for item in proof.evidence})

    def test_two_qualifying_contradictory_clusters_are_ambiguous(self) -> None:
        localizer = _scripted_localizer(
            {
                "p2_institute_facade": (10, -20),
                "p4_garden_terrace": (10, -20),
                "t5_barracks_roofs": (10, -20),
                "p3_institute_base_left": (300, 400),
                "p6_path_right": (300, 400),
                "p5_plaza_low": (300, 400),
            }
        )

        proof = localizer.localize(Image.new("RGB", (900, 1600)))

        self.assertEqual(HomeCityCameraStatus.AMBIGUOUS, proof.status)
        self.assertIsNone(proof.translation)


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
        # No qualified target is visible, so nothing publishes a body or tap.
        self.assertFalse(localizer.matched_target_objects(prepared, proof=proof))

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


def _zoomed_fixture(image: Image.Image, zoom: float) -> Image.Image:
    """Re-renders a fixture's scene content at ``zoom`` around the viewport center.

    Scaling the content inside the same reference-size canvas mimics a game
    zoom change: scene positions become ``zoom * s + (1 - zoom) * center``
    while the matcher is exercised on genuinely resampled pixels.
    """

    base = image.resize(HOME_CITY_CAMERA_REFERENCE_SIZE, Image.Resampling.LANCZOS)
    scaled_size = (
        round(HOME_CITY_CAMERA_REFERENCE_SIZE[0] * zoom),
        round(HOME_CITY_CAMERA_REFERENCE_SIZE[1] * zoom),
    )
    scaled = base.resize(scaled_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", HOME_CITY_CAMERA_REFERENCE_SIZE, (0, 0, 0))
    canvas.paste(
        scaled,
        (
            (HOME_CITY_CAMERA_REFERENCE_SIZE[0] - scaled_size[0]) // 2,
            (HOME_CITY_CAMERA_REFERENCE_SIZE[1] - scaled_size[1]) // 2,
        ),
    )
    return canvas


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
        not match at scale 1.072. The independently qualified Goddess body
        remains visible without weakening the Institute match contract.
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
            [HomeCityObjectId.GODDESS_STATUE.value],
            [item.metadata["home_city_object_id"] for item in objects],
        )

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


class HomeCityCameraTargetTests(unittest.TestCase):
    """Body targets only publish when they agree with the localized projection."""

    def test_institute_body_matches_pan_view_with_verified_action_geometry(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.9)
        # The verified 07 tap (256,322) at 900x1600 scales to (154,193) at 540x960.
        self.assertEqual((154, 193), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_institute_body_matches_reference_and_mega_views(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)
        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _SCREEN_RECOGNITION / "home_city_panned_core.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
        ):
            with self.subTest(fixture=name.name):
                image = _fixture(name)
                frame = localizer.prepare_frame(image)
                proof = localizer.localize(frame)
                match = localizer.match_target(frame, target, proof=proof)
                self.assertIsNotNone(match)
                self.assertGreaterEqual(match.score, 0.9)

    def test_institute_body_rejects_when_projection_disagrees(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        frame = localizer.prepare_frame(image)
        target = catalog.target_for(HomeCityObjectId.INSTITUTE)

        # A contradictory camera hypothesis must not publish a body target.
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="contradictory hypothesis",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(900, 1600),
        )
        match = localizer.match_target(frame, target, proof=foreign_proof)

        self.assertIsNone(match)

    def test_tower_body_matches_only_its_qualified_view(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.TOWER_OF_TRIAL)

        image = _fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        # Verified tower tap (299,854) at 900x1600 scales to (179,512) at 540x960.
        self.assertEqual((179, 512), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, proof=other_proof)
                )

    def test_campaign_body_matches_portal_view_with_verified_action_geometry(self) -> None:
        """The portal body carries the verified c45 tap, not a label anchor."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        image = _fixture(_CAMERA_FIXTURES / "home_city_campaign_portal_20260915.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.93)
        # Verified Campaign tap (201,412) at 900x1600 scales to (121,247) at 540x960.
        self.assertEqual((121, 247), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_campaign_body_matches_bridge_view_above_the_safe_band(self) -> None:
        """The T2 bridge view matches the same body slightly above the tap band."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        image = _fixture(_CAMERA_FIXTURES / "home_city_bridge_t2_20260916.png")
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertGreaterEqual(match.score, 0.93)
        # Live-qualified point (660,278) at 900x1600 scales to (395,167) at 540x960;
        # 167 is above the HUD-safe minimum, so the route must pan before tapping.
        self.assertEqual((395, 167), match.action_point)

    def test_campaign_body_is_nonactionable_when_absent_or_unlocalized(self) -> None:
        """No body may be invented on views that cannot see the portal."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.CAMPAIGN)

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_tower_pan_28.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
            _CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, proof=other_proof)
                )

    def test_manor_body_matches_native_view_with_verified_action_geometry(self) -> None:
        """The Manor body carries the verified 17:52:15 body tap, not a label anchor."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        frame = localizer.prepare_frame(image)
        proof = localizer.localize(frame)
        match = localizer.match_target(frame, target, proof=proof)

        self.assertIsNotNone(match)
        self.assertLessEqual(match.projection_error, 8.0)
        self.assertGreaterEqual(match.score, 0.9)
        # The verified PW tap (511,722) is already at the native 900x1600 size.
        self.assertEqual((511, 722), match.action_point)
        self.assertTrue(match.action_bounds.contains_point(match.action_point))
        self.assertTrue(match.bounds.contains_bounds(match.action_bounds))

    def test_manor_body_rejects_when_projection_disagrees(self) -> None:
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        image = _fixture(
            _SCREEN_RECOGNITION
            / "building_routes"
            / "home_city_illusory_beast_manor_20260921.png"
        )
        frame = localizer.prepare_frame(image)
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        # A contradictory camera hypothesis must not publish a body target.
        foreign_proof = HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="contradictory hypothesis",
            translation=(-532, 222),
            zoom=1.0,
            frame_size=(900, 1600),
        )
        match = localizer.match_target(frame, target, proof=foreign_proof)

        self.assertIsNone(match)

    def test_manor_body_is_nonactionable_when_absent_or_unlocalized(self) -> None:
        """No Manor body may be invented on views that cannot see the structure."""
        localizer = _localizer()
        catalog = load_home_city_camera_catalog()
        target = catalog.target_for(HomeCityObjectId.ILLUSORY_BEAST_MANOR)

        for name in (
            _SCREEN_RECOGNITION / "home_city_core.png",
            _CAMERA_FIXTURES / "home_city_pan_07.png",
            _CAMERA_FIXTURES / "home_city_tower_pan_28.png",
            _CAMERA_FIXTURES / "home_city_mega_castle.png",
            _CAMERA_FIXTURES / "home_city_bridge_t1_20260916.png",
        ):
            with self.subTest(fixture=name.name):
                other = localizer.prepare_frame(_fixture(name))
                other_proof = localizer.localize(other)
                self.assertIsNone(
                    localizer.match_target(other, target, proof=other_proof)
                )


class HomeCityCameraSurfaceTests(unittest.TestCase):
    """The shared surface carries the proof and merges measured targets with OCR."""

    def test_surface_publishes_proof_and_template_objects_without_labels(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_tower_pan_28.png")

        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )

        self.assertIsNotNone(surface.camera_proof)
        self.assertTrue(surface.camera_proof.localized)
        objects = {
            home_city_object_id_from_metadata(item.metadata): item
            for item in surface.objects
        }
        tower = objects[HomeCityObjectId.TOWER_OF_TRIAL]
        institute = objects[HomeCityObjectId.INSTITUTE]
        for object_ in (tower, institute):
            self.assertEqual(SpatialObjectKind.HOME_BUILDING, object_.kind)
            self.assertEqual(SpatialObjectSourceKind.TEMPLATE, object_.source_kind)
            self.assertIsNotNone(object_.action_point)
            self.assertIsNotNone(object_.action_bounds)
            self.assertTrue(object_.action_bounds.contains_point(object_.action_point))
            self.assertEqual("camera_template", object_.metadata["detection_source"])
        self.assertEqual("Tower of Trial", tower.name_text)
        self.assertEqual("Institute", institute.name_text)

    def test_surface_without_camera_keeps_existing_ocr_objects(self) -> None:
        from tests.support.pnc.capture_vision.ocr_line import _ocr_line

        surface = build_home_city_spatial_surface(
            image=Image.new("RGB", (900, 1600), (74, 104, 34)),
            lines=(_ocr_line("Institute", x=400, y=900, width=120, height=24),),
            selector_registry=None,
        )

        self.assertIsNone(surface.camera_proof)
        institute = next(
            item
            for item in surface.objects
            if home_city_object_id_from_metadata(item.metadata) == HomeCityObjectId.INSTITUTE
        )
        self.assertEqual(SpatialObjectSourceKind.OCR, institute.source_kind)

    def test_camera_merge_preserves_ocr_label_and_level_on_the_measured_object(self) -> None:
        from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, SpatialObjectRelationship

        ocr_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(100, 100, 80, 60),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Insitute",
            level=12,
            action_point=(140, 130),
            metadata={"home_city_object_id": "institute", "home_city_label": "Insitute"},
        )
        camera_object = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(139, 185, 48, 45),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Institute",
            action_point=(154, 193),
            action_bounds=Bounds(146, 187, 18, 11),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": "institute", "detection_source": "camera_template"},
        )

        merged = merge_camera_target_objects((ocr_object,), (camera_object,))

        self.assertEqual(1, len(merged))
        merged_object = merged[0]
        self.assertEqual(SpatialObjectSourceKind.TEMPLATE, merged_object.source_kind)
        self.assertEqual(Bounds(139, 185, 48, 45), merged_object.bounds)
        self.assertEqual((154, 193), merged_object.action_point)
        self.assertEqual("Insitute", merged_object.name_text)
        self.assertEqual(12, merged_object.level)
        self.assertEqual("Insitute", merged_object.metadata["home_city_label"])

    def test_camera_merge_keeps_unmatched_objects_and_adds_new_targets(self) -> None:
        from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, SpatialObjectRelationship

        goddess = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(10, 10, 50, 40),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Goddess Statue",
            action_point=(35, 30),
            source_kind=SpatialObjectSourceKind.OCR,
            metadata={"home_city_object_id": "goddess_statue"},
        )
        tower = DetectedSpatialObject(
            kind=SpatialObjectKind.HOME_BUILDING,
            bounds=Bounds(144, 456, 78, 84),
            relationship=SpatialObjectRelationship.SELF,
            name_text="Tower of Trial",
            action_point=(179, 512),
            action_bounds=Bounds(163, 492, 34, 30),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": "tower_of_trial"},
        )

        merged = merge_camera_target_objects((goddess,), (tower,))

        self.assertEqual(2, len(merged))
        ids = [home_city_object_id_from_metadata(item.metadata) for item in merged]
        self.assertEqual(
            [HomeCityObjectId.GODDESS_STATUE, HomeCityObjectId.TOWER_OF_TRIAL], ids
        )

    def test_provenance_binding_stamps_and_rejects_contradictory_spatial_facts(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )
        frame_ref = _frame_ref("camera-proof")

        bound = bind_spatial_surface(
            surface,
            frame_ref=frame_ref,
            source_screen=ScreenType.PNC_HOME_CITY,
            source_layout_id="layout-a",
        )

        self.assertEqual(frame_ref, bound.camera_proof.frame_ref)
        self.assertEqual(ScreenType.PNC_HOME_CITY, bound.camera_proof.source_screen)
        self.assertEqual("layout-a", bound.camera_proof.source_layout_id)
        self.assertTrue(all(item.frame_ref == frame_ref for item in bound.objects))
        self.assertTrue(
            all(item.source_screen == ScreenType.PNC_HOME_CITY for item in bound.objects)
        )

        foreign = replace(
            bound,
            camera_proof=replace(bound.camera_proof, frame_ref=_frame_ref("stale")),
        )
        with self.assertRaises(SelectorResolutionError):
            bind_spatial_surface(
                foreign,
                frame_ref=frame_ref,
                source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id="layout-a",
            )

    def test_provenance_binding_rejects_wrong_screen_on_objects(self) -> None:
        image = _fixture(_CAMERA_FIXTURES / "home_city_pan_07.png")
        surface = build_home_city_spatial_surface(
            image=image,
            lines=(),
            selector_registry=None,
            camera=_localizer(),
        )
        bound = bind_spatial_surface(
            surface,
            frame_ref=_frame_ref("proof"),
            source_screen=ScreenType.PNC_HOME_CITY,
            source_layout_id="layout-a",
        )
        foreign = replace(
            bound,
            objects=(replace(bound.objects[0], source_screen=ScreenType.PNC_WORLD_MAP),)
            + bound.objects[1:],
        )
        with self.assertRaises(SelectorResolutionError):
            bind_spatial_surface(
                foreign,
                frame_ref=_frame_ref("proof"),
                source_screen=ScreenType.PNC_HOME_CITY,
                source_layout_id="layout-a",
            )


class _AnchorScriptedMatcher(_ZoomScriptedMatcher):
    """Matcher stub scripting anchor-template hits per evaluated scale.

    ``hits`` maps ``(template file name, template_scale)`` to the match a real
    resized-template search would return; matching the anchor spec's scale
    sweep therefore exercises the same correspondence, lane, viewport and HUD
    checks the production matcher feeds.
    """

    def __init__(self, hits: dict[tuple[str, float], TemplateMatch | None]) -> None:
        self._hits = hits

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        return self._hits.get((template_path.name, scale))


def _anchor_hit(
    center: tuple[float, float],
    *,
    scale: float = 1.0,
    size: tuple[int, int] = (170, 200),
    score: float = 0.95,
) -> TemplateMatch:
    """Builds a scaled patch match whose bounds stay centered on the scripted feature."""

    width = int(round(scale * size[0]))
    height = int(round(scale * size[1]))
    return TemplateMatch(
        bounds=Bounds(
            x=int(round(center[0] - width / 2)),
            y=int(round(center[1] - height / 2)),
            width=width,
            height=height,
        ),
        confidence=score,
    )


def _view_on_scripted_matcher(
    matcher: _ZoomScriptedMatcher,
    *,
    proof: HomeCityCameraProof | None = None,
) -> HomeCityViewEvidence:
    """Analyzes one scripted frame under a non-localized proof."""

    localizer = HomeCityCameraLocalizer(
        matcher=matcher,
        catalog=load_home_city_camera_catalog(),
    )
    image = Image.new("RGB", (900, 1600))
    camera_proof = proof or HomeCityCameraProof(
        status=HomeCityCameraStatus.INSUFFICIENT,
        reason="scripted view test",
        frame_size=(900, 1600),
    )
    return localizer.analyze_view(image, camera_proof=camera_proof)


class _PrepareCountingMatcher(OpenCvTemplateMatcher):
    """Matcher wrapper counting frame preparations for producer-once checks."""

    def __init__(self) -> None:
        super().__init__()
        self.prepare_frame_calls = 0

    def prepare_frame(self, image: Image.Image, *, reference_size=None):
        self.prepare_frame_calls += 1
        return super().prepare_frame(image, reference_size=reference_size)


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


if __name__ == "__main__":
    unittest.main()
