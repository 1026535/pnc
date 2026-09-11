"""Offline pre-ADB tests for the daily-maintenance command boundary."""

from __future__ import annotations

import argparse
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceConfig,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    AppConfig,
    CastleIdentity,
    DefaultsConfig,
    LiveAutomationRole,
    RuntimeConfig,
)
from pnc_automation.app.entrypoints.cli import _run_daily_maintenance
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId
from pnc_automation.core.infra.emulator.models import BlueStacksInstanceConfig


class DailyCliTests(unittest.TestCase):
    """Requires promotion and authority checks before connected runner construction."""

    def test_disabled_config_fails_before_worker_factory(self) -> None:
        """Stops even claim-only work before creating any connected runtime."""

        with (
            patch("pnc_automation.app.entrypoints.cli.load_app_config", return_value=_app_config()),
            patch(
                "pnc_automation.app.entrypoints.cli.load_daily_maintenance_config",
                return_value=DailyMaintenanceConfig("America/Toronto", 2, 0, (_target(),)),
            ),
            patch("pnc_automation.app.entrypoints.cli.ConnectedClaimOnlyRunnerFactory") as factory,
        ):
            with self.assertRaisesRegex(PermissionError, "disabled"):
                _run_daily_maintenance(_arguments(_acknowledgement(max_mutations=100)))
        factory.assert_not_called()

    def test_reset_uses_utc_date_during_toronto_previous_evening(self) -> None:
        """Separates the local maintenance date from the midnight-UTC game day."""

        with (
            patch("pnc_automation.app.entrypoints.cli.load_app_config", return_value=_app_config()),
            patch(
                "pnc_automation.app.entrypoints.cli.load_daily_maintenance_config",
                return_value=DailyMaintenanceConfig(
                    "America/Toronto", 2, 0, (_target(),), automatic_runs_enabled=True,
                ),
            ),
            patch("pnc_automation.app.entrypoints.cli.datetime") as clock,
            patch("pnc_automation.app.entrypoints.cli.DailyMutationAuthorizer"),
            patch("pnc_automation.app.entrypoints.cli.ConnectedClaimOnlyRunnerFactory"),
            patch("pnc_automation.app.entrypoints.cli.DailyMaintenanceApplicationService") as service,
            patch("pnc_automation.app.entrypoints.cli.asdict", return_value={}),
            patch("builtins.print"),
        ):
            clock.now.return_value = datetime(2026, 9, 8, 21, tzinfo=ZoneInfo("America/Toronto"))
            _run_daily_maintenance(_arguments(_acknowledgement(max_mutations=100)))
        boundary = service.return_value.run.call_args.kwargs["boundary"]
        self.assertEqual("2026-09-08", boundary.maintenance_date.isoformat())
        self.assertEqual("pnc-reset-2026-09-09-00", boundary.game_reset_id)

    def test_unpromoted_capability_fails_before_worker_factory(self) -> None:
        """Rejects enabled action work before any component capable of ADB is built."""

        app_config = _app_config()
        target = _target(
            capabilities=(DailyCapabilityPolicy(DailyQuestId.HERO_ARENA, TaskId.HERO_ARENA, 3),)
        )
        with (
            patch("pnc_automation.app.entrypoints.cli.load_app_config", return_value=app_config),
            patch(
                "pnc_automation.app.entrypoints.cli.load_daily_maintenance_config",
                return_value=DailyMaintenanceConfig("America/Toronto", 2, 0, (target,), automatic_runs_enabled=True),
            ),
            patch("pnc_automation.app.entrypoints.cli.ConnectedClaimOnlyRunnerFactory") as factory,
        ):
            with self.assertRaisesRegex(PermissionError, "not passed their live promotion gates"):
                _run_daily_maintenance(_arguments(_acknowledgement(max_mutations=100)))
        factory.assert_not_called()

    def test_mismatched_claim_cap_fails_before_worker_factory(self) -> None:
        """Rejects a broad or narrow acknowledgement before connected construction."""

        app_config = _app_config()
        with (
            patch("pnc_automation.app.entrypoints.cli.load_app_config", return_value=app_config),
            patch(
                "pnc_automation.app.entrypoints.cli.load_daily_maintenance_config",
                return_value=DailyMaintenanceConfig("America/Toronto", 2, 0, (_target(),), automatic_runs_enabled=True),
            ),
            patch("pnc_automation.app.entrypoints.cli.ConnectedClaimOnlyRunnerFactory") as factory,
        ):
            with self.assertRaises(PermissionError):
                _run_daily_maintenance(_arguments(_acknowledgement(max_mutations=99)))
        factory.assert_not_called()


def _app_config() -> AppConfig:
    """Builds one minimal application config."""

    return AppConfig(
        config_path=Path("accounts.yaml"),
        castle_roster_path=Path("castles.yaml"),
        castle_targets_path=Path("targets.yaml"),
        mail_definitions_path=Path("mail.yaml"),
        mail_schedules_path=Path("schedules.yaml"),
        artifact_root=Path("artifacts"),
        archive_root=Path("archive"),
        defaults=DefaultsConfig(),
        runtime=RuntimeConfig(),
        instances=(BlueStacksInstanceConfig("instance", "Instance", "game"),),
        accounts=(
            AccountConfig(
                "account",
                "instance",
                "pnc",
                live_roles=frozenset({LiveAutomationRole.DAILY_CANARY}),
            ),
        ),
    )


def _target(*, capabilities=()) -> DailyMaintenanceTargetConfig:
    """Builds one exact target fixture."""

    return DailyMaintenanceTargetConfig(
        account_id="account",
        castle_ref="castle",
        castle=CastleIdentity("K1", "Castle"),
        capabilities=capabilities,
        max_claims=100,
    )


def _arguments(acknowledgement: str) -> argparse.Namespace:
    """Builds parsed-command shaped arguments."""

    return argparse.Namespace(
        config="accounts.yaml",
        daily_config="daily.yaml",
        acknowledgement=[acknowledgement],
        verbose=False,
    )


def _acknowledgement(*, max_mutations: int) -> str:
    """Builds one current-date strict claim acknowledgement."""

    return json.dumps(
        {
            "account_id": "account",
            "castle_ref": "castle",
            "capability": "claim_completed",
            "maintenance_date": datetime.now(ZoneInfo("America/Toronto")).date().isoformat(),
            "max_mutations": max_mutations,
            "max_diamond_spend": 0,
        }
    )


if __name__ == "__main__":
    unittest.main()
