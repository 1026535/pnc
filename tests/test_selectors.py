"""Selector-registry tests."""

from __future__ import annotations

import unittest

from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.selectors import build_default_selector_registry


class SelectorRegistryTests(unittest.TestCase):
    """Validates canonical selector-registry construction."""

    def test_build_default_selector_registry_merges_shared_selector_ids(self) -> None:
        """Builds the default registry without duplicate selector ids and preserves shared screens."""

        registry = build_default_selector_registry()
        selector_ids = tuple(selector.id for selector in registry.all())

        self.assertEqual(len(selector_ids), len(set(selector_ids)))
        hero_upgrade_tab = registry.require(UiElementId.PNC_HERO_DETAIL_TAB_UPGRADE)
        self.assertEqual(
            hero_upgrade_tab.screens,
            (ScreenType.PNC_HERO_DETAIL_UPGRADE, ScreenType.PNC_HERO_DETAIL_ENHANCE),
        )
        cash_mall_shortcut = registry.require(UiElementId.PNC_HOME_RIGHT_RAIL_CASH_MALL_ICON)
        self.assertEqual(cash_mall_shortcut.status.value, "click_mapped")
        self.assertEqual(cash_mall_shortcut.click_outcomes[0].target_screen, ScreenType.PNC_CASH_MALL)
        self.assertEqual(
            cash_mall_shortcut.click_outcomes[0].verification_selectors,
            (UiElementId.PNC_CASH_MALL_TAB_DAILY_SALE,),
        )


if __name__ == "__main__":
    unittest.main()
