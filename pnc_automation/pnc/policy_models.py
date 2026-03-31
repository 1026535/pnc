"""Typed task policies loaded from run-script parameters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from pnc_automation.errors import ScriptValidationError
from pnc_automation.pnc.building_catalog import (
    HomeCityObjectId,
    HomeCityObjectRole,
    default_building_upgrade_priority,
    home_city_object_definition,
)
from pnc_automation.pnc.building_priority_input import resolve_building_priority_values

TEnum = TypeVar("TEnum", bound=StrEnum)


class BuildingPriority(StrEnum):
    """Supported exact home-city building ids for upgrade policy."""

    CASTLE = "castle"
    WALL = "wall"
    INSTITUTE = "institute"
    WAREHOUSE = "warehouse"
    TRAP_WORKSHOP = "trap_workshop"
    WATCHTOWER = "watchtower"
    FARM = "farm"
    LUMBER_CAMP = "lumber_camp"
    MOON_WELL = "moon_well"
    RECRUITING_CENTER = "recruiting_center"
    INFIRMARY = "infirmary"
    IRON_MINE = "iron_mine"
    GOLD_MINE = "gold_mine"
    BLACKSMITH = "blacksmith"
    ALLIANCE_HALL = "alliance_hall"
    MARKET = "market"
    INFANTRY_BARRACKS = "infantry_barracks"
    CAVALRY_BARRACKS = "cavalry_barracks"
    RANGED_BARRACKS = "ranged_barracks"
    SIEGE_FACTORY = "siege_factory"
    HALL_OF_WAR = "hall_of_war"
    SAUROI_LAIR = "sauroi_lair"
    GODDESS_STATUE = "goddess_statue"


class ResearchCategory(StrEnum):
    """Supported research categories for institute automation."""

    ECONOMY = "economy"
    DEVELOPMENT = "development"
    MILITARY = "military"


class ResourceType(StrEnum):
    """Supported gatherable resource priorities."""

    FOOD = "food"
    WOOD = "wood"
    IRON = "iron"
    STONE = "stone"


class CampaignMode(StrEnum):
    """Supported campaign execution modes."""

    STANDARD = "standard"
    ELITE = "elite"


@dataclass(frozen=True, slots=True)
class BuildingUpgradePolicy:
    """Task parameters for building upgrade execution."""

    priority: tuple[BuildingPriority, ...] = tuple(
        BuildingPriority(home_city_object_id.value) for home_city_object_id in default_building_upgrade_priority()
    )
    allow_speedups: bool = False

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "BuildingUpgradePolicy":
        """Builds a typed policy from raw script params."""

        try:
            priority_values = resolve_building_priority_values(
                priority=params.get("priority"),
                priority_file=params.get("priority_file"),
                default_priority=[member.value for member in cls().priority],
            )
        except (OSError, TypeError, ValueError) as error:
            raise ScriptValidationError(str(error), field="priority") from error
        return cls(
            priority=_parse_enum_list(
                priority_values,
                enum_type=BuildingPriority,
                field_name="priority",
            ),
            allow_speedups=_parse_bool(params.get("allow_speedups", False), field_name="allow_speedups"),
        )


@dataclass(frozen=True, slots=True)
class OpenBuildingPolicy:
    """Task parameters for opening one exact home-city building screen."""

    building: HomeCityObjectId = HomeCityObjectId.CASTLE

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "OpenBuildingPolicy":
        """Builds a typed policy from raw script params."""

        raw_building = params.get("building")
        if not isinstance(raw_building, str):
            raise ScriptValidationError("Expected 'building' to be a string.", field="building")
        try:
            building = HomeCityObjectId(raw_building)
        except ValueError as error:
            raise ScriptValidationError(
                f"Unsupported value '{raw_building}' for 'building'.",
                field="building",
                value=raw_building,
            ) from error
        role = home_city_object_definition(building).role
        if role not in {HomeCityObjectRole.HOME_CITY_BUILDING, HomeCityObjectRole.REPEATABLE_SMALL_BUILDING}:
            raise ScriptValidationError(
                f"Unsupported value '{raw_building}' for 'building'.",
                field="building",
                value=raw_building,
            )
        return cls(building=building)


@dataclass(frozen=True, slots=True)
class ResearchPolicy:
    """Task parameters for institute research execution."""

    priority: tuple[ResearchCategory, ...] = (
        ResearchCategory.ECONOMY,
        ResearchCategory.DEVELOPMENT,
        ResearchCategory.MILITARY,
    )

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "ResearchPolicy":
        """Builds a typed policy from raw script params."""

        return cls(
            priority=_parse_enum_list(
                params.get("priority", [member.value for member in cls().priority]),
                enum_type=ResearchCategory,
                field_name="priority",
            )
        )


@dataclass(frozen=True, slots=True)
class GatheringPolicy:
    """Task parameters for world-map gathering."""

    preferred_resources: tuple[ResourceType, ...] = (
        ResourceType.FOOD,
        ResourceType.WOOD,
        ResourceType.IRON,
    )
    max_parallel_marches: int = 2

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "GatheringPolicy":
        """Builds a typed policy from raw script params."""

        march_limit = params.get("max_parallel_marches", 2)
        if not isinstance(march_limit, int) or isinstance(march_limit, bool) or march_limit <= 0:
            raise ScriptValidationError(
                "Gathering policy requires max_parallel_marches to be a positive integer.",
                field="max_parallel_marches",
            )
        return cls(
            preferred_resources=_parse_enum_list(
                params.get("preferred_resources", [member.value for member in cls().preferred_resources]),
                enum_type=ResourceType,
                field_name="preferred_resources",
            ),
            max_parallel_marches=march_limit,
        )


@dataclass(frozen=True, slots=True)
class CampaignPolicy:
    """Task parameters for campaign automation."""

    enabled_modes: tuple[CampaignMode, ...] = (CampaignMode.STANDARD,)

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "CampaignPolicy":
        """Builds a typed policy from raw script params."""

        return cls(
            enabled_modes=_parse_enum_list(
                params.get("enabled_modes", [member.value for member in cls().enabled_modes]),
                enum_type=CampaignMode,
                field_name="enabled_modes",
            )
        )


def _parse_enum_list(values: Any, *, enum_type: type[TEnum], field_name: str) -> tuple[TEnum, ...]:
    """Parses a sequence of strings into a tuple of enum values."""

    if not isinstance(values, list):
        raise ScriptValidationError(f"Expected '{field_name}' to be a list.", field=field_name)
    parsed: list[TEnum] = []
    for item in values:
        if not isinstance(item, str):
            raise ScriptValidationError(f"Expected '{field_name}' entries to be strings.", field=field_name)
        try:
            parsed.append(enum_type(item))
        except ValueError as error:
            raise ScriptValidationError(
                f"Unsupported value '{item}' for '{field_name}'.",
                field=field_name,
                value=item,
            ) from error
    if not parsed:
        raise ScriptValidationError(f"Expected '{field_name}' to contain at least one value.", field=field_name)
    return tuple(parsed)


def _parse_bool(value: Any, *, field_name: str) -> bool:
    """Parses a strict boolean field."""

    if not isinstance(value, bool):
        raise ScriptValidationError(f"Expected '{field_name}' to be a boolean.", field=field_name)
    return value
