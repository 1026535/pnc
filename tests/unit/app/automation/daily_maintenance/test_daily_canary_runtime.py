"""Offline regressions for canonical canary identity preflight."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pnc_automation.app.automation.daily_maintenance.canary_runtime import verify_canary_identity
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.observations import make_observation


class CanaryIdentityRecoveryTests(unittest.TestCase):
    """Protects named canaries through the caller-owned canonical core runtime."""

    def test_canonical_preflight_borrows_connected_runtime_and_returns_home_evidence(self) -> None:
        """Uses one caller-owned core graph and returns its final unblocked Home observation."""

        active = CastleIdentity("K157", "NPC 2", 22)
        target = _target(active)
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        actions = Mock()
        runtime.require_observed_action_executor.return_value = actions
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        home = make_observation(ScreenType.PNC_HOME_CITY)
        core_runtime.last_observation = home
        connected = SimpleNamespace(runtime=runtime)

        with patch(
            "pnc_automation.app.automation.daily_maintenance.canary_runtime.assemble_core_runtime",
            return_value=core_runtime,
        ) as assemble:
            result = verify_canary_identity(
                script_runner=script_runner,
                connected=connected,
                target=target,
            )

        self.assertEqual(home, result.observation)
        self.assertIs(actions, result.action_executor)
        assemble.assert_called_once_with(
            script_runner=script_runner,
            connected_runtime=runtime,
            account=account,
            artifact_directory="account",
            policy=None,
            trace_path=None,
        )
        core_runtime.preflight_active_castle_identity.assert_called_once_with()
        core_runtime.close.assert_not_called()
        runtime.observation_service.observe.assert_not_called()
        script_runner.run_task.assert_not_called()

    def test_mismatched_target_fails_without_fallback_or_runtime_close(self) -> None:
        """Stops on an exact identity mismatch without replaying legacy bootstrap or UI logic."""

        active = CastleIdentity("K157", "NPC 2", 22)
        target = _target(CastleIdentity("K158", "NPC 2", 22))
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.return_value = active
        core_runtime.last_observation = make_observation(ScreenType.PNC_HOME_CITY)
        connected = SimpleNamespace(runtime=runtime)

        with patch(
            "pnc_automation.app.automation.daily_maintenance.canary_runtime.assemble_core_runtime",
            return_value=core_runtime,
        ):
            with self.assertRaisesRegex(ValueError, "different active castle"):
                verify_canary_identity(
                    script_runner=script_runner,
                    connected=connected,
                    target=target,
                )

        runtime.require_observed_action_executor.assert_not_called()
        runtime.observation_service.observe.assert_not_called()
        script_runner.run_task.assert_not_called()
        core_runtime.close.assert_not_called()

    def test_missing_blocked_or_non_home_final_evidence_fails_closed(self) -> None:
        """Rejects a successful identity match without fresh, unblocked Home evidence."""

        active = CastleIdentity("K157", "NPC 2", 22)
        target = _target(active)
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        connected = SimpleNamespace(runtime=runtime)

        invalid_evidence = (
            ("missing", None),
            ("blocked_home", make_observation(ScreenType.PNC_HOME_CITY, blocking_popup=True)),
            ("non_home", make_observation(ScreenType.PNC_CASTLE_SELECTION)),
        )
        for label, evidence in invalid_evidence:
            with self.subTest(label=label):
                core_runtime = Mock()
                core_runtime.preflight_active_castle_identity.return_value = active
                core_runtime.last_observation = evidence
                with patch(
                    "pnc_automation.app.automation.daily_maintenance.canary_runtime.assemble_core_runtime",
                    return_value=core_runtime,
                ):
                    with self.assertRaisesRegex(ValueError, "Home City observation"):
                        verify_canary_identity(
                            script_runner=script_runner,
                            connected=connected,
                            target=target,
                        )

                runtime.require_observed_action_executor.assert_not_called()
                runtime.observation_service.observe.assert_not_called()
                script_runner.run_task.assert_not_called()
                core_runtime.close.assert_not_called()

    def test_preflight_exception_propagates_without_fallback_or_close(self) -> None:
        """Propagates core preflight failure without legacy recovery or cleanup ownership."""

        active = CastleIdentity("K157", "NPC 2", 22)
        target = _target(active)
        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        runtime = Mock()
        core_runtime = Mock()
        core_runtime.preflight_active_castle_identity.side_effect = RuntimeError("preflight failed")
        connected = SimpleNamespace(runtime=runtime)

        with patch(
            "pnc_automation.app.automation.daily_maintenance.canary_runtime.assemble_core_runtime",
            return_value=core_runtime,
        ):
            with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                verify_canary_identity(
                    script_runner=script_runner,
                    connected=connected,
                    target=target,
                )

        runtime.require_observed_action_executor.assert_not_called()
        runtime.observation_service.observe.assert_not_called()
        script_runner.run_task.assert_not_called()
        core_runtime.close.assert_not_called()


def _target(castle: CastleIdentity) -> DailyMaintenanceTargetConfig:
    """Builds a named canary target for one exact castle."""

    return DailyMaintenanceTargetConfig(
        account_id="account_a",
        castle_ref="npc_2",
        castle=castle,
        capabilities=(),
    )


if __name__ == "__main__":
    unittest.main()
