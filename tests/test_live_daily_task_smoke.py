"""Opt-in live smoke test for one incrementally promoted daily-maintenance task."""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.task import TaskStatus
from pnc_automation.app.authoring.config.mutation_acknowledgement import (
    parse_mutation_acknowledgement,
)
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from tests.live_smoke_support import live_session_cleanup_policy_from_environment


def _live_daily_task_smoke_enabled() -> bool:
    """Returns whether the explicit state-changing daily-task smoke was enabled."""

    return os.getenv("PNC_RUN_LIVE_DAILY_TASK_SMOKE") == "1"


def _require_environment(name: str) -> str:
    """Returns one explicit non-empty live-smoke variable before runtime construction."""

    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Live Daily smoke requires explicit {name}.")
    return value


@unittest.skipUnless(
    _live_daily_task_smoke_enabled(),
    "Set PNC_RUN_LIVE_DAILY_TASK_SMOKE=1 to run the live daily-task smoke.",
)
class LiveDailyTaskSmokeTests(unittest.TestCase):
    """Runs one explicitly acknowledged daily feature smoke on one exact castle."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds the runtime and executes the requested single-feature smoke script."""

        config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        cls.account_id = _require_environment("PNC_LIVE_SMOKE_ACCOUNT")
        cls.script_path = Path(_require_environment("PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT"))
        castle_ref = _require_environment("PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF")
        acknowledgement = parse_mutation_acknowledgement(
            _require_environment("PNC_LIVE_DAILY_TASK_SMOKE_ACKNOWLEDGEMENT")
        )
        expected_date = datetime.now(ZoneInfo("America/Toronto")).date()
        if (
            acknowledgement.account_id != cls.account_id
            or acknowledgement.castle_ref != castle_ref
            or acknowledgement.maintenance_date != expected_date
        ):
            raise ValueError(
                "Live Daily smoke acknowledgement must match the explicit account, castle, "
                "and current America/Toronto date."
            )
        cls.application = build_application_runner(config_path)
        account = cls.application.script_runner.config.require_account(cls.account_id)
        account.require_live_role(LiveAutomationRole.DAILY_CANARY)
        cls.lease_bundle = cls.application.reserve_accounts((cls.account_id,))
        cls.addClassCleanup(cls.lease_bundle.close)
        cls.run_result = cls.application.run(
            account_id=cls.account_id,
            script_path=str(cls.script_path),
            castle_refs=[castle_ref],
            required_role=LiveAutomationRole.DAILY_CANARY,
            session_cleanup_policy=live_session_cleanup_policy_from_environment(),
        )

    def test_live_daily_task_smoke_completes_without_failure(self) -> None:
        """Requires every bootstrap and feature step to complete or safely skip."""

        accepted_statuses = {TaskStatus.SUCCESS, TaskStatus.SKIPPED}
        self.assertTrue(
            all(step.status in accepted_statuses for step in self.run_result.steps),
            self.run_result.steps,
        )

    def test_live_daily_task_smoke_contains_one_feature_step(self) -> None:
        """Prevents the incremental smoke from silently expanding into several feature tasks."""

        feature_steps = tuple(
            step
            for step in self.run_result.steps
            if step.task_id.value not in {"ensure_game_running", "login"}
        )
        self.assertEqual(len(feature_steps), 1, feature_steps)


if __name__ == "__main__":
    unittest.main()
