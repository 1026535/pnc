"""Safely verify that live home-city buildings expose their Upgrade entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    home_city_map_coordinate,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import SelectorResolutionError
from tests.live_smoke_support import build_live_automation_runner, execute_live_flow_until

UpgradeResult = tuple[str, str, bool, bool, str]


def _parse_args() -> argparse.Namespace:
    """Parses the live account and explicitly bounded building target list."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--account", default="testing")
    parser.add_argument("--targets", required=True, help="Comma-separated canonical building ids.")
    parser.add_argument("--targeted-only", action="store_true", help="Skip the generic panorama tour.")
    parser.add_argument(
        "--inspect-speedup-dialog",
        action="store_true",
        help="Open an already-active building's Speedup dialog without consuming an item.",
    )
    return parser.parse_args()


def _inspect_visible_targets(
    *,
    runner: AutomationRunner,
    observation: Observation,
    targets: frozenset[HomeCityObjectId],
    results: dict[HomeCityObjectId, UpgradeResult],
    inspect_speedup_dialog: bool,
) -> Observation:
    """Opens each new OCR-proven target in the current view and returns to the same city camera."""

    visible_targets = tuple(
        (object_id, object_)
        for object_ in observation.spatial_objects(SpatialObjectKind.HOME_BUILDING)
        for object_id in (home_city_object_id_from_metadata(object_.metadata),)
        if object_id in targets and object_id not in results
    )
    for target, object_ in visible_targets:
        actions = runner.flow_planner.open_visible_home_city_object(
            observation,
            object_,
            reason=f"phase1_open_visible_{target.value}",
        )
        execution = runner.action_executor.execute_actions(
            actions,
            observation,
            observe=lambda label, request=None: runner.observation_service.observe(
                f"phase1_upgrade_entry_{target.value}_{label}",
                request,
            ),
        )
        opened = execution.observation
        has_upgrade = opened.has(UiElementId.PNC_BUILDING_UPGRADE_BUTTON)
        has_speedup = opened.has(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON)
        status = "pass" if has_upgrade or has_speedup else "progression_locked"
        results[target] = (
            status,
            opened.screen_type.value,
            has_upgrade,
            has_speedup,
            str(opened.artifact_path),
        )
        if inspect_speedup_dialog and has_speedup:
            execution = runner.action_executor.execute_actions(
                [
                    TapAction(
                        selector_id=UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,
                        reason=f"inspect_{target.value}_speedup_dialog",
                        observe_after=True,
                    )
                ],
                opened,
                observe=lambda label, request=None: runner.observation_service.observe(
                    f"phase1_speedup_dialog_{target.value}_{label}",
                    request,
                ),
            )
            dialog = execution.observation
            print(f"speedup_dialog|{target.value}|{dialog.screen_type.value}|{dialog.artifact_path}")
        observation = execute_live_flow_until(
            runner=runner,
            label_prefix=f"phase1_upgrade_return_{target.value}",
            planner=runner.flow_planner.ensure_home_city,
            done=lambda current: current.screen_type == ScreenType.PNC_HOME_CITY,
            max_steps=6,
        )
    return observation


def main() -> int:
    """Surveys once, opens encountered targets, and never presses the Upgrade control."""

    args = _parse_args()
    targets = frozenset(HomeCityObjectId(value.strip()) for value in args.targets.split(",") if value.strip())
    application = build_application_runner(args.config)
    account = application.script_runner.config.require_account(args.account)
    runner = build_live_automation_runner(config_account=account, script_runner=application.script_runner)
    observation = execute_live_flow_until(
        runner=runner,
        label_prefix="phase1_upgrade_survey_home",
        planner=runner.flow_planner.ensure_home_city,
        done=lambda current: current.screen_type == ScreenType.PNC_HOME_CITY,
        max_steps=6,
    )
    results: dict[HomeCityObjectId, UpgradeResult] = {}
    survey_state: dict[str, object] = {}
    survey_query = SpatialObjectQuery(
        surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
        kind=SpatialObjectKind.HOME_BUILDING,
        name_text="__phase1_survey_target__",
    )
    if not args.targeted_only:
        for step_index in range(runner.flow_planner.home_city_navigator.focus_step_budget() + 1):
            observation = _inspect_visible_targets(
                runner=runner,
                observation=observation,
                targets=targets,
                results=results,
                inspect_speedup_dialog=args.inspect_speedup_dialog,
            )
            if step_index >= runner.flow_planner.home_city_navigator.focus_step_budget():
                break
            actions = runner.flow_planner.focus_home_city_object(
                observation,
                survey_query,
                runtime_state=survey_state,
            )
            execution = runner.action_executor.execute_actions(
                actions,
                observation,
                observe=lambda label, request=None: runner.observation_service.observe(
                    f"phase1_upgrade_survey_{step_index}_{label}",
                    request,
                ),
            )
            observation = execution.observation

    for target in sorted(targets - results.keys(), key=lambda item: item.value):
        coordinate = home_city_map_coordinate(target)
        if coordinate is None:
            continue
        route_state: dict[str, object] = {}
        actions = []
        anchor_state: dict[str, object] = {}
        for anchor_attempt in range(6):
            try:
                actions = runner.flow_planner.focus_home_city_coordinate(
                    observation,
                    coordinate,
                    runtime_state=route_state,
                )
                break
            except SelectorResolutionError:
                anchor_actions = runner.flow_planner.focus_home_city_object(
                    observation,
                    survey_query,
                    runtime_state=anchor_state,
                )
                execution = runner.action_executor.execute_actions(
                    anchor_actions,
                    observation,
                    observe=lambda label, request=None: runner.observation_service.observe(
                        f"phase1_upgrade_anchor_{target.value}_{anchor_attempt}_{label}",
                        request,
                    ),
                )
                observation = execution.observation
        if actions:
            execution = runner.action_executor.execute_actions(
                actions,
                observation,
                observe=lambda label, request=None: runner.observation_service.observe(
                    f"phase1_upgrade_focus_{target.value}_{label}",
                    request,
                ),
            )
            observation = execution.observation
        observation = _inspect_visible_targets(
            runner=runner,
            observation=observation,
            targets=targets,
            results=results,
            inspect_speedup_dialog=args.inspect_speedup_dialog,
        )

    print("building|status|screen|upgrade|speedup|artifact")
    for target in sorted(targets, key=lambda item: item.value):
        result = results.get(target)
        if result is None:
            print(f"{target.value}|not_observed|||false|")
            continue
        status, screen, upgrade, speedup, artifact = result
        print(f"{target.value}|{status}|{screen}|{str(upgrade).lower()}|{str(speedup).lower()}|{artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
