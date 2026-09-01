"""Opt-in live smoke test for one incrementally promoted daily-maintenance task."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.task import TaskStatus


def _live_daily_task_smoke_enabled() -> bool:
    """Returns whether the explicit state-changing daily-task smoke was enabled."""

    return os.getenv("PNC_RUN_LIVE_DAILY_TASK_SMOKE") == "1"


@unittest.skipUnless(
    _live_daily_task_smoke_enabled(),
    "Set PNC_RUN_LIVE_DAILY_TASK_SMOKE=1 to run the live daily-task smoke.",
)
class LiveDailyTaskSmokeTests(unittest.TestCase):
    """Runs one authored daily feature smoke on the currently active configured castle."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds the runtime and executes the requested single-feature smoke script."""

        config_path = Path(os.getenv("PNC_LIVE_SMOKE_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_SMOKE_ACCOUNT", "testing")
        cls.script_path = Path(
            os.getenv(
                "PNC_LIVE_DAILY_TASK_SMOKE_SCRIPT",
                "scripts/smoke/building_upgrade_smoke.yaml",
            )
        )
        castle_ref = os.getenv("PNC_LIVE_DAILY_TASK_SMOKE_CASTLE_REF")
        cls.application = build_application_runner(config_path)
        cls.run_result = cls.application.run(
            account_id=cls.account_id,
            script_path=str(cls.script_path),
            castle_refs=None if castle_ref is None else (castle_ref,),
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
