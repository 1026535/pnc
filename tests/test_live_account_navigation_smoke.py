"""Opt-in live smoke tests for account bootstrap and castle targeting."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.scripts.loader import load_run_script
from pnc_automation.pnc.screen_type import ScreenType
from tests.live_smoke_support import build_live_runtime


def _live_smoke_enabled() -> bool:
    """Returns whether the explicit live-smoke opt-in flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_SMOKE") == "1"


@unittest.skipUnless(_live_smoke_enabled(), "Set PNC_RUN_LIVE_SMOKE=1 to run live smoke tests.")
class LiveAccountNavigationSmokeTests(unittest.TestCase):
    """Runs minimal live account-navigation smoke coverage against a configured BlueStacks session."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds the live runtime, captures a pre-run observation, executes the smoke script, and re-observes."""

        cls.config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_SMOKE_ACCOUNT", "testing")
        cls.script_path = Path(os.getenv("PNC_LIVE_SMOKE_SCRIPT", "scripts/smoke/account_navigation_smoke.yaml"))
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        cls.prepared_script = cls.script_runner.task_registry.prepare_script(
            load_run_script(cls.script_path),
            castle_targets=cls.script_runner.config.find_castle_targets(cls.account_id),
        )
        cls.target_castle = next(
            (
                step.castle
                for step in cls.prepared_script.steps
                if step.task.value == "select_castle" and step.castle is not None
            ),
            None,
        )
        runtime = build_live_runtime(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )
        cls.session = runtime.session
        cls.observation_service = runtime.observation_service
        cls.before_observation = cls.observation_service.observe("live_smoke_account_navigation_before")
        cls.run_result = cls.application.run(account_id=cls.account_id, script_path=str(cls.script_path))
        cls.after_observation = cls.observation_service.observe("live_smoke_account_navigation_after")

    def test_live_smoke_run_reports_all_steps_successful(self) -> None:
        """Verifies the live minimal bootstrap script completed without task failures."""

        self.assertGreaterEqual(len(self.run_result.steps), 3)
        self.assertTrue(all(step.status.value == "success" for step in self.run_result.steps), self.run_result.steps)

    def test_live_smoke_final_state_matches_the_configured_castle(self) -> None:
        """Verifies the post-run live observation reflects the explicit script castle target."""

        target_castle = self.target_castle
        self.assertIsNotNone(target_castle)
        if self.after_observation.matches_current_castle(target_castle):
            return
        matching_entry = self.after_observation.find_castle_entry(target_castle)
        self.assertIsNotNone(matching_entry, self.after_observation)
        self.assertTrue(matching_entry.selected)
        self.assertEqual(self.after_observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)

    def test_live_smoke_roster_cache_contains_the_configured_castle(self) -> None:
        """Verifies the live run leaves the roster cache synchronized with the explicit castle target."""

        self.assertIsNotNone(self.target_castle)
        roster = self.script_runner.castle_roster_store.get(self.account.pnc_account_id)
        self.assertIsNotNone(roster)
        self.assertTrue(any(castle == self.target_castle for castle in roster.castles), roster)

