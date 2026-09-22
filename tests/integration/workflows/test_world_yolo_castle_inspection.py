"""Castle inspection requires one qualified source and a verified return route."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    Observation,
    SpatialObjectActionQualification,
    SpatialObjectKind,
    SpatialObjectSourceKind,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.support.pnc.observations import make_observation


def _world_source(*, qualified: bool, name: str | None = "Remote Lord") -> Observation:
    point = (260, 400) if qualified else None
    target = DetectedSpatialObject(
        kind=SpatialObjectKind.CASTLE,
        bounds=Bounds(205, 350, 110, 105),
        name_text=name,
        action_point=point,
        action_bounds=Bounds(260, 400, 1, 1) if qualified else None,
        action_qualification=SpatialObjectActionQualification(
            geometry_policy="fixture_point",
            expected_screen=ScreenType.PNC_PLAYER_TERRITORY,
            review_ref="test_fixture",
        ) if qualified else None,
        source_kind=SpatialObjectSourceKind.YOLO,
    )
    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        image_size=(540, 960),
        spatial_surface=SpatialSurfaceObservation(
            SpatialSurfaceType.WORLD_MAP,
            SpatialViewport(SpatialViewportAddressingKind.COORDINATE_BAR, x=485, y=73),
            objects=(target,),
        ),
    )


class WorldYoloCastleInspectionTests(unittest.TestCase):
    active_castle = CastleIdentity(kingdom="1", castle_name="Own Lord")

    def test_default_observation_only_producer_refuses_before_connection(self) -> None:
        runner = ApplicationRunner(script_runner=Mock())

        with self.assertRaisesRegex(ValueError, "reviewed YOLO interaction policy"):
            runner.run_world_yolo_castle_inspection(account_id="test")

        runner.script_runner.config.require_account.assert_not_called()

    def test_qualified_castle_reaches_player_territory_and_returns_to_world(self) -> None:
        previous = make_observation(ScreenType.PNC_WORLD_MAP)
        source = _world_source(qualified=True)
        detail = make_observation(
            ScreenType.PNC_PLAYER_TERRITORY,
            visible_ids=(
                UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
            ),
        )
        profile = make_observation(
            ScreenType.PNC_PLAYER_PROFILE,
            profile_player_name="Remote Lord",
        )
        territory_return = make_observation(ScreenType.PNC_PLAYER_TERRITORY)
        returned = make_observation(ScreenType.PNC_WORLD_MAP)
        executor = Mock()
        executor.execute_actions.side_effect = (
            SimpleNamespace(observation=detail),
            SimpleNamespace(observation=profile),
            SimpleNamespace(observation=territory_return),
            SimpleNamespace(observation=returned),
        )
        runtime = Mock()
        runtime.observation_count = 2
        runtime.observe.return_value = source
        runtime.runtime.require_observed_action_executor.return_value = executor
        context = WorkflowContext(runtime, last_observation=previous)

        target, observed_source, observed_detail, observed_profile, observed_return = (
            context.inspect_world_yolo_castle(active_castle=self.active_castle)
        )

        self.assertEqual(target.kind, SpatialObjectKind.CASTLE)
        self.assertIs(observed_source, source)
        self.assertIs(observed_detail, detail)
        self.assertIs(observed_profile, profile)
        self.assertIs(observed_return, returned)
        self.assertEqual(executor.execute_actions.call_count, 4)
        first_action = executor.execute_actions.call_args_list[0].args[0][0]
        self.assertEqual(first_action.expected_object, target)
        self.assertEqual(first_action.target_point, target.action_point)

    def test_unqualified_castle_stops_before_executor_access(self) -> None:
        previous = make_observation(ScreenType.PNC_WORLD_MAP)
        runtime = Mock()
        runtime.observation_count = 2
        runtime.observe.return_value = _world_source(qualified=False)
        context = WorkflowContext(runtime, last_observation=previous)

        with self.assertRaisesRegex(RuntimeError, "not qualified"):
            context.inspect_world_yolo_castle(active_castle=self.active_castle)

        runtime.runtime.require_observed_action_executor.assert_not_called()

    def test_unexpected_detail_stops_before_return_input(self) -> None:
        previous = make_observation(ScreenType.PNC_WORLD_MAP)
        source = _world_source(qualified=True)
        executor = Mock()
        executor.execute_actions.return_value = SimpleNamespace(
            observation=make_observation(ScreenType.PNC_WORLD_MAP),
        )
        runtime = Mock()
        runtime.observation_count = 2
        runtime.observe.return_value = source
        runtime.runtime.require_observed_action_executor.return_value = executor
        context = WorkflowContext(runtime, last_observation=previous)

        with self.assertRaisesRegex(RuntimeError, "did not open"):
            context.inspect_world_yolo_castle(active_castle=self.active_castle)

        executor.execute_actions.assert_called_once()

    def test_profile_name_mismatch_stops_before_return_input(self) -> None:
        previous = make_observation(ScreenType.PNC_WORLD_MAP)
        source = _world_source(qualified=True)
        detail = make_observation(
            ScreenType.PNC_PLAYER_TERRITORY,
            visible_ids=(
                UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
            ),
        )
        profile = make_observation(
            ScreenType.PNC_PLAYER_PROFILE,
            profile_player_name="Different Lord",
        )
        executor = Mock()
        executor.execute_actions.side_effect = (
            SimpleNamespace(observation=detail),
            SimpleNamespace(observation=profile),
        )
        runtime = Mock()
        runtime.observation_count = 2
        runtime.observe.return_value = source
        runtime.runtime.require_observed_action_executor.return_value = executor
        context = WorkflowContext(runtime, last_observation=previous)

        with self.assertRaisesRegex(RuntimeError, "did not match"):
            context.inspect_world_yolo_castle(active_castle=self.active_castle)

        self.assertEqual(executor.execute_actions.call_count, 2)

    def test_active_castle_label_stops_before_input(self) -> None:
        previous = make_observation(ScreenType.PNC_WORLD_MAP)
        runtime = Mock()
        runtime.observation_count = 2
        runtime.observe.return_value = _world_source(qualified=True, name="Own Lord")
        context = WorkflowContext(runtime, last_observation=previous)

        with self.assertRaisesRegex(RuntimeError, "active castle"):
            context.inspect_world_yolo_castle(active_castle=self.active_castle)

        runtime.runtime.require_observed_action_executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
