"""Opt-in read-only smoke coverage for explicit replacement-core recovery."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.core_runtime import build_core_runtime
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.live_smoke_support import live_session_cleanup_policy_from_environment


def _live_smoke_enabled() -> bool:
    """Returns whether the explicit read-only recovery smoke was enabled."""

    return os.getenv("PNC_RUN_LIVE_SMOKE") == "1"


def _require_environment(name: str) -> str:
    """Returns one explicit non-empty live-smoke setting."""

    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Replacement-core recovery smoke requires explicit {name}.")
    return value


@unittest.skipUnless(
    _live_smoke_enabled(),
    "Set PNC_RUN_LIVE_SMOKE=1 to run the replacement-core recovery smoke.",
)
class LiveCoreWorkflowSmokeTests(unittest.TestCase):
    """Confirms the current ``SMOKE_TEST`` account reaches Home twice without mutation."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds one configured ScriptRunner runtime and performs one explicit recovery."""

        config_path = Path(_require_environment("PNC_LIVE_SMOKE_CONFIG"))
        account_id = _require_environment("PNC_LIVE_SMOKE_ACCOUNT")
        application = build_application_runner(config_path)
        account = application.script_runner.config.require_account(account_id)
        core_runtime = build_core_runtime(
            application.script_runner,
            account,
            account.artifact_directory_name,
            required_role=LiveAutomationRole.SMOKE_TEST,
            session_cleanup_policy=live_session_cleanup_policy_from_environment(),
        )
        cls.addClassCleanup(core_runtime.close)
        cls.recovered = CoreWorkflowRunner(core_runtime).recover_to_home()
        cls.follow_up = core_runtime.observe("live_recovery_follow_up")

    def test_recovery_and_follow_up_are_fresh_unblocked_home_frames(self) -> None:
        """Requires two fresh Home observations after the single reviewed recovery call."""

        self.assertEqual(ScreenType.PNC_HOME_CITY, self.recovered.screen_type)
        self.assertFalse(self.recovered.blocking_popup)
        self.assertEqual(ScreenType.PNC_HOME_CITY, self.follow_up.screen_type)
        self.assertFalse(self.follow_up.blocking_popup)
        self.assertGreater(self.follow_up.captured_at, self.recovered.captured_at)


if __name__ == "__main__":
    unittest.main()
