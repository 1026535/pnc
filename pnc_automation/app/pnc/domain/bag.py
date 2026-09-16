"""Canonical Bag subtab identities shared by vision measurement and navigation."""

from __future__ import annotations

from enum import StrEnum

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


class BagTab(StrEnum):
    """The five Bag subtabs in their fixed left-to-right slot order."""

    RESOURCE = "resource"
    SPEEDUP = "speedup"
    MILITARY = "military"
    TREASURE = "treasure"
    MISC = "misc"


BAG_TAB_ORDER: tuple[BagTab, ...] = (
    BagTab.RESOURCE,
    BagTab.SPEEDUP,
    BagTab.MILITARY,
    BagTab.TREASURE,
    BagTab.MISC,
)

_BAG_TAB_SELECTOR_IDS: dict[BagTab, UiElementId] = {
    BagTab.RESOURCE: UiElementId.PNC_BAG_SUBTAB_RESOURCE,
    BagTab.SPEEDUP: UiElementId.PNC_BAG_SUBTAB_SPEEDUP,
    BagTab.MILITARY: UiElementId.PNC_BAG_SUBTAB_MILITARY,
    BagTab.TREASURE: UiElementId.PNC_BAG_SUBTAB_TREASURE,
    BagTab.MISC: UiElementId.PNC_BAG_SUBTAB_MISC,
}


def bag_tab_selector_id(tab: BagTab) -> UiElementId:
    """Returns the selector that activates the requested Bag subtab."""

    return _BAG_TAB_SELECTOR_IDS[tab]
