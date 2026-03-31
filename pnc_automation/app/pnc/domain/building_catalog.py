"""Canonical home-city building and slot metadata shared across automation layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.text.normalization import normalize_ocr_text


class BuildingAction(StrEnum):
    """Enumerates the currently modeled home-city building actions."""

    UPGRADE = "upgrade"
    OPEN_TERRITORY_OVERVIEW = "open_territory_overview"
    OPEN_GLORY_LEVEL = "open_glory_level"
    OPEN_DEFENSE_INFO = "open_defense_info"
    OPEN_REPAIR_WALL = "open_repair_wall"
    OPEN_DEVELOPMENT_RESEARCH = "open_development_research"
    OPEN_ECONOMY_RESEARCH = "open_economy_research"
    OPEN_MILITARY_RESEARCH = "open_military_research"
    OPEN_FORTIFICATION_RESEARCH = "open_fortification_research"
    OPEN_TRAP_EFFECT_TABLE = "open_trap_effect_table"
    CRAFT_TRAPS = "craft_traps"
    SPEEDUP_CRAFTING = "speedup_crafting"
    COLLECT_CRAFTED_TRAPS = "collect_crafted_traps"
    CONSTRUCT_FROM_SMALL_SLOT = "construct_from_small_slot"
    OPEN_GEAR_SCREEN = "open_gear_screen"
    OPEN_GEM_SCREEN = "open_gem_screen"
    OPEN_SAURGEM_SCREEN = "open_saurgem_screen"
    OPEN_HERO_CURIO = "open_hero_curio"
    OPEN_WARSIGIL_SCREEN = "open_warsigil_screen"
    OPEN_ASCEND_SCREEN = "open_ascend_screen"
    SEND_BACK_REINFORCEMENTS = "send_back_reinforcements"
    OPEN_REINFORCEMENT_MEMBER_LIST = "open_reinforcement_member_list"
    OPEN_TRANSPORT_MEMBER_LIST = "open_transport_member_list"
    OPEN_UNIT_UNLOCK_TABLE = "open_unit_unlock_table"
    TRAIN_UNITS = "train_units"
    SPEEDUP_TRAINING = "speedup_training"
    COLLECT_TRAINED_UNITS = "collect_trained_units"
    SET_PRIORITIZED_UNIT_TYPE = "set_prioritized_unit_type"
    JOIN_RALLY_ATTACK = "join_rally_attack"
    REINFORCE_ALLIES = "reinforce_allies"
    SET_TROOP_FORMATION = "set_troop_formation"
    OPEN_HERO_HALL_RECRUIT_TAB = "open_hero_hall_recruit_tab"
    SELECT_HERO_RECRUIT_BANNER = "select_hero_recruit_banner"
    RECRUIT_HEROES_1X = "recruit_heroes_1x"
    RECRUIT_HEROES_10X = "recruit_heroes_10x"
    OPEN_HERO_HALL_EXCHANGE_TAB = "open_hero_hall_exchange_tab"
    EXCHANGE_HERO_FRAGMENTS = "exchange_hero_fragments"
    OPEN_ARTIFACT_COLLECTION = "open_artifact_collection"
    OPEN_RELICS = "open_relics"
    OPEN_TRIAL_CHALLENGE = "open_trial_challenge"
    OBTAIN_LIFE_ESSENCE = "obtain_life_essence"
    OPEN_CAMPAIGN = "open_campaign"
    OPEN_VERSUS_CENTER = "open_versus_center"
    SPEEDUP_UPGRADE = "speedup_upgrade"
    OPEN_BLESSING_RECORD = "open_blessing_record"
    HARVEST = "harvest"
    OPEN_RARE_EARTH_FIELD = "open_rare_earth_field"
    OPEN_FIXED_BUILD_MENU = "open_fixed_build_menu"
    OPEN_LARGE_BUILD_MENU = "open_large_build_menu"
    UNLOCK_TERRITORY_REGION = "unlock_territory_region"
    OPEN_SMALL_BUILD_MENU = "open_small_build_menu"


class HomeCityObjectRole(StrEnum):
    """Declares the canonical semantic role of one home-city object."""

    HOME_CITY_BUILDING = "home_city_building"
    REPEATABLE_SMALL_BUILDING = "repeatable_small_building"
    RESERVED_HOME_CITY_SLOT = "reserved_home_city_slot"
    FLEXIBLE_LARGE_BUILD_SLOT = "flexible_large_build_slot"
    LOCKED_TERRITORY_REGION = "locked_territory_region"
    TERRITORY_UNLOCK_CONTROL = "territory_unlock_control"
    FLEXIBLE_SMALL_BUILD_SLOT = "flexible_small_build_slot"


class HomeCityObjectGroup(StrEnum):
    """Groups related home-city objects without collapsing their exact ids."""

    BARRACKS_FAMILY = "barracks_family"
    FIXED_UTILITY_BUILDING_FAMILY = "fixed_utility_building_family"
    LARGE_SUPPORT_BUILDING_FAMILY = "large_support_building_family"
    SMALL_TERRITORY_BUILDING_FAMILY = "small_territory_building_family"


class HomeCityObjectId(StrEnum):
    """Enumerates the canonical home-city buildings and semantically distinct slots."""

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
    HERO_HALL = "hero_hall"
    SANCTUM = "sanctum"
    TOWER_OF_TRIAL = "tower_of_trial"
    SAUROI_LAIR = "sauroi_lair"
    CAMPAIGN = "campaign"
    ARENA = "arena"
    GODDESS_STATUE = "goddess_statue"
    SACRED_TREE = "sacred_tree"
    PIT = "pit"
    BANK = "bank"
    DRAGONDOM_CONQUEST = "dragondom_conquest"
    RESERVED_INSTITUTE_SLOT = "reserved_institute_slot"
    RESERVED_WAREHOUSE_SLOT = "reserved_warehouse_slot"
    RESERVED_TRAP_WORKSHOP_SLOT = "reserved_trap_workshop_slot"
    RESERVED_GODDESS_STATUE_SLOT = "reserved_goddess_statue_slot"
    LARGE_SUPPORT_BUILD_SLOT = "large_support_build_slot"
    LOCKED_TERRITORY_REGION_BELOW_WALL = "locked_territory_region_below_wall"
    TERRITORY_UNLOCK_LOCK_ICON = "territory_unlock_lock_icon"
    SMALL_TERRITORY_BUILD_SLOT = "small_territory_build_slot"


@dataclass(frozen=True, slots=True)
class HomeCityObjectDefinition:
    """Defines one canonical home-city building or semantically distinct slot."""

    id: HomeCityObjectId
    role: HomeCityObjectRole
    display_name: str
    home_city_labels: tuple[str, ...] = ()
    building_group: HomeCityObjectGroup | None = None
    supported_actions: tuple[BuildingAction, ...] = ()
    upgradeable: bool = False
    map_coordinate: "HomeCityMapCoordinate | None" = None


@dataclass(frozen=True, slots=True)
class HomeCityMapCoordinate:
    """Represents one canonical fixed-atlas coordinate on the inferred home-city panorama."""

    x: int
    y: int

    def __post_init__(self) -> None:
        """Rejects invalid negative atlas coordinates before navigation consumes them."""

        if self.x < 0 or self.y < 0:
            raise ValueError("Home-city atlas coordinates must be non-negative integers.")


@dataclass(frozen=True, slots=True)
class HomeCityMapAtlas:
    """Describes the inferred home-city panorama bounds plus its canonical viewport size."""

    width_units: int
    height_units: int
    viewport_width_units: int
    viewport_height_units: int

    def __post_init__(self) -> None:
        """Rejects non-positive atlas geometry before planning relies on it."""

        if self.width_units <= 0 or self.height_units <= 0:
            raise ValueError("Home-city atlas bounds must be positive.")
        if self.viewport_width_units <= 0 or self.viewport_height_units <= 0:
            raise ValueError("Home-city atlas viewport dimensions must be positive.")


_HOME_CITY_MAP_ATLAS = HomeCityMapAtlas(
    width_units=2800,
    height_units=3200,
    viewport_width_units=900,
    viewport_height_units=1600,
)


_HOME_CITY_OBJECT_DEFINITIONS = (
    HomeCityObjectDefinition(
        id=HomeCityObjectId.CASTLE,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Castle",
        home_city_labels=("Castle",),
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_TERRITORY_OVERVIEW,
            BuildingAction.OPEN_GLORY_LEVEL,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=991, y=625),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.WALL,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Wall",
        home_city_labels=("Wall",),
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_DEFENSE_INFO,
            BuildingAction.OPEN_REPAIR_WALL,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1804, y=1831),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.INSTITUTE,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Institute",
        home_city_labels=("Institute", "Academy"),
        building_group=HomeCityObjectGroup.FIXED_UTILITY_BUILDING_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_DEVELOPMENT_RESEARCH,
            BuildingAction.OPEN_ECONOMY_RESEARCH,
            BuildingAction.OPEN_MILITARY_RESEARCH,
            BuildingAction.OPEN_FORTIFICATION_RESEARCH,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1270, y=1121),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.WAREHOUSE,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Warehouse",
        home_city_labels=("Warehouse",),
        building_group=HomeCityObjectGroup.FIXED_UTILITY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.UPGRADE, BuildingAction.OPEN_GLORY_LEVEL),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1449, y=1041),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.TRAP_WORKSHOP,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Trap Workshop",
        home_city_labels=("Trap Workshop",),
        building_group=HomeCityObjectGroup.FIXED_UTILITY_BUILDING_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_TRAP_EFFECT_TABLE,
            BuildingAction.CRAFT_TRAPS,
            BuildingAction.SPEEDUP_CRAFTING,
            BuildingAction.COLLECT_CRAFTED_TRAPS,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1295, y=2237),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.WATCHTOWER,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Watch Tower",
        home_city_labels=("Watch Tower", "Watchtower"),
        supported_actions=(BuildingAction.UPGRADE, BuildingAction.OPEN_GLORY_LEVEL),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1518, y=728),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.FARM,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Farm",
        home_city_labels=("Farm",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.LUMBER_CAMP,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Lumber Camp",
        home_city_labels=("Lumber Camp",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.MOON_WELL,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Moon Well",
        home_city_labels=("Moon Well",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RECRUITING_CENTER,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Recruiting Center",
        home_city_labels=("Recruiting Center",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.INFIRMARY,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Infirmary",
        home_city_labels=("Infirmary",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.IRON_MINE,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Iron Mine",
        home_city_labels=("Iron Mine",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.GOLD_MINE,
        role=HomeCityObjectRole.REPEATABLE_SMALL_BUILDING,
        display_name="Gold Mine",
        home_city_labels=("Gold Mine",),
        building_group=HomeCityObjectGroup.SMALL_TERRITORY_BUILDING_FAMILY,
        supported_actions=(BuildingAction.CONSTRUCT_FROM_SMALL_SLOT, BuildingAction.UPGRADE),
        upgradeable=True,
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.BLACKSMITH,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Blacksmith",
        home_city_labels=("Blacksmith",),
        building_group=HomeCityObjectGroup.LARGE_SUPPORT_BUILDING_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_GEAR_SCREEN,
            BuildingAction.OPEN_GEM_SCREEN,
            BuildingAction.OPEN_SAURGEM_SCREEN,
            BuildingAction.OPEN_HERO_CURIO,
            BuildingAction.OPEN_WARSIGIL_SCREEN,
            BuildingAction.OPEN_ASCEND_SCREEN,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1244, y=1796),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.ALLIANCE_HALL,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Alliance Hall",
        home_city_labels=("Alliance Hall",),
        building_group=HomeCityObjectGroup.LARGE_SUPPORT_BUILDING_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.SEND_BACK_REINFORCEMENTS,
            BuildingAction.OPEN_REINFORCEMENT_MEMBER_LIST,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1881, y=1538),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.MARKET,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Market",
        home_city_labels=("Market",),
        building_group=HomeCityObjectGroup.LARGE_SUPPORT_BUILDING_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_TRANSPORT_MEMBER_LIST,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1568, y=1836),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.INFANTRY_BARRACKS,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Infantry Barracks",
        home_city_labels=("Infantry Barracks",),
        building_group=HomeCityObjectGroup.BARRACKS_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_UNIT_UNLOCK_TABLE,
            BuildingAction.TRAIN_UNITS,
            BuildingAction.SPEEDUP_TRAINING,
            BuildingAction.COLLECT_TRAINED_UNITS,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=660, y=899),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.CAVALRY_BARRACKS,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Cavalry Barracks",
        home_city_labels=("Cavalry Barracks",),
        building_group=HomeCityObjectGroup.BARRACKS_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_UNIT_UNLOCK_TABLE,
            BuildingAction.TRAIN_UNITS,
            BuildingAction.SPEEDUP_TRAINING,
            BuildingAction.COLLECT_TRAINED_UNITS,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=470, y=992),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RANGED_BARRACKS,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Ranged Barracks",
        home_city_labels=("Ranged Barracks",),
        building_group=HomeCityObjectGroup.BARRACKS_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_UNIT_UNLOCK_TABLE,
            BuildingAction.TRAIN_UNITS,
            BuildingAction.SPEEDUP_TRAINING,
            BuildingAction.COLLECT_TRAINED_UNITS,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=668, y=1117),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.SIEGE_FACTORY,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Siege Factory",
        home_city_labels=("Siege Factory", "Siege Barracks"),
        building_group=HomeCityObjectGroup.BARRACKS_FAMILY,
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.OPEN_UNIT_UNLOCK_TABLE,
            BuildingAction.TRAIN_UNITS,
            BuildingAction.SPEEDUP_TRAINING,
            BuildingAction.COLLECT_TRAINED_UNITS,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=400, y=1151),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.HALL_OF_WAR,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Hall of War",
        home_city_labels=("Hall of War",),
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.SET_PRIORITIZED_UNIT_TYPE,
            BuildingAction.JOIN_RALLY_ATTACK,
            BuildingAction.REINFORCE_ALLIES,
            BuildingAction.SET_TROOP_FORMATION,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=996, y=1601),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.HERO_HALL,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Hero Hall",
        home_city_labels=("Hero Hall",),
        supported_actions=(
            BuildingAction.OPEN_HERO_HALL_RECRUIT_TAB,
            BuildingAction.SELECT_HERO_RECRUIT_BANNER,
            BuildingAction.RECRUIT_HEROES_1X,
            BuildingAction.RECRUIT_HEROES_10X,
            BuildingAction.OPEN_HERO_HALL_EXCHANGE_TAB,
            BuildingAction.EXCHANGE_HERO_FRAGMENTS,
        ),
        map_coordinate=HomeCityMapCoordinate(x=1001, y=1216),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.SANCTUM,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Sanctum",
        home_city_labels=("Sanctum",),
        supported_actions=(BuildingAction.OPEN_ARTIFACT_COLLECTION, BuildingAction.OPEN_RELICS),
        map_coordinate=HomeCityMapCoordinate(x=623, y=1974),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.TOWER_OF_TRIAL,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Tower of Trial",
        home_city_labels=("Tower of Trial",),
        supported_actions=(BuildingAction.OPEN_TRIAL_CHALLENGE,),
        map_coordinate=HomeCityMapCoordinate(x=835, y=1639),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.SAUROI_LAIR,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Sauroi Lair",
        home_city_labels=("Sauroi Lair", "Sauregg"),
        supported_actions=(BuildingAction.UPGRADE, BuildingAction.OBTAIN_LIFE_ESSENCE),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1814, y=837),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.CAMPAIGN,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Campaign",
        home_city_labels=("Campaign",),
        supported_actions=(BuildingAction.OPEN_CAMPAIGN,),
        map_coordinate=HomeCityMapCoordinate(x=1854, y=1140),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.ARENA,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Arena",
        home_city_labels=("Arena",),
        supported_actions=(BuildingAction.OPEN_VERSUS_CENTER,),
        map_coordinate=HomeCityMapCoordinate(x=2124, y=958),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.GODDESS_STATUE,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Goddess Statue",
        home_city_labels=("Goddess Statue",),
        supported_actions=(
            BuildingAction.UPGRADE,
            BuildingAction.OPEN_GLORY_LEVEL,
            BuildingAction.SPEEDUP_UPGRADE,
        ),
        upgradeable=True,
        map_coordinate=HomeCityMapCoordinate(x=1046, y=985),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.SACRED_TREE,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Sacred Tree",
        home_city_labels=("Sacred Tree",),
        supported_actions=(BuildingAction.OPEN_BLESSING_RECORD, BuildingAction.HARVEST),
        map_coordinate=HomeCityMapCoordinate(x=1169, y=1793),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.PIT,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Pit",
        home_city_labels=("Pit",),
        supported_actions=(BuildingAction.OPEN_RARE_EARTH_FIELD,),
        map_coordinate=HomeCityMapCoordinate(x=850, y=1710),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.BANK,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Bank",
        home_city_labels=("Bank",),
        map_coordinate=HomeCityMapCoordinate(x=1275, y=1850),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.DRAGONDOM_CONQUEST,
        role=HomeCityObjectRole.HOME_CITY_BUILDING,
        display_name="Dragondom Conquest",
        home_city_labels=("Dragondom Conquest", "Dragondom Cong"),
        map_coordinate=HomeCityMapCoordinate(x=733, y=1583),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RESERVED_INSTITUTE_SLOT,
        role=HomeCityObjectRole.RESERVED_HOME_CITY_SLOT,
        display_name="Reserved Institute Slot",
        supported_actions=(BuildingAction.OPEN_FIXED_BUILD_MENU,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RESERVED_WAREHOUSE_SLOT,
        role=HomeCityObjectRole.RESERVED_HOME_CITY_SLOT,
        display_name="Reserved Warehouse Slot",
        supported_actions=(BuildingAction.OPEN_FIXED_BUILD_MENU,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RESERVED_TRAP_WORKSHOP_SLOT,
        role=HomeCityObjectRole.RESERVED_HOME_CITY_SLOT,
        display_name="Reserved Trap Workshop Slot",
        supported_actions=(BuildingAction.OPEN_FIXED_BUILD_MENU,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.RESERVED_GODDESS_STATUE_SLOT,
        role=HomeCityObjectRole.RESERVED_HOME_CITY_SLOT,
        display_name="Reserved Goddess Statue Slot",
        supported_actions=(BuildingAction.OPEN_FIXED_BUILD_MENU,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.LARGE_SUPPORT_BUILD_SLOT,
        role=HomeCityObjectRole.FLEXIBLE_LARGE_BUILD_SLOT,
        display_name="Large Support Build Slot",
        supported_actions=(BuildingAction.OPEN_LARGE_BUILD_MENU,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.LOCKED_TERRITORY_REGION_BELOW_WALL,
        role=HomeCityObjectRole.LOCKED_TERRITORY_REGION,
        display_name="Locked Territory Region Below Wall",
        supported_actions=(BuildingAction.UNLOCK_TERRITORY_REGION,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.TERRITORY_UNLOCK_LOCK_ICON,
        role=HomeCityObjectRole.TERRITORY_UNLOCK_CONTROL,
        display_name="Territory Unlock Lock Icon",
        supported_actions=(BuildingAction.UNLOCK_TERRITORY_REGION,),
    ),
    HomeCityObjectDefinition(
        id=HomeCityObjectId.SMALL_TERRITORY_BUILD_SLOT,
        role=HomeCityObjectRole.FLEXIBLE_SMALL_BUILD_SLOT,
        display_name="Small Territory Build Slot",
        supported_actions=(BuildingAction.OPEN_SMALL_BUILD_MENU,),
    ),
)

_HOME_CITY_OBJECT_DEFINITION_BY_ID = {definition.id: definition for definition in _HOME_CITY_OBJECT_DEFINITIONS}
_HOME_CITY_OBJECT_DEFINITION_BY_LABEL = {
    normalize_ocr_text(label): definition
    for definition in _HOME_CITY_OBJECT_DEFINITIONS
    for label in definition.home_city_labels
}
_DEFAULT_BUILDING_UPGRADE_PRIORITY = (
    HomeCityObjectId.CASTLE,
    HomeCityObjectId.WALL,
    HomeCityObjectId.INSTITUTE,
    HomeCityObjectId.INFANTRY_BARRACKS,
    HomeCityObjectId.CAVALRY_BARRACKS,
    HomeCityObjectId.RANGED_BARRACKS,
    HomeCityObjectId.SIEGE_FACTORY,
)
_PRIMARY_SCREEN_BY_HOME_CITY_OBJECT_ID = {
    HomeCityObjectId.CASTLE: ScreenType.PNC_CASTLE,
    HomeCityObjectId.HALL_OF_WAR: ScreenType.PNC_HALL_OF_WAR,
    HomeCityObjectId.SACRED_TREE: ScreenType.PNC_SACRED_TREE,
    HomeCityObjectId.PIT: ScreenType.PNC_PIT,
    HomeCityObjectId.SANCTUM: ScreenType.PNC_SANCTUM,
    HomeCityObjectId.TOWER_OF_TRIAL: ScreenType.PNC_TOWER_OF_TRIAL,
    HomeCityObjectId.GODDESS_STATUE: ScreenType.PNC_GODDESS_STATUE,
    HomeCityObjectId.INSTITUTE: ScreenType.PNC_INSTITUTE,
    HomeCityObjectId.WAREHOUSE: ScreenType.PNC_WAREHOUSE,
    HomeCityObjectId.TRAP_WORKSHOP: ScreenType.PNC_TRAP_WORKSHOP,
    HomeCityObjectId.HERO_HALL: ScreenType.PNC_HERO_HALL,
    HomeCityObjectId.WATCHTOWER: ScreenType.PNC_WATCHTOWER,
    HomeCityObjectId.BLACKSMITH: ScreenType.PNC_BLACKSMITH,
    HomeCityObjectId.ALLIANCE_HALL: ScreenType.PNC_ALLIANCE_HALL,
    HomeCityObjectId.MARKET: ScreenType.PNC_MARKET,
    HomeCityObjectId.INFANTRY_BARRACKS: ScreenType.PNC_INFANTRY_BARRACKS,
    HomeCityObjectId.CAVALRY_BARRACKS: ScreenType.PNC_CAVALRY_BARRACKS,
    HomeCityObjectId.RANGED_BARRACKS: ScreenType.PNC_RANGED_BARRACKS,
    HomeCityObjectId.SIEGE_FACTORY: ScreenType.PNC_SIEGE_FACTORY,
    HomeCityObjectId.SAUROI_LAIR: ScreenType.PNC_SAUROI_LAIR,
    HomeCityObjectId.WALL: ScreenType.PNC_WALL,
}
_BUILD_MENU_MATCH_BY_HOME_CITY_OBJECT_ID = {
    HomeCityObjectId.INSTITUTE: (ScreenType.PNC_BUILD_MENU_FIXED_SLOT, UiElementId.PNC_BUILD_INSTITUTE_OPTION),
    HomeCityObjectId.WAREHOUSE: (ScreenType.PNC_BUILD_MENU_FIXED_SLOT, UiElementId.PNC_BUILD_WAREHOUSE_OPTION),
    HomeCityObjectId.TRAP_WORKSHOP: (ScreenType.PNC_BUILD_MENU_FIXED_SLOT, UiElementId.PNC_BUILD_TRAP_WORKSHOP_OPTION),
    HomeCityObjectId.GODDESS_STATUE: (ScreenType.PNC_BUILD_MENU_FIXED_SLOT, UiElementId.PNC_BUILD_GODDESS_STATUE_OPTION),
    HomeCityObjectId.ALLIANCE_HALL: (ScreenType.PNC_BUILD_MENU_LARGE_SLOT, UiElementId.PNC_BUILD_ALLIANCE_HALL_OPTION),
    HomeCityObjectId.BLACKSMITH: (ScreenType.PNC_BUILD_MENU_LARGE_SLOT, UiElementId.PNC_BUILD_BLACKSMITH_OPTION),
    HomeCityObjectId.MARKET: (ScreenType.PNC_BUILD_MENU_LARGE_SLOT, UiElementId.PNC_BUILD_MARKET_OPTION),
    HomeCityObjectId.FARM: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_FARM_OPTION),
    HomeCityObjectId.LUMBER_CAMP: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_LUMBER_CAMP_OPTION),
    HomeCityObjectId.MOON_WELL: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_MOON_WELL_OPTION),
    HomeCityObjectId.RECRUITING_CENTER: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_RECRUITING_CENTER_OPTION),
    HomeCityObjectId.INFIRMARY: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_INFIRMARY_OPTION),
    HomeCityObjectId.IRON_MINE: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_IRON_MINE_OPTION),
    HomeCityObjectId.GOLD_MINE: (ScreenType.PNC_BUILD_MENU_SMALL_SLOT, UiElementId.PNC_BUILD_GOLD_MINE_OPTION),
}
_OWNING_HOME_CITY_OBJECT_ID_BY_SCREEN = {
    ScreenType.PNC_CASTLE: HomeCityObjectId.CASTLE,
    ScreenType.PNC_TERRITORY_OVERVIEW: HomeCityObjectId.CASTLE,
    ScreenType.PNC_HALL_OF_WAR: HomeCityObjectId.HALL_OF_WAR,
    ScreenType.PNC_SACRED_TREE: HomeCityObjectId.SACRED_TREE,
    ScreenType.PNC_SACRED_TREE_BLESSING_RECORD: HomeCityObjectId.SACRED_TREE,
    ScreenType.PNC_OTHER_LORD_SACRED_TREE: HomeCityObjectId.SACRED_TREE,
    ScreenType.PNC_PIT: HomeCityObjectId.PIT,
    ScreenType.PNC_RARE_EARTH_FIELD: HomeCityObjectId.PIT,
    ScreenType.PNC_DISPATCH: HomeCityObjectId.PIT,
    ScreenType.PNC_SANCTUM: HomeCityObjectId.SANCTUM,
    ScreenType.PNC_RELICS: HomeCityObjectId.SANCTUM,
    ScreenType.PNC_TOWER_OF_TRIAL: HomeCityObjectId.TOWER_OF_TRIAL,
    ScreenType.PNC_TRIAL_CHALLENGE: HomeCityObjectId.TOWER_OF_TRIAL,
    ScreenType.PNC_GODDESS_STATUE: HomeCityObjectId.GODDESS_STATUE,
    ScreenType.PNC_INSTITUTE: HomeCityObjectId.INSTITUTE,
    ScreenType.PNC_RESEARCH_TREE: HomeCityObjectId.INSTITUTE,
    ScreenType.PNC_WAREHOUSE: HomeCityObjectId.WAREHOUSE,
    ScreenType.PNC_TRAP_WORKSHOP: HomeCityObjectId.TRAP_WORKSHOP,
    ScreenType.PNC_TRAP_WORKSHOP_EFFECT_TABLE: HomeCityObjectId.TRAP_WORKSHOP,
    ScreenType.PNC_HERO_HALL: HomeCityObjectId.HERO_HALL,
    ScreenType.PNC_WATCHTOWER: HomeCityObjectId.WATCHTOWER,
    ScreenType.PNC_BLACKSMITH: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_GEAR: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_GEM: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_SAURGEM: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_WARSIGIL: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_HERO_CURIO: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_ASCEND: HomeCityObjectId.BLACKSMITH,
    ScreenType.PNC_ALLIANCE_HALL: HomeCityObjectId.ALLIANCE_HALL,
    ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE: HomeCityObjectId.ALLIANCE_HALL,
    ScreenType.PNC_MARKET: HomeCityObjectId.MARKET,
    ScreenType.PNC_ALLIANCE_MEMBER_TRANSPORT: HomeCityObjectId.MARKET,
    ScreenType.PNC_INFANTRY_BARRACKS: HomeCityObjectId.INFANTRY_BARRACKS,
    ScreenType.PNC_CAVALRY_BARRACKS: HomeCityObjectId.CAVALRY_BARRACKS,
    ScreenType.PNC_RANGED_BARRACKS: HomeCityObjectId.RANGED_BARRACKS,
    ScreenType.PNC_SIEGE_FACTORY: HomeCityObjectId.SIEGE_FACTORY,
    ScreenType.PNC_SAUROI_LAIR: HomeCityObjectId.SAUROI_LAIR,
    ScreenType.PNC_SAUREGG: HomeCityObjectId.SAUROI_LAIR,
    ScreenType.PNC_WALL: HomeCityObjectId.WALL,
    ScreenType.PNC_DEFENSE_INFO: HomeCityObjectId.WALL,
    ScreenType.PNC_CAMPAIGN_MAP: HomeCityObjectId.CAMPAIGN,
    ScreenType.PNC_VERSUS_CENTER: HomeCityObjectId.ARENA,
}
_UPGRADEABLE_PRIMARY_SCREEN_TYPES = frozenset(
    screen_type
    for home_city_object_id, screen_type in _PRIMARY_SCREEN_BY_HOME_CITY_OBJECT_ID.items()
    if _HOME_CITY_OBJECT_DEFINITION_BY_ID[home_city_object_id].upgradeable
)


def home_city_object_definition(home_city_object_id: HomeCityObjectId) -> HomeCityObjectDefinition:
    """Returns one required canonical home-city object definition."""

    return _HOME_CITY_OBJECT_DEFINITION_BY_ID[home_city_object_id]


def home_city_object_definition_for_label(label_text: str) -> HomeCityObjectDefinition | None:
    """Returns the canonical home-city object definition implied by one OCR-visible label."""

    return _HOME_CITY_OBJECT_DEFINITION_BY_LABEL.get(normalize_ocr_text(label_text))


def default_building_upgrade_priority() -> tuple[HomeCityObjectId, ...]:
    """Returns the canonical default upgrade priority used by policy parsing and APIs."""

    return _DEFAULT_BUILDING_UPGRADE_PRIORITY


def home_city_map_atlas() -> HomeCityMapAtlas:
    """Returns the canonical inferred home-city atlas shared by navigation and smoke tests."""

    return _HOME_CITY_MAP_ATLAS


def home_city_map_coordinate(home_city_object_id: HomeCityObjectId) -> HomeCityMapCoordinate | None:
    """Returns the inferred atlas coordinate for one exact home-city object when recorded."""

    return home_city_object_definition(home_city_object_id).map_coordinate


def known_home_city_map_object_ids() -> tuple[HomeCityObjectId, ...]:
    """Returns the exact home-city objects that currently have recorded atlas coordinates."""

    return tuple(
        definition.id
        for definition in _HOME_CITY_OBJECT_DEFINITIONS
        if definition.map_coordinate is not None
    )


def primary_screen_type_for_home_city_object(home_city_object_id: HomeCityObjectId) -> ScreenType | None:
    """Returns the primary interaction screen currently owned by one home-city object, when modeled."""

    return _PRIMARY_SCREEN_BY_HOME_CITY_OBJECT_ID.get(home_city_object_id)


def home_city_object_id_for_screen(screen_type: ScreenType) -> HomeCityObjectId | None:
    """Returns the owning home-city object id for one modeled building-owned screen."""

    return _OWNING_HOME_CITY_OBJECT_ID_BY_SCREEN.get(screen_type)


def build_menu_screen_type_for_home_city_object(home_city_object_id: HomeCityObjectId) -> ScreenType | None:
    """Returns the build-menu screen family that proves one unbuilt home-city target was opened."""

    build_menu_match = _BUILD_MENU_MATCH_BY_HOME_CITY_OBJECT_ID.get(home_city_object_id)
    return None if build_menu_match is None else build_menu_match[0]


def build_menu_option_selector_for_home_city_object(home_city_object_id: HomeCityObjectId) -> UiElementId | None:
    """Returns the exact build-menu option selector that proves one unbuilt home-city target was opened."""

    build_menu_match = _BUILD_MENU_MATCH_BY_HOME_CITY_OBJECT_ID.get(home_city_object_id)
    return None if build_menu_match is None else build_menu_match[1]


def is_upgradeable_primary_screen(screen_type: ScreenType) -> bool:
    """Returns whether one screen is the primary detail screen for an upgradeable home-city building."""

    return screen_type in _UPGRADEABLE_PRIMARY_SCREEN_TYPES


def is_repeatable_home_city_object(home_city_object_id: HomeCityObjectId) -> bool:
    """Returns whether one home-city object id represents a repeatable small-building instance."""

    return home_city_object_definition(home_city_object_id).role == HomeCityObjectRole.REPEATABLE_SMALL_BUILDING


def is_home_city_object_usable_as_atlas_anchor(home_city_object_id: HomeCityObjectId) -> bool:
    """Returns whether one home-city object id is unique enough to anchor viewport inference on the static atlas."""

    return home_city_object_definition(home_city_object_id).role in {
        HomeCityObjectRole.HOME_CITY_BUILDING,
        HomeCityObjectRole.RESERVED_HOME_CITY_SLOT,
        HomeCityObjectRole.LOCKED_TERRITORY_REGION,
        HomeCityObjectRole.TERRITORY_UNLOCK_CONTROL,
    }


def home_city_object_id_from_metadata(metadata: object) -> HomeCityObjectId | None:
    """Returns one canonical home-city object id from spatial-object metadata when present."""

    if not isinstance(metadata, dict):
        return None
    value = metadata.get("home_city_object_id")
    if not isinstance(value, str):
        return None
    try:
        return HomeCityObjectId(value)
    except ValueError:
        return None


def home_city_object_supports_action(metadata: object, action: BuildingAction) -> bool:
    """Returns whether one metadata mapping exposes the requested canonical building action."""

    if not isinstance(metadata, dict):
        return False
    supported_actions = metadata.get("supported_actions")
    if not isinstance(supported_actions, tuple):
        return False
    return action.value in supported_actions


def build_home_city_object_metadata(home_city_object_id: HomeCityObjectId) -> dict[str, object]:
    """Builds canonical spatial metadata for one parsed home-city object."""

    definition = home_city_object_definition(home_city_object_id)
    metadata: dict[str, object] = {
        "home_city_object_id": definition.id.value,
        "home_city_object_role": definition.role.value,
        "supported_actions": tuple(action.value for action in definition.supported_actions),
        "upgradeable": definition.upgradeable,
    }
    if definition.building_group is not None:
        metadata["building_group"] = definition.building_group.value
    if definition.map_coordinate is not None:
        metadata["home_city_map_coordinate"] = (definition.map_coordinate.x, definition.map_coordinate.y)
    return metadata
