"""Selector-registry tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    SelectorCatalogClickOutcome,
    SelectorCatalogDocument,
    SelectorCatalogEntry,
)
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
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
        self.assertEqual(cash_mall_shortcut.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(cash_mall_shortcut.click_outcomes[0].target_screen, ScreenType.PNC_CASH_MALL)
        self.assertEqual(
            cash_mall_shortcut.click_outcomes[0].verification_selectors,
            (UiElementId.PNC_CASH_MALL_TAB_DAILY_SALE,),
        )
        home_lord_info_shortcut = registry.require(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT)
        self.assertIsNotNone(home_lord_info_shortcut.relative_bounds)
        self.assertAlmostEqual(home_lord_info_shortcut.relative_bounds.action_x_ratio, 0.11)
        home_world_switch = registry.require(UiElementId.PNC_HOME_WORLD_SWITCH)
        self.assertEqual(home_world_switch.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(home_world_switch.click_outcomes[0].target_screen, ScreenType.PNC_WORLD_MAP)
        self.assertIsNotNone(home_world_switch.relative_bounds)
        self.assertAlmostEqual(home_world_switch.relative_bounds.action_y_ratio, 0.95)
        chat_shortcut = registry.require(UiElementId.PNC_CHAT_SHORTCUT)
        self.assertEqual(chat_shortcut.screens, (ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP))
        self.assertEqual(chat_shortcut.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(chat_shortcut.click_outcomes[0].target_screen, ScreenType.PNC_CHAT)
        self.assertIsNotNone(chat_shortcut.relative_bounds)
        self.assertEqual(
            registry.require(UiElementId.PNC_CHAT_HEADER).interaction_kind,
            SelectorInteractionKind.LABEL,
        )
        chat_input_field = registry.require(UiElementId.PNC_CHAT_INPUT_FIELD)
        self.assertEqual(chat_input_field.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertEqual(chat_input_field.screens, (ScreenType.PNC_CHAT,))
        self.assertIsNotNone(chat_input_field.relative_bounds)
        home_daily_to_do_shortcut = registry.require(UiElementId.PNC_HOME_DAILY_TO_DO_SHORTCUT)
        self.assertEqual(home_daily_to_do_shortcut.click_outcomes[0].target_screen, ScreenType.PNC_DAILY_TO_DO)
        self.assertEqual(
            home_daily_to_do_shortcut.click_outcomes[0].verification_selectors,
            (UiElementId.PNC_DAILY_TO_DO_HEADER,),
        )
        self.assertEqual(
            registry.require(UiElementId.PNC_DAILY_TO_DO_HEADER).interaction_kind,
            SelectorInteractionKind.LABEL,
        )
        login_submit_button = registry.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON)
        self.assertEqual(login_submit_button.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertIsNotNone(login_submit_button.relative_bounds)
        self.assertAlmostEqual(login_submit_button.relative_bounds.width_ratio, 0.388888888889, places=9)
        self.assertFalse(registry.require(UiElementId.PNC_MORE_MANAGE_CHAR).materialize_relative_bounds)
        self.assertEqual(
            registry.require(UiElementId.PNC_LORD_INFO_HEADER).interaction_kind,
            SelectorInteractionKind.LABEL,
        )

    def test_selector_catalog_rejects_navigation_without_reviewed_destination(self) -> None:
        """Fails fast when a navigation selector omits the reviewed destination contract."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_HOME",
                        screens=("PNC_HOME_CITY",),
                        status="click_mapped",
                        detection_kind="template",
                        interaction_kind="navigation",
                    ),
                )
            )

    def test_selector_catalog_rejects_label_click_metadata(self) -> None:
        """Fails fast when a non-interactive label declares click behavior."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_VIP_HEADER",
                        screens=("PNC_VIP",),
                        status="screenshot_seeded",
                        detection_kind="planned",
                        interaction_kind="label",
                        click=SelectorCatalogClickDefinition(
                            anchor="center",
                            outcomes=(
                                SelectorCatalogClickOutcome(
                                    target_screen="PNC_HOME_CITY",
                                    verification_selectors=(),
                                    verification_texts=(),
                                    safe_to_click=True,
                                    monetized=False,
                                    notes=(),
                                ),
                            ),
                        ),
                    ),
                )
            )

    def test_selector_catalog_allows_empty_verification_texts(self) -> None:
        """Accepts reviewed click outcomes whose unsupported text-verification field stays empty."""

        document = SelectorCatalogDocument(
            selectors=(
                SelectorCatalogEntry(
                    id="PNC_BOTTOM_NAV_BAG",
                    screens=("PNC_HOME_CITY",),
                    status="click_mapped",
                    detection_kind="template",
                    interaction_kind="navigation",
                    click=SelectorCatalogClickDefinition(
                        anchor="center",
                        outcomes=(
                            SelectorCatalogClickOutcome(
                                target_screen="PNC_BAG",
                                verification_selectors=(),
                                verification_texts=(),
                                safe_to_click=True,
                                monetized=False,
                                notes=(),
                            ),
                        ),
                    ),
                ),
            )
        )

        self.assertEqual(document.selectors[0].click.outcomes[0].verification_texts, ())

    def test_selector_catalog_rejects_verification_texts_until_runtime_support_exists(self) -> None:
        """Fails fast when catalog content requests text verification that runtime matching does not support."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_BAG",
                        screens=("PNC_HOME_CITY",),
                        status="click_mapped",
                        detection_kind="template",
                        interaction_kind="navigation",
                        click=SelectorCatalogClickDefinition(
                            anchor="center",
                            outcomes=(
                                SelectorCatalogClickOutcome(
                                    target_screen="PNC_BAG",
                                    verification_selectors=(),
                                    verification_texts=("Bag",),
                                    safe_to_click=True,
                                    monetized=False,
                                    notes=(),
                                ),
                            ),
                        ),
                    ),
                )
            )

    def test_build_default_selector_registry_rejects_ocr_region_selectors_without_relative_bounds(self) -> None:
        """Fails fast when a live ocr_region selector omits the required normalized geometry."""

        with tempfile.TemporaryDirectory() as temp_directory:
            catalog_path = Path(temp_directory) / "selector_registry.yaml"
            catalog_path.write_text(
                "selectors:\n"
                "  - id: PNC_CASH_MALL_ENTRY_TITLE_REGION\n"
                "    screens: [PNC_CASH_MALL]\n"
                "    status: screenshot_seeded\n"
                "    detection_kind: ocr_region\n",
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                build_default_selector_registry(catalog_path=catalog_path, template_root=Path(temp_directory))

    def test_build_default_selector_registry_rejects_legacy_ocr_region_schema(self) -> None:
        """Fails fast when catalog content still uses the obsolete absolute OCR rectangle field."""

        with tempfile.TemporaryDirectory() as temp_directory:
            catalog_path = Path(temp_directory) / "selector_registry.yaml"
            catalog_path.write_text(
                "selectors:\n"
                "  - id: PNC_CASH_MALL_ENTRY_TITLE_REGION\n"
                "    screens: [PNC_CASH_MALL]\n"
                "    status: screenshot_seeded\n"
                "    detection_kind: ocr_region\n"
                "    ocr_region:\n"
                "      x: 10\n"
                "      y: 20\n"
                "      width: 30\n"
                "      height: 12\n",
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                build_default_selector_registry(catalog_path=catalog_path, template_root=Path(temp_directory))


if __name__ == "__main__":
    unittest.main()
