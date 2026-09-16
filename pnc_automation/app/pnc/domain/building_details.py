"""Canonical typed building detail facts published by vision producers.

A ``BuildingDetail`` describes what one accepted building-owned frame shows:
which building owns it (``HomeCityObjectId`` when proved), which panel phase is
displayed, the observed ``current/max`` level pair, ordinary resource costs,
original/actual times, and the measured prerequisite row. It never authorizes
an action: a ``PRIMARY`` panel's Upgrade control only opens the upgrade detail,
while the ``UPGRADE`` panel's ordinary Upgrade is the mutation surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.resource_cost import ResourceCost
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds


class BuildingDetailPhase(StrEnum):
    """The observed panel phase of one building-owned screen."""

    PRIMARY = "primary"
    UPGRADE = "upgrade"
    CONSTRUCTION = "construction"


_BUILDING_LEVEL_PATTERN = re.compile(r"^\s*(?P<current>\d+)\s*/\s*(?P<max>\d+)\s*$")


def parse_building_level_pair(text: str) -> tuple[int, int] | None:
    """Parse one exact ``current/max`` building level label such as ``7/45``.

    Both values are returned together or neither is; partial labels, bare
    integers, and arbitrary text never produce a level.
    """

    match = _BUILDING_LEVEL_PATTERN.match(text)
    if match is None:
        return None
    return int(match.group("current")), int(match.group("max"))


@dataclass(frozen=True, slots=True)
class BuildingRequirementRow:
    """One explicit prerequisite row measured on a building detail panel.

    ``go_bounds`` carries only this row's own independently measured `Go`
    control. A row without a measured `Go` keeps the observed target text but
    cannot claim an actionable unmet prerequisite.
    """

    target_text: str
    target_bounds: Bounds
    target_building: HomeCityObjectId | None = None
    target_level: int | None = None
    go_bounds: Bounds | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keep row facts typed, measured, and bounded."""

        if not isinstance(self.target_text, str) or not self.target_text.strip():
            raise ValueError("BuildingRequirementRow.target_text must be non-empty.")
        if not isinstance(self.target_bounds, Bounds):
            raise TypeError("BuildingRequirementRow.target_bounds must be Bounds.")
        if self.target_building is not None and not isinstance(self.target_building, HomeCityObjectId):
            raise TypeError("BuildingRequirementRow.target_building must be a HomeCityObjectId or None.")
        if self.target_level is not None and (
            not isinstance(self.target_level, int) or isinstance(self.target_level, bool) or self.target_level < 0
        ):
            raise SelectorResolutionError(
                "BuildingRequirementRow.target_level must be a non-negative integer or None.",
                value=self.target_level,
            )
        if self.go_bounds is not None and not isinstance(self.go_bounds, Bounds):
            raise TypeError("BuildingRequirementRow.go_bounds must be Bounds or None.")


@dataclass(frozen=True, slots=True)
class BuildingDetail:
    """Typed facts measured on one building-owned detail or primary panel.

    ``phase`` distinguishes the read-only primary panel from the mutation-owning
    upgrade detail and the construction panel. ``current_level``/``max_level``
    publish only the observed ``N/M`` pair. ``requirement`` records the explicit
    prerequisite row; premium values are read-only facts without a usable action.
    """

    building_id: HomeCityObjectId | None = None
    phase: BuildingDetailPhase | None = None
    title_text: str | None = None
    current_level: int | None = None
    max_level: int | None = None
    level_text: str | None = None
    costs: tuple[ResourceCost, ...] = ()
    original_time_text: str | None = None
    actual_time_text: str | None = None
    requirement: BuildingRequirementRow | None = None
    premium_cost_text: str | None = None
    premium_button_bounds: Bounds | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keep detail facts typed, paired, and measured."""

        if self.building_id is not None and not isinstance(self.building_id, HomeCityObjectId):
            raise TypeError("BuildingDetail.building_id must be a HomeCityObjectId or None.")
        if self.phase is not None and not isinstance(self.phase, BuildingDetailPhase):
            raise TypeError("BuildingDetail.phase must be a BuildingDetailPhase or None.")
        for field_name in ("current_level", "max_level"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"BuildingDetail.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if (self.current_level is None) != (self.max_level is None):
            raise SelectorResolutionError(
                "BuildingDetail levels must be observed together or stay unknown."
            )
        if self.level_text is not None and (not isinstance(self.level_text, str) or not self.level_text.strip()):
            raise ValueError("BuildingDetail.level_text must be non-empty or None.")
        if self.requirement is not None and not isinstance(self.requirement, BuildingRequirementRow):
            raise TypeError("BuildingDetail.requirement must be a BuildingRequirementRow or None.")
        if self.premium_button_bounds is not None and not isinstance(self.premium_button_bounds, Bounds):
            raise TypeError("BuildingDetail.premium_button_bounds must be Bounds or None.")
