"""Canonical screen-family OCR capability registry shared by requests and enrichment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType


class ScreenFamilyOcrStrategy(StrEnum):
    """Declares how a registered screen family may obtain content OCR."""

    REVIEWED_REGION_PLAN = "reviewed_region_plan"
    GUARDED_FULL_FRAME_REUSE = "guarded_full_frame_reuse"


@dataclass(frozen=True, slots=True)
class ScreenFamilyOcrCapability:
    """Typed content strategy for one registered screen family."""

    family: ScreenType
    strategy: ScreenFamilyOcrStrategy
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        """Keep fallback diagnostics explicit and reviewed plans unambiguous."""

        if self.strategy == ScreenFamilyOcrStrategy.REVIEWED_REGION_PLAN:
            if self.fallback_reason is not None:
                raise ValueError("Reviewed region plans cannot carry a fallback reason.")
        elif self.fallback_reason is None:
            raise ValueError("Guarded full-frame strategies require a fallback reason.")


FAMILY_REGIONS_NOT_REVIEWED = "family_regions_not_reviewed"

# These families are backed by compiled fixed-field, coordinate, or body-row
# region-plan owners. Other families retain the guarded full-frame strategy.
_REVIEWED_REGION_PLAN_FAMILIES = frozenset(
    {
        ScreenType.PNC_BAG,
        ScreenType.PNC_CHAT,
        ScreenType.PNC_MAIL_COMPOSE_POPUP,
        ScreenType.PNC_QUEST_MAIN,
        ScreenType.PNC_QUEST_DAILY,
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        ScreenType.PNC_WORLD_MAP,
    }
)

_HOME_CITY_ADJACENT_SCREENS = frozenset(
    {
        ScreenType.UNKNOWN,
        ScreenType.PNC_CASTLE_SELECTION,
        ScreenType.PNC_HOME_CITY_ROOT,
        ScreenType.PNC_HOME_CITY,
        ScreenType.PNC_MORE_MENU,
        ScreenType.PNC_SETTINGS,
    }
)
_HOME_CITY_BUILDING_FLOW_SCREENS = _HOME_CITY_ADJACENT_SCREENS | frozenset({ScreenType.PNC_BUILDING_DETAILS})
_HOME_CITY_QUEUE_SCREENS = _HOME_CITY_ADJACENT_SCREENS | frozenset({ScreenType.PNC_BUILD_QUEUE, ScreenType.PNC_POPUP})

_SCREEN_FAMILY_OBSERVED_SCREENS = {
    ScreenType.ANDROID_HOME: frozenset({ScreenType.UNKNOWN, ScreenType.ANDROID_HOME}),
    ScreenType.PNC_LOGIN: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_LOGIN}),
    ScreenType.PNC_ACCOUNT_SWITCH: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_ACCOUNT_SWITCH}),
    ScreenType.PNC_LORD_INFO: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_LORD_INFO}),
    ScreenType.PNC_PLAYER_TERRITORY: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_PLAYER_TERRITORY, ScreenType.PNC_WORLD_MAP}),
    ScreenType.PNC_PLAYER_PROFILE: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_PLAYER_PROFILE,
            ScreenType.PNC_PLAYER_TERRITORY,
            ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
            ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
            ScreenType.PNC_MIGHT_RANK,
        }
    ),
    ScreenType.PNC_VIP: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_VIP}),
    ScreenType.PNC_VIP_DAILY_RESET: _HOME_CITY_QUEUE_SCREENS | frozenset({ScreenType.PNC_VIP_DAILY_RESET}),
    ScreenType.PNC_IMPROVE_MIGHT: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_IMPROVE_MIGHT}),
    ScreenType.PNC_EVENT_CENTER: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_EVENT_CENTER,
            ScreenType.PNC_MIGHT_RANK,
        }
    ),
    ScreenType.PNC_GIFT_CENTER: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_HOME_CITY, ScreenType.PNC_GIFT_CENTER}),
    ScreenType.PNC_WORLD_MAP: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_WORLD_MAP_ROOT, ScreenType.PNC_WORLD_MAP}),
    ScreenType.PNC_WORLD_COORDINATE_DIALOG: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_WORLD_MAP,
            ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        }
    ),
    ScreenType.PNC_WORLD_MAP_OVERVIEW: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_WORLD_MAP,
            ScreenType.PNC_WORLD_MAP_OVERVIEW,
            ScreenType.PNC_WORLD_KINGDOM_LIST,
        }
    ),
    ScreenType.PNC_WORLD_KINGDOM_LIST: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_WORLD_MAP_OVERVIEW,
            ScreenType.PNC_WORLD_KINGDOM_LIST,
        }
    ),
    ScreenType.PNC_MAIL_HUB: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_MAIL_HUB, ScreenType.PNC_HOME_CITY}),
    ScreenType.PNC_MAILBOX_LIST: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_MAIL_HUB,
            ScreenType.PNC_MAILBOX_LIST,
            ScreenType.PNC_MAIL_THREAD,
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
        }
    ),
    ScreenType.PNC_MAIL_THREAD: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_MAILBOX_LIST, ScreenType.PNC_MAIL_THREAD}),
    ScreenType.PNC_MAIL_COMPOSE_POPUP: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_MAILBOX_LIST,
            ScreenType.PNC_MAIL_COMPOSE_POPUP,
            ScreenType.PNC_ALLIANCE_HOME,
            ScreenType.PNC_PLAYER_PROFILE,
        }
    ),
    ScreenType.PNC_ALLIANCE_HOME: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_ALLIANCE_HOME,
            ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            ScreenType.PNC_MIGHT_RANK,
        }
    ),
    ScreenType.PNC_MORE_MENU: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}),
    ScreenType.PNC_SETTINGS: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_BUILDING_DETAILS: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BUILD_SPEEDUP: _HOME_CITY_BUILDING_FLOW_SCREENS | frozenset({ScreenType.PNC_BUILD_SPEEDUP}),
    ScreenType.PNC_BUILD_SPEEDUP_CONFIRM: _HOME_CITY_BUILDING_FLOW_SCREENS
    | frozenset({ScreenType.PNC_BUILD_SPEEDUP, ScreenType.PNC_BUILD_SPEEDUP_CONFIRM, ScreenType.PNC_POPUP}),
    ScreenType.PNC_CASTLE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_TERRITORY_OVERVIEW: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_HALL_OF_WAR: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SACRED_TREE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SACRED_TREE_BLESSING_RECORD: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_OTHER_LORD_SACRED_TREE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_PIT: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_RARE_EARTH_FIELD: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_DISPATCH: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SANCTUM: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_RELICS: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_TOWER_OF_TRIAL: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_TRIAL_CHALLENGE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_GODDESS_STATUE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BUILD_MENU_FIXED_SLOT: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BUILD_MENU_LARGE_SLOT: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BUILD_MENU_SMALL_SLOT: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BUILDING_CONSTRUCTION: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_INSTITUTE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_WAREHOUSE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_TRAP_WORKSHOP: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_TRAP_WORKSHOP_EFFECT_TABLE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_HERO_HALL: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_WATCHTOWER: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BLACKSMITH: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_GEAR: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_GEM: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SAURGEM: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_WARSIGIL: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_HERO_CURIO: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_ASCEND: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_ALLIANCE_HALL: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_MARKET: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_ALLIANCE_MEMBER_TRANSPORT: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_INFANTRY_BARRACKS: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_CAVALRY_BARRACKS: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_RANGED_BARRACKS: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SIEGE_FACTORY: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_BARRACKS_UNLOCK_TABLE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SAUROI_LAIR: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_SAUREGG: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_WALL: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_DEFENSE_INFO: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_HOME_CITY: _HOME_CITY_ADJACENT_SCREENS,
    ScreenType.PNC_BUILD_QUEUE: _HOME_CITY_QUEUE_SCREENS,
    ScreenType.PNC_POPUP: _HOME_CITY_QUEUE_SCREENS,
    ScreenType.PNC_BAG: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_QUEST_MAIN: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_HOME_CITY, ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}
    ),
    ScreenType.PNC_QUEST_DAILY: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_HOME_CITY, ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}
    ),
    ScreenType.PNC_ALLIANCE_JOIN: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_CHAT: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CHAT,
            ScreenType.PNC_HOME_CITY_ROOT,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_WORLD_MAP_ROOT,
            ScreenType.PNC_WORLD_MAP,
        }
    ),
    ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_CHAT, ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP}),
    ScreenType.PNC_ALLIANCE_MEMBER_LIST: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_ALLIANCE_MEMBER_LIST}
    ),
    ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_MEMBER_LIST, ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP}
    ),
    ScreenType.PNC_DAILY_TO_DO: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_MIGHT_RANK: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MIGHT_RANK}),
    ScreenType.PNC_RESEARCH_TREE: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_CASTLE_SELECTION: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_CASTLE_SELECTION,
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_SETTINGS,
        }
    ),
    ScreenType.PNC_CAMPAIGN_MAP: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_CAMPAIGN_STAGE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_VERSUS_CENTER: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_VERSUS_CENTER, ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO}
    ),
    ScreenType.PNC_HERO_FORMATION: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_VERSUS_CENTER,
            ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO,
            ScreenType.PNC_HERO_FORMATION,
        }
    ),
    ScreenType.PNC_HERO_SHOWDOWN_RANKING: frozenset(
        {
            ScreenType.UNKNOWN,
            ScreenType.PNC_VERSUS_CENTER,
            ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO,
            ScreenType.PNC_HERO_FORMATION,
            ScreenType.PNC_HERO_SHOWDOWN_RANKING,
        }
    ),
}


def screen_family_ocr_capability(screen_type: ScreenType) -> ScreenFamilyOcrCapability:
    """Returns the typed content strategy for one registered screen family."""

    if screen_type not in _SCREEN_FAMILY_OBSERVED_SCREENS:
        raise KeyError(f"Screen family '{screen_type}' is not registered for OCR.")
    if screen_type in _REVIEWED_REGION_PLAN_FAMILIES:
        return ScreenFamilyOcrCapability(
            family=screen_type,
            strategy=ScreenFamilyOcrStrategy.REVIEWED_REGION_PLAN,
        )
    return ScreenFamilyOcrCapability(
        family=screen_type,
        strategy=ScreenFamilyOcrStrategy.GUARDED_FULL_FRAME_REUSE,
        fallback_reason=FAMILY_REGIONS_NOT_REVIEWED,
    )


def runtime_screen_family_ocr_capabilities() -> tuple[ScreenFamilyOcrCapability, ...]:
    """Returns one typed content strategy for every registered screen family."""

    return tuple(
        screen_family_ocr_capability(screen_type)
        for screen_type in sorted(_SCREEN_FAMILY_OBSERVED_SCREENS, key=lambda value: value.value)
    )


def runtime_screen_family_ocr_types() -> frozenset[ScreenType]:
    """Returns the screen families with concrete OCR enrichers in the runtime."""

    return frozenset(_SCREEN_FAMILY_OBSERVED_SCREENS)


def can_attempt_screen_family_ocr(*, request_screen: ScreenType, observed_screen: ScreenType) -> bool:
    """Returns whether one screen-family OCR builder should run for the observed coarse screen."""

    observed_screens = _SCREEN_FAMILY_OBSERVED_SCREENS.get(request_screen)
    if observed_screens is None:
        return False
    # Every registered family must admit its exact screen.  Some legacy
    # adjacency tables intentionally omit the family itself, which otherwise
    # prevents exact-screen OCR capabilities from ever running after a prior
    # observation already established that identity.
    return observed_screen == request_screen or observed_screen in observed_screens
