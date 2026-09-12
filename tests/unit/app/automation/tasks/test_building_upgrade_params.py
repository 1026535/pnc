"""Building upgrade params."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.tasks.building_upgrade_task import BuildingUpgradeTask
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.pnc.domain.policy_models import BuildingPrerequisiteMode, BuildingPriority

from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


class BuildingUpgradeParamsTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves building upgrade params."""

    def test_building_upgrade_task_parse_params_accepts_priority_file(self) -> None:
        """Loads one ordered building list from a text file so scripts do not need one YAML per target sequence."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "priorities.txt"
            priority_file.write_text("institute\nwarehouse\n", encoding="utf-8")

            params = BuildingUpgradeTask().parse_params({"priority_file": str(priority_file), "allow_speedups": False})

        self.assertEqual(params.priority, (BuildingPriority.INSTITUTE, BuildingPriority.WAREHOUSE))
        self.assertFalse(params.allow_speedups)

    def test_building_upgrade_task_parse_params_supports_explicit_mutation_policies(self) -> None:
        """Loads independent prerequisite, speedup, and premium-material guards."""

        params = BuildingUpgradeTask().parse_params(
            {
                "priority": ["hall_of_war"],
                "allow_speedups": True,
                "prerequisite_mode": "queue",
                "allow_premium_material_purchases": True,
            }
        )

        self.assertTrue(params.allow_speedups)
        self.assertEqual(params.prerequisite_mode, BuildingPrerequisiteMode.QUEUE)
        self.assertTrue(params.allow_premium_material_purchases)

    def test_building_upgrade_task_parse_params_rejects_priority_and_priority_file_together(self) -> None:
        """Fails fast when scripts try to mix direct building priorities with one priority-file source."""

        with tempfile.TemporaryDirectory() as temp_directory:
            priority_file = Path(temp_directory) / "priorities.txt"
            priority_file.write_text("institute\n", encoding="utf-8")

            with self.assertRaises(ScriptValidationError):
                BuildingUpgradeTask().parse_params(
                    {
                        "priority": ["warehouse"],
                        "priority_file": str(priority_file),
                        "allow_speedups": False,
                    }
                )
