"""Selector-registry tests."""

from __future__ import annotations

import unittest

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import SelectorResolutionKind
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogClickDefinition,
    SelectorCatalogClickOutcome,
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    SelectorCatalogResolutionStep,
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
        self.assertAlmostEqual(_relative_bounds(home_lord_info_shortcut).action_x_ratio, 0.11)
        home_world_switch = registry.require(UiElementId.PNC_HOME_WORLD_SWITCH)
        self.assertEqual(home_world_switch.interaction_kind, SelectorInteractionKind.NAVIGATION)
        self.assertEqual(home_world_switch.click_outcomes[0].target_screen, ScreenType.PNC_WORLD_MAP)
        self.assertAlmostEqual(_relative_bounds(home_world_switch).action_y_ratio, 0.95)
        login_submit_button = registry.require(UiElementId.PNC_LOGIN_SUBMIT_BUTTON)
        self.assertEqual(login_submit_button.interaction_kind, SelectorInteractionKind.ACTION)
        self.assertAlmostEqual(_relative_bounds(login_submit_button).width_ratio, 0.388888888889, places=9)
        self.assertEqual(
            tuple(step.kind for step in registry.require(UiElementId.PNC_MORE_MANAGE_CHAR).resolution.steps),
            (SelectorResolutionKind.PARSER_CANDIDATE, SelectorResolutionKind.RELATIVE_BOUNDS),
        )
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
                        resolution=_template_resolution("pnc_bottom_nav_home.png"),
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
                        resolution=(
                            SelectorCatalogResolutionStep(
                                kind=SelectorResolutionKind.PARSER_CANDIDATE.value,
                            ),
                        ),
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

    def test_selector_catalog_rejects_duplicate_resolution_steps(self) -> None:
        """Fails fast when a selector declares the same resolution kind more than once."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        resolution=(
                            SelectorCatalogResolutionStep(
                                kind=SelectorResolutionKind.TEMPLATE.value,
                                template_path="pnc_home_build_button.png",
                            ),
                            SelectorCatalogResolutionStep(
                                kind=SelectorResolutionKind.TEMPLATE.value,
                                template_path="pnc_home_build_button_variant.png",
                            ),
                        ),
                    ),
                )
            )

    def test_selector_catalog_rejects_relative_bounds_before_stronger_steps(self) -> None:
        """Fails fast when geometry fallback is authored before stronger strategies."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="click_mapped",
                        resolution=(
                            _relative_bounds_step(),
                            SelectorCatalogResolutionStep(
                                kind=SelectorResolutionKind.TEMPLATE.value,
                                template_path="pnc_home_build_button.png",
                            ),
                        ),
                    ),
                )
            )

    def test_selector_catalog_rejects_non_planned_selector_without_resolution(self) -> None:
        """Fails fast when a refined selector still omits the canonical resolution policy."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                    ),
                )
            )

    def test_selector_catalog_rejects_invalid_parser_candidate_selector(self) -> None:
        """Fails fast when a parser-candidate step targets an unsupported selector id."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_CHARACTER_PANEL",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        resolution=(
                            SelectorCatalogResolutionStep(
                                kind=SelectorResolutionKind.PARSER_CANDIDATE.value,
                            ),
                        ),
                    ),
                )
            )

    def test_selector_catalog_rejects_template_step_without_asset_path(self) -> None:
        """Fails fast when a template resolution step omits its explicit asset path."""

        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogResolutionStep(kind=SelectorResolutionKind.TEMPLATE.value)


def _template_resolution(template_path: str) -> tuple[SelectorCatalogResolutionStep, ...]:
    """Builds a one-step template resolution policy for test catalog fixtures."""

    return (
        SelectorCatalogResolutionStep(
            kind=SelectorResolutionKind.TEMPLATE.value,
            template_path=template_path,
        ),
    )


def _relative_bounds_step() -> SelectorCatalogResolutionStep:
    """Builds a one-step relative-bounds fallback for test catalog fixtures."""

    return SelectorCatalogResolutionStep(
        kind=SelectorResolutionKind.RELATIVE_BOUNDS.value,
        relative_bounds=SelectorCatalogRelativeBounds(
            x_ratio=0.1,
            y_ratio=0.2,
            width_ratio=0.3,
            height_ratio=0.15,
        ),
    )


def _relative_bounds(selector: object) -> object:
    """Returns the authored relative-bounds fallback for one runtime selector."""

    step = next(
        (step for step in selector.resolution.steps if step.kind == SelectorResolutionKind.RELATIVE_BOUNDS),
        None,
    )
    if step is None or step.relative_bounds is None:
        raise AssertionError(f"Selector '{selector.id}' is missing relative-bounds fallback.")
    return step.relative_bounds


if __name__ == "__main__":
    unittest.main()
