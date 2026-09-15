"""Typed identities and receipts for building mutations.

The action identity is deliberately separate from the optional Daily quest
context.  This keeps a direct construction request and a Daily-Go upgrade
request on the same durable operation boundary without inventing a
construction quest.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from pnc_automation.app.pnc.domain.building_catalog import (
    ConstructionSlotFamily,
    HomeCityObjectId,
    require_building_construction_source,
)
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId
from pnc_automation.app.pnc.domain.policy_models import BuildingPrerequisiteMode
from pnc_automation.app.pnc.domain.observation import DetectedSpatialObject, SpatialObjectKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class BuildingMutationKind(StrEnum):
    """The two resource-changing actions owned by the building package."""

    CONSTRUCT = "building_construct"
    UPGRADE = "building_upgrade"


def observable_building_instance_key(
    building: HomeCityObjectId,
    object_: DetectedSpatialObject,
) -> str:
    """Return an identity token made only from published Home geometry and id metadata."""

    if object_.kind is not SpatialObjectKind.HOME_BUILDING:
        raise ValueError("Home object is not a building scene object.")
    if object_.metadata.get("home_city_object_id") != building.value:
        raise ValueError("Home object does not belong to the requested building id.")
    bounds = object_.bounds
    point = object_.action_point
    point_text = "none" if point is None else f"{point[0]},{point[1]}"
    return (
        f"home:{building.value}:"
        f"{bounds.x},{bounds.y},{bounds.width},{bounds.height}:"
        f"{point_text}"
    )


def observable_construction_slot_key(
    slot_id: HomeCityObjectId,
    object_: DetectedSpatialObject,
) -> str:
    """Return the strongest available identity for one observed empty slot."""

    if object_.metadata.get("home_city_object_id") != slot_id.value:
        raise ValueError("Home object does not belong to the requested construction slot.")
    bounds = object_.bounds
    point = object_.action_point
    point_text = "none" if point is None else f"{point[0]},{point[1]}"
    return f"home-slot:{slot_id.value}:{bounds.x},{bounds.y},{bounds.width},{bounds.height}:{point_text}"


@dataclass(frozen=True, slots=True)
class BuildingConstructionTarget:
    """Identifies one building and its exact empty-slot source."""

    building: HomeCityObjectId
    slot_id: HomeCityObjectId
    slot_family: ConstructionSlotFamily
    option_selector_id: UiElementId
    slot_instance_key: str | None = None

    def __post_init__(self) -> None:
        """Require the target to agree with the canonical construction catalog."""

        if not isinstance(self.building, HomeCityObjectId):
            raise TypeError("BuildingConstructionTarget.building must be a HomeCityObjectId.")
        if not isinstance(self.slot_id, HomeCityObjectId):
            raise TypeError("BuildingConstructionTarget.slot_id must be a HomeCityObjectId.")
        if not isinstance(self.slot_family, ConstructionSlotFamily):
            raise TypeError("BuildingConstructionTarget.slot_family must be a ConstructionSlotFamily.")
        if not isinstance(self.option_selector_id, UiElementId):
            raise TypeError("BuildingConstructionTarget.option_selector_id must be a UiElementId.")
        if self.slot_instance_key is not None and (
            not isinstance(self.slot_instance_key, str) or not self.slot_instance_key.strip()
        ):
            raise ValueError("BuildingConstructionTarget.slot_instance_key cannot be blank.")
        source = require_building_construction_source(self.building)
        if (self.slot_id, self.slot_family, self.option_selector_id) != (
            source.slot_id,
            source.slot_family,
            source.option_selector_id,
        ):
            raise ValueError("Construction target does not match its canonical source family and option.")

    @classmethod
    def for_building(cls, building: HomeCityObjectId) -> "BuildingConstructionTarget":
        """Build a target from the one canonical source mapping."""

        source = require_building_construction_source(building)
        return cls(
            building=building,
            slot_id=source.slot_id,
            slot_family=source.slot_family,
            option_selector_id=source.option_selector_id,
        )

    def as_metadata(self) -> dict[str, str]:
        """Return a journal-safe target projection."""

        return {
            "building": self.building.value,
            "slot_id": self.slot_id.value,
            "slot_family": self.slot_family.value,
            "option_selector_id": self.option_selector_id.value,
            "slot_instance_key": self.slot_instance_key or "",
        }

    def bind_slot(self, slot_instance_key: str) -> "BuildingConstructionTarget":
        """Bind the catalog source to the exact slot observed on the dispatch route."""

        return BuildingConstructionTarget(
            building=self.building,
            slot_id=self.slot_id,
            slot_family=self.slot_family,
            option_selector_id=self.option_selector_id,
            slot_instance_key=slot_instance_key,
        )

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "BuildingConstructionTarget":
        """Rehydrate a journaled construction target without inventing new identity."""

        if not isinstance(metadata, Mapping):
            raise TypeError("Construction target metadata must be a mapping.")
        slot_instance_key = metadata.get("slot_instance_key")
        if slot_instance_key == "":
            slot_instance_key = None
        return cls(
            building=HomeCityObjectId(metadata["building"]),
            slot_id=HomeCityObjectId(metadata["slot_id"]),
            slot_family=ConstructionSlotFamily(metadata["slot_family"]),
            option_selector_id=UiElementId(metadata["option_selector_id"]),
            slot_instance_key=slot_instance_key,
        )


@dataclass(frozen=True, slots=True)
class BuildingUpgradeTarget:
    """Identifies one observed instance and one exact level transition."""

    building: HomeCityObjectId
    instance_key: str
    current_level: int
    next_level: int
    prerequisite_mode: BuildingPrerequisiteMode = BuildingPrerequisiteMode.FAIL
    allow_speedups: bool = False
    allow_premium_material_purchases: bool = False
    request_help: bool = False

    def __post_init__(self) -> None:
        """Reject ambiguous instance or level transitions before any input."""

        if not isinstance(self.building, HomeCityObjectId):
            raise TypeError("BuildingUpgradeTarget.building must be a HomeCityObjectId.")
        if not isinstance(self.instance_key, str) or not self.instance_key.strip():
            raise ValueError("BuildingUpgradeTarget.instance_key cannot be empty.")
        if type(self.current_level) is not int or self.current_level < 0:
            raise ValueError("BuildingUpgradeTarget.current_level must be non-negative.")
        if type(self.next_level) is not int or self.next_level != self.current_level + 1:
            raise ValueError("BuildingUpgradeTarget.next_level must be exactly current_level + 1.")
        if not isinstance(self.prerequisite_mode, BuildingPrerequisiteMode):
            raise TypeError("BuildingUpgradeTarget.prerequisite_mode must be a BuildingPrerequisiteMode.")
        for name, value in (
            ("allow_speedups", self.allow_speedups),
            ("allow_premium_material_purchases", self.allow_premium_material_purchases),
            ("request_help", self.request_help),
        ):
            if type(value) is not bool:
                raise TypeError(f"BuildingUpgradeTarget.{name} must be a bool.")

    def as_metadata(self) -> dict[str, Any]:
        """Return a journal-safe target projection."""

        return {
            "building": self.building.value,
            "instance_key": self.instance_key,
            "current_level": self.current_level,
            "next_level": self.next_level,
            "prerequisite_mode": self.prerequisite_mode.value,
            "allow_speedups": self.allow_speedups,
            "allow_premium_material_purchases": self.allow_premium_material_purchases,
            "request_help": self.request_help,
        }

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, Any]) -> "BuildingUpgradeTarget":
        """Rehydrate a journaled upgrade target without trusting untyped caller input."""

        if not isinstance(metadata, Mapping):
            raise TypeError("Upgrade target metadata must be a mapping.")
        return cls(
            building=HomeCityObjectId(metadata["building"]),
            instance_key=metadata["instance_key"],
            current_level=metadata["current_level"],
            next_level=metadata["next_level"],
            prerequisite_mode=BuildingPrerequisiteMode(metadata.get("prerequisite_mode", "fail")),
            allow_speedups=metadata.get("allow_speedups", False),
            allow_premium_material_purchases=metadata.get("allow_premium_material_purchases", False),
            request_help=metadata.get("request_help", False),
        )


@dataclass(frozen=True, slots=True)
class BuildingActionIdentity:
    """Durable identity shared by direct and Daily-Go entry paths."""

    kind: BuildingMutationKind
    operation_id: str
    target: BuildingConstructionTarget | BuildingUpgradeTarget
    daily_quest_id: DailyQuestId | None = None

    def __post_init__(self) -> None:
        """Ensure action kind and target type cannot drift across retries."""

        if not isinstance(self.kind, BuildingMutationKind):
            raise TypeError("BuildingActionIdentity.kind must be a BuildingMutationKind.")
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("BuildingActionIdentity.operation_id cannot be empty.")
        if self.kind is BuildingMutationKind.CONSTRUCT and not isinstance(self.target, BuildingConstructionTarget):
            raise TypeError("Construction action identities require a BuildingConstructionTarget.")
        if self.kind is BuildingMutationKind.CONSTRUCT and self.target.slot_instance_key is None:
            raise ValueError("Construction action identities require an exact observed slot instance.")
        if self.kind is BuildingMutationKind.UPGRADE and not isinstance(self.target, BuildingUpgradeTarget):
            raise TypeError("Upgrade action identities require a BuildingUpgradeTarget.")
        if self.daily_quest_id is not None and not isinstance(self.daily_quest_id, DailyQuestId):
            raise TypeError("BuildingActionIdentity.daily_quest_id must be a DailyQuestId or None.")

    def as_metadata(self) -> dict[str, Any]:
        """Return the stable action identity used in a mutation intent."""

        return {
            "action_kind": self.kind.value,
            "target": self.target.as_metadata(),
            "daily_quest_id": None if self.daily_quest_id is None else self.daily_quest_id.value,
        }


class BuildingReceiptStatus(StrEnum):
    """Known post-dispatch dispositions for building actions."""

    STARTED = "started"
    LEVEL_INCREASED = "level_increased"
    PENDING_CLARIFICATION = "pending_clarification"


@dataclass(frozen=True, slots=True)
class BuildingMutationReceipt:
    """Target-correlated receipt persisted with the canonical journal intent."""

    operation_id: str
    action_kind: BuildingMutationKind
    status: BuildingReceiptStatus
    target: BuildingConstructionTarget | BuildingUpgradeTarget
    artifact_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Keep receipts target-bound and replay-safe."""

        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("BuildingMutationReceipt.operation_id cannot be empty.")
        if not isinstance(self.action_kind, BuildingMutationKind):
            raise TypeError("BuildingMutationReceipt.action_kind must be a BuildingMutationKind.")
        if not isinstance(self.status, BuildingReceiptStatus):
            raise TypeError("BuildingMutationReceipt.status must be a BuildingReceiptStatus.")
        if self.action_kind is BuildingMutationKind.CONSTRUCT and not isinstance(self.target, BuildingConstructionTarget):
            raise TypeError("Construction receipts require a construction target.")
        if self.action_kind is BuildingMutationKind.UPGRADE and not isinstance(self.target, BuildingUpgradeTarget):
            raise TypeError("Upgrade receipts require an upgrade target.")
