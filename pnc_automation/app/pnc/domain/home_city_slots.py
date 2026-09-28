"""Typed Home-city slot eligibility and occupancy models.

Static slot eligibility comes from the client's ``BuildingPosition`` table
recovered from the PNC 5.0.203/233 APK (XOR-0x2c payload,
sha256 ``81538538b0a9e118da2d0f48cf802cada4dde2bf64f55f25c94fed5ab0e56574``,
with the table's declared defaults applied).  The table defines 54 ordinary
slots: 16 single-type fixed slots and 38 multi-type slots whose occupant the
player chooses.  Client ``BuildIdType`` members bind to canonical
``HomeCityObjectId`` values only where dispatcher, build-menu, or
live-verified evidence exists; unbound types stay unbound instead of guessing
a semantic identity.

Eligibility is *not* occupancy.  What a slot may legally hold says nothing
about what the connected account actually built there: multi-type occupants
are runtime observations scoped to the current castle identity.  Every
ordinary slot and every extracted ``sys_*`` marker publishes a calibrated
atlas pivot from the reviewed CityScene transform fit — candidate search
geometry, never tap authorization, a body target, a route, or occupancy.
Single-type slots additionally keep their bound occupant's catalog map
coordinate as an inferred search hint.  Slot indices are scene handles,
not coordinates, and are never used to infer atlas positions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityMapCoordinate,
    HomeCityObjectId,
    home_city_object_definition,
)
from pnc_automation.core.errors import SelectorResolutionError


class HomeCitySlotKind(StrEnum):
    """Identifies whether the client pinned one building type to a slot."""

    SINGLE_TYPE = "single_type"
    MULTI_TYPE = "multi_type"


class HomeCitySlotOccupancyState(StrEnum):
    """Disposition of one slot's current-account occupancy observation."""

    OCCUPIED = "occupied"
    EMPTY = "empty"
    LOCKED = "locked"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class HomeCitySlotSelector:
    """Identifies one ordinary Home-city build slot by index.

    The selector names slot identity only: it is never an occupant claim, a
    system-node reference, or an authorization.  Indices are scene handles in
    the client ``BuildingPosition`` range ``1..54``.
    """

    slot_index: int

    def __post_init__(self) -> None:
        """Rejects booleans, non-integers, and out-of-range slot handles."""

        if (
            not isinstance(self.slot_index, int)
            or isinstance(self.slot_index, bool)
            or not 1 <= self.slot_index <= 54
        ):
            raise SelectorResolutionError(
                "Home-city slot selectors require an integer index in 1..54.",
                slot_index=self.slot_index,
            )


@dataclass(frozen=True, slots=True)
class HomeCityClientBuildingType:
    """Binds one client ``BuildIdType`` member to its semantic object and destination."""

    client_type_id: int
    client_name: str
    object_id: HomeCityObjectId | None
    window_prefab: str | None
    binding_evidence: str | None

    @property
    def bound(self) -> bool:
        """Returns whether this client type has a verified semantic binding."""

        return self.object_id is not None


@dataclass(frozen=True, slots=True)
class HomeCitySlotEligibility:
    """Static client eligibility for one ordinary Home-city build slot."""

    slot_index: int
    area_id: int
    kind: HomeCitySlotKind
    init_position: bool
    client_type_ids: frozenset[int]
    eligible_object_ids: frozenset[HomeCityObjectId]
    unlock_cost_item_id: int | None
    unlock_cost_count: int | None
    atlas_coordinate: HomeCityMapCoordinate | None
    coordinate_evidence: str | None
    inferred_atlas_coordinate: HomeCityMapCoordinate | None
    inferred_coordinate_source: str | None

    def __post_init__(self) -> None:
        """Keeps qualified geometry and nominal hints on separate evidence.

        ``atlas_coordinate`` is verified slot geometry and therefore requires
        named qualification evidence; the building catalog's map coordinate is
        an inferred scene anchor and may only feed ``inferred_atlas_coordinate``.
        """

        if self.atlas_coordinate is not None:
            if not self.coordinate_evidence:
                raise SelectorResolutionError(
                    "A calibrated slot coordinate requires named qualification evidence.",
                    slot_index=self.slot_index,
                )
            if self.coordinate_evidence.startswith(_CATALOG_INFERENCE_SOURCE):
                raise SelectorResolutionError(
                    "Catalog map coordinates are inferred search hints, not calibration evidence.",
                    slot_index=self.slot_index,
                    coordinate_evidence=self.coordinate_evidence,
                )
        elif self.coordinate_evidence is not None:
            raise SelectorResolutionError(
                "Coordinate qualification evidence requires a calibrated coordinate.",
                slot_index=self.slot_index,
            )
        if self.inferred_atlas_coordinate is not None and (
            not self.inferred_coordinate_source
        ):
            raise SelectorResolutionError(
                "An inferred slot coordinate must name its source.",
                slot_index=self.slot_index,
            )

    @property
    def calibrated(self) -> bool:
        """Returns whether this slot has evidence-backed atlas geometry."""

        return self.atlas_coordinate is not None


@dataclass(frozen=True, slots=True)
class HomeCitySystemNodeEligibility:
    """Static client eligibility for one declared system scene node."""

    client_type_id: int
    client_name: str
    node_path: str
    object_id: HomeCityObjectId | None
    required_castle_level: int
    atlas_coordinate: HomeCityMapCoordinate
    coordinate_evidence: str

    def __post_init__(self) -> None:
        """Keeps the calibrated pivot bound to its named evidence."""

        if not self.coordinate_evidence:
            raise SelectorResolutionError(
                "A calibrated system-node coordinate requires named qualification evidence.",
                client_type_id=self.client_type_id,
            )


@dataclass(frozen=True, slots=True)
class HomeCitySystemMarker:
    """Calibrated geometry of one extracted ``sys_*`` scene marker.

    Marker geometry is independent of semantic eligibility: the scene ships 16
    markers while the decoded ``BuildingSystem`` table declares only 15, so an
    extracted marker can exist without a declared node (``sys_13``) and a
    declared node can stay semantically unbound (``5014``).
    """

    marker: str
    implied_client_type_id: int
    declared_in_system_table: bool
    node_path: str
    atlas_coordinate: HomeCityMapCoordinate
    coordinate_evidence: str


@dataclass(frozen=True, slots=True)
class HomeCityGeometryExtent:
    """Measured atlas extent of the extracted scene markers.

    This is a geometry extent only: it is not a camera boundary, movement
    clamp, or reachability claim.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass(frozen=True, slots=True)
class HomeCitySceneCalibration:
    """Provenance and uncertainty of the published CityScene pivot calibration."""

    transform_model: str
    scale: float
    translate_x: float
    translate_y: float
    uncertainty_reference_px: float
    leave_one_out_max_reference_px: float
    extent: HomeCityGeometryExtent
    archived_build: str


@dataclass(frozen=True, slots=True)
class HomeCitySlotOccupancy:
    """One current-account occupancy observation for a slot, scoped by evidence.

    Occupancy is runtime evidence, never static eligibility: it is produced by
    observing the connected castle and must be invalidated when the account or
    castle identity changes or the observation goes stale.
    """

    slot_index: int
    state: HomeCitySlotOccupancyState
    observed_object_id: HomeCityObjectId | None
    evidence: str

    def __post_init__(self) -> None:
        """Rejects occupancy claims without evidence or with impossible fields."""

        if not self.evidence:
            raise SelectorResolutionError(
                "Slot occupancy requires observation evidence.",
                slot_index=self.slot_index,
            )
        if self.state == HomeCitySlotOccupancyState.OCCUPIED and self.observed_object_id is None:
            raise SelectorResolutionError(
                "An occupied slot must name its observed occupant.",
                slot_index=self.slot_index,
            )
        if (
            self.state != HomeCitySlotOccupancyState.OCCUPIED
            and self.observed_object_id is not None
        ):
            raise SelectorResolutionError(
                "Only an occupied slot may publish an observed occupant.",
                slot_index=self.slot_index,
                state=self.state.value,
            )


# Client BuildIdType bindings verified against the recovered city dispatcher
# (gameplay-lua scenes/cityscene build item handlers), the reviewed building-
# endpoints workflow note, the decoded build-menu icon tables, and the
# September 2026 live route audit.  Types without such evidence stay unbound.
_HOME_CITY_CLIENT_BUILDING_TYPES = (
    HomeCityClientBuildingType(1001, "CASTLEID", HomeCityObjectId.CASTLE, "CASTLE_BUILD_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1002, "WALLID", HomeCityObjectId.WALL, "WALL_WIN", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(1003, "CAMPID", HomeCityObjectId.RECRUITING_CENTER, "TRAININGCAMP_BUILD_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1004, "INFIRMARYID", HomeCityObjectId.INFIRMARY, "INFIRMARY_WIN2", "client_dispatcher"),
    HomeCityClientBuildingType(1005, "CELLARID", HomeCityObjectId.WAREHOUSE, "CELLAR_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1006, "WATCHTOWERID", HomeCityObjectId.WATCHTOWER, "TOWER_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1007, "COLLEGEID", HomeCityObjectId.INSTITUTE, "COLLEGE_PANEL", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(1008, "CONSTRUCTIONID", HomeCityObjectId.BLACKSMITH, "EQUIP_ENTER_WIN", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(1009, "FAIRID", HomeCityObjectId.MARKET, "FAIR_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1010, "EMBASSYID", HomeCityObjectId.ALLIANCE_HALL, "EMBASSY_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1011, "WARID", HomeCityObjectId.HALL_OF_WAR, "WAR_HALL_WIN", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(1015, "MANORID", HomeCityObjectId.GOLD_MINE, "RES_BUILD_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1016, "FARMID", HomeCityObjectId.FARM, "RES_BUILD_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1017, "LOGGINGID", HomeCityObjectId.LUMBER_CAMP, "RES_BUILD_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1019, "PITID", HomeCityObjectId.IRON_MINE, "RES_BUILD_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1020, "CAMP_BUBING", HomeCityObjectId.INFANTRY_BARRACKS, "CAMP_PANEL", "client_dispatcher+builditem_name"),
    HomeCityClientBuildingType(1021, "CAMP_QIBING", HomeCityObjectId.CAVALRY_BARRACKS, "CAMP_PANEL", "client_dispatcher+builditem_name"),
    HomeCityClientBuildingType(1022, "CAMP_GONGBING", HomeCityObjectId.RANGED_BARRACKS, "CAMP_PANEL", "client_dispatcher+builditem_name"),
    HomeCityClientBuildingType(1023, "CAMP_CHEBING", HomeCityObjectId.SIEGE_FACTORY, "CAMP_PANEL", "client_dispatcher+builditem_name"),
    HomeCityClientBuildingType(1024, "TREVI_FOUNTAIN", HomeCityObjectId.GODDESS_STATUE, "TREVI_FOUNTAIN_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1025, "TRAP", HomeCityObjectId.TRAP_WORKSHOP, "TROP_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(1026, "VALKYRIE", None, None, "client_dispatcher_empty_branch"),
    HomeCityClientBuildingType(1027, "SOUL_MINE", HomeCityObjectId.MOON_WELL, "RES_BUILD_WIN", "client_dispatcher+build_menu_icons"),
    HomeCityClientBuildingType(1028, "HERO_RUNE", None, None, "unbound"),
    HomeCityClientBuildingType(1029, "SEASON_TECH", None, None, "unbound"),
    HomeCityClientBuildingType(1030, "WARGOD_MECHA", None, None, "unbound"),
    HomeCityClientBuildingType(5001, "BANK", HomeCityObjectId.BANK, "TREASURE_CAVE_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(5002, "HEROWARID", None, None, "unbound"),
    HomeCityClientBuildingType(5003, "REMAINS", HomeCityObjectId.DRAGONDOM_CONQUEST, "DRAGON_CAVE_MAIN_WIN", "client_dispatcher"),
    HomeCityClientBuildingType(5004, "MERCHANTMANID", None, "activity_shop", "client_dispatcher_no_semantic_binding"),
    HomeCityClientBuildingType(5005, "BILLBOARD", None, None, "unbound"),
    HomeCityClientBuildingType(5006, "GROUND", None, None, "unbound"),
    HomeCityClientBuildingType(5007, "TREASURE", None, None, "client_dispatcher_empty_branch"),
    HomeCityClientBuildingType(5008, "PUB", HomeCityObjectId.HERO_HALL, "Pub_Main_View", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(5009, "MINE_HOLE", HomeCityObjectId.PIT, "MineWarData:sendOpenMineMainWin", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(5010, "ARENA_BUILD", HomeCityObjectId.ARENA, "ARENA_ENTER_HUB", "client_dispatcher+live_202609"),
    HomeCityClientBuildingType(5011, "FESTIVAL_DECORATE", None, None, "unbound"),
    HomeCityClientBuildingType(5012, "OVERLORD_WAR_ENTER", None, None, "unbound"),
    # 5013 TOWER_DEFEND is declared in BuildIdType but absent from the decoded
    # BuildingSystem table; the semantic Tower-of-Trial binding stays unverified.
    HomeCityClientBuildingType(5013, "TOWER_DEFEND", None, None, "unbound_absent_from_system_table"),
    HomeCityClientBuildingType(5014, "FARM_ENTER", None, None, "unbound"),
    HomeCityClientBuildingType(5015, "BUILD_ENTER_15", HomeCityObjectId.SACRED_TREE, "WATER_FLOWER_WIN", "client_dispatcher+live_202609"),
    # 5016 BEAST_MANOR is the Illusory Beast Manor: the archived sys_16 scene
    # marker and the reviewed 2026-09-21 PW destination evidence (verified tap
    # (511,722) -> PNC_ILLUSORY_BEAST_MANOR) support the semantic binding.
    HomeCityClientBuildingType(
        5016,
        "BEAST_MANOR",
        HomeCityObjectId.ILLUSORY_BEAST_MANOR,
        "ln_ENTER_VIEW",
        "client_dispatcher+pw_destination_20260921",
    ),
    # 9999 HIDEWARID is a wall-hide flag, not a building; intentionally absent.
)


def _decode_slot_rows() -> tuple[tuple[int, int, str, int, str, int, int], ...]:
    """Returns the decoded ``BuildingPosition`` rows with defaults applied.

    Each row is ``(slot_index, area_id, building_id_spec, init_position,
    cost_item_spec, cost_item_id, cost_count)``.  The client table's declared
    defaults (``areaId=1`` and the seven-type small-slot eligibility
    ``1016|1017|1027|1003|1004|1019|1015``) are applied where rows omit them.
    """

    return (
        (1, 1, "1001", 1, "", 0, 0),
        (2, 1, "1002", 1, "", 0, 0),
        (3, 1, "1005", 1, "", 0, 0),
        (4, 1, "1006", 1, "", 0, 0),
        (5, 1, "1020", 1, "", 0, 0),
        (6, 1, "1021", 1, "", 0, 0),
        (7, 1, "1022", 1, "", 0, 0),
        (8, 1, "1023", 1, "", 0, 0),
        (9, 1, "1007", 0, "", 0, 0),
        (10, 1, "1025", 0, "", 0, 0),
        (11, 1, "1010|1008|1009", 0, "", 0, 0),
        (12, 1, "1010|1008|1009", 0, "", 0, 0),
        (13, 1, "1010|1008|1009", 0, "", 0, 0),
        (14, 1, "1011", 0, "", 0, 0),
        (15, 1, "1024", 0, "", 0, 0),
        (16, 1, "1026", 1, "", 0, 0),
        (17, 2, "", 0, "", 0, 0),
        (18, 2, "", 0, "", 0, 0),
        (19, 2, "", 0, "", 0, 0),
        (20, 2, "", 0, "", 0, 0),
        (21, 3, "", 0, "", 0, 0),
        (22, 3, "", 0, "", 0, 0),
        (23, 3, "", 0, "", 0, 0),
        (24, 3, "", 0, "", 0, 0),
        (25, 3, "", 0, "", 0, 0),
        (26, 3, "", 0, "", 0, 0),
        (27, 4, "", 0, "", 0, 0),
        (28, 4, "", 0, "", 0, 0),
        (29, 4, "", 0, "", 0, 0),
        (30, 4, "", 0, "", 0, 0),
        (31, 4, "", 0, "", 0, 0),
        (32, 5, "", 0, "", 0, 0),
        (33, 5, "", 0, "", 0, 0),
        (34, 5, "", 0, "", 0, 0),
        (35, 5, "", 0, "", 0, 0),
        (36, 5, "", 0, "", 0, 0),
        (37, 6, "", 0, "", 0, 0),
        (38, 6, "", 0, "", 0, 0),
        (39, 6, "", 0, "", 0, 0),
        (40, 6, "", 0, "", 0, 0),
        (41, 6, "", 0, "", 0, 0),
        (42, 7, "", 0, "", 0, 0),
        (43, 7, "", 0, "", 0, 0),
        (44, 7, "", 0, "", 0, 0),
        (45, 7, "", 0, "", 0, 0),
        (46, 7, "", 0, "", 0, 0),
        (47, 8, "", 0, "cost", 12031001, 100),
        (48, 8, "", 0, "cost", 12031001, 500),
        (49, 8, "", 0, "cost", 12031001, 5000),
        (50, 8, "", 0, "cost", 12031001, 10000),
        (51, 8, "", 0, "cost", 12031001, 10000),
        (52, 1, "1028", 1, "cost", 12031001, 100),
        (53, 1, "1029", 0, "", 0, 0),
        (54, 1, "1030", 0, "", 0, 0),
    )


_DEFAULT_SLOT_TYPE_IDS = frozenset({1016, 1017, 1027, 1003, 1004, 1019, 1015})

# Evidence prefix reserved for coordinates inferred from the building catalog's
# authored map anchors; it can never qualify slot geometry on its own.
_CATALOG_INFERENCE_SOURCE = "catalog_map_coordinate"

# Named qualification evidence for the published CityScene pivot calibration;
# full provenance lives in the packaged artifact's ``provenance`` section.
_SCENE_PIVOT_EVIDENCE = "cityscene_pivot_calibration_20260922"

_SCENE_GEOMETRY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "home_city" / "scene_geometry.json"
)

# Decoded ``BuildingSystem`` rows: client type -> required castle level.
_SYSTEM_NODE_CASTLE_LEVELS = {
    5001: 1,
    5002: 1,
    5003: 10,
    5004: 12,
    5005: 3,
    5006: 1,
    5007: 6,
    5008: 1,
    5009: 16,
    5010: 1,
    5011: 1,
    5012: 1,
    5014: 15,
    5015: 9,
    5016: 24,
}


@lru_cache(maxsize=1)
def _client_type_by_id() -> dict[int, HomeCityClientBuildingType]:
    return {entry.client_type_id: entry for entry in _HOME_CITY_CLIENT_BUILDING_TYPES}


@lru_cache(maxsize=1)
def _scene_geometry() -> Mapping[str, Any]:
    """Loads and shape-checks the packaged scene-geometry artifact once."""

    try:
        data = json.loads(_SCENE_GEOMETRY_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SelectorResolutionError(
            "The packaged Home-city scene geometry is unavailable.",
            path=str(_SCENE_GEOMETRY_PATH),
        ) from exc
    slots = data.get("ordinary_slots")
    markers = data.get("system_markers")
    if (
        data.get("schema") != "home_city_scene_geometry"
        or data.get("version") != 1
        or not isinstance(slots, list)
        or [slot.get("slot_index") for slot in slots] != list(range(1, 55))
        or not isinstance(markers, list)
        or [marker.get("marker") for marker in markers] != [f"sys_{index}" for index in range(1, 17)]
    ):
        raise SelectorResolutionError(
            "The packaged Home-city scene geometry does not cover slots 1..54 and sys_1..sys_16.",
            path=str(_SCENE_GEOMETRY_PATH),
        )
    return data


def _pivot(record: Mapping[str, Any]) -> HomeCityMapCoordinate:
    """Returns the calibrated atlas pivot of one packaged geometry record."""

    x, y = record["atlas_pivot"]
    return HomeCityMapCoordinate(x=x, y=y)


@lru_cache(maxsize=1)
def home_city_scene_calibration() -> HomeCitySceneCalibration:
    """Returns the published CityScene pivot calibration metadata.

    The calibration qualifies candidate *search* geometry only: it carries no
    occupancy, tap, body-target, route, or camera-boundary authority.
    """

    data = _scene_geometry()
    transform = data["transform"]
    calibration = data["calibration"]
    extent = data["measured_extent_atlas"]
    archived = data["provenance"]["archived_build"]
    return HomeCitySceneCalibration(
        transform_model=transform["model"],
        scale=transform["k"],
        translate_x=transform["tx"],
        translate_y=transform["ty"],
        uncertainty_reference_px=calibration["uncertainty_reference_px"],
        leave_one_out_max_reference_px=calibration["leave_one_out_max_reference_px"],
        extent=HomeCityGeometryExtent(
            min_x=extent["min_x"],
            min_y=extent["min_y"],
            max_x=extent["max_x"],
            max_y=extent["max_y"],
        ),
        archived_build=f"{archived['version_name']}/{archived['version_code']}",
    )


@lru_cache(maxsize=1)
def home_city_slot_eligibility() -> tuple[HomeCitySlotEligibility, ...]:
    """Returns the 54 static ordinary-slot eligibility records in slot order.

    Every slot publishes its calibrated atlas pivot — measured candidate search
    geometry, never tap or route authorization.  Single-type slots also inherit
    their bound occupant's catalog map coordinate as an *inferred* search hint
    only; the hint stays separate from the calibrated pivot.
    """

    type_by_id = _client_type_by_id()
    slots: list[HomeCitySlotEligibility] = []
    for slot_index, area_id, id_spec, init_position, _cost_flag, cost_item, cost_count in _decode_slot_rows():
        type_ids = frozenset(
            int(part) for part in id_spec.split("|") if part
        ) or _DEFAULT_SLOT_TYPE_IDS
        object_ids = frozenset(
            entry.object_id
            for entry in (type_by_id[type_id] for type_id in type_ids)
            if entry.object_id is not None
        )
        inferred_coordinate = None
        inferred_source = None
        if len(type_ids) == 1 and len(object_ids) == 1:
            definition = home_city_object_definition(next(iter(object_ids)))
            if definition.map_coordinate is not None:
                inferred_coordinate = definition.map_coordinate
                inferred_source = (
                    f"{_CATALOG_INFERENCE_SOURCE}:{definition.id.value}"
                )
        slots.append(
            HomeCitySlotEligibility(
                slot_index=slot_index,
                area_id=area_id,
                kind=HomeCitySlotKind.SINGLE_TYPE if len(type_ids) == 1 else HomeCitySlotKind.MULTI_TYPE,
                init_position=bool(init_position),
                client_type_ids=type_ids,
                eligible_object_ids=object_ids,
                unlock_cost_item_id=cost_item or None,
                unlock_cost_count=cost_count or None,
                atlas_coordinate=_pivot(_scene_geometry()["ordinary_slots"][slot_index - 1]),
                coordinate_evidence=_SCENE_PIVOT_EVIDENCE,
                inferred_atlas_coordinate=inferred_coordinate,
                inferred_coordinate_source=inferred_source,
            )
        )
    return tuple(slots)


@lru_cache(maxsize=1)
def home_city_system_markers() -> tuple[HomeCitySystemMarker, ...]:
    """Returns all 16 extracted ``sys_*`` scene markers in marker order.

    Marker geometry is published for every extracted node regardless of
    semantic binding: ``sys_13`` appears here even though its implied client
    type is absent from the decoded ``BuildingSystem`` table.  ``sys_16``'s
    implied type ``5016`` binds to the Illusory Beast Manor through the
    reviewed PW destination evidence.
    """

    return tuple(
        HomeCitySystemMarker(
            marker=record["marker"],
            implied_client_type_id=record["implied_client_type_id"],
            declared_in_system_table=record["declared_in_system_table"],
            node_path=record["node_path"],
            atlas_coordinate=_pivot(record),
            coordinate_evidence=_SCENE_PIVOT_EVIDENCE,
        )
        for record in _scene_geometry()["system_markers"]
    )


@lru_cache(maxsize=1)
def home_city_system_nodes() -> tuple[HomeCitySystemNodeEligibility, ...]:
    """Returns the 15 declared system scene nodes in client-type order."""

    type_by_id = _client_type_by_id()
    marker_by_type = {marker.implied_client_type_id: marker for marker in home_city_system_markers()}
    return tuple(
        HomeCitySystemNodeEligibility(
            client_type_id=type_id,
            client_name=type_by_id[type_id].client_name,
            node_path=f"sys_{type_id - 5000}/{type_id}",
            object_id=type_by_id[type_id].object_id,
            required_castle_level=castle_level,
            atlas_coordinate=marker_by_type[type_id].atlas_coordinate,
            coordinate_evidence=_SCENE_PIVOT_EVIDENCE,
        )
        for type_id, castle_level in sorted(_SYSTEM_NODE_CASTLE_LEVELS.items())
    )


def home_city_client_building_type(client_type_id: int) -> HomeCityClientBuildingType | None:
    """Returns the binding record for one client ``BuildIdType`` id."""

    return _client_type_by_id().get(client_type_id)


def home_city_slot(slot_index: int) -> HomeCitySlotEligibility:
    """Returns the static eligibility record for one slot index."""

    for slot in home_city_slot_eligibility():
        if slot.slot_index == slot_index:
            return slot
    raise SelectorResolutionError(
        "Unknown Home-city slot index.",
        slot_index=slot_index,
    )


def home_city_slots_for_object(object_id: HomeCityObjectId) -> tuple[HomeCitySlotEligibility, ...]:
    """Returns the slots whose static eligibility permits one semantic object."""

    return tuple(
        slot for slot in home_city_slot_eligibility() if object_id in slot.eligible_object_ids
    )


def validate_home_city_slot_selector(
    object_id: HomeCityObjectId, selector: HomeCitySlotSelector | None
) -> None:
    """Reject an incompatible exact-instance request before observing or acting."""

    if selector is None:
        return
    if not isinstance(selector, HomeCitySlotSelector):
        raise SelectorResolutionError("An exact building instance requires HomeCitySlotSelector.")
    if object_id not in home_city_slot(selector.slot_index).eligible_object_ids:
        raise SelectorResolutionError(
            "The selected Home-city slot cannot host the requested building.",
            target=object_id.value,
            slot_index=selector.slot_index,
        )
