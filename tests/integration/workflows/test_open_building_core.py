"""Focused offline coverage for the replacement-core open-building boundary."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy
from pnc_automation.app.automation.open_building import (
    OpenBuildingResult,
    OpenBuildingWorkflow,
    build_open_building_workflow,
)
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_object_id_for_screen,
    primary_screen_type_for_home_city_object,
)
from pnc_automation.app.pnc.domain.building_details import BuildingDetail, BuildingDetailPhase
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.observations import make_observation


def _building_panel(
    screen: ScreenType,
    building: HomeCityObjectId | None,
    phase: BuildingDetailPhase | None,
    *,
    visible_ids: tuple[UiElementId, ...] = (),
) -> Observation:
    """One synthetic building panel carrying the typed detail the producer publishes."""

    return make_observation(
        screen,
        visible_ids=visible_ids,
        building_detail=(
            None
            if building is None and phase is None
            else BuildingDetail(
                building_id=building,
                phase=phase,
                current_level=7,
                max_level=45,
                level_text="7/45",
            )
        ),
    )


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

    def test_campaign_uses_canonical_primary_screen_and_workflow_endpoint(self) -> None:
        workflow = build_open_building_workflow({"building": HomeCityObjectId.CAMPAIGN.value})

        self.assertEqual(
            ScreenType.PNC_CAMPAIGN_MAP,
            primary_screen_type_for_home_city_object(HomeCityObjectId.CAMPAIGN),
        )
        self.assertEqual(
            HomeCityObjectId.CAMPAIGN,
            home_city_object_id_for_screen(ScreenType.PNC_CAMPAIGN_MAP),
        )
        self.assertEqual(HomeCityObjectId.CAMPAIGN, workflow.policy.building)
        self.assertEqual(ScreenType.PNC_CAMPAIGN_MAP, workflow.spec.exit_screen)

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


class OpenBuildingUpgradeDetailTests(unittest.TestCase):
    """The core upgrade-detail operation taps only the phase-owned entry control."""

    def _core(self, frames: list[Observation]):
        """Wire a scripted content observer and a recording actuator."""

        dispatched: list[TapAction] = []
        actuator = SimpleNamespace(
            execute_action=lambda action, _before: dispatched.append(action) or True,
        )
        observed = iter(frames)
        captured_at = iter(
            datetime(2026, 9, 14, 12, 0, tzinfo=UTC) + timedelta(seconds=index)
            for index in range(len(frames) + 8)
        )
        core = NavigationCore(
            actuator,
            lambda _label: None,
            (),
            policy=NavigationPolicy(poll_seconds=0, max_observations=4, stable_observations=2),
            sleep=lambda _seconds: None,
        )

        def observe(_label: str) -> Observation:
            return replace(next(observed), captured_at=next(captured_at))

        return core, dispatched, observe

    def test_primary_source_taps_generic_entry_and_requires_matching_upgrade_detail(self) -> None:
        primary = _building_panel(
            ScreenType.PNC_BUILDING_DETAILS,
            HomeCityObjectId.FARM,
            BuildingDetailPhase.PRIMARY,
            visible_ids=(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,),
        )
        upgrade = _building_panel(
            ScreenType.PNC_BUILDING_DETAILS,
            HomeCityObjectId.FARM,
            BuildingDetailPhase.UPGRADE,
        )
        core, dispatched, observe = self._core([primary, upgrade, upgrade, upgrade])

        result = core.open_building_upgrade_detail(
            HomeCityObjectId.FARM,
            observe_content=observe,
        )

        self.assertEqual(result.building_detail, upgrade.building_detail)
        self.assertEqual(1, len(dispatched))
        self.assertIsInstance(dispatched[0], TapAction)
        self.assertEqual(
            UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,
            dispatched[0].selector_id,
        )

    def test_named_primary_source_taps_its_own_entry_selector(self) -> None:
        primary = _building_panel(
            ScreenType.PNC_INSTITUTE,
            HomeCityObjectId.INSTITUTE,
            BuildingDetailPhase.PRIMARY,
            visible_ids=(UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON,),
        )
        upgrade = _building_panel(
            ScreenType.PNC_INSTITUTE,
            HomeCityObjectId.INSTITUTE,
            BuildingDetailPhase.UPGRADE,
        )
        core, dispatched, observe = self._core([primary, upgrade, upgrade, upgrade])

        result = core.open_building_upgrade_detail(
            HomeCityObjectId.INSTITUTE,
            observe_content=observe,
        )

        self.assertEqual(result.building_detail, upgrade.building_detail)
        self.assertEqual(
            UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON,
            dispatched[0].selector_id,
        )

    def test_proved_upgrade_source_returns_without_any_tap(self) -> None:
        upgrade = _building_panel(
            ScreenType.PNC_BUILDING_DETAILS,
            HomeCityObjectId.FARM,
            BuildingDetailPhase.UPGRADE,
        )
        core, dispatched, observe = self._core([upgrade])

        result = core.open_building_upgrade_detail(
            HomeCityObjectId.FARM,
            observe_content=observe,
        )

        self.assertEqual(result.building_detail, upgrade.building_detail)
        self.assertEqual([], dispatched)

    def test_upgrade_back_requires_primary_phase_before_home_route(self) -> None:
        upgrade = _building_panel(
            ScreenType.PNC_INSTITUTE, HomeCityObjectId.INSTITUTE, BuildingDetailPhase.UPGRADE,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT,),
        )
        primary = _building_panel(
            ScreenType.PNC_INSTITUTE, HomeCityObjectId.INSTITUTE, BuildingDetailPhase.PRIMARY,
        )
        core, dispatched, observe = self._core([upgrade, upgrade, primary, primary])
        result = core.close_building_upgrade_detail(HomeCityObjectId.INSTITUTE, observe_content=observe)
        self.assertEqual(BuildingDetailPhase.PRIMARY, result.building_detail.phase)
        self.assertEqual([UiElementId.PNC_BACK_BUTTON_TOP_LEFT], [action.selector_id for action in dispatched])

    def test_upgrade_back_does_not_accept_unchanged_upgrade_phase_or_repeat(self) -> None:
        upgrade = _building_panel(
            ScreenType.PNC_INSTITUTE, HomeCityObjectId.INSTITUTE, BuildingDetailPhase.UPGRADE,
            visible_ids=(UiElementId.PNC_BACK_BUTTON_TOP_LEFT,),
        )
        core, dispatched, observe = self._core([upgrade] * 5)
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.close_building_upgrade_detail(HomeCityObjectId.INSTITUTE, observe_content=observe)
        self.assertEqual(1, len(dispatched))

    def test_workflow_navigation_closes_internal_detail_before_graph_route(self) -> None:
        upgrade = _building_panel(
            ScreenType.PNC_INSTITUTE, HomeCityObjectId.INSTITUTE, BuildingDetailPhase.UPGRADE,
        )
        primary = _building_panel(
            ScreenType.PNC_INSTITUTE, HomeCityObjectId.INSTITUTE, BuildingDetailPhase.PRIMARY,
        )
        runtime = Mock()
        runtime.navigation.close_building_upgrade_detail.return_value = primary
        runtime.navigation.navigate.return_value = make_observation(ScreenType.PNC_HOME_CITY)
        context = WorkflowContext(runtime, last_observation=upgrade)
        context.navigate(ScreenType.PNC_HOME_CITY)
        calls = runtime.navigation.mock_calls
        self.assertEqual(["close_building_upgrade_detail", "navigate"], [call[0] for call in calls])

    def test_foreign_or_unphased_source_stops_without_replay(self) -> None:
        cases = (
            _building_panel(
                ScreenType.PNC_BUILDING_DETAILS,
                HomeCityObjectId.FARM,
                BuildingDetailPhase.PRIMARY,
                visible_ids=(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,),
            ),
            _building_panel(
                ScreenType.PNC_BLACKSMITH,
                HomeCityObjectId.BLACKSMITH,
                None,
                visible_ids=(UiElementId.PNC_BLACKSMITH_UPGRADE_BUTTON,),
            ),
            # Even if a generic selector survived publication, an unproved
            # phase still cannot authorize a navigation tap.
            _building_panel(
                ScreenType.PNC_BUILDING_DETAILS,
                HomeCityObjectId.BLACKSMITH,
                None,
                visible_ids=(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,),
            ),
        )
        for source in cases:
            with self.subTest(screen=source.screen_type, phase=source.building_detail.phase):
                core, dispatched, observe = self._core([source])
                with self.assertRaisesRegex(RuntimeError, "unphased|foreign|absent"):
                    core.open_building_upgrade_detail(
                        HomeCityObjectId.BLACKSMITH,
                        observe_content=observe,
                    )
                self.assertEqual([], dispatched)

    def test_foreign_landing_never_confirms_and_never_repeats(self) -> None:
        primary = _building_panel(
            ScreenType.PNC_BUILDING_DETAILS,
            HomeCityObjectId.FARM,
            BuildingDetailPhase.PRIMARY,
            visible_ids=(UiElementId.PNC_BUILDING_DETAILS_UPGRADE_BUTTON,),
        )
        foreign = _building_panel(
            ScreenType.PNC_BUILDING_DETAILS,
            HomeCityObjectId.BLACKSMITH,
            BuildingDetailPhase.UPGRADE,
        )
        core, dispatched, observe = self._core([primary, foreign, foreign, foreign, foreign])

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.open_building_upgrade_detail(
                HomeCityObjectId.FARM,
                observe_content=observe,
            )

        self.assertEqual(1, len(dispatched))


if __name__ == "__main__":
    unittest.main()
