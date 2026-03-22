"""Canonical screen-family OCR capability registry shared by requests and enrichment."""

from __future__ import annotations

from pnc_automation.pnc.screen_type import ScreenType

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
    ScreenType.PNC_BUILDING_DETAILS: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_HOME_CITY: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
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
    ScreenType.PNC_ACADEMY: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_RESEARCH_TREE: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
    ScreenType.PNC_CASTLE_SELECTION: frozenset(
        {ScreenType.UNKNOWN, ScreenType.PNC_CASTLE_SELECTION, ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}
    ),
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
