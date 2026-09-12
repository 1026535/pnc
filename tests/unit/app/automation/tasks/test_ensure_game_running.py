"""Ensure game running."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskStatus
from pnc_automation.app.automation.tasks.ensure_game_running_task import EnsureGameRunningTask
from pnc_automation.app.pnc.domain.action_requests import KeyEventAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class EnsureGameRunningTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves ensure game running."""

    def test_recover_unknown_game_screen_uses_back_without_relaunching(self) -> None:
        """Uses one in-game back increment for unknown endpoint states instead of restarting the app."""

        actions = self.flows.recover_unknown_game_screen(
            make_observation(ScreenType.UNKNOWN),
            reason="recover_unknown_endpoint",
        )

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].reason, "recover_unknown_endpoint")

    def test_ensure_game_running_waits_on_unknown_once_launch_is_in_progress(self) -> None:
        """Keeps waiting on the launch splash instead of bouncing back through Android home."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)
        context.runtime_state["ensure_game_running_launch_started"] = True
        observation = make_observation(ScreenType.UNKNOWN)

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], WaitAction)
        self.assertEqual(actions[0].reason, "wait_for_pnc_launch")

    def test_ensure_game_running_recovers_unknown_in_game_state_before_any_relaunch(self) -> None:
        """Uses one bounded in-game recovery increment before the bootstrap task is allowed to relaunch anything."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)

        actions = task.plan(context, make_observation(ScreenType.UNKNOWN))

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], KeyEventAction)
        self.assertEqual(actions[0].key_code, "KEYCODE_BACK")
        self.assertEqual(actions[0].reason, "recover_unknown_before_foreground")

    def test_ensure_game_running_replans_when_launch_lands_on_unknown_splash(self) -> None:
        """Treats an unknown post-launch splash as in-progress foregrounding instead of immediate failure."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)

        result = task.verify(
            context,
            make_observation(ScreenType.ANDROID_HOME),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)
        self.assertTrue(context.runtime_state["ensure_game_running_launch_started"])

    def test_ensure_game_running_replans_bounded_unknown_recovery_before_failing(self) -> None:
        """Uses a small unknown-state recovery budget and then fails cleanly instead of looping through relaunchs."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)

        first = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(ScreenType.UNKNOWN),
        )
        second = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(ScreenType.UNKNOWN),
        )
        third = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(first.status, TaskStatus.REPLAN)
        self.assertEqual(second.status, TaskStatus.REPLAN)
        self.assertEqual(third.status, TaskStatus.FAILED)
        self.assertTrue(third.retryable)

    def test_ensure_game_running_keeps_waiting_after_four_unknown_launch_observations(self) -> None:
        """Allows slower live launch/login handoffs instead of hard-failing after only a few splash observations."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)
        context.runtime_state["ensure_game_running_launch_started"] = True
        context.runtime_state["ensure_game_running_launch_wait_attempts"] = 4

        result = task.verify(
            context,
            make_observation(ScreenType.UNKNOWN),
            make_observation(ScreenType.UNKNOWN),
        )

        self.assertEqual(result.status, TaskStatus.REPLAN)

    def test_ensure_game_running_uses_task_local_replan_budget_for_launch_waiting(self) -> None:
        """Keeps one task-local budget covering unknown recovery, launch handoff, and splash waiting."""

        task = EnsureGameRunningTask()
        context = self._make_context(params=None)

        self.assertEqual(task.max_replans_per_step(context), 15)
