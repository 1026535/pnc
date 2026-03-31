"""Canonical screen-family OCR capability registry shared by requests and enrichment."""

from __future__ import annotations

from pnc_automation.pnc.screen_type import ScreenType

_HOME_CITY_ADJACENT_SCREENS = frozenset(
    {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
)
_HOME_CITY_BUILDING_FLOW_SCREENS = _HOME_CITY_ADJACENT_SCREENS | frozenset({ScreenType.PNC_BUILDING_DETAILS})
_HOME_CITY_QUEUE_SCREENS = _HOME_CITY_ADJACENT_SCREENS | frozenset({ScreenType.PNC_BUILD_QUEUE, ScreenType.PNC_POPUP})

_SCREEN_FAMILY_OBSERVED_SCREENS = {
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
    ScreenType.PNC_IMPROVE_MIGHT: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_IMPROVE_MIGHT}),
    ScreenType.PNC_WORLD_MAP: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_WORLD_MAP}),
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
    ScreenType.PNC_BUILDING_DETAILS: _HOME_CITY_BUILDING_FLOW_SCREENS,
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
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_ALLIANCE_JOIN: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_CHAT: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CHAT, ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP}
    ),
    ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_CHAT, ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP}),
    ScreenType.PNC_ALLIANCE_MEMBER_LIST: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_ALLIANCE_MEMBER_LIST}
    ),
    ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_MEMBER_LIST, ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP}
    ),
    ScreenType.PNC_DAILY_TO_DO: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_MIGHT_RANK: frozenset({ScreenType.UNKNOWN, ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_MIGHT_RANK}),
    ScreenType.PNC_RESEARCH_TREE: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_CASTLE_SELECTION: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_CAMPAIGN_MAP: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_CAMPAIGN_STAGE: _HOME_CITY_BUILDING_FLOW_SCREENS,
    ScreenType.PNC_VERSUS_CENTER: _HOME_CITY_BUILDING_FLOW_SCREENS,
}


def runtime_screen_family_ocr_types() -> frozenset[ScreenType]:
    """Returns the screen families with concrete OCR enrichers in the runtime."""

    return frozenset(_SCREEN_FAMILY_OBSERVED_SCREENS)


def can_attempt_screen_family_ocr(*, request_screen: ScreenType, observed_screen: ScreenType) -> bool:
    """Returns whether one screen-family OCR builder should run for the observed coarse screen."""

    observed_screens = _SCREEN_FAMILY_OBSERVED_SCREENS.get(request_screen)
    if observed_screens is None:
        return False
    return observed_screen in observed_screens
