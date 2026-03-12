"""Canonical selector ids that the trusted P&C screen interpreter can synthesize."""

from __future__ import annotations

from pnc_automation.pnc.ui_element_id import UiElementId

SUPPORTED_PARSER_CANDIDATE_IDS = frozenset(
    {
        UiElementId.PNC_ACCOUNT_SWITCH_CHANGE_ACCOUNT_BUTTON,
        UiElementId.PNC_ACCOUNT_SWITCH_CONTINUE_BUTTON,
        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
        UiElementId.PNC_BAG_MAIN_TAB_BAG,
        UiElementId.PNC_BAG_USE_BUTTON,
        UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
        UiElementId.PNC_BOTTOM_NAV_BAG,
        UiElementId.PNC_BOTTOM_NAV_HERO,
        UiElementId.PNC_BOTTOM_NAV_HOME,
        UiElementId.PNC_BOTTOM_NAV_MAIL,
        UiElementId.PNC_BOTTOM_NAV_MORE,
        UiElementId.PNC_BOTTOM_NAV_QUEST,
        UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
        UiElementId.PNC_CASTLE_LIST_ENTRY,
        UiElementId.PNC_CASTLE_SELECTED_CHECKMARK,
        UiElementId.PNC_HOME_BUILD_BUTTON,
        UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
        UiElementId.PNC_HOME_RESEARCH_BUTTON,
        UiElementId.PNC_IMPROVE_MIGHT_HEADER,
        UiElementId.PNC_LOADING_RECONNECT_BUTTON,
        UiElementId.PNC_LOGIN_PASSWORD_FIELD,
        UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
        UiElementId.PNC_LOGIN_USERNAME_FIELD,
        UiElementId.PNC_LORD_INFO_HEADER,
        UiElementId.PNC_LORD_INFO_NAME_LABEL,
        UiElementId.PNC_MORE_IMPROVE_MIGHT,
        UiElementId.PNC_MORE_LORD_INFO,
        UiElementId.PNC_MORE_MANAGE_CHAR,
        UiElementId.PNC_MORE_SETTINGS,
        UiElementId.PNC_MORE_VIP,
        UiElementId.PNC_POPUP_CLOSE_BUTTON,
        UiElementId.PNC_VIP_HEADER,
    }
)
