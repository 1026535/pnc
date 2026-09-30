"""Typed Home-city camera catalog values and target geometry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotEligibility,
    HomeCitySlotSelector,
    home_city_slots_for_object,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds

HOME_CITY_CAMERA_REFERENCE_SIZE = (900, 1600)
HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET = (-532, 222)

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
