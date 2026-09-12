"""Castle target preparation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pathlib import Path
import unittest

from pnc_automation.app.authoring.scripts.models import CastleRefRepeatBlock, RunScript, ScriptStep
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.models import (
    AccountCastleTargetsConfig,
    CastleTargetDefinition,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.core.errors import ScriptValidationError

from tests.support.entrypoints.castle_targeting.runtime_castle_targeting_fixtures import (
    RuntimeCastleTargetingFixtures,
)


class CastleTargetPreparationTests(RuntimeCastleTargetingFixtures, unittest.TestCase):
    """Proves castle target preparation."""

    def test_prepare_script_rejects_castle_for_disallowed_task(self) -> None:
        """Rejects step-level castle targeting on tasks that explicitly disallow it."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(ScriptStep(task=TaskId.LOGIN, castle=self.target_castle),),
        )

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(script)

    def test_prepare_script_requires_castle_for_select_castle(self) -> None:
        """Rejects `select_castle` steps that omit their required explicit target."""

        registry = build_default_task_registry()
        script = RunScript(
            name="invalid",
            path=Path("invalid.yaml"),
            steps=(ScriptStep(task=TaskId.SELECT_CASTLE),),
        )

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(script)

    def test_prepare_script_accepts_castle_for_optional_task(self) -> None:
        """Preserves optional step-level castle targets on normal post-login tasks."""

        registry = build_default_task_registry()
        prepared = registry.prepare_script(
            RunScript(
                name="valid",
                path=Path("valid.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle=self.target_castle, params={}),),
            )
        )

        self.assertEqual(prepared.steps[0].castle, self.target_castle)

    def test_prepare_script_resolves_castle_ref_from_account_targets(self) -> None:
        """Resolves authored castle aliases once the selected account's target catalog is available."""

        registry = build_default_task_registry()
        prepared = registry.prepare_script(
            RunScript(
                name="valid",
                path=Path("valid.yaml"),
                steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle_ref="main", params={}),),
            ),
            castle_targets=AccountCastleTargetsConfig(
                account_id=self.account.id,
                targets=(CastleTargetDefinition(target_id="main", castle=self.target_castle),),
            ),
        )

        self.assertEqual(prepared.steps[0].castle, self.target_castle)
        self.assertEqual(prepared.steps[0].castle_ref, "main")

    def test_prepare_script_rejects_unknown_castle_ref(self) -> None:
        """Fails fast when a script references a castle alias absent from the selected account."""

        registry = build_default_task_registry()

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(
                RunScript(
                    name="invalid",
                    path=Path("invalid.yaml"),
                    steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE, castle_ref="main", params={}),),
                ),
                castle_targets=AccountCastleTargetsConfig(account_id=self.account.id, targets=()),
            )

    def test_prepare_script_expands_repeat_block_in_authored_castle_then_step_order(self) -> None:
        """Flattens one multi-castle repeat block into the existing concrete prepared-step contract."""

        registry = build_default_task_registry()
        farm_castle = CastleIdentity(kingdom="K230", castle_name="Farm", castle_level=6)
        prepared = registry.prepare_script(
            RunScript(
                name="multi_castle",
                path=Path("multi_castle.yaml"),
                steps=(
                    ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                    CastleRefRepeatBlock(
                        castle_refs=("main", "farm"),
                        steps=(
                            ScriptStep(
                                task=TaskId.BUILDING_UPGRADE,
                                params={"priority": ["castle"], "allow_speedups": False},
                            ),
                            ScriptStep(task=TaskId.RESEARCH, params={"priority": ["economy"]}),
                        ),
                    ),
                ),
            ),
            castle_targets=AccountCastleTargetsConfig(
                account_id=self.account.id,
                targets=(
                    CastleTargetDefinition(target_id="main", castle=self.target_castle),
                    CastleTargetDefinition(target_id="farm", castle=farm_castle),
                ),
            ),
        )

        self.assertEqual(
            [step.task for step in prepared.steps],
            [
                TaskId.ENSURE_GAME_RUNNING,
                TaskId.BUILDING_UPGRADE,
                TaskId.RESEARCH,
                TaskId.BUILDING_UPGRADE,
                TaskId.RESEARCH,
            ],
        )
        self.assertEqual([step.castle_ref for step in prepared.steps[1:]], ["main", "main", "farm", "farm"])
        self.assertEqual(
            [step.castle for step in prepared.steps[1:]],
            [self.target_castle, self.target_castle, farm_castle, farm_castle],
        )
        self.assertEqual(prepared.steps[1].provenance["step_path"], "steps[1].steps[0]")
        self.assertEqual(prepared.steps[3].provenance["repeat_castle_ref"], "farm")

    def test_prepare_script_binds_castle_agnostic_routine_to_runtime_castle_refs(self) -> None:
        """Repeats one canonical routine body for ordered CLI-supplied castle aliases."""

        registry = build_default_task_registry()
        farm_castle = CastleIdentity(kingdom="K230", castle_name="Farm", castle_level=6)

        prepared = registry.prepare_script(
            RunScript(
                name="daily",
                path=Path("daily.yaml"),
                steps=(
                    ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
                    ScriptStep(task=TaskId.LOGIN),
                    ScriptStep(
                        task=TaskId.BUILDING_UPGRADE,
                        params={"priority": ["castle"], "allow_speedups": False},
                    ),
                ),
            ),
            castle_targets=AccountCastleTargetsConfig(
                account_id=self.account.id,
                targets=(
                    CastleTargetDefinition(target_id="main", castle=self.target_castle),
                    CastleTargetDefinition(target_id="farm", castle=farm_castle),
                ),
            ),
            castle_refs=["main", "farm"],
        )

        self.assertEqual(
            [step.task for step in prepared.steps],
            [
                TaskId.ENSURE_GAME_RUNNING,
                TaskId.LOGIN,
                TaskId.BUILDING_UPGRADE,
                TaskId.BUILDING_UPGRADE,
            ],
        )
        self.assertEqual([step.castle_ref for step in prepared.steps[2:]], ["main", "farm"])
        self.assertEqual([step.castle for step in prepared.steps[2:]], [self.target_castle, farm_castle])
        self.assertEqual(prepared.steps[2].provenance["binding"], "runtime_castle_refs")

    def test_prepare_script_rejects_duplicate_runtime_castle_refs(self) -> None:
        """Prevents one scheduler invocation from maintaining the same castle twice."""

        registry = build_default_task_registry()

        with self.assertRaises(ScriptValidationError):
            registry.prepare_script(
                RunScript(
                    name="daily",
                    path=Path("daily.yaml"),
                    steps=(ScriptStep(task=TaskId.BUILDING_UPGRADE),),
                ),
                castle_refs=["main", "main"],
            )

    def test_prepare_script_rejects_unknown_repeat_block_castle_ref(self) -> None:
        """Fails fast when a repeat block references an alias absent from the selected account."""

        registry = build_default_task_registry()

        with self.assertRaises(ScriptValidationError) as error_context:
            registry.prepare_script(
                RunScript(
                    name="invalid",
                    path=Path("invalid.yaml"),
                    steps=(
                        CastleRefRepeatBlock(
                            castle_refs=("main",),
                            steps=(
                                ScriptStep(
                                    task=TaskId.BUILDING_UPGRADE,
                                    params={"priority": ["castle"], "allow_speedups": False},
                                ),
                            ),
                        ),
                    ),
                ),
                castle_targets=AccountCastleTargetsConfig(account_id=self.account.id, targets=()),
            )

        self.assertEqual(error_context.exception.details["step_path"], "steps[0].castle_refs[0]")

    def test_prepare_script_applies_task_target_policy_after_repeat_block_expansion(self) -> None:
        """Keeps the existing task target-policy validation after multi-castle authored expansion."""

        registry = build_default_task_registry()

        with self.assertRaises(ScriptValidationError) as error_context:
            registry.prepare_script(
                RunScript(
                    name="invalid",
                    path=Path("invalid.yaml"),
                    steps=(
                        CastleRefRepeatBlock(
                            castle_refs=("main",),
                            steps=(ScriptStep(task=TaskId.LOGIN),),
                        ),
                    ),
                ),
                castle_targets=AccountCastleTargetsConfig(
                    account_id=self.account.id,
                    targets=(CastleTargetDefinition(target_id="main", castle=self.target_castle),),
                ),
            )

        self.assertEqual(error_context.exception.details["step_path"], "steps[0].steps[0]")

    def test_repeat_block_model_rejects_programmatic_nested_castle_override_inside_repeat_block(self) -> None:
        """Keeps repeat-block castle ownership canonical even for in-memory script construction."""

        with self.assertRaises(ScriptValidationError) as error_context:
            CastleRefRepeatBlock(
                castle_refs=("main",),
                steps=(
                    ScriptStep(
                        task=TaskId.BUILDING_UPGRADE,
                        castle=self.target_castle,
                        params={"priority": ["castle"], "allow_speedups": False},
                    ),
                ),
            )

        self.assertEqual(error_context.exception.details["nested_step_index"], 0)
        self.assertEqual(error_context.exception.details["castle"], self.target_castle)

    def test_repeat_block_model_rejects_non_step_items_during_programmatic_construction(self) -> None:
        """Fails fast with a typed validation error before registry preparation inspects malformed nested items."""

        with self.assertRaises(ScriptValidationError) as error_context:
            CastleRefRepeatBlock(castle_refs=("main",), steps=(object(),))

        self.assertEqual(error_context.exception.details["nested_step_index"], 0)
        self.assertEqual(error_context.exception.details["nested_step_type"], "object")
