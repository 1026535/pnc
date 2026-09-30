"""Request-local measured Home coverage, occupancy, and candidate ordering.

Only fresh template bodies establish occupancy. Projected, fully exposed body
regions establish inspection, which is a separate fact and never proves empty.
Nothing here persists across workflow/account/castle changes or authorizes input.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraProof
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotOccupancy,
    HomeCitySlotOccupancyState,
    HomeCitySlotSelector,
    home_city_slots_for_object,
    validate_home_city_slot_selector,
)
from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, Observation, SpatialObjectSourceKind
from pnc_automation.app.pnc.domain.home_city_camera_catalog import HomeCityCameraTarget


class HomeCityScanStopReason(StrEnum):
    """What ended a bounded discovery, independently of target availability."""

    CANDIDATES_INSPECTED = "qualified_candidates_inspected"
    BUDGET_EXHAUSTED = "gesture_budget_exhausted"
    LOCALIZATION_UNRESOLVED = "localization_unresolved"
    NO_QUALIFIED_ROUTE = "no_qualified_route"
    NO_PROGRESS = "no_measured_progress"
    ZOOM_UNRESOLVED = "zoom_unresolved"
    ZOOM_ANCHOR_UNRESOLVED = "zoom_anchor_unresolved"
    ZOOM_INEFFECTIVE = "zoom_ineffective"
    ZOOM_BUDGET_EXHAUSTED = "zoom_budget_exhausted"
    ZOOM_CHANGED = "zoom_changed"
    NO_SAFE_GESTURE = "no_safe_gesture"
    INPUT_UNCERTAIN = "input_uncertain"
    UNEXPECTED_DESTINATION = "unexpected_destination"
    DEADLINE_EXHAUSTED = "deadline_exhausted"


@dataclass(frozen=True, slots=True)
class HomeCityCoverageRegion:
    """One HUD-free viewed region in common atlas units, not camera limits."""

    left: float
    top: float
    right: float
    bottom: float

    def contains(self, other: "HomeCityCoverageRegion") -> bool:
        """Require the whole relevant body region to remain usable."""
        return (self.left <= other.left and self.top <= other.top
                and self.right >= other.right and self.bottom >= other.bottom)

    @property
    def area(self) -> float:
        """Area of this measured region in square atlas units."""
        return max(0.0, self.right - self.left) * max(0.0, self.bottom - self.top)


@dataclass(frozen=True, slots=True)
class HomeCityScanResult:
    """A bounded measured survey; uninspected and unknown are never absent."""

    stop_reason: HomeCityScanStopReason
    gestures: int
    coverage: tuple[HomeCityCoverageRegion, ...]
    inspected_slots: tuple[HomeCitySlotSelector, ...]
    inspected_candidates: tuple[tuple[HomeCityObjectId, HomeCitySlotSelector], ...]
    occupancy: tuple[HomeCitySlotOccupancy, ...]
    remaining_slots: tuple[HomeCitySlotSelector, ...]
    qualified_targets: tuple[HomeCityObjectId, ...]
    inspected_fixed_targets: tuple[HomeCityObjectId, ...]
    remaining_fixed_targets: tuple[HomeCityObjectId, ...]
    captured_at: datetime | None
    zoom_inputs: int = 0


class HomeCityScanError(RuntimeError):
    """Preserve the building error contract while retaining measured coverage gaps."""

    def __init__(self, message: str, result: HomeCityScanResult) -> None:
        super().__init__(message)
        self.result = result


def _subtract_region(
    region: HomeCityCoverageRegion, covered: HomeCityCoverageRegion
) -> tuple[HomeCityCoverageRegion, ...]:
    """Keep the disjoint parts of one viewed rectangle not previously covered."""

    left, right = max(region.left, covered.left), min(region.right, covered.right)
    top, bottom = max(region.top, covered.top), min(region.bottom, covered.bottom)
    if left >= right or top >= bottom:
        return (region,)
    return tuple(piece for piece in (
        HomeCityCoverageRegion(region.left, region.top, region.right, top),
        HomeCityCoverageRegion(region.left, bottom, region.right, region.bottom),
        HomeCityCoverageRegion(region.left, top, left, bottom),
        HomeCityCoverageRegion(right, top, region.right, bottom),
    ) if piece.area > 0)


def camera_view_center_atlas(proof: HomeCityCameraProof) -> tuple[float, float]:
    """Compare camera positions in atlas units, independently of game zoom."""

    width, height = proof.reference_size
    return proof.project_reference_to_atlas((width / 2, height / 2))


def projected_body_region(
    target: HomeCityCameraTarget,
    slot: HomeCitySlotSelector | None,
) -> HomeCityCoverageRegion:
    """Return candidate body geometry in atlas units, without an occupancy claim."""

    action_x, action_y = target.atlas_action_point(home_city_slot=slot)
    bounds = target.reference_bounds
    left = action_x + bounds.x - target.reference_action_point[0]
    top = action_y + bounds.y - target.reference_action_point[1]
    return HomeCityCoverageRegion(left, top, left + bounds.width, top + bounds.height)


@dataclass(slots=True)
class HomeCityScanState:
    """One request's history, shared by building acquisition and discovery."""

    coverage: list[HomeCityCoverageRegion] = field(default_factory=list)
    inspected_slots: set[HomeCitySlotSelector] = field(default_factory=set)
    inspected_candidates: set[tuple[HomeCityObjectId, HomeCitySlotSelector]] = field(default_factory=set)
    inspected_targets: set[HomeCityObjectId] = field(default_factory=set)
    occupancy: dict[int, HomeCitySlotOccupancy] = field(default_factory=dict)
    gestures: int = 0
    zoom_inputs: int = 0
    captured_at: datetime | None = None
    consecutive_no_progress: int = 0
    _current_region: HomeCityCoverageRegion | None = None

    def observe(
        self,
        observation: Observation,
        *,
        targets: tuple[HomeCityCameraTarget, ...],
        usable_region: HomeCityCoverageRegion,
    ) -> bool:
        """Update measured coverage and body inspection; report useful new facts.

        The caller owns the Home/guard/identity and localized-proof checks. This
        method still rejects stale captures, so history cannot be refreshed by
        replaying a previous image. Regions passed here are inverse-projected
        from the current HUD-free viewport, never inferred from swipe distance.
        """

        if self.captured_at is not None and observation.captured_at <= self.captured_at:
            raise RuntimeError("Home-city scan received a stale capture.")
        self.captured_at = observation.captured_at
        self._current_region = usable_region
        previous_occupancy = dict(self.occupancy)
        uncovered = (usable_region,)
        for prior in self.coverage:
            uncovered = tuple(piece for region in uncovered for piece in _subtract_region(region, prior))
        # Twelve atlas pixels are the existing localization-noise allowance.
        # A noisy edge sliver must not keep a cycling scan alive indefinitely.
        coverage_progress = any(
            piece.right - piece.left > 12 and piece.bottom - piece.top > 12
            for piece in uncovered
        )
        if coverage_progress:
            self.coverage.extend(uncovered)
        previously_inspected = len(self.inspected_candidates) + len(self.inspected_targets)
        for target in targets:
            slots = (tuple(HomeCitySlotSelector(s.slot_index)
                           for s in home_city_slots_for_object(target.object_id))
                     if target.reference_slot is not None else (None,))
            for slot in slots:
                if not usable_region.contains(projected_body_region(target, slot)):
                    continue
                if slot is None:
                    self.inspected_targets.add(target.object_id)
                else:
                    self.inspected_slots.add(slot)
                    self.inspected_candidates.add((target.object_id, slot))
                    self.occupancy[slot.slot_index] = HomeCitySlotOccupancy(
                        slot.slot_index, HomeCitySlotOccupancyState.UNKNOWN, None,
                        f"Inspected {target.object_id.value} body region; {observation.captured_at.isoformat()}",
                    )
        occupancy_progress = False
        surface = observation.spatial_surface
        if surface is not None:
            claims: dict[HomeCitySlotSelector, list[DetectedSpatialObject]] = {}
            for body in surface.objects:
                slot = body.home_city_slot
                identity = home_city_object_id_from_metadata(body.metadata)
                if slot is None or identity is None or body.source_kind != SpatialObjectSourceKind.TEMPLATE:
                    continue
                validate_home_city_slot_selector(identity, slot)
                claims.setdefault(slot, []).append(body)
            for slot, bodies in claims.items():
                if len(bodies) != 1:
                    self.occupancy[slot.slot_index] = HomeCitySlotOccupancy(
                        slot.slot_index, HomeCitySlotOccupancyState.UNKNOWN, None,
                        f"Ambiguous measured slot claims; {observation.captured_at.isoformat()}",
                    )
                    continue
                identity = home_city_object_id_from_metadata(bodies[0].metadata)
                old = previous_occupancy.get(slot.slot_index)
                occupancy_progress |= old is None or old.observed_object_id != identity
                self.occupancy[slot.slot_index] = HomeCitySlotOccupancy(
                    slot.slot_index, HomeCitySlotOccupancyState.OCCUPIED, identity,
                    f"Fresh measured body; {observation.captured_at.isoformat()}; {observation.artifact_path}",
                )
        return (coverage_progress or occupancy_progress
                or len(self.inspected_candidates) + len(self.inspected_targets) > previously_inspected)

    def candidate_slots(
        self, target: HomeCityCameraTarget, proof: HomeCityCameraProof,
        *, exact: HomeCitySlotSelector | None = None,
    ) -> tuple[HomeCitySlotSelector | None, ...]:
        """Order compatible observed hints, then nearest uninspected candidates.

        A fixed scene target has one None candidate. An exhausted ordinary
        family returns no candidates, never a fixed-target sentinel or absence.
        """

        validate_home_city_slot_selector(target.object_id, exact)
        if target.reference_slot is None:
            return (None,)
        if exact is not None:
            return (exact,)
        center_x, center_y = camera_view_center_atlas(proof)
        slots = [s for s in home_city_slots_for_object(target.object_id)
                 if s.atlas_coordinate is not None]
        hints = [s for s in slots if (old := self.occupancy.get(s.slot_index)) is not None
                 and old.observed_object_id == target.object_id]
        hint_ids = {s.slot_index for s in hints}
        candidates = [s for s in slots if s.slot_index in hint_ids
                      or (target.object_id, HomeCitySlotSelector(s.slot_index))
                      not in self.inspected_candidates]
        ordered = sorted(candidates, key=lambda s: (
            s.slot_index not in hint_ids,
            not (self._current_region is not None and self._current_region.contains(
                projected_body_region(target, HomeCitySlotSelector(s.slot_index))
            )),
            (s.atlas_coordinate.x - center_x) ** 2 + (s.atlas_coordinate.y - center_y) ** 2,
            s.slot_index,
        ))
        return tuple(HomeCitySlotSelector(slot.slot_index) for slot in ordered)

    def candidate_inspected(
        self,
        target: HomeCityCameraTarget,
        slot: HomeCitySlotSelector | None,
    ) -> bool:
        """Whether this request already completed inspecting that exact candidate.

        One request-local lookup serves fixed targets and ordinary slot
        candidates so discovery never revisits a body it already exposed,
        whichever family the candidate came from.  An observed occupant hint
        stays useful for acquisition, but a hint never un-inspects a candidate,
        and an inspected candidate still carries unknown occupancy --
        inspection never means absent.
        """

        if slot is None:
            return target.object_id in self.inspected_targets
        return (target.object_id, slot) in self.inspected_candidates

    def result(
        self, reason: HomeCityScanStopReason, *, targets: tuple[HomeCityCameraTarget, ...] = (),
    ) -> HomeCityScanResult:
        """Retain all ordinary coverage gaps, including unqualified families."""

        return HomeCityScanResult(
            reason, self.gestures, tuple(self.coverage),
            tuple(sorted(self.inspected_slots, key=lambda s: s.slot_index)),
            tuple(sorted(self.inspected_candidates, key=lambda c: (c[0].value, c[1].slot_index))),
            tuple(self.occupancy[i] for i in sorted(self.occupancy)),
            tuple(HomeCitySlotSelector(i) for i in range(1, 55)
                  if HomeCitySlotSelector(i) not in self.inspected_slots),
            tuple(sorted((target.object_id for target in targets), key=lambda t: t.value)),
            tuple(sorted(self.inspected_targets, key=lambda t: t.value)),
            tuple(sorted((target.object_id for target in targets
                          if target.reference_slot is None and target.object_id not in self.inspected_targets),
                         key=lambda t: t.value)),
            self.captured_at,
            zoom_inputs=self.zoom_inputs,
        )
