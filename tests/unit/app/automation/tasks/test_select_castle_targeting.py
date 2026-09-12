"""Select castle targeting."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.select_castle_task import SelectCastleTask
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.app.pnc.domain.action_requests import (
    KeyEventAction,
    TapAction,
    TapListEntryAction,
    WaitAction,
)
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    resolve_unambiguous_castle_identity,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_entry, make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class SelectCastleTargetingTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves select castle targeting."""

    def test_select_castle_opens_manage_char_directly_when_current_castle_is_unknown(self) -> None:
        """Uses the explicit Manage Char switch path directly instead of chaining Lord Info first."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 3)
        self.assertIsInstance(actions[0], TapAction)
        self.assertEqual(actions[0].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_select_castle_switches_from_lord_info_when_origin_castle_is_wrong(self) -> None:
        """Leaves Lord Info and continues straight into Manage Char when the origin castle is not the target."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle_name="Wrong",
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 4)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertIsInstance(actions[1], TapAction)
        self.assertEqual(actions[1].selector_id, UiElementId.PNC_BOTTOM_NAV_MORE)
        self.assertIsInstance(actions[2], TapAction)
        self.assertEqual(actions[2].selector_id, UiElementId.PNC_MORE_SETTINGS)
        self.assertIsInstance(actions[3], TapAction)
        self.assertEqual(actions[3].selector_id, UiElementId.PNC_MORE_MANAGE_CHAR)

    def test_select_castle_returns_to_home_from_a_building_screen_before_opening_manage_char(self) -> None:
        """Uses the explicit castle-switch step to leave in-progress screens before Manage Char navigation."""

        task = SelectCastleTask()
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=self.target_castle,
        )
        observation = make_observation(ScreenType.PNC_INFANTRY_BARRACKS)

        actions = task.plan(context, observation)
        result = task.verify(context, observation, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(actions, self.flows.ensure_home_city(observation))
        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertIn("root-adjacent", result.message)

    def test_select_castle_taps_visible_target_despite_spacing_only_ocr_drift(self) -> None:
        """Treats spacing-only OCR drift as the same visible target castle on Manage Char."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="please bgentle",
                    metadata={"kingdom": "K226", "castle_level": 12},
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertEqual(actions[0].title_text, "please b gentle")
        self.assertEqual(actions[0].metadata_key, "kingdom")
        self.assertEqual(actions[0].metadata_value, "K226")
        self.assertIsInstance(actions[1], WaitAction)

    def test_select_castle_returns_home_when_manage_char_visually_marks_target_selected(self) -> None:
        """Uses the selected-row checkmark when top-level current-castle evidence is absent."""

        task = SelectCastleTask()
        target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        context = self._make_context(
            params=None,
            task_id=TaskId.SELECT_CASTLE,
            target_castle=target_castle,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT,),
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="pine cobaye 1",
                    metadata={"kingdom": "K287"},
                    selected=True,
                ),
            ),
        )

        actions = task.plan(context, observation)
        result = task.verify(context, observation, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(actions, self.flows.return_to_safe_root_screen(observation))
        self.assertTrue(result.succeeded)
        self.assertEqual(12, task.max_replans_per_step(context))

    def test_resolve_unambiguous_castle_identity_prefers_the_exact_requested_name_variant(self) -> None:
        """Returns the exact preferred castle spelling even when an equivalent variant appears first."""

        first_variant = CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12)
        exact_variant = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)

        resolved = resolve_unambiguous_castle_identity(
            (first_variant, exact_variant),
            preferred_name="please b gentle",
        )

        self.assertEqual(resolved, exact_variant)

    def test_select_castle_fails_fast_without_an_explicit_target(self) -> None:
        """Rejects direct select-castle execution when the step omitted its runtime castle target."""

        task = SelectCastleTask()

        with self.assertRaises(TaskVerificationError):
            task.plan(
                self._make_context(params=None, task_id=TaskId.SELECT_CASTLE),
                make_observation(ScreenType.PNC_HOME_CITY),
            )
