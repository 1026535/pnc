"""Hero canary reconciliation preserves the original journal's calendar boundary."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import JournaledMutationResult
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from tests.support.paths import REPOSITORY_ROOT


class HeroHallCanaryTests(unittest.TestCase):
    def test_reconcile_after_local_midnight_uses_persisted_date_without_new_authority(self) -> None:
        """One UTC reset can span local midnight; receipt inspection must still work."""

        module = _load_tool()
        castle = CastleIdentity("K157", "NPC 2", 22)
        target = DailyMaintenanceTargetConfig("mega_old_acc", "npc_2", castle, (
            DailyCapabilityPolicy(DailyQuestId.HERO_HALL, TaskId.HERO_HALL, 5),
        ))
        checkpoint = DailyTaskCheckpoint(
            "2026-09-13", "pnc-reset-2026-09-14-00", target.account_id, castle,
            mutation_intents=(MutationIntent(
                "hero-hall-recruit-001", DailyQuestId.HERO_HALL, MutationIntentState.DISPATCHED,
                "Free with five attempts", "attempts reduced to four",
                metadata={"before_remaining_daily_attempts": 5},
            ),),
        )
        account = SimpleNamespace(
            id=target.account_id, artifact_directory_name=target.account_id,
            require_live_role=Mock(),
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            DailyRunJournalStore(root).save(checkpoint)
            config = SimpleNamespace(artifact_root=root, require_account=lambda _: account)
            script_runner = SimpleNamespace(
                config=config, reserve_accounts=lambda _: nullcontext(),
                build_connected_runtime_bundle=Mock(side_effect=AssertionError("legacy execution entered")),
            )
            core = object()
            result = CoreWorkflowResult(
                "hero_hall_reconciliation", True,
                JournaledMutationResult(checkpoint, False, False, True, ()),
                ScreenType.PNC_HOME_CITY, "trace.jsonl",
            )
            with (
                patch.object(sys, "argv", ["run_hero_hall_canary.py", "--role", "npc_2",
                    "--reconcile-only", "--game-reset-id", checkpoint.game_reset_id]),
                patch.object(module, "datetime") as clock,
                patch.object(module, "load_app_config", return_value=config),
                patch.object(module, "load_daily_maintenance_config",
                    return_value=SimpleNamespace(canary_targets=(target,))),
                patch.object(module, "build_application_runner",
                    return_value=SimpleNamespace(script_runner=script_runner)),
                patch.object(module, "build_core_runtime", return_value=nullcontext(core)),
                patch.object(module, "CoreWorkflowRunner") as runner,
                patch.object(module.HeroHallRecruitmentExecutor, "execute") as execute,
                patch.object(module, "_write_report"),
                patch.object(module.logging, "disable"),
            ):
                clock.now.return_value = datetime(2026, 9, 14, 4, 10, tzinfo=UTC)
                runner.return_value.run.return_value = result
                self.assertEqual(2, module.main())

            runtime, scope = runner.call_args.args
            self.assertIs(core, runtime)
            self.assertEqual(checkpoint.maintenance_date, scope.boundary.maintenance_date.isoformat())
            self.assertEqual(checkpoint, scope.load_checkpoint(reconcilable_quest=DailyQuestId.HERO_HALL))
            with self.assertRaises(PermissionError):
                scope.authorize()
            workflow = runner.return_value.run.call_args.args[0]
            self.assertEqual("hero-hall-recruit-001", workflow.operation_id)
            self.assertEqual(checkpoint, workflow.checkpoint)
            execute.assert_not_called()
            script_runner.build_connected_runtime_bundle.assert_not_called()


def _load_tool():
    """Load the CLI without executing it or accessing local account configuration."""

    with patch.object(sys, "path", [str(REPOSITORY_ROOT / "tools"), *sys.path]):
        spec = importlib.util.spec_from_file_location(
            "hero_hall_canary_under_test", REPOSITORY_ROOT / "tools" / "run_hero_hall_canary.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
