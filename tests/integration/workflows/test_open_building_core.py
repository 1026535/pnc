"""Focused offline coverage for the replacement-core open-building boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.automation.open_building import (
    OpenBuildingResult,
    OpenBuildingWorkflow,
    build_open_building_workflow,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class OpenBuildingCoreTests(unittest.TestCase):
    """Covers the typed workflow and constrained context."""

    def test_workflow_uses_dynamic_exact_endpoint_and_typed_result(self) -> None:
        workflow = build_open_building_workflow({"building": HomeCityObjectId.INSTITUTE.value})
        captured_at = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
        observation = Observation(
            screen_type=ScreenType.PNC_INSTITUTE,
            visible_elements={},
            captured_at=captured_at,
            artifact_path=Path("institute.png"),
        )
        context = Mock()
        context.open_building.return_value = observation

        result = workflow.execute(context)

        self.assertEqual(ScreenType.PNC_INSTITUTE, workflow.spec.exit_screen)
        self.assertEqual(
            OpenBuildingResult(
                building=HomeCityObjectId.INSTITUTE,
                screen_type=ScreenType.PNC_INSTITUTE,
                captured_at=captured_at,
                artifact_path="institute.png",
            ),
            result,
        )
        context.open_building.assert_called_once_with(HomeCityObjectId.INSTITUTE)

    def test_context_delegates_once_and_does_not_replay_failure(self) -> None:
        runtime = Mock()
        runtime.navigation.open_building.side_effect = RuntimeError("completion failed")
        context = WorkflowContext(
            runtime,
            last_observation=Observation(
                screen_type=ScreenType.PNC_HOME_CITY,
                visible_elements={},
                captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "completion failed"):
            context.open_building(HomeCityObjectId.INSTITUTE)

        runtime.navigation.open_building.assert_called_once()


if __name__ == "__main__":
    unittest.main()
