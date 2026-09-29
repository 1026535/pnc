"""Measured Home-city camera localization from reviewed scene landmarks.

One prepared frame at the atlas reference size is matched against a small
package-data landmark catalog.  At least three accepted correspondences from at
least two independent scene groups must agree on a single transform within
tolerance before a camera proof is published, and the agreeing reference
positions must span enough distance to separate camera zoom from translation.
Institute-correlated crops share one group so they cannot outvote
contradictory evidence, and HUD, nameplate, focus-pin, or promo material is
never part of the catalog.  Landmarks whose buildings occupy player-chosen
multi-type slots are marked movable: they may corroborate an established
transform but can never establish or contradict one, because their scene
position legitimately varies between accounts.

The atlas-to-reference offset is the accepted Castle / Infantry Barracks
calibration basis: measured reference nameplate centers (458, 847) and
(129, 1122) against catalog coordinates (991, 625) and (660, 899) resolve to
(-532, +222) within about one pixel.  The offset maps canonical atlas
coordinates into the authored reference view, so a landmark authored at
reference position ``p`` appears in the current frame's reference space at
``zoom * p + image_translation`` and an atlas point ``a`` projects to
``zoom * a + (zoom * offset + image_translation)``.
``HomeCityCameraProof.translation`` publishes that combined atlas-to-frame
value and ``HomeCityCameraProof.zoom`` publishes the measured relative zoom;
both come only from current-frame landmark geometry, never from guessing.

Localization evaluates a bounded grid of template-scale hypotheses on every
frame; every hypothesis is scored by the same consensus machinery,
contradictory qualifying transforms at any scale are rejected as ambiguous,
and the surviving cluster is refit by least squares so the published zoom is
the measured value rather than the grid step.  Correspondences are measured
between landmark and match bounds centers: the top-left of a match moves
with the evaluated template scale while its center stays on the physical
feature, so center geometry is the scale-invariant contract.

Body targets bound to player-chosen ordinary slots carry a typed reference
slot marking the calibrated pivot their crop was authored from.  Every
eligible slot's predicted body rectangle is derived by translating the
authored bounds by that candidate's pivot delta and projecting through the
localized transform; the OpenCV search is bounded to the predicted
neighborhood inside the frame, partially visible bodies are skipped, and a
measured hit that would claim the same physical body for two slots is
rejected as ambiguous rather than resolved by order.  Slot tags on the
published objects are current-frame observations only -- never static
occupancy, routes, or tap authorization.
"""

from __future__ import annotations

import json
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
    home_city_object_definition,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotEligibility,
    HomeCitySlotSelector,
    home_city_slots_for_object,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraEvidence,
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomAnchor,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialObjectSourceKind,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

HOME_CITY_CAMERA_REFERENCE_SIZE = (900, 1600)
HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET = (-532, 222)
_CAMERA_DATA_DIR = Path(__file__).resolve().parent / "data" / "home_city_camera"
_CAMERA_CONSENSUS_TOLERANCE_PX = 3
_CAMERA_MIN_MATCHES = 3
_CAMERA_MIN_GROUPS = 2
# Bounded relative-zoom hypotheses evaluated on every frame.  The endpoints
# are grid limits, not measured bounds: fitted zooms are constrained to this
# domain and an unresolved result is the honest answer for a camera outside
# it.
_CAMERA_ZOOM_SEARCH = tuple(round(0.70 + 0.05 * index, 2) for index in range(15))
_CAMERA_ZOOM_MIN = _CAMERA_ZOOM_SEARCH[0]
_CAMERA_ZOOM_MAX = _CAMERA_ZOOM_SEARCH[-1]
_CAMERA_ZOOM_FIT_SNAP = 0.02
_CAMERA_SCALE_SEPARATION_MIN_PX = 100.0
# Two qualifying hypotheses whose measured transforms differ beyond these
# tolerances are contradictory evidence rather than grid quantization.
_CAMERA_RIVAL_ZOOM_DELTA = 0.10
_CAMERA_RIVAL_TRANSLATION_PX = 10.0
# Bound on concurrent scale evaluations; each is read-only over the prepared
# frame and the lock-guarded matcher cache, so results stay deterministic.
_CAMERA_SWEEP_WORKERS = 8
_NORMALIZATION_FILE_NAME = "normalization.json"
# Qualifying anchor hits at different template scales must land on the same
# physical feature; a wider center gap means the views are non-corresponding
# placement evidence and publish no anchor.
_ANCHOR_CORRESPONDENCE_PX = 30.0


@dataclass(frozen=True, slots=True)
class HomeCityCameraLandmark:
    """One authored scene crop and its position in the reference view."""

    id: str
    group_id: str
    file_name: str
    reference_bounds: Bounds
    min_score: float
    movable: bool = False

    @property
    def reference_center(self) -> tuple[float, float]:
        """Returns the authored bounds midpoint -- the canonical correspondence point.

        Neighboring template scales produce differently sized matches of the
        same physical feature: the observed top-left shifts with the evaluated
        scale while the center stays anchored on the feature. Correspondences
        are therefore measured center-to-center; the authored bounds and the
        measured match bounds themselves are preserved for evidence and
        rendering.
        """

        return (
            self.reference_bounds.x + self.reference_bounds.width / 2,
            self.reference_bounds.y + self.reference_bounds.height / 2,
        )


@dataclass(frozen=True, slots=True)
class HomeCityCameraTarget:
    """One evidence-backed body crop with measured current-frame action geometry."""

    object_id: HomeCityObjectId
    landmark_id: str
    file_name: str
    reference_bounds: Bounds
    reference_action_bounds: Bounds
    reference_action_point: tuple[int, int]
    min_score: float
    max_projection_error: int
    reference_slot: HomeCitySlotSelector | None = None

    def __post_init__(self) -> None:
        """A slot-bound target must name a calibrated slot that can host its object."""

        if self.reference_slot is None:
            return
        if not isinstance(self.reference_slot, HomeCitySlotSelector):
            raise SelectorResolutionError(
                "Camera-target reference slots must use HomeCitySlotSelector or None.",
                landmark_id=self.landmark_id,
                reference_slot=self.reference_slot,
            )
        slot = self._eligible_slots().get(self.reference_slot.slot_index)
        if slot is None or slot.atlas_coordinate is None:
            raise SelectorResolutionError(
                "A camera target's reference slot must be a calibrated slot eligible for its object.",
                landmark_id=self.landmark_id,
                reference_slot=self.reference_slot.slot_index,
            )

    def _eligible_slots(self) -> dict[int, HomeCitySlotEligibility]:
        """Returns the calibrated ordinary slots eligible for this object."""

        return {
            slot.slot_index: slot
            for slot in home_city_slots_for_object(self.object_id)
        }

    def atlas_action_point(
        self, *, home_city_slot: HomeCitySlotSelector | None = None
    ) -> tuple[int, int]:
        """Returns the authored action point expressed in atlas coordinates.

        Fixed scene targets own exactly one atlas point and reject a slot
        argument.  A slot-bound target owns geometry authored at its
        calibrated reference slot: callers must pass the selected slot when
        the object can occupy more than one candidate, and the point is
        translated by that slot's pivot delta so a reference binding never
        masquerades as observed occupancy.  A single-type binding leaves the
        authored point unchanged.
        """

        offset_x, offset_y = HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET
        if self.reference_slot is None:
            if home_city_slot is not None:
                raise SelectorResolutionError(
                    "Fixed camera targets carry no slot identity.",
                    landmark_id=self.landmark_id,
                )
            return (
                self.reference_action_point[0] - offset_x,
                self.reference_action_point[1] - offset_y,
            )
        slots = self._eligible_slots()
        if home_city_slot is None:
            if len(slots) > 1:
                raise SelectorResolutionError(
                    "A movable camera target requires an explicit selected slot for atlas action geometry.",
                    landmark_id=self.landmark_id,
                )
            home_city_slot = self.reference_slot
        if not isinstance(home_city_slot, HomeCitySlotSelector):
            raise SelectorResolutionError(
                "Selected slots must use HomeCitySlotSelector.",
                landmark_id=self.landmark_id,
                home_city_slot=home_city_slot,
            )
        slot = slots.get(home_city_slot.slot_index)
        if slot is None or slot.atlas_coordinate is None:
            raise SelectorResolutionError(
                "The selected slot cannot host this camera target.",
                landmark_id=self.landmark_id,
                home_city_slot=home_city_slot.slot_index,
            )
        reference_pivot = slots[self.reference_slot.slot_index].atlas_coordinate
        pivot = slot.atlas_coordinate
        return (
            self.reference_action_point[0] - offset_x + pivot.x - reference_pivot.x,
            self.reference_action_point[1] - offset_y + pivot.y - reference_pivot.y,
        )


@dataclass(frozen=True, slots=True)
class HomeCityCameraTargetMatch:
    """One projection-agreed body match with its measured frame-space action geometry."""

    target: HomeCityCameraTarget
    bounds: Bounds
    action_bounds: Bounds
    action_point: tuple[int, int]
    score: float
    projection_error: float
    home_city_slot: HomeCitySlotSelector | None = None


@dataclass(frozen=True, slots=True)
class HomeCityZoomEndpointCalibration:
    """Qualified endpoint calibration measured from retained native captures.

    ``zoom_interval`` is the permitted relative-zoom band for the maximally
    zoomed-out Home view and ``non_endpoint_floor`` the lowest fitted zoom
    measured on a natively closer retained view.  A fit strictly between the
    two classes or outside the documented separation stays unresolved rather
    than choosing a side.
    """

    id: str
    reference_size: tuple[int, int]
    zoom_interval: tuple[float, float]
    non_endpoint_floor: float
    min_fixed_groups: int
    max_mean_residual_px: float
    native_sources: tuple[str, ...]
    holdout_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HomeCityZoomAnchorSpec:
    """One qualified native scenery patch containing a reviewed gesture point.

    ``file_name`` is a packaged native crop that contains the dispatch point
    a reviewed gesture touched; ``point_offset`` is that point inside the
    crop in template pixels.  A match at ``template_scale`` ``s`` publishes
    the match's own bounds and the point ``bounds.origin + s * point_offset``
    -- the pixels the published point sits on participated directly in the
    correlation, so no projection can drift the point off its qualified
    feature.  ``scales`` lists only the native template scales with saved
    positive and negative match evidence.
    """

    id: str
    file_name: str
    point_offset: tuple[int, int]
    scales: tuple[float, ...]
    min_score: float
    native_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HomeCityViewNormalization:
    """The packaged view calibration: endpoint verdict, anchors, HUD exclusion.

    ``native_frame_size`` is the authored capture-size boundary this
    calibration was measured on -- separate from the endpoint's atlas
    reference size.  Only native captures at exactly this size carry view
    calibration evidence; any other capture size publishes UNSUPPORTED and
    no anchor.
    """

    hud_exclusion_bounds: tuple[Bounds, ...]
    native_frame_size: tuple[int, int]
    endpoint: HomeCityZoomEndpointCalibration | None
    zoom_anchors: tuple[HomeCityZoomAnchorSpec, ...]


@dataclass(frozen=True, slots=True)
class HomeCityCameraCatalog:
    """Immutable package-data landmark and target definitions for the Home camera."""

    landmarks: tuple[HomeCityCameraLandmark, ...]
    targets: tuple[HomeCityCameraTarget, ...]
    reference_size: tuple[int, int]
    atlas_to_reference_offset: tuple[int, int]
    anchor_object_ids: tuple[HomeCityObjectId, ...]
    reference_source: str
    data_dir: Path
    normalization: HomeCityViewNormalization | None = None

    def template_path(self, file_name: str) -> Path:
        """Returns the resolved package-data path for one authored template."""

        return (self.data_dir / file_name).resolve()

    def target_for(self, object_id: HomeCityObjectId) -> HomeCityCameraTarget | None:
        """Returns the camera-qualified target spec for one canonical object id."""

        for target in self.targets:
            if target.object_id == object_id:
                return target
        return None


@dataclass(frozen=True, slots=True)
class _CameraVote:
    """One above-floor landmark correspondence before consensus fitting.

    ``observed`` is the matched bounds center in reference coordinates and
    ``translation`` the per-vote implied image translation at the evaluated
    ``zoom``; ``bounds`` retains the exact measured rectangle for evidence.
    """

    landmark: HomeCityCameraLandmark
    bounds: Bounds
    score: float
    observed: tuple[float, float]
    translation: tuple[float, float]
    zoom: float


@dataclass(frozen=True, slots=True)
class _CameraHypothesis:
    """One evaluated template scale with its surviving fitted transform."""

    evaluated_zoom: float
    zoom: float
    translation: tuple[float, float]
    votes: tuple[_CameraVote, ...]
    cluster: tuple[_CameraVote, ...]
    groups: frozenset[str]
    separation: float

    @property
    def qualified(self) -> bool:
        """Returns whether the cluster can establish a transform on its own.

        The fitted zoom must stay inside the searched domain: a cluster whose
        positions imply an out-of-domain zoom is honest unresolved evidence,
        not a usable camera measurement.
        """

        return (
            len(self.cluster) >= _CAMERA_MIN_MATCHES
            and len(self.groups) >= _CAMERA_MIN_GROUPS
            and self.separation >= _CAMERA_SCALE_SEPARATION_MIN_PX
            and _CAMERA_ZOOM_MIN <= self.zoom <= _CAMERA_ZOOM_MAX
        )


@lru_cache(maxsize=1)
def load_home_city_camera_catalog() -> HomeCityCameraCatalog:
    """Loads the reviewed landmark catalog once and validates every packaged crop."""

    institute_body_bounds = Bounds(700, 1240, 80, 75)
    tower_body_bounds = Bounds(240, 1620, 130, 140)
    campaign_body_bounds = Bounds(1480, 1306, 150, 70)
    manor_body_bounds = Bounds(441, 2210, 132, 112)
    catalog = HomeCityCameraCatalog(
        landmarks=(
            HomeCityCameraLandmark(
                id="p2_institute_facade",
                group_id="institute_structure",
                file_name="p2_institute_facade.png",
                reference_bounds=Bounds(615, 1185, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p3_institute_base_left",
                group_id="institute_structure",
                file_name="p3_institute_base_left.png",
                reference_bounds=Bounds(585, 1250, 105, 70),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p4_garden_terrace",
                group_id="garden_terrace",
                file_name="p4_garden_terrace.png",
                reference_bounds=Bounds(583, 1071, 90, 110),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p5_plaza_low",
                group_id="plaza_low",
                file_name="p5_plaza_low.png",
                reference_bounds=Bounds(610, 1345, 120, 45),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="t6_plaza_south",
                group_id="plaza_low",
                file_name="t6_plaza_south.png",
                reference_bounds=Bounds(540, 1340, 130, 50),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p6_path_right",
                group_id="institute_structure",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="t5_barracks_roofs",
                group_id="barracks_roofs",
                file_name="t5_barracks_roofs.png",
                reference_bounds=Bounds(121, 990, 140, 110),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="tower_of_trial_body",
                group_id="tower_structure",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="blacksmith_structure",
                group_id="blacksmith_structure",
                file_name="blacksmith_structure.png",
                reference_bounds=Bounds(640, 1845, 120, 130),
                min_score=0.90,
                # Blacksmith is a player-chosen occupant of large slots 11-13;
                # its scene position legitimately varies between accounts.
                movable=True,
            ),
            HomeCityCameraLandmark(
                id="southern_courtyard",
                group_id="southern_courtyard",
                file_name="southern_courtyard.png",
                reference_bounds=Bounds(640, 1530, 100, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="castle_fountain",
                group_id="castle_structure",
                file_name="castle_fountain.png",
                reference_bounds=Bounds(417, 875, 85, 70),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="castle_tower",
                group_id="castle_structure",
                file_name="castle_tower.png",
                reference_bounds=Bounds(543, 667, 62, 157),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="statue_wings",
                # The monument and its circular base are correlated parts of
                # the same plaza, not two independent camera landmarks.
                group_id="plaza_low",
                file_name="statue_wings.png",
                reference_bounds=Bounds(390, 1030, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="garden_west",
                group_id="courtyard_garden",
                file_name="garden_west.png",
                reference_bounds=Bounds(300, 1060, 90, 110),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="plaza_ring",
                group_id="plaza_low",
                file_name="plaza_ring.png",
                reference_bounds=Bounds(340, 1290, 60, 60),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_aqueduct",
                group_id="east_fortification",
                file_name="east_aqueduct.png",
                reference_bounds=Bounds(1451, 1505, 120, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_parapet",
                group_id="east_fortification",
                file_name="east_parapet.png",
                reference_bounds=Bounds(1651, 1715, 80, 60),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_cliff_rock",
                group_id="east_cliff",
                file_name="east_cliff_rock.png",
                reference_bounds=Bounds(1681, 1825, 80, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_rock_trees",
                group_id="east_cliff",
                file_name="east_rock_trees.png",
                reference_bounds=Bounds(1521, 1965, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="campaign_portal_body",
                group_id="campaign_portal",
                file_name="campaign_portal_body.png",
                reference_bounds=campaign_body_bounds,
                # The Campaign portal is a fixed scene structure, not a
                # player-chosen slot occupant; the independently measured
                # post-pan pedestal score (.92164) is documented in the
                # fixture manifest and home-camera-navigation.md.
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="campaign_left_pedestal",
                group_id="campaign_portal",
                file_name="campaign_left_pedestal.png",
                reference_bounds=Bounds(1371, 1222, 85, 135),
                # A second fixed region of the same Campaign structure: it
                # shares campaign_portal with the body, so the two crops are
                # one structure's correspondences and never independent
                # votes. Localization evidence only -- no target or tap.
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="ridge_wall",
                group_id="east_fortification",
                file_name="ridge_wall.png",
                reference_bounds=Bounds(1117, 1365, 100, 130),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="alliance_hall_structure",
                group_id="alliance_hall_structure",
                file_name="alliance_hall_structure.png",
                reference_bounds=Bounds(1197, 1675, 140, 80),
                min_score=0.90,
                # Alliance Hall is a player-chosen occupant of large slots
                # 11-13; its scene position legitimately varies between
                # accounts.
                movable=True,
            ),
            HomeCityCameraLandmark(
                id="west_trial_wall",
                group_id="tower_structure",
                file_name="west_trial_wall.png",
                reference_bounds=Bounds(110, 1875, 120, 140),
                min_score=0.95,
            ),
            HomeCityCameraLandmark(
                id="west_sanctum_column",
                group_id="sanctum_structure",
                file_name="west_sanctum_column.png",
                reference_bounds=Bounds(50, 2005, 80, 105),
                min_score=0.95,
            ),
            # Two non-overlapping fixed parts of the Illusory Beast Manor share
            # one group: they are one structure's identity correspondences and
            # cannot supply an independent consensus vote by themselves.
            HomeCityCameraLandmark(
                id="illusory_beast_manor_owl_head",
                group_id="illusory_beast_manor_structure",
                file_name="illusory_beast_manor_owl_head.png",
                reference_bounds=Bounds(441, 2210, 72, 53),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="illusory_beast_manor_right_tower",
                group_id="illusory_beast_manor_structure",
                file_name="illusory_beast_manor_right_tower.png",
                reference_bounds=Bounds(527, 2237, 46, 75),
                min_score=0.90,
            ),
            # Northeast coverage measured on 2026-09-23 157_farm frames: the
            # Sauroi Lair pier is one fixed structure group, and the two moat
            # fortification parts join east_fortification rather than voting
            # independently. All three exclude HUD, nameplates and badges.
            HomeCityCameraLandmark(
                id="northeast_sauroi_pier",
                group_id="sauroi_lair_structure",
                file_name="northeast_sauroi_pier.png",
                reference_bounds=Bounds(1361, 957, 90, 125),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="northeast_moat_cap",
                group_id="east_fortification",
                file_name="northeast_moat_cap.png",
                reference_bounds=Bounds(1246, 1112, 95, 115),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="northeast_moat_shaft",
                group_id="east_fortification",
                file_name="northeast_moat_shaft.png",
                reference_bounds=Bounds(1291, 1227, 70, 95),
                min_score=0.90,
            ),
        ),
        targets=(
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.INSTITUTE,
                landmark_id="p6_path_right",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                reference_action_bounds=Bounds(712, 1244, 30, 18),
                reference_action_point=(724, 1253),
                min_score=0.90,
                max_projection_error=8,
                # Authored at the static single-type slot 9: the binding tags
                # the observed slot without changing candidate behavior.
                reference_slot=HomeCitySlotSelector(9),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.TOWER_OF_TRIAL,
                landmark_id="tower_of_trial_body",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                reference_action_bounds=Bounds(272, 1680, 56, 50),
                reference_action_point=(299, 1714),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CAMPAIGN,
                landmark_id="campaign_portal_body",
                file_name="campaign_portal_body.png",
                reference_bounds=campaign_body_bounds,
                reference_action_bounds=Bounds(1540, 1332, 22, 22),
                reference_action_point=(1551, 1343),
                # The independent post-pan live body scores .922; retained
                # non-Home negatives stay below .40. Projection agreement and
                # independent camera consensus remain mandatory.
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BLACKSMITH,
                landmark_id="blacksmith_structure",
                file_name="blacksmith_structure.png",
                reference_bounds=Bounds(640, 1845, 120, 130),
                # Candidate action geometry measured inside the front
                # wall/door on the saved 157_farm f2 view (native 712,829);
                # it awaits live destination qualification and is not a
                # previously proved click.
                reference_action_bounds=Bounds(700, 1915, 20, 20),
                reference_action_point=(710, 1925),
                min_score=0.90,
                # 12 reference px covers the 6 px scene-calibration
                # uncertainty plus matching noise; failures are retained
                # rather than loosened without new evidence.
                max_projection_error=12,
                # The crop was authored while Blacksmith occupied slot 12 on
                # the reviewed 157_farm views; live candidates are all
                # eligible large slots (11-13) and the binding is evidence,
                # not a universal layout claim.
                reference_slot=HomeCitySlotSelector(12),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.ALLIANCE_HALL,
                landmark_id="alliance_hall_body",
                file_name="alliance_hall_body.png",
                # Native slot-13 body on 157_farm f5 (2026-09-22), with a
                # separate f6 capture as holdout. At zoom 1 and translation
                # (-1632,-718), this crops frame (106,610,162,180), below
                # the spire tips and above the nameplate. The floating
                # upgrade arrow/level badge lies outside the crop.
                reference_bounds=Bounds(1206, 1550, 162, 180),
                # Clear front-wall pixels at native (172,736), away from
                # flags, help/upgrade controls and nameplate. This is a
                # measured body candidate, not live collider qualification.
                reference_action_bounds=Bounds(1262, 1666, 20, 20),
                reference_action_point=(1272, 1676),
                min_score=0.90,
                max_projection_error=12,
                # Reference geometry only: eligibility is 11/12/13 and
                # matching must establish the current same-type occupant.
                # The movable landmark cannot vote for camera pose.
                reference_slot=HomeCitySlotSelector(13),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.ILLUSORY_BEAST_MANOR,
                landmark_id="illusory_beast_manor_body",
                file_name="illusory_beast_manor_body.png",
                reference_bounds=manor_body_bounds,
                reference_action_bounds=Bounds(490, 2280, 20, 20),
                reference_action_point=(500, 2290),
                # The 2026-09-21 verified tap (511,722) relative to the matched
                # body scores .918-.931 on three independent PW captures;
                # non-overlapping rivals stay below .65 and the generic Manor
                # is never selected. The body is one identity correspondence,
                # not an additional independent landmark vote.
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.WALL,
                landmark_id="wall_gatehouse",
                file_name="wall_gatehouse.png",
                reference_bounds=Bounds(1180, 1845, 95, 125),
                reference_action_bounds=Bounds(1205, 1907, 32, 32),
                reference_action_point=(1221, 1923),
                min_score=0.90,
                max_projection_error=12,
                reference_slot=HomeCitySlotSelector(2),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.GODDESS_STATUE,
                landmark_id="goddess_statue_body",
                file_name="goddess_statue_body.png",
                # The body is the static gold statue column/plinth measured on
                # the 2026-09-23 live005 frame 0066 (native 368,145,60,78 under
                # camera (-595,-847)); the earlier circular platform trim was
                # never a proved clickable body. The crop excludes the upper
                # HUD, the mutable level badge at the statue's right edge, the
                # floating nameplate, and the platform ring below.
                reference_bounds=Bounds(431, 1214, 60, 78),
                # Keep the candidate tap on the interior gold column body.
                reference_action_bounds=Bounds(451, 1259, 20, 20),
                reference_action_point=(461, 1269),
                min_score=0.90,
                max_projection_error=12,
                reference_slot=HomeCitySlotSelector(15),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CASTLE,
                landmark_id="castle_tower",
                file_name="castle_tower.png",
                reference_bounds=Bounds(543, 667, 62, 157),
                # Interior stonework on the two native Castle views from
                # 2026-09-21; destination qualification remains a live gate.
                reference_action_bounds=Bounds(560, 742, 28, 24),
                reference_action_point=(574, 754),
                min_score=0.90,
                max_projection_error=8,
                reference_slot=HomeCitySlotSelector(1),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.WAREHOUSE,
                landmark_id="warehouse_body",
                file_name="warehouse_body.png",
                reference_bounds=Bounds(902, 1050, 112, 138),
                # The L-shaped keep plus courtyard measured on the 2026-09-29
                # turn006 post-pan frame 0047 (native 282,667,83,102 under
                # camera (-777,55) at zoom ~0.739); the independent 0084
                # survey view scores .957. The crop excludes the nameplate,
                # level badge and the sidebar-occluded edge.
                reference_action_bounds=Bounds(956, 1108, 22, 22),
                reference_action_point=(967, 1119),
                min_score=0.90,
                # 12 reference px covers scene-calibration uncertainty plus
                # matching noise; the same skin republishes at slot 3 on
                # other castles, which is correct slot-3-only evidence.
                max_projection_error=12,
                # Warehouse is the single occupant type slot 3 allows; the
                # binding tags the authored slot without narrowing
                # candidate behavior beyond its reviewed eligibility.
                reference_slot=HomeCitySlotSelector(3),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.BANK,
                landmark_id="bank_body",
                file_name="bank_body.png",
                reference_bounds=Bounds(-212, 1543, 160, 129),
                # Golden facade and blue dome under the fixed sys_1/5001
                # marker, measured on the 2026-09-29 attempt1 baseline frame
                # 0022 (native 216,1036,120,97 under camera (-24,45) at zoom
                # 0.75); the independent 0092 survey view scores .972. The
                # crop starts below the floating '!' badge pointer and
                # excludes the nameplate. The node projects outside the
                # canonical reference window but matching is frame-space.
                reference_action_bounds=Bounds(-144, 1578, 22, 22),
                reference_action_point=(-133, 1589),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.INFANTRY_BARRACKS,
                landmark_id="infantry_barracks_body",
                file_name="infantry_barracks_body.png",
                # White facade between the red columns under the front
                # watchtower, measured on the 2026-09-29 attempt1 baseline
                # frame 0022 (native 415,625,83,78 under camera (-24,45) at
                # zoom 0.75) with a readable 'Infantry Barracks' nameplate;
                # the independent 0092 survey view measures the same body at
                # (287,559,83,78) and the zoom-1.0 f0 baseline at
                # (53,995,111,104). The crop excludes the floating coin
                # bubble and pennant above, the gold 'Z' marker and level
                # badge at the right, and the nameplate below.
                reference_bounds=Bounds(53, 995, 111, 104),
                # Interior parapet point clear of all floating controls on
                # both saved views; destination qualification remains a live
                # gate since collider routing is not proven by a body match.
                reference_action_bounds=Bounds(89, 1038, 22, 22),
                reference_action_point=(100, 1049),
                min_score=0.90,
                # 12 reference px covers the scene-calibration uncertainty
                # plus matching noise, matching the slot-bound convention.
                max_projection_error=12,
                # Slot 5 is the single-type infantry slot (client 1020); the
                # binding tags the authored slot's reviewed eligibility.
                reference_slot=HomeCitySlotSelector(5),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CAVALRY_BARRACKS,
                landmark_id="cavalry_barracks_body",
                file_name="cavalry_barracks_body.png",
                # Blue awning and tower under the radar dome, measured on the
                # 2026-09-29 attempt1 baseline frame 0022 (native
                # 252,690,100,42 under camera (-24,45) at zoom 0.75); the
                # independent 0092 survey view measures the same body at
                # (124,624,100,42) and carries the readable 'Cavalry
                # Barracks' nameplate that corroborates the slot-6 body.
                # The crop excludes the floating 'Z' marker grazing its
                # upper-right and the statue/nameplate below the awning.
                reference_bounds=Bounds(-164, 1082, 133, 56),
                # Interior awning point clear of floating controls on both
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(-101, 1114, 22, 22),
                reference_action_point=(-90, 1125),
                min_score=0.90,
                max_projection_error=12,
                # Slot 6 is the single-type cavalry slot (client 1021).
                reference_slot=HomeCitySlotSelector(6),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.RANGED_BARRACKS,
                landmark_id="ranged_barracks_body",
                file_name="ranged_barracks_body.png",
                # Gong, towers and platform band, measured on the 2026-09-29
                # attempt1 baseline frame 0022 (native 390,800,120,34 under
                # camera (-24,45) at zoom 0.75) with a readable 'Ranged
                # Barracks' nameplate; the independent 0092 survey view
                # measures the same body at (262,734,120,34). The crop
                # excludes the '6' badge above, the red '0' badges and 'Z'
                # marker at the right, and the nameplate below.
                reference_bounds=Bounds(20, 1229, 160, 45),
                # Interior platform point clear of floating controls on both
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(82, 1242, 22, 22),
                reference_action_point=(93, 1253),
                min_score=0.90,
                max_projection_error=12,
                # Slot 7 is the single-type ranged slot (client 1022).
                reference_slot=HomeCitySlotSelector(7),
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.SIEGE_FACTORY,
                landmark_id="siege_factory_body",
                file_name="siege_factory_body.png",
                # Factory front wall between the blue-topped towers, measured
                # on the 2026-09-29 attempt1 baseline frame 0022 (native
                # 212,806,72,84 under camera (-24,45) at zoom 0.75) with a
                # readable 'Siege Factory' nameplate; the independent 0092
                # survey view measures the same body at (84,740,72,84), where
                # the action point projects inside the declared left-HUD
                # exclusion band. The crop excludes the floating 'Z' marker
                # at its upper-right and the cavalry nameplate above.
                reference_bounds=Bounds(-217, 1237, 96, 112),
                # Interior wall point clear of floating controls on the
                # saved views; destination qualification remains a live gate.
                reference_action_bounds=Bounds(-184, 1291, 22, 22),
                reference_action_point=(-173, 1302),
                min_score=0.90,
                max_projection_error=12,
                # Slot 8 is the single-type siege slot (client 1023).
                reference_slot=HomeCitySlotSelector(8),
            ),
        ),
        reference_size=HOME_CITY_CAMERA_REFERENCE_SIZE,
        atlas_to_reference_offset=HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
        anchor_object_ids=(
            HomeCityObjectId.CASTLE,
            HomeCityObjectId.INFANTRY_BARRACKS,
        ),
        reference_source=(
            "20260915T160615Z_core_20260915T160413Z_018f500d_0025_06_fresh_fresh_home_for_pan.png"
        ),
        data_dir=_CAMERA_DATA_DIR,
    )
    for item in (*catalog.landmarks, *catalog.targets):
        path = catalog.template_path(item.file_name)
        if not path.is_file():
            raise SelectorResolutionError(
                "Home-camera catalog template is missing from package data.",
                template=str(path),
            )
        with Image.open(path) as template:
            if template.size != (item.reference_bounds.width, item.reference_bounds.height):
                raise SelectorResolutionError(
                    "Home-camera catalog template size does not match its reference bounds.",
                    template=str(path),
                    expected=(item.reference_bounds.width, item.reference_bounds.height),
                    actual=template.size,
                )
    for target in catalog.targets:
        if not target.reference_bounds.contains_bounds(target.reference_action_bounds):
            raise SelectorResolutionError(
                "Camera target action bounds must stay inside the authored body crop.",
                landmark_id=target.landmark_id,
            )
        if not target.reference_action_bounds.contains_point(target.reference_action_point):
            raise SelectorResolutionError(
                "Camera target action bounds must contain the verified action point.",
                landmark_id=target.landmark_id,
            )
    return replace(catalog, normalization=_load_view_normalization(catalog))


def _load_view_normalization(
    catalog: HomeCityCameraCatalog,
) -> HomeCityViewNormalization:
    """Loads and validates the packaged endpoint/anchor view calibration."""

    path = catalog.data_dir / _NORMALIZATION_FILE_NAME
    if not path.is_file():
        raise SelectorResolutionError(
            "Home-camera view normalization calibration is missing from package data.",
            template=str(path),
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SelectorResolutionError(
            "Home-camera view normalization calibration is not valid JSON.",
            template=str(path),
        ) from error
    if not isinstance(document, dict):
        raise SelectorResolutionError(
            "Home-camera view normalization calibration must be a JSON object.",
            template=str(path),
        )
    if document.get("version") != 1:
        raise SelectorResolutionError(
            "Home-camera view normalization calibration must declare version 1.",
            template=str(path),
            version=document.get("version"),
        )
    endpoint = _normalization_endpoint(document.get("endpoint"), catalog)
    native_frame_size = document.get("native_frame_size")
    if (
        not isinstance(native_frame_size, list | tuple)
        or len(native_frame_size) != 2
        or any(
            type(value) is not int or value <= 0 for value in native_frame_size
        )
    ):
        raise SelectorResolutionError(
            "Home-camera view normalization must declare a positive native frame size.",
            entry=native_frame_size,
        )
    return HomeCityViewNormalization(
        hud_exclusion_bounds=tuple(
            _normalization_bounds(item, field="hud_exclusion_bounds")
            for item in document.get("hud_exclusion_bounds", ())
        ),
        native_frame_size=(native_frame_size[0], native_frame_size[1]),
        endpoint=endpoint,
        zoom_anchors=tuple(
            _normalization_anchor(item, catalog)
            for item in document.get("zoom_anchors", ())
        ),
    )


def _normalization_bounds(entry: object, *, field: str) -> Bounds:
    """Coerces one ``[x, y, w, h]`` authored rectangle into typed bounds."""

    if (
        not isinstance(entry, list | tuple)
        or len(entry) != 4
        or any(type(value) is not int for value in entry)
    ):
        raise SelectorResolutionError(
            "Home-camera view normalization bounds must be four integers.",
            field=field,
            entry=entry,
        )
    bounds = Bounds(*entry)
    if bounds.width <= 0 or bounds.height <= 0:
        raise SelectorResolutionError(
            "Home-camera view normalization bounds must have positive size.",
            field=field,
            entry=entry,
        )
    return bounds


def _normalization_endpoint(
    entry: object,
    catalog: HomeCityCameraCatalog,
) -> HomeCityZoomEndpointCalibration | None:
    """Parses the authored endpoint calibration against the catalog layout."""

    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must be a JSON object.",
            entry=entry,
        )
    endpoint_id = entry.get("id")
    reference_size = entry.get("reference_size")
    zoom_interval = entry.get("zoom_interval")
    non_endpoint_floor = entry.get("non_endpoint_floor")
    min_fixed_groups = entry.get("min_fixed_groups")
    max_mean_residual = entry.get("max_mean_residual_px")
    if not isinstance(endpoint_id, str) or endpoint_id == "":
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must name a stable calibration id.",
            entry=entry,
        )
    if (
        not isinstance(reference_size, list | tuple)
        or len(reference_size) != 2
        or any(type(value) is not int or value <= 0 for value in reference_size)
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare a supported reference size.",
            entry=entry,
        )
    if tuple(reference_size) != tuple(catalog.reference_size):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration's reference size must match the catalog layout.",
            entry=entry,
            reference_size=catalog.reference_size,
        )
    if (
        not isinstance(zoom_interval, list | tuple)
        or len(zoom_interval) != 2
        or any(
            not isinstance(value, int | float) or not math.isfinite(value)
            for value in zoom_interval
        )
        or not 0.0 < zoom_interval[0] < zoom_interval[1]
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare an increasing positive zoom interval.",
            entry=entry,
        )
    if (
        not isinstance(non_endpoint_floor, int | float)
        or not math.isfinite(non_endpoint_floor)
        or non_endpoint_floor <= zoom_interval[1]
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration's non-endpoint floor must exceed its interval.",
            entry=entry,
        )
    if type(min_fixed_groups) is not int or min_fixed_groups < 1:
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must require at least one independent group.",
            entry=entry,
        )
    if (
        not isinstance(max_mean_residual, int | float)
        or not math.isfinite(max_mean_residual)
        or max_mean_residual <= 0.0
    ):
        raise SelectorResolutionError(
            "The Home-camera endpoint calibration must declare a positive residual bound.",
            entry=entry,
        )
    return HomeCityZoomEndpointCalibration(
        id=endpoint_id,
        reference_size=(reference_size[0], reference_size[1]),
        zoom_interval=(float(zoom_interval[0]), float(zoom_interval[1])),
        non_endpoint_floor=float(non_endpoint_floor),
        min_fixed_groups=min_fixed_groups,
        max_mean_residual_px=float(max_mean_residual),
        native_sources=_normalization_sources(entry.get("native_sources")),
        holdout_sources=_normalization_sources(entry.get("holdout_sources")),
    )


def _normalization_sources(entry: object) -> tuple[str, ...]:
    """Coerces one authored source-capture list into provenance strings."""

    if not isinstance(entry, list | tuple):
        return ()
    if any(not isinstance(item, str) or item == "" for item in entry):
        raise SelectorResolutionError(
            "Home-camera view normalization sources must be non-empty names.",
            entry=entry,
        )
    return tuple(entry)


def _normalization_anchor(
    entry: object,
    catalog: HomeCityCameraCatalog,
) -> HomeCityZoomAnchorSpec:
    """Parses one authored native scenery patch plus its contained point."""

    if not isinstance(entry, dict):
        raise SelectorResolutionError(
            "A Home-camera zoom-anchor spec must be a JSON object.",
            entry=entry,
        )
    anchor_id = entry.get("id")
    file_name = entry.get("file_name")
    point_offset = entry.get("point_offset")
    scales = entry.get("scales")
    min_score = entry.get("min_score")
    if not isinstance(anchor_id, str) or anchor_id == "":
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must name a stable qualification id.",
            entry=entry,
        )
    if not isinstance(file_name, str) or not catalog.template_path(file_name).is_file():
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must name a packaged template crop.",
            entry=entry,
            template=file_name,
        )
    if (
        not isinstance(point_offset, list | tuple)
        or len(point_offset) != 2
        or any(type(value) is not int or value < 0 for value in point_offset)
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor's point must be a non-negative integer offset inside its crop.",
            entry=entry,
        )
    with Image.open(catalog.template_path(file_name)) as template:
        template_size = template.size
    if not (
        point_offset[0] < template_size[0]
        and point_offset[1] < template_size[1]
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor's point must lie inside its packaged crop.",
            entry=entry,
            template_size=template_size,
        )
    if (
        not isinstance(scales, list | tuple)
        or not scales
        or any(
            not isinstance(value, int | float)
            or not math.isfinite(value)
            or value <= 0.0
            for value in scales
        )
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must declare non-empty positive template scales.",
            entry=entry,
        )
    if (
        not isinstance(min_score, int | float)
        or not math.isfinite(min_score)
        or not 0.0 < min_score <= 1.0
    ):
        raise SelectorResolutionError(
            "A Home-camera zoom anchor must declare a match floor in (0, 1].",
            entry=entry,
        )
    return HomeCityZoomAnchorSpec(
        id=anchor_id,
        file_name=file_name,
        point_offset=(point_offset[0], point_offset[1]),
        scales=tuple(float(value) for value in scales),
        min_score=float(min_score),
        native_sources=_normalization_sources(entry.get("native_sources")),
    )


def home_city_camera_target(object_id: HomeCityObjectId) -> HomeCityCameraTarget | None:
    """Returns the camera-qualified target spec for one canonical object id."""

    return load_home_city_camera_catalog().target_for(object_id)


class HomeCityCameraLocalizer:
    """Matches the shared scene-landmark catalog on one prepared frame per call."""

    def __init__(
        self,
        *,
        matcher: OpenCvTemplateMatcher,
        catalog: HomeCityCameraCatalog | None = None,
        zoom_search: tuple[float, ...] | None = None,
    ) -> None:
        self._matcher = matcher
        self._catalog = catalog if catalog is not None else load_home_city_camera_catalog()
        self._zoom_search = _CAMERA_ZOOM_SEARCH if zoom_search is None else zoom_search
        if (
            not self._zoom_search
            or any(
                not math.isfinite(zoom) or zoom <= 0.0 for zoom in self._zoom_search
            )
        ):
            raise ValueError("zoom_search must be a non-empty tuple of finite positive scales")

    @property
    def catalog(self) -> HomeCityCameraCatalog:
        """Returns the loaded landmark/target catalog."""

        return self._catalog

    def prepare_frame(self, image: Image.Image) -> PreparedFrame | None:
        """Normalizes one screenshot at the atlas reference size, or None when unsupported."""

        return self._matcher.prepare_frame(
            image,
            reference_size=self._catalog.reference_size,
        )

    def localize(self, image: Image.Image | PreparedFrame) -> HomeCityCameraProof:
        """Publishes the current-frame camera verdict from scene correspondences only."""

        frame = self._coerce_frame(image)
        frame_size = frame.original_size if frame is not None else image.size
        if frame is None:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.UNSUPPORTED,
                reason="unsupported_frame_layout",
                frame_size=frame_size,
            )
        # One half-resolution proposal frame serves every scale hypothesis of
        # this localization; it is immutable prepared data, not matcher state.
        proposal_frame = self._matcher.prepare_proposal_frame(frame)
        hypotheses = self._evaluate_zoom_sweep(frame, proposal_frame)
        qualifying = [
            hypothesis for hypothesis in hypotheses if hypothesis.qualified
        ]
        if not qualifying:
            for hypothesis in hypotheses:
                if self._is_ambiguous(hypothesis):
                    return self._ambiguous(
                        "conflicting_landmark_clusters", hypothesis, frame_size
                    )
            return self._insufficient(hypotheses, frame_size)
        winner = max(
            qualifying,
            key=lambda hypothesis: (
                len(hypothesis.cluster),
                len(hypothesis.groups),
                sum(vote.score for vote in hypothesis.cluster),
            ),
        )
        for index, first in enumerate(qualifying):
            for second in qualifying[index + 1 :]:
                if self._contradicts(first, second):
                    return self._ambiguous(
                        "conflicting_zoom_hypotheses", winner, frame_size
                    )
        for hypothesis in hypotheses:
            if self._rival_cluster(hypothesis, reference=winner) is not None:
                return self._ambiguous(
                    "conflicting_landmark_clusters", winner, frame_size
                )
        return self._publish(frame, winner, frame_size, proposal_frame)

    def analyze_view(
        self,
        image: Image.Image | PreparedFrame,
        *,
        camera_proof: HomeCityCameraProof,
    ) -> HomeCityViewEvidence:
        """Publishes the current view's measured zoom class plus qualified anchor.

        The zoom verdict consumes the camera proof this frame already
        produced: a localized proof's fixed-landmark correspondences are refit
        without the published grid snap so the verdict answers the scene's
        true measured scale.  Anchor recognition runs on the frame's own
        pixels independently of that pose, so an anchor can publish on a view
        whose camera is still unresolved and a localized view can carry no
        anchor.  Both verdicts apply only to captures at the calibration's
        authored native frame size -- a resized or otherwise unqualified
        capture publishes UNSUPPORTED and no anchor, though the enclosing
        camera proof still localizes and measures bodies normally.
        """

        frame = self._coerce_frame(image)
        if frame is None:
            return HomeCityViewEvidence(
                zoom_status=HomeCityZoomStatus.UNSUPPORTED,
                reason="unsupported_frame_layout",
                calibration_id=None,
                zoom_anchor=None,
                frame_size=image.size,
            )
        if (
            camera_proof.frame_size is not None
            and tuple(camera_proof.frame_size) != tuple(frame.original_size)
        ):
            raise SelectorResolutionError(
                "Home view evidence requires the camera proof produced on the same frame.",
                proof_frame_size=camera_proof.frame_size,
                frame_size=frame.original_size,
            )
        if tuple(camera_proof.reference_size) != tuple(frame.reference_size):
            raise SelectorResolutionError(
                "Home view evidence requires a camera proof at the catalog reference size.",
                proof_reference_size=camera_proof.reference_size,
                reference_size=frame.reference_size,
            )
        normalization = self._catalog.normalization
        if (
            normalization is not None
            and tuple(frame.original_size) != tuple(normalization.native_frame_size)
        ):
            endpoint_id = (
                normalization.endpoint.id
                if normalization.endpoint is not None
                else None
            )
            return HomeCityViewEvidence(
                zoom_status=HomeCityZoomStatus.UNSUPPORTED,
                reason="unsupported_capture_size",
                calibration_id=endpoint_id,
                zoom_anchor=None,
                frame_size=frame.original_size,
            )
        zoom_status, reason, calibration_id = self._classify_zoom(camera_proof)
        return HomeCityViewEvidence(
            zoom_status=zoom_status,
            reason=reason,
            calibration_id=calibration_id,
            zoom_anchor=self._match_zoom_anchor(frame),
            frame_size=frame.original_size,
        )

    def _evaluate_zoom_sweep(
        self, frame: PreparedFrame, proposal_frame: PreparedFrame
    ) -> list[_CameraHypothesis]:
        """Evaluates every configured scale, bounded workers when sweeping.

        Fixed-landmark evaluation is read-only over the immutable prepared
        frames and the lock-guarded matcher caches, so concurrent evaluation
        is deterministic; results stay in configured grid order.
        """

        zoom_search = self._zoom_search
        if len(zoom_search) == 1:
            return [self._evaluate_zoom(frame, proposal_frame, zoom_search[0])]
        with ThreadPoolExecutor(
            max_workers=min(_CAMERA_SWEEP_WORKERS, len(zoom_search)),
            thread_name_prefix="home-camera-zoom",
        ) as pool:
            futures = [
                pool.submit(self._evaluate_zoom, frame, proposal_frame, zoom)
                for zoom in zoom_search
            ]
            return [future.result() for future in futures]

    def _evaluate_zoom(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        zoom: float,
    ) -> _CameraHypothesis:
        """Evaluates one template scale over fixed landmarks only.

        Movable landmarks are excluded because their buildings occupy
        player-chosen slots: their scene position legitimately varies between
        accounts, so they can neither establish nor contradict a transform.
        Matched positions carry the scene's true scale, so the surviving
        cluster is refit rather than quantized to the evaluated grid value.
        """

        votes = self._collect_votes(
            frame,
            proposal_frame,
            zoom=zoom,
            landmarks=tuple(
                landmark for landmark in self._catalog.landmarks if not landmark.movable
            ),
        )
        cluster, fitted_zoom, translation = self._best_fit_cluster(
            votes, evaluated_zoom=zoom
        )
        return _CameraHypothesis(
            evaluated_zoom=zoom,
            zoom=fitted_zoom,
            translation=translation,
            votes=votes,
            cluster=cluster,
            groups=frozenset(vote.landmark.group_id for vote in cluster),
            separation=self._cluster_separation(cluster),
        )

    def _best_fit_cluster(
        self,
        votes: tuple[_CameraVote, ...],
        *,
        evaluated_zoom: float,
    ) -> tuple[tuple[_CameraVote, ...], float, tuple[float, float]]:
        """Selects the strongest transform-consistent cluster over the votes.

        Every vote seeds the translation-only candidate at the evaluated
        scale, and every sufficiently separated vote pair seeds the similarity
        transform its positions imply; the winner is refit by least squares
        and snapped back to the evaluated scale only inside the snap
        tolerance.
        """

        seeds: list[tuple[float, tuple[float, float]]] = [
            (evaluated_zoom, vote.translation) for vote in votes
        ]
        for index, first in enumerate(votes):
            for second in votes[index + 1 :]:
                delta_px = (
                    second.landmark.reference_center[0]
                    - first.landmark.reference_center[0]
                )
                delta_py = (
                    second.landmark.reference_center[1]
                    - first.landmark.reference_center[1]
                )
                span_squared = delta_px * delta_px + delta_py * delta_py
                if span_squared < _CAMERA_SCALE_SEPARATION_MIN_PX**2:
                    continue
                delta_qx = second.observed[0] - first.observed[0]
                delta_qy = second.observed[1] - first.observed[1]
                seed_zoom = (delta_qx * delta_px + delta_qy * delta_py) / span_squared
                if (
                    not math.isfinite(seed_zoom)
                    or not _CAMERA_ZOOM_MIN <= seed_zoom <= _CAMERA_ZOOM_MAX
                ):
                    continue
                seeds.append(
                    (
                        seed_zoom,
                        (
                            (first.observed[0] + second.observed[0]) / 2
                            - seed_zoom
                            * (
                                first.landmark.reference_center[0]
                                + second.landmark.reference_center[0]
                            )
                            / 2,
                            (first.observed[1] + second.observed[1]) / 2
                            - seed_zoom
                            * (
                                first.landmark.reference_center[1]
                                + second.landmark.reference_center[1]
                            )
                            / 2,
                        ),
                    )
                )
        best_key: tuple[int, int, float] | None = None
        best: tuple[_CameraVote, ...] = ()
        for seed_zoom, seed_translation in seeds:
            members = tuple(
                vote
                for vote in votes
                if self._residual(vote, seed_zoom, seed_translation)
                <= _CAMERA_CONSENSUS_TOLERANCE_PX
            )
            groups = frozenset(vote.landmark.group_id for vote in members)
            key = (
                len(members),
                len(groups),
                sum(vote.score for vote in members),
            )
            if best_key is None or key > best_key:
                best_key = key
                best = members
        if not best:
            return (), evaluated_zoom, (0.0, 0.0)
        fitted_zoom, fitted_translation = self._fit_transform(best)
        if abs(fitted_zoom - evaluated_zoom) <= _CAMERA_ZOOM_FIT_SNAP:
            fitted_zoom = evaluated_zoom
            fitted_translation = self._consensus_translation(best, zoom=fitted_zoom)
        inliers = tuple(
            vote
            for vote in best
            if self._residual(vote, fitted_zoom, fitted_translation)
            <= _CAMERA_CONSENSUS_TOLERANCE_PX
        )
        return inliers, fitted_zoom, fitted_translation

    def _residual(
        self,
        vote: _CameraVote,
        zoom: float,
        translation: tuple[float, float],
    ) -> float:
        """Returns the vote's center error under one candidate transform."""

        return math.dist(
            vote.observed,
            (
                zoom * vote.landmark.reference_center[0] + translation[0],
                zoom * vote.landmark.reference_center[1] + translation[1],
            ),
        )

    def _rival_cluster(
        self,
        hypothesis: _CameraHypothesis,
        *,
        reference: _CameraHypothesis | None = None,
    ) -> tuple[_CameraVote, ...] | None:
        """Returns a qualifying contradictory cluster left over at one zoom.

        The leftover fit is compared against ``reference`` (the hypothesis
        itself when omitted) so agreeing leftover clusters do not veto a
        consistent transform measured at another scale.
        """

        reference = reference or hypothesis
        remaining = tuple(
            vote for vote in hypothesis.votes if vote not in hypothesis.cluster
        )
        rival, rival_zoom, rival_translation = self._best_fit_cluster(
            remaining, evaluated_zoom=hypothesis.evaluated_zoom
        )
        rival_groups = frozenset(vote.landmark.group_id for vote in rival)
        if (
            len(rival) < _CAMERA_MIN_MATCHES
            or len(rival_groups) < _CAMERA_MIN_GROUPS
            or self._cluster_separation(rival) < _CAMERA_SCALE_SEPARATION_MIN_PX
            or not _CAMERA_ZOOM_MIN <= rival_zoom <= _CAMERA_ZOOM_MAX
        ):
            return None
        if abs(rival_zoom - reference.zoom) <= _CAMERA_RIVAL_ZOOM_DELTA and (
            self._transforms_agree(
                rival_zoom,
                rival_translation,
                reference.zoom,
                reference.translation,
                self._evidence_centroid(rival),
            )
        ):
            return None
        return rival

    def _is_ambiguous(self, hypothesis: _CameraHypothesis) -> bool:
        """Returns whether an unqualified hypothesis still shows rival clusters."""

        return self._rival_cluster(hypothesis) is not None

    def _contradicts(
        self, winner: _CameraHypothesis, other: _CameraHypothesis
    ) -> bool:
        """Returns whether two qualifying hypotheses publish contradictory transforms."""

        if abs(winner.zoom - other.zoom) > _CAMERA_RIVAL_ZOOM_DELTA:
            return True
        centroid = self._evidence_centroid((*winner.cluster, *other.cluster))
        return not self._transforms_agree(
            winner.zoom,
            winner.translation,
            other.zoom,
            other.translation,
            centroid,
        )

    def _evidence_centroid(
        self, votes: tuple[_CameraVote, ...]
    ) -> tuple[float, float]:
        """Returns the mean authored center of the votes' landmarks."""

        return (
            statistics.fmean(
                vote.landmark.reference_center[0] for vote in votes
            ),
            statistics.fmean(
                vote.landmark.reference_center[1] for vote in votes
            ),
        )

    def _transforms_agree(
        self,
        zoom_a: float,
        translation_a: tuple[float, float],
        zoom_b: float,
        translation_b: tuple[float, float],
        centroid: tuple[float, float],
    ) -> bool:
        """Returns whether two transforms place the evidence centroid together.

        Translation is origin-relative, so a small zoom difference between
        two fits of the same correspondences scales into a large origin gap
        (``Δt ≈ -Δz · centroid``): comparing raw translations would flag
        re-measurements of the same scene as rivals. Comparing where each
        transform puts the evidence itself is the scale-invariant check.
        """

        return math.dist(
            (
                zoom_a * centroid[0] + translation_a[0],
                zoom_a * centroid[1] + translation_a[1],
            ),
            (
                zoom_b * centroid[0] + translation_b[0],
                zoom_b * centroid[1] + translation_b[1],
            ),
        ) <= _CAMERA_RIVAL_TRANSLATION_PX

    def _ambiguous(
        self,
        reason: str,
        hypothesis: _CameraHypothesis,
        frame_size: tuple[int, int],
    ) -> HomeCityCameraProof:
        """Publishes an ambiguous verdict with the winning cluster's evidence."""

        return HomeCityCameraProof(
            status=HomeCityCameraStatus.AMBIGUOUS,
            reason=reason,
            frame_size=frame_size,
            evidence=tuple(
                self._evidence_for_transform(
                    hypothesis.cluster, hypothesis.zoom, hypothesis.translation
                )
            ),
        )

    def _insufficient(
        self,
        hypotheses: list[_CameraHypothesis],
        frame_size: tuple[int, int],
    ) -> HomeCityCameraProof:
        """Publishes the most informative unresolved verdict across hypotheses."""

        if not any(hypothesis.votes for hypothesis in hypotheses):
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason="no_landmark_correspondences",
                frame_size=frame_size,
            )
        strongest = max(
            hypotheses,
            key=lambda hypothesis: (
                len(hypothesis.cluster),
                len(hypothesis.groups),
                hypothesis.separation,
            ),
        )
        if (
            len(strongest.cluster) >= _CAMERA_MIN_MATCHES
            and len(strongest.groups) >= _CAMERA_MIN_GROUPS
            and strongest.separation >= _CAMERA_SCALE_SEPARATION_MIN_PX
            and not _CAMERA_ZOOM_MIN <= strongest.zoom <= _CAMERA_ZOOM_MAX
        ):
            reason = "unsupported_zoom_fit"
        elif (
            len(strongest.cluster) >= _CAMERA_MIN_MATCHES
            and len(strongest.groups) >= _CAMERA_MIN_GROUPS
        ):
            reason = "insufficient_scale_separation"
        elif len(strongest.groups) < _CAMERA_MIN_GROUPS:
            reason = "insufficient_independent_landmark_groups"
        else:
            reason = "insufficient_landmark_correspondences"
        return HomeCityCameraProof(
            status=HomeCityCameraStatus.INSUFFICIENT,
            reason=reason,
            frame_size=frame_size,
            evidence=tuple(
                self._evidence_for_transform(
                    strongest.cluster, strongest.zoom, strongest.translation
                )
            ),
        )

    def _publish(
        self,
        frame: PreparedFrame,
        hypothesis: _CameraHypothesis,
        frame_size: tuple[int, int],
        proposal_frame: PreparedFrame,
    ) -> HomeCityCameraProof:
        """Publishes the measured transform for the surviving hypothesis.

        Agreeing movable landmarks attach as residual-verified evidence at the
        published zoom without counting toward the qualifying minimums.
        """

        zoom, translation = hypothesis.zoom, hypothesis.translation
        movable = self._collect_votes(
            frame,
            proposal_frame,
            zoom=zoom,
            landmarks=tuple(
                landmark for landmark in self._catalog.landmarks if landmark.movable
            ),
        )
        attached = tuple(
            vote for vote in movable if self._residual(vote, zoom, translation)
            <= _CAMERA_CONSENSUS_TOLERANCE_PX
        )
        cluster = (*hypothesis.cluster, *attached)
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        return HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="consensus_landmark_cluster",
            translation=(
                int(round(translation[0] + zoom * offset_x)),
                int(round(translation[1] + zoom * offset_y)),
            ),
            zoom=zoom,
            reference_size=self._catalog.reference_size,
            frame_size=frame.original_size,
            evidence=tuple(
                self._evidence_for_transform(cluster, zoom, translation)
            ),
            matched_group_ids=frozenset(
                vote.landmark.group_id for vote in cluster
            ),
        )

    def _fit_transform(
        self,
        cluster: tuple[_CameraVote, ...],
    ) -> tuple[float, tuple[float, float]]:
        """Least-squares fit of ``(zoom, image_translation)`` for one cluster.

        ``q_i = zoom * p_i + T`` is fitted across both axes jointly over the
        reference/observed center pairs; centers carry the scene's true
        scale, so the fitted zoom recovers the measured camera zoom rather
        than the evaluated template scale.  A degenerate cluster that cannot
        separate zoom from translation degrades to the unit transform.
        """

        fitted = _fit_zoom_translation(
            tuple(
                (vote.landmark.reference_center, vote.observed)
                for vote in cluster
            )
        )
        if fitted is not None:
            return fitted
        mean_px = statistics.fmean(
            vote.landmark.reference_center[0] for vote in cluster
        )
        mean_py = statistics.fmean(
            vote.landmark.reference_center[1] for vote in cluster
        )
        mean_qx = statistics.fmean(vote.observed[0] for vote in cluster)
        mean_qy = statistics.fmean(vote.observed[1] for vote in cluster)
        return 1.0, (mean_qx - mean_px, mean_qy - mean_py)

    def _cluster_separation(self, cluster: tuple[_CameraVote, ...]) -> float:
        """Returns the widest authored-center distance inside a cluster."""

        separation = 0.0
        for index, vote in enumerate(cluster):
            for other in cluster[index + 1 :]:
                separation = max(
                    separation,
                    math.dist(
                        vote.landmark.reference_center,
                        other.landmark.reference_center,
                    ),
                )
        return separation

    def match_target(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> HomeCityCameraTargetMatch | None:
        """Returns one body match only when it agrees with the localized projection.

        Slot-bound targets publish through the plural candidate matcher and
        return a match only while exactly one eligible slot claims a
        projection-agreed body; an ambiguous claim stays unpublished rather
        than choosing the first slot.
        """

        if target.reference_slot is not None:
            matches = self.match_target_candidates(image, target, proof=proof)
            return matches[0] if len(matches) == 1 else None
        return self._match_fixed_target(image, target, proof=proof)

    def match_target_candidates(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> tuple[HomeCityCameraTargetMatch, ...]:
        """Returns every eligible slot carrying a projection-agreed body match.

        Fixed targets delegate to the singular matcher.  A slot-bound target
        derives each candidate's predicted body rectangle by translating the
        authored reference bounds from the calibrated reference pivot to the
        candidate pivot, then projecting through the proof transform.  The
        OpenCV search is bounded to the predicted neighborhood clipped to the
        frame, bodies must stay fully visible, and measured hits that would
        claim the same physical body for two slots are ambiguity evidence --
        every claim is rejected rather than picking the first slot.  Distinct
        bodies measured at different eligible slots remain separate matches.
        """

        if target.reference_slot is None:
            match = self._match_fixed_target(image, target, proof=proof)
            return () if match is None else (match,)
        frame = self._coerce_frame(image)
        if (
            frame is None
            or not proof.localized
            or proof.translation is None
            or proof.zoom is None
        ):
            return ()
        zoom = proof.zoom
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        image_translation = (
            proof.translation[0] - zoom * offset_x,
            proof.translation[1] - zoom * offset_y,
        )
        slots = target._eligible_slots()
        reference_slot = slots[target.reference_slot.slot_index]
        reference_pivot = reference_slot.atlas_coordinate
        if reference_pivot is None:
            raise SelectorResolutionError(
                "A slot-bound camera target requires a calibrated reference pivot.",
                landmark_id=target.landmark_id,
            )
        frame_bounds = Bounds(0, 0, *frame.reference_size)
        padding = target.max_projection_error
        matches: list[HomeCityCameraTargetMatch] = []
        for slot in sorted(slots.values(), key=lambda item: item.slot_index):
            pivot = slot.atlas_coordinate
            if pivot is None:
                continue
            predicted = (
                zoom * (target.reference_bounds.x + pivot.x - reference_pivot.x)
                + image_translation[0],
                zoom * (target.reference_bounds.y + pivot.y - reference_pivot.y)
                + image_translation[1],
            )
            predicted_bounds = Bounds(
                int(round(predicted[0])),
                int(round(predicted[1])),
                max(1, int(round(zoom * target.reference_bounds.width))),
                max(1, int(round(zoom * target.reference_bounds.height))),
            )
            if not frame_bounds.contains_bounds(predicted_bounds):
                continue
            region_left = max(frame_bounds.x, predicted_bounds.x - padding)
            region_top = max(frame_bounds.y, predicted_bounds.y - padding)
            region_right = min(
                frame_bounds.x + frame_bounds.width,
                predicted_bounds.x + predicted_bounds.width + padding,
            )
            region_bottom = min(
                frame_bounds.y + frame_bounds.height,
                predicted_bounds.y + predicted_bounds.height + padding,
            )
            if region_right - region_left <= 0 or region_bottom - region_top <= 0:
                continue
            hit = self._matcher.find_best_match(
                frame,
                self._catalog.template_path(target.file_name),
                threshold=target.min_score,
                search_region=Bounds(
                    region_left,
                    region_top,
                    region_right - region_left,
                    region_bottom - region_top,
                ),
                template_scale=zoom,
            )
            if hit is None:
                continue
            match_reference = self._reference_bounds(hit.bounds, frame)
            projection_error = math.dist(
                (match_reference.x, match_reference.y), predicted
            )
            if projection_error > target.max_projection_error:
                continue
            matches.append(
                self._build_match(
                    target,
                    hit,
                    match_reference,
                    zoom,
                    frame,
                    projection_error,
                    home_city_slot=HomeCitySlotSelector(slot.slot_index),
                )
            )
        kept = [
            match
            for match in matches
            if not any(
                other is not match
                and _claims_same_body(match.bounds, other.bounds)
                for other in matches
            )
        ]
        return tuple(kept)

    def _match_fixed_target(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> HomeCityCameraTargetMatch | None:
        """Returns the fixed-target body match when it agrees with the projection."""

        frame = self._coerce_frame(image)
        if (
            frame is None
            or not proof.localized
            or proof.translation is None
            or proof.zoom is None
        ):
            return None
        zoom = proof.zoom
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        image_translation = (
            proof.translation[0] - zoom * offset_x,
            proof.translation[1] - zoom * offset_y,
        )
        hit = self._matcher.find_best_match(
            frame,
            self._catalog.template_path(target.file_name),
            threshold=target.min_score,
            template_scale=zoom,
        )
        if hit is None:
            return None
        match_reference = self._reference_bounds(hit.bounds, frame)
        projection_error = math.dist(
            (match_reference.x, match_reference.y),
            (
                zoom * target.reference_bounds.x + image_translation[0],
                zoom * target.reference_bounds.y + image_translation[1],
            ),
        )
        if projection_error > target.max_projection_error:
            return None
        return self._build_match(
            target,
            hit,
            match_reference,
            zoom,
            frame,
            projection_error,
            home_city_slot=None,
        )

    def _build_match(
        self,
        target: HomeCityCameraTarget,
        hit: TemplateMatch,
        match_reference: Bounds,
        zoom: float,
        frame: PreparedFrame,
        projection_error: float,
        *,
        home_city_slot: HomeCitySlotSelector | None,
    ) -> HomeCityCameraTargetMatch:
        """Publishes measured action geometry anchored on the observed match."""

        scale_x = frame.original_size[0] / frame.reference_size[0]
        scale_y = frame.original_size[1] / frame.reference_size[1]

        def to_frame_point(reference_point: tuple[float, float]) -> tuple[int, int]:
            observed_x = match_reference.x + zoom * (
                reference_point[0] - target.reference_bounds.x
            )
            observed_y = match_reference.y + zoom * (
                reference_point[1] - target.reference_bounds.y
            )
            return (
                int(round(observed_x * scale_x)),
                int(round(observed_y * scale_y)),
            )

        action_point = to_frame_point(target.reference_action_point)
        action_left, action_top = to_frame_point(
            (
                target.reference_action_bounds.x,
                target.reference_action_bounds.y,
            )
        )
        action_right, action_bottom = to_frame_point(
            (
                target.reference_action_bounds.x
                + target.reference_action_bounds.width,
                target.reference_action_bounds.y
                + target.reference_action_bounds.height,
            )
        )
        return HomeCityCameraTargetMatch(
            target=target,
            bounds=hit.bounds,
            action_bounds=Bounds(
                action_left,
                action_top,
                max(1, action_right - action_left),
                max(1, action_bottom - action_top),
            ),
            action_point=action_point,
            score=hit.confidence,
            projection_error=projection_error,
            home_city_slot=home_city_slot,
        )

    def matched_target_objects(
        self,
        frame: PreparedFrame,
        *,
        proof: HomeCityCameraProof,
    ) -> tuple[DetectedSpatialObject, ...]:
        """Builds typed building objects for every projection-agreed body match.

        Slot-bound targets contribute one measured object per unambiguous
        eligible slot, each tagged with the observed ``home_city_slot``; the
        tag records the current frame's body evidence, never static occupancy.
        """

        if (
            not proof.localized
            or proof.translation is None
            or proof.zoom is None
            or proof.frame_size is None
        ):
            return ()
        objects: list[DetectedSpatialObject] = []
        viewport_bounds = Bounds(0, 0, *proof.frame_size)
        for target in self._catalog.targets:
            for match in self.match_target_candidates(frame, target, proof=proof):
                metadata = build_home_city_object_metadata(target.object_id)
                metadata.update(
                    {
                        "detection_source": "camera_template",
                        "camera_landmark_id": target.landmark_id,
                        "camera_match_score": round(match.score, 4),
                        "camera_projection_error": round(match.projection_error, 2),
                    }
                )
                if match.home_city_slot is not None:
                    metadata["home_city_slot_index"] = match.home_city_slot.slot_index
                objects.append(
                    DetectedSpatialObject(
                        kind=SpatialObjectKind.HOME_BUILDING,
                        bounds=match.bounds,
                        relationship=SpatialObjectRelationship.SELF,
                        name_text=home_city_object_definition(target.object_id).display_name,
                        action_point=match.action_point,
                        action_bounds=match.action_bounds,
                        viewport_offset=(
                            match.bounds.center()[0] - viewport_bounds.center()[0],
                            match.bounds.center()[1] - viewport_bounds.center()[1],
                        ),
                        viewport_offset_ratio=(
                            (match.bounds.center()[0] - viewport_bounds.center()[0])
                            / max(viewport_bounds.width, 1),
                            (match.bounds.center()[1] - viewport_bounds.center()[1])
                            / max(viewport_bounds.height, 1),
                        ),
                        source_kind=SpatialObjectSourceKind.TEMPLATE,
                        home_city_slot=match.home_city_slot,
                        metadata=metadata,
                    )
                )
        return tuple(objects)

    def _coerce_frame(self, image: Image.Image | PreparedFrame) -> PreparedFrame | None:
        """Reuses an already normalized frame or prepares one at the reference size."""

        if isinstance(image, PreparedFrame):
            if image.reference_size != self._catalog.reference_size:
                raise SelectorResolutionError(
                    "Home-camera frames must be prepared at the catalog reference size.",
                    reference_size=image.reference_size,
                    expected=self._catalog.reference_size,
                )
            return image
        return self.prepare_frame(image)

    def _collect_votes(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        *,
        zoom: float,
        landmarks: tuple[HomeCityCameraLandmark, ...],
    ) -> tuple[_CameraVote, ...]:
        """Matches each landmark at one template scale and keeps above-floor hits."""

        votes: list[_CameraVote] = []
        for landmark in landmarks:
            # Coarse proposals bound the global search, but a vote exists only
            # when the best-confidence natively refined candidate reaches the
            # landmark's floor, so the floor can be passed down directly.
            hit = self._matcher.find_best_match_coarse_to_fine(
                frame,
                proposal_frame,
                self._catalog.template_path(landmark.file_name),
                threshold=landmark.min_score,
                template_scale=zoom,
            )
            if hit is None:
                continue
            match_reference = self._reference_bounds(hit.bounds, frame)
            observed = (
                match_reference.x + match_reference.width / 2,
                match_reference.y + match_reference.height / 2,
            )
            votes.append(
                _CameraVote(
                    landmark=landmark,
                    bounds=hit.bounds,
                    score=hit.confidence,
                    observed=observed,
                    translation=(
                        observed[0] - zoom * landmark.reference_center[0],
                        observed[1] - zoom * landmark.reference_center[1],
                    ),
                    zoom=zoom,
                )
            )
        return tuple(votes)

    def _reference_bounds(self, bounds: Bounds, frame: PreparedFrame) -> Bounds:
        """Converts original-frame match bounds back into normalized reference units."""

        scale_x = frame.reference_size[0] / frame.original_size[0]
        scale_y = frame.reference_size[1] / frame.original_size[1]
        return Bounds(
            x=int(round(bounds.x * scale_x)),
            y=int(round(bounds.y * scale_y)),
            width=max(1, int(round(bounds.width * scale_x))),
            height=max(1, int(round(bounds.height * scale_y))),
        )

    def _consensus_translation(
        self, votes: tuple[_CameraVote, ...], *, zoom: float
    ) -> tuple[float, float]:
        """Fits the cluster translation as the component-wise median of its members."""

        return (
            statistics.median(
                vote.observed[0] - zoom * vote.landmark.reference_center[0]
                for vote in votes
            ),
            statistics.median(
                vote.observed[1] - zoom * vote.landmark.reference_center[1]
                for vote in votes
            ),
        )

    def _evidence_for_transform(
        self,
        votes: tuple[_CameraVote, ...],
        zoom: float,
        translation: tuple[float, float],
    ) -> list[HomeCityCameraEvidence]:
        """Publishes evidence with residuals measured against the published transform."""

        return [
            HomeCityCameraEvidence(
                landmark_id=vote.landmark.id,
                group_id=vote.landmark.group_id,
                bounds=vote.bounds,
                reference_bounds=vote.landmark.reference_bounds,
                score=vote.score,
                translation=(
                    int(round(vote.translation[0])),
                    int(round(vote.translation[1])),
                ),
                residual=math.dist(
                    vote.observed,
                    (
                        zoom * vote.landmark.reference_center[0] + translation[0],
                        zoom * vote.landmark.reference_center[1] + translation[1],
                    ),
                ),
                zoom=vote.zoom,
            )
            for vote in votes
        ]

    def _classify_zoom(
        self,
        camera_proof: HomeCityCameraProof,
    ) -> tuple[HomeCityZoomStatus, str, str | None]:
        """Classifies the proof's fixed-landmark scale against the endpoint calibration.

        The published ``zoom`` is grid-snapped within the consensus tolerance,
        which erases the few-hundredths separation between the endpoint band
        and the nearest closer rung; the verdict therefore refits the raw
        similarity scale over the proof's fixed-landmark center pairs.  A
        movable occupant corroborates pose but never establishes scale, so it
        is excluded from the fit exactly as it is excluded from consensus.
        """

        normalization = self._catalog.normalization
        endpoint = None if normalization is None else normalization.endpoint
        if endpoint is None:
            return HomeCityZoomStatus.UNSUPPORTED, "missing_zoom_calibration", None
        if not camera_proof.localized:
            return HomeCityZoomStatus.UNRESOLVED, camera_proof.reason, endpoint.id
        movable_ids = frozenset(
            landmark.id for landmark in self._catalog.landmarks if landmark.movable
        )
        fixed_evidence = tuple(
            item for item in camera_proof.evidence if item.landmark_id not in movable_ids
        )
        if len(fixed_evidence) < 2:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_fixed_scale_evidence",
                endpoint.id,
            )
        if (
            len({item.group_id for item in fixed_evidence})
            < endpoint.min_fixed_groups
        ):
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_independent_landmark_groups",
                endpoint.id,
            )
        pairs = tuple(
            self._evidence_center_pair(item, camera_proof) for item in fixed_evidence
        )
        fitted = _fit_zoom_translation(pairs)
        if fitted is None:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_scale_separation",
                endpoint.id,
            )
        zoom, translation = fitted
        mean_residual = statistics.fmean(
            math.dist(
                observed,
                (
                    zoom * authored[0] + translation[0],
                    zoom * authored[1] + translation[1],
                ),
            )
            for authored, observed in pairs
        )
        if mean_residual > endpoint.max_mean_residual_px:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "zoom_fit_residual_exceeded",
                endpoint.id,
            )
        if endpoint.zoom_interval[0] <= zoom <= endpoint.zoom_interval[1]:
            return HomeCityZoomStatus.AT_ENDPOINT, "measured_zoom_at_endpoint", endpoint.id
        if zoom >= endpoint.non_endpoint_floor:
            return (
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                endpoint.id,
            )
        return (
            HomeCityZoomStatus.UNRESOLVED,
            "measured_zoom_between_classes",
            endpoint.id,
        )

    def _evidence_center_pair(
        self,
        evidence: HomeCityCameraEvidence,
        camera_proof: HomeCityCameraProof,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Returns one evidence item's authored/observed center pair in reference units."""

        if camera_proof.frame_size is None:
            raise SelectorResolutionError(
                "A localized camera proof must carry its producing frame size.",
                landmark_id=evidence.landmark_id,
            )
        scale_x = camera_proof.reference_size[0] / camera_proof.frame_size[0]
        scale_y = camera_proof.reference_size[1] / camera_proof.frame_size[1]
        return (
            (
                evidence.reference_bounds.x + evidence.reference_bounds.width / 2,
                evidence.reference_bounds.y + evidence.reference_bounds.height / 2,
            ),
            (
                (evidence.bounds.x + evidence.bounds.width / 2) * scale_x,
                (evidence.bounds.y + evidence.bounds.height / 2) * scale_y,
            ),
        )

    def _match_zoom_anchor(self, frame: PreparedFrame) -> HomeCityZoomAnchor | None:
        """Locates a qualified scenery patch on the current frame's own pixels.

        Anchor recognition is pose-independent: each spec's native crop --
        which contains the reviewed dispatch point -- is matched across its
        evidence-backed scales, every qualifying hit must land on the same
        physical feature, and the patch's contained point must stay inside
        the match, the viewport, and outside every authored HUD/occlusion
        region.  Ambiguous, occluded, or offscreen placements publish no
        anchor rather than falling back to a corner, center, or unqualified
        patch.
        """

        normalization = self._catalog.normalization
        if normalization is None:
            return None
        proposal_frame = self._matcher.prepare_proposal_frame(frame)
        for spec in normalization.zoom_anchors:
            anchor = self._match_anchor_spec(
                frame,
                proposal_frame,
                normalization,
                spec,
            )
            if anchor is not None:
                return anchor
        return None

    def _match_anchor_spec(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        normalization: HomeCityViewNormalization,
        spec: HomeCityZoomAnchorSpec,
    ) -> HomeCityZoomAnchor | None:
        """Resolves one spec's patch placement when every qualifying hit agrees.

        The published bounds are the match's own rectangle in the frame's
        reference space; the published point is ``bounds.origin + scale *
        point_offset`` -- the native offset the reviewed dispatch point
        occupies inside the crop -- so the pixels checked are the same
        pixels the point sits on.
        """

        hits: list[tuple[float, TemplateMatch]] = []
        for scale in spec.scales:
            hit = self._matcher.find_best_match_coarse_to_fine(
                frame,
                proposal_frame,
                self._catalog.template_path(spec.file_name),
                threshold=spec.min_score,
                template_scale=scale,
            )
            if hit is not None:
                hits.append((scale, hit))
        if not hits:
            return None
        best_scale, best = max(hits, key=lambda item: item[1].confidence)
        best_center = (
            best.bounds.x + best.bounds.width / 2,
            best.bounds.y + best.bounds.height / 2,
        )
        for _, hit in hits:
            center = (
                hit.bounds.x + hit.bounds.width / 2,
                hit.bounds.y + hit.bounds.height / 2,
            )
            if math.dist(center, best_center) > _ANCHOR_CORRESPONDENCE_PX:
                return None
        lane = self._reference_bounds(best.bounds, frame)
        lane_tuple = (
            float(lane.x),
            float(lane.y),
            float(lane.width),
            float(lane.height),
        )
        point = (
            lane.x + best_scale * spec.point_offset[0],
            lane.y + best_scale * spec.point_offset[1],
        )
        if not _bounds_tuple_contains_point(lane_tuple, point):
            return None
        if not (
            lane_tuple[0] >= 0
            and lane_tuple[1] >= 0
            and lane_tuple[0] + lane_tuple[2] <= frame.reference_size[0]
            and lane_tuple[1] + lane_tuple[3] <= frame.reference_size[1]
        ):
            return None
        if any(
            _bounds_contains_float_point(excluded, point)
            for excluded in normalization.hud_exclusion_bounds
        ):
            return None
        scale_x = frame.original_size[0] / frame.reference_size[0]
        scale_y = frame.original_size[1] / frame.reference_size[1]
        return HomeCityZoomAnchor(
            point=(
                int(round(point[0] * scale_x)),
                int(round(point[1] * scale_y)),
            ),
            bounds=Bounds(
                int(round(lane_tuple[0] * scale_x)),
                int(round(lane_tuple[1] * scale_y)),
                max(1, int(round(lane_tuple[2] * scale_x))),
                max(1, int(round(lane_tuple[3] * scale_y))),
            ),
            qualification_id=spec.id,
        )


def _fit_zoom_translation(
    pairs: tuple[tuple[tuple[float, float], tuple[float, float]], ...],
) -> tuple[float, tuple[float, float]] | None:
    """Least-squares ``q = zoom * p + T`` fit over authored/observed center pairs.

    The pairs carry the scene's true scale, so the fitted zoom recovers the
    measured camera zoom rather than a grid hypothesis.  ``None`` is the
    honest answer when the authored centers are degenerate and cannot
    separate zoom from translation.
    """

    if len(pairs) < 2:
        return None
    mean_px = statistics.fmean(pair[0][0] for pair in pairs)
    mean_py = statistics.fmean(pair[0][1] for pair in pairs)
    mean_qx = statistics.fmean(pair[1][0] for pair in pairs)
    mean_qy = statistics.fmean(pair[1][1] for pair in pairs)
    numerator = 0.0
    denominator = 0.0
    for (authored_x, authored_y), (observed_x, observed_y) in pairs:
        delta_px = authored_x - mean_px
        delta_py = authored_y - mean_py
        numerator += (observed_x - mean_qx) * delta_px + (
            observed_y - mean_qy
        ) * delta_py
        denominator += delta_px * delta_px + delta_py * delta_py
    if denominator <= 0.0:
        return None
    zoom = numerator / denominator
    return zoom, (mean_qx - zoom * mean_px, mean_qy - zoom * mean_py)


def _bounds_tuple_contains_point(
    bounds: tuple[float, float, float, float],
    point: tuple[float, float],
) -> bool:
    """Returns whether a float point lies inside one projected float rectangle."""

    return (
        bounds[0] <= point[0] <= bounds[0] + bounds[2]
        and bounds[1] <= point[1] <= bounds[1] + bounds[3]
    )


def _bounds_contains_float_point(bounds: Bounds, point: tuple[float, float]) -> bool:
    """Returns whether a float point lies inside one integer-authored region."""

    return (
        bounds.x <= point[0] <= bounds.x + bounds.width
        and bounds.y <= point[1] <= bounds.y + bounds.height
    )


def _claims_same_body(first: Bounds, second: Bounds) -> bool:
    """Returns whether two matches describe the same physical building body."""

    return first.contains_point(second.center()) or second.contains_point(
        first.center()
    )


def merge_camera_target_objects(
    objects: tuple[DetectedSpatialObject, ...],
    camera_objects: tuple[DetectedSpatialObject, ...],
) -> tuple[DetectedSpatialObject, ...]:
    """Prefer measured bodies and attach only mutually unambiguous label facts.

    All measured instances survive. Once a semantic type has measured body
    evidence, its OCR-only duplicates cannot remain selectable objects. A
    label enriches a body only if each has exactly one compatible counterpart;
    counting both sides before merging prevents order-dependent level claims.
    """

    if not camera_objects:
        return objects
    object_ids = tuple(home_city_object_id_from_metadata(item.metadata) for item in objects)
    camera_ids = tuple(home_city_object_id_from_metadata(item.metadata) for item in camera_objects)
    measured_ids = {object_id for object_id in camera_ids if object_id is not None}
    compatible_bodies: list[list[int]] = [[] for _ in objects]
    compatible_labels: list[list[int]] = [[] for _ in camera_objects]
    for label_index, (label, object_id) in enumerate(zip(objects, object_ids)):
        if object_id not in measured_ids:
            continue
        for body_index, (body, camera_id) in enumerate(zip(camera_objects, camera_ids)):
            if camera_id != object_id:
                continue
            if (
                label.home_city_slot is not None
                and body.home_city_slot is not None
                and label.home_city_slot != body.home_city_slot
            ):
                continue
            compatible_bodies[label_index].append(body_index)
            compatible_labels[body_index].append(label_index)

    merged = [
        item for item, object_id in zip(objects, object_ids)
        if object_id not in measured_ids
    ]
    for body_index, body in enumerate(camera_objects):
        labels = compatible_labels[body_index]
        if len(labels) == 1 and len(compatible_bodies[labels[0]]) == 1:
            label = objects[labels[0]]
            body = replace(
                body,
                name_text=label.name_text or body.name_text,
                level=label.level if label.level is not None else body.level,
                metadata={
                    **body.metadata,
                    **{key: value for key, value in label.metadata.items() if key == "home_city_label"},
                },
            )
        merged.append(body)
    return tuple(merged)
