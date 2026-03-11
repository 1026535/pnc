"""Opt-in live smoke tests for account bootstrap and castle targeting."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.models import AccountConfig
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.observation_builder import ObservationService


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
        cls.account_id = os.getenv("PNC_LIVE_SMOKE_ACCOUNT", "BlueStacks App Player 1")
        cls.script_path = Path(os.getenv("PNC_LIVE_SMOKE_SCRIPT", "scripts/account_navigation_smoke.yaml"))
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        cls.session = _build_live_session(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )
        cls.observation_service = _build_observation_service(
            config_account=cls.account,
            script_runner=cls.script_runner,
            session=cls.session,
        )
        cls.before_observation = cls.observation_service.observe("live_smoke_account_navigation_before")
        cls.run_result = cls.application.run(account_id=cls.account_id, script_path=str(cls.script_path))
        cls.after_observation = cls.observation_service.observe("live_smoke_account_navigation_after")

    def test_live_smoke_run_reports_all_steps_successful(self) -> None:
        """Verifies the live minimal bootstrap script completed without task failures."""

        self.assertGreaterEqual(len(self.run_result.steps), 3)
        self.assertTrue(all(step.status.value == "success" for step in self.run_result.steps), self.run_result.steps)

    def test_live_smoke_final_state_matches_the_configured_castle(self) -> None:
        """Verifies the post-run live observation reflects the configured castle selection."""

        target_castle = self.account.selected_castle
        if self.after_observation.matches_current_castle(target_castle):
            return
        matching_entry = self.after_observation.find_castle_entry(target_castle)
        self.assertIsNotNone(matching_entry, self.after_observation)
        self.assertTrue(matching_entry.selected)
        self.assertEqual(self.after_observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)

    def test_live_smoke_roster_cache_contains_the_configured_castle(self) -> None:
        """Verifies the live run leaves the roster cache synchronized with the selected castle target."""

        roster = self.script_runner.castle_roster_store.get(self.account.pnc_account_id)
        self.assertIsNotNone(roster)
        self.assertTrue(any(castle == self.account.selected_castle for castle in roster.castles), roster)


def _build_live_session(*, config_account: AccountConfig, script_runner: object) -> BlueStacksSession:
    """Creates and connects one live BlueStacks session using the application runtime's authoritative wiring."""

    config = script_runner.config
    instance = BlueStacksInstance.from_config(config.require_instance(config_account.instance_id))
    session = BlueStacksSession(adb_client=script_runner.adb_client, instance=instance)
    session.connect()
    session.ensure_responsive()
    return session


def _build_observation_service(
    *,
    config_account: AccountConfig,
    script_runner: object,
    session: BlueStacksSession,
) -> ObservationService:
    """Builds one live observation service from the same runtime components used by the application."""

    return ObservationService(
        screenshot_service=_require_screenshot_service(script_runner),
        observation_builder=script_runner.observation_builder,
        session=session,
        artifact_directory=config_account.artifact_directory_name,
        pnc_account_id=config_account.pnc_account_id,
        castle_roster_store=script_runner.castle_roster_store,
    )


def _require_screenshot_service(script_runner: object) -> ScreenshotService:
    """Returns the runtime screenshot service or fails fast when the script runner shape changes."""

    screenshot_service = getattr(script_runner, "screenshot_service", None)
    if not isinstance(screenshot_service, ScreenshotService):
        raise AssertionError("Live smoke tests require ScriptRunner.screenshot_service.")
    return screenshot_service
