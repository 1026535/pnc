"""Replacement-core castle selection navigation tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.select_castle import SelectCastleWorkflow
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner, WorkflowContext, WorkflowEffect
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapListEntryAction
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_entry, make_observation


class _SequenceObserver:
    """Returns a finite, deterministic sequence of fresh observations."""

    def __init__(self, observations):
        self.observations = list(observations)
        self.labels: list[str] = []

    def __call__(self, label: str):
        self.labels.append(label)
        if not self.observations:
            raise AssertionError(f"No fixture observation remains for {label}.")
        return self.observations.pop(0)


class _RecordingActuator:
    """Records declarative actions without bypassing NavigationCore."""

    def __init__(self):
        self.actions = []

    def execute_action(self, action, observation):
        self.actions.append((action, observation))
        return True


class SelectCastleNavigationTests(unittest.TestCase):
    """Proves exact row selection, bounded scanning, and fail-closed guards."""

    target = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)

    def test_workflow_is_nonspending_home_to_home_and_reuses_context_selection(self) -> None:
        context = Mock()
        context.select_castle.return_value = self._window(self.target, selected=True, at=1)
        context.verify_active_castle_identity.return_value = self.target
        workflow = SelectCastleWorkflow(original_castle=self.target, target_castle=self.target)

        result = workflow.execute(context)

        self.assertEqual(workflow.spec.entry_screen, ScreenType.PNC_HOME_CITY)
        self.assertEqual(workflow.spec.exit_screen, ScreenType.PNC_HOME_CITY)
        self.assertEqual(workflow.spec.effect.value, "nonspending_state_change")
        context.navigate.assert_called_once_with(ScreenType.PNC_CASTLE_SELECTION)
        context.select_castle.assert_called_once_with(self.target)
        context.verify_active_castle_identity.assert_called_once_with(self.target)
        self.assertFalse(result.switched)

    def test_workflow_runner_confirms_home_exit_after_exact_postflight(self) -> None:
        runtime = Mock()
        home = self._frame((), screen=ScreenType.PNC_HOME_CITY, at=1)
        manage = self._window(self.target, at=2)
        selected = self._window(self.target, selected=True, at=3)
        runtime.navigation.navigate.side_effect = [home, manage, home]
        runtime.navigation.select_castle.return_value = selected
        runtime.preflight_active_castle_identity.return_value = self.target
        runtime.observation_count = 3
        runtime.last_observation = selected
        workflow = SelectCastleWorkflow(original_castle=self.target, target_castle=self.target)

        result = CoreWorkflowRunner(runtime).run(workflow)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.exit_screen, ScreenType.PNC_HOME_CITY)
        self.assertEqual(runtime.navigation.navigate.call_args_list[0].args, (ScreenType.PNC_HOME_CITY,))
        self.assertEqual(runtime.navigation.navigate.call_args_list[-1].args, (ScreenType.PNC_HOME_CITY,))
        runtime.navigation.select_castle.assert_called_once()
        runtime.preflight_active_castle_identity.assert_called_once_with()

    def test_selected_target_is_a_noop(self) -> None:
        observer = _SequenceObserver([self._window(self.target, selected=True, at=1)])
        actuator = _RecordingActuator()

        result = self._navigation(actuator, observer).select_castle(
            self.target,
            observe_content=observer,
        )

        self.assertEqual(result.screen_type, ScreenType.PNC_CASTLE_SELECTION)
        self.assertEqual(actuator.actions, [])

    def test_visible_target_reacquires_then_taps_once_and_confirms_selected(self) -> None:
        observer = _SequenceObserver(
            [
                self._window(self.target, at=1),
                self._window(self.target, at=2),
                self._window(self.target, selected=True, at=3),
                self._window(self.target, selected=True, at=4),
            ]
        )
        actuator = _RecordingActuator()

        result = self._navigation(actuator, observer).select_castle(
            self.target,
            observe_content=observer,
        )

        self.assertEqual(result.captured_at, self._time(4))
        self.assertEqual(len(actuator.actions), 1)
        self.assertIsInstance(actuator.actions[0][0], TapListEntryAction)
        self.assertEqual(actuator.actions[0][0].metadata_value, "K230")

    def test_offscreen_target_uses_bounded_fresh_scan_then_taps_once(self) -> None:
        other = CastleIdentity(kingdom="K229", castle_name="Other", castle_level=7)
        observer = _SequenceObserver(
            [
                self._window(other, at=1),
                self._window(other, at=2),
                self._window(self.target, at=3),
                self._window(self.target, at=4),
                self._window(self.target, at=5),
                self._window(self.target, selected=True, at=6),
                self._window(self.target, selected=True, at=7),
            ]
        )
        actuator = _RecordingActuator()

        result = self._navigation(actuator, observer).select_castle(
            self.target,
            observe_content=observer,
        )

        self.assertEqual(result.captured_at, self._time(7))
        self.assertEqual(len(actuator.actions), 2)
        self.assertTrue(all(isinstance(action, SwipeAction) for action, _ in actuator.actions[:1]))
        self.assertIsInstance(actuator.actions[-1][0], TapListEntryAction)

    def test_missing_target_stops_after_repeated_windows_without_tap(self) -> None:
        other = CastleIdentity(kingdom="K229", castle_name="Other", castle_level=7)
        observer = _SequenceObserver(
            [
                self._window(other, at=1),
                self._window(other, at=2),
                self._window(other, at=3),
                self._window(other, at=4),
                self._window(other, at=5),
                self._window(other, at=6),
                self._window(other, at=7),
            ]
        )
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "bounded roster scan"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(len(actuator.actions), 2)
        self.assertTrue(all(isinstance(action, SwipeAction) for action, _ in actuator.actions))

    def test_ambiguous_target_fails_before_any_gesture(self) -> None:
        row = make_entry(ListEntryKind.CASTLE, title="Main", metadata={"kingdom": "K230", "castle_level": 8})
        equivalent_name = make_entry(
            ListEntryKind.CASTLE,
            title="Main",
            metadata={"kingdom": "K230", "castle_level": 10},
        )
        observer = _SequenceObserver([self._frame((row, equivalent_name), at=1)])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def test_changed_row_action_point_fails_before_tap(self) -> None:
        malformed = make_entry(
            ListEntryKind.CASTLE,
            title="Main",
            metadata={"kingdom": "K230", "castle_level": 8},
            action_point=(999, 999),
        )
        observer = _SequenceObserver([self._frame((malformed,), at=1), self._frame((malformed,), at=2)])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "malformed action point"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def test_name_match_with_mismatched_level_fails_before_tap(self) -> None:
        wrong_level = make_entry(
            ListEntryKind.CASTLE,
            title="Main",
            metadata={"kingdom": "K230", "castle_level": 9},
        )
        observer = _SequenceObserver([self._frame((wrong_level,), at=1)])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "mismatched level"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def test_stale_reacquisition_fails_without_tap(self) -> None:
        observer = _SequenceObserver([self._window(self.target, at=1), self._window(self.target, at=1)])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "stale"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def test_unknown_reacquisition_fails_without_tap(self) -> None:
        observer = _SequenceObserver([
            self._window(self.target, at=1),
            self._frame((), screen=ScreenType.UNKNOWN, at=2),
        ])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "Manage Characters"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def test_selection_timeout_does_not_replay_the_row_tap(self) -> None:
        observer = _SequenceObserver([
            self._window(self.target, at=1),
            self._window(self.target, at=2),
            self._window(self.target, at=3),
            self._window(self.target, at=4),
        ])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "completion budget"):
            self._navigation(
                actuator,
                observer,
                policy=NavigationPolicy(max_observations=2, max_seconds=5, poll_seconds=0),
            ).select_castle(self.target, observe_content=observer)

        self.assertEqual(len(actuator.actions), 1)
        self.assertIsInstance(actuator.actions[0][0], TapListEntryAction)

    def test_read_only_context_rejects_castle_selection_before_navigation(self) -> None:
        runtime = Mock()
        context = WorkflowContext(
            runtime,
            last_observation=self._window(self.target, selected=True, at=1),
            effect=WorkflowEffect.READ_ONLY,
        )

        with self.assertRaisesRegex(PermissionError, "NONSPENDING_STATE_CHANGE"):
            context.select_castle(self.target)

        runtime.navigation.select_castle.assert_not_called()

    def test_interrupted_source_fails_without_gesture(self) -> None:
        observer = _SequenceObserver([self._frame((), screen=ScreenType.PNC_POPUP, at=1)])
        actuator = _RecordingActuator()

        with self.assertRaisesRegex(RuntimeError, "Manage Characters"):
            self._navigation(actuator, observer).select_castle(self.target, observe_content=observer)

        self.assertEqual(actuator.actions, [])

    def _navigation(self, actuator, observer, *, policy=None) -> NavigationCore:
        return NavigationCore(
            actuator=actuator,
            observe=observer,
            edges=(),
            policy=policy or NavigationPolicy(max_observations=4, max_seconds=5, poll_seconds=0),
            sleep=lambda _: None,
        )

    def _window(self, castle: CastleIdentity, *, selected: bool = False, at: int):
        row = make_entry(
            ListEntryKind.CASTLE,
            title=castle.castle_name,
            metadata={"kingdom": castle.kingdom, "castle_level": castle.castle_level},
            selected=selected,
        )
        return self._frame((row,), at=at)

    def _frame(self, entries, *, screen=ScreenType.PNC_CASTLE_SELECTION, at: int):
        observation = make_observation(screen, list_entries=entries)
        return replace(observation, captured_at=self._time(at))

    @staticmethod
    def _time(at: int) -> datetime:
        return datetime(2026, 9, 12, 18, 0, at, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
