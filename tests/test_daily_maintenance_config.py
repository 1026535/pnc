"""Offline tests for typed daily-maintenance configuration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.authoring.config.daily_maintenance import load_daily_maintenance_config
from pnc_automation.app.authoring.config.models import (
    AccountCastleTargetsConfig,
    AccountConfig,
    AppConfig,
    CastleIdentity,
    CastleTargetDefinition,
    DefaultsConfig,
    RuntimeConfig,
)
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CampaignExecutionMode,
    DailyQuestId,
    TrialShopPolicyKind,
)
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.models import BlueStacksInstanceConfig


class DailyMaintenanceConfigTests(unittest.TestCase):
    """Covers strict policy parsing and cross-config target validation."""

    def setUp(self) -> None:
        """Creates a private filesystem and canonical app config for each test."""

        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        castle = CastleIdentity(kingdom="K157", castle_name="NPC 2", castle_level=22)
        self.app_config = AppConfig(
            config_path=root / "accounts.yaml",
            castle_roster_path=root / "castles.yaml",
            castle_targets_path=root / "castle_targets.yaml",
            mail_definitions_path=root / "mail_definitions.yaml",
            mail_schedules_path=root / "mail_schedules.yaml",
            artifact_root=root / "artifacts",
            archive_root=root / "archives",
            defaults=DefaultsConfig(),
            runtime=RuntimeConfig(),
            instances=(
                BlueStacksInstanceConfig(id="bs", display_name="PNC Test", app_package="com.example.pnc"),
            ),
            accounts=(AccountConfig(id="mega_old_acc", instance_id="bs", pnc_account_id="test-account"),),
            castle_targets=(
                AccountCastleTargetsConfig(
                    account_id="mega_old_acc",
                    targets=(CastleTargetDefinition(target_id="npc_2", castle=castle),),
                ),
            ),
        )

    def test_loads_typed_campaign_trial_and_premium_limits(self) -> None:
        """Loads one complete target and derives bounded capability policies."""

        config = self._load(
            """
maintenance_timezone: America/Toronto
maintenance_hour_local: 2
game_reset_hour_utc: 0
targets:
  - account_id: mega_old_acc
    castle_ref: npc_2
    enabled_capabilities: [campaign, trial_shop, wishes, resource_building_boost]
    campaign:
      mode: progress_then_farm
      target: {chapter: 10, node: 3}
    trial_shop:
      kind: one_speedup_then_gem
      maximum_quantity: 1
    wishes: {target_total: 5, game_day_limit: 50, max_diamond_spend: null}
    resource_boost: {max_diamond_spend: 200}
"""
        )

        target = config.targets[0]
        self.assertEqual(CampaignExecutionMode.PROGRESS_THEN_FARM, target.campaign.mode)
        self.assertEqual(TrialShopPolicyKind.ONE_SPEEDUP_THEN_GEM, target.trial_shop.kind)
        self.assertIsNone(target.capability(DailyQuestId.WISHES).max_diamond_spend)
        self.assertEqual(5, target.capability(DailyQuestId.WISHES).max_mutations)
        self.assertEqual(50, target.wishes.game_day_limit)
        self.assertEqual(200, target.capability(DailyQuestId.RESOURCE_BUILDING_BOOST).max_diamond_spend)

    def test_rejects_excluded_capability(self) -> None:
        """Prevents an excluded building upgrade from entering the enabled set."""

        with self.assertRaisesRegex(ConfigurationError, "claim-only"):
            self._load(self._minimal_yaml("upgrade_building"))

    def test_defaults_to_disabled_and_midnight_utc(self) -> None:
        """Keeps a newly authored target list inert until deliberately promoted."""

        config = self._load(self._minimal_yaml("praise"))
        self.assertFalse(config.automatic_runs_enabled)
        self.assertEqual(0, config.game_reset_hour_utc)

    def test_rejects_non_boolean_enablement(self) -> None:
        """Rejects truthy strings that could silently enable automatic execution."""

        with self.assertRaisesRegex(ConfigurationError, "must be a boolean"):
            self._load('automatic_runs_enabled: "false"\n' + self._minimal_yaml("praise"))

    def test_rejects_canary_in_automatic_targets(self) -> None:
        """Prevents the same physical castle from taking both roles."""

        with self.assertRaisesRegex(ConfigurationError, "same account/castle"):
            self._load(self._minimal_yaml("praise") + """
canary_targets:
  - account_id: mega_old_acc
    castle_ref: npc_2
    enabled_capabilities: []
""")

    def test_rejects_non_midnight_reset(self) -> None:
        """Does not confuse Toronto maintenance time with the fixed game reset."""

        with self.assertRaisesRegex(ConfigurationError, "midnight UTC"):
            self._load(self._minimal_yaml("praise").replace("game_reset_hour_utc: 0", "game_reset_hour_utc: 1"))

    def test_rejects_fifty_as_daily_wish_target(self) -> None:
        """Rejects the superseded fifty-wish Daily objective."""

        with self.assertRaisesRegex(ConfigurationError, "five"):
            self._load(self._minimal_yaml("wishes") + "    wishes: {target_total: 50}\n")

    def test_rejects_ninety_nine_trial_purchase(self) -> None:
        """Preserves the one-item canary limit instead of the old bulk policy."""

        with self.assertRaisesRegex(ConfigurationError, "maximum_quantity=1"):
            self._load(self._minimal_yaml("trial_shop") + """
    trial_shop: {kind: one_speedup_then_gem, maximum_quantity: 99}
""")

    def test_rejects_missing_campaign_policy(self) -> None:
        """Requires an exact Campaign behavior variant before runtime."""

        with self.assertRaisesRegex(ConfigurationError, "requires a campaign policy"):
            self._load(self._minimal_yaml("campaign"))

    def test_rejects_resource_boost_above_hard_cap(self) -> None:
        """Enforces the locked 200-diamond boost maximum."""

        raw = self._minimal_yaml("resource_building_boost").replace(
            "targets:\n",
            "targets:\n",
        )
        raw += "    resource_boost: {max_diamond_spend: 201}\n"
        with self.assertRaisesRegex(ConfigurationError, "between 0 and 200"):
            self._load(raw)

    def test_rejects_unknown_castle_alias(self) -> None:
        """Fails before emulator launch when an authored alias is stale."""

        with self.assertRaisesRegex(ConfigurationError, "does not define castle target"):
            self._load(self._minimal_yaml("praise").replace("npc_2", "missing"))

    def test_rejects_unexpected_schema_field(self) -> None:
        """Rejects misspelled fields rather than silently using defaults."""

        with self.assertRaisesRegex(ConfigurationError, "Unexpected field 'capabilites'"):
            self._load(self._minimal_yaml("praise") + "    capabilites: []\n")

    def _load(self, text: str):
        """Writes and loads one isolated daily-maintenance configuration."""

        path = Path(self.temporary_directory.name) / "daily_maintenance.yaml"
        path.write_text(text, encoding="utf-8")
        return load_daily_maintenance_config(path, app_config=self.app_config)

    @staticmethod
    def _minimal_yaml(capability: str) -> str:
        """Returns one minimal valid configuration with a chosen capability."""

        return f"""maintenance_timezone: America/Toronto
maintenance_hour_local: 2
game_reset_hour_utc: 0
targets:
  - account_id: mega_old_acc
    castle_ref: npc_2
    enabled_capabilities: [{capability}]
"""


if __name__ == "__main__":
    unittest.main()
