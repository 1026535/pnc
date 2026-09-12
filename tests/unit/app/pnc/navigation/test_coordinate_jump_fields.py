"""Coordinate jump fields."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_search import (
    WorldMapCoordinateDialogState,
    WorldMapCoordinateNavigator,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.world_search.world_map_search_fixtures import WorldMapSearchFixtures
from tests.support.pnc.world_search.make_coordinate_dialog_observation import (
    _make_coordinate_dialog_observation,
)
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation


class CoordinateJumpFieldsTests(WorldMapSearchFixtures, unittest.TestCase):
    """Proves coordinate jump fields."""

    def test_coordinate_navigator_plan_jump_rejects_out_of_domain_target(self) -> None:
        """Fails fast before typing when the raw target lies outside the world-map domain."""

        navigator = WorldMapCoordinateNavigator()

        with self.assertRaises(SelectorResolutionError):
            navigator.plan_jump(
                target=(512, 1),
                current_observation=_make_world_map_observation(10, 10),
            )

    def test_coordinate_navigator_plan_jump_normalizes_targets_and_commits_each_numeric_field(self) -> None:
        """Uses one canonical selector sequence and commits each edited field before submit."""

        navigator = WorldMapCoordinateNavigator()

        plan = navigator.plan_jump(
            target=(511, 0),
            current_observation=_make_world_map_observation(10, 10),
        )

        self.assertEqual(plan.normalized_target_coordinate, (510, 0))
        self.assertIsInstance(plan.open_action, ActionRequest)
        self.assertEqual(
            [type(action).__name__ for action in plan.fill_actions],
            ["InputTextAction", "KeyEventAction", "InputTextAction", "KeyEventAction"],
        )
        self.assertEqual(
            [getattr(action, "selector_id", None) for action in plan.fill_actions if hasattr(action, "selector_id")],
            [
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
            ],
        )
        self.assertTrue(all(action.key_code == "KEYCODE_ENTER" for action in plan.fill_actions if isinstance(action, KeyEventAction)))

    def test_coordinate_navigator_requires_committed_dialog_values_before_submit(self) -> None:
        """Proves the filled dialog state from committed K/X/Y values before pressing Go."""

        navigator = WorldMapCoordinateNavigator()
        plan = navigator.plan_jump(
            target=(511, 2),
            current_observation=_make_world_map_observation(10, 10),
        )
        initial_state = navigator.require_dialog_state(_make_coordinate_dialog_observation(157, 10, 10))
        current_state = navigator.require_pre_submit_state(
            _make_coordinate_dialog_observation(157, 510, 2),
            plan=plan,
            initial_state=initial_state,
        )

        self.assertEqual(current_state, WorldMapCoordinateDialogState(kingdom=157, coordinate=(510, 2)))
