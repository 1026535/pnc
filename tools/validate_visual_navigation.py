"""Prove read-only visual navigation on the active castle, with an append-only trace."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from time import monotonic
from uuid import uuid4

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.navigation_core import NavigationCore, reviewed_navigation_edges
from pnc_automation.app.pnc.domain.action_requests import ActionRequest, KeyEventAction, TapAction, WaitAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.runtime.observation_mode import ObservationMode


ALLOWED_TAPS = frozenset({
    UiElementId.PNC_POPUP_CLOSE_BUTTON,
    UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
    UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,
    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
    UiElementId.PNC_BOTTOM_NAV_MORE,
    UiElementId.PNC_MORE_SETTINGS,
    UiElementId.PNC_MORE_MANAGE_CHAR,
    UiElementId.PNC_BOTTOM_NAV_QUEST,
    UiElementId.PNC_QUEST_TAB_MAIN,
    UiElementId.PNC_QUEST_TAB_DAILY,
    UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
    UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
    UiElementId.PNC_WORLD_HOME_NAV,
})


def validate_probe_action(action: ActionRequest) -> None:
    """Reject any mutation, list-row selection, raw tap, or unbounded wait."""
    if isinstance(action, TapAction) and action.selector_id in ALLOWED_TAPS:
        return
    if isinstance(action, KeyEventAction) and action.key_code == "KEYCODE_BACK":
        return
    if isinstance(action, WaitAction) and 0 <= action.milliseconds <= 1000:
        return
    raise ValueError("Action is outside the read-only visual-navigation allowlist.")


def summarize(observation: Observation) -> dict[str, object]:
    """Persist state and selector evidence without player text or account secrets."""
    return {
        "screen": observation.screen_type.name,
        "blocking_popup": observation.blocking_popup,
        "castle_observed": observation.current_castle is not None,
        "artifact": str(observation.artifact_path),
        "elements": [
            {"id": item.selector_id.value, "source": item.source_kind.value, "bounds": asdict(item.bounds)}
            for item in observation.visible_elements.values()
        ],
    }


def run_probe(config: Path, account_id: str, output_root: Path) -> Path:
    """Launch PNC, prove identity without switching, visit Quest, and return Home."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    directory = output_root / run_id
    directory.mkdir(parents=True, exist_ok=False)
    trace = directory / "trace.jsonl"
    summary_path = directory / "summary.json"
    summary: dict[str, object] = {"run_id": run_id, "status": "running", "trace": str(trace)}
    summary_path.write_text(json.dumps(summary, indent=2))
    started = monotonic()
    action_count = 0
    capture_count = 0

    def record(entry: dict[str, object]) -> None:
        """Flush every pending or completed transition before proceeding."""
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")

    try:
        app = build_application_runner(config, observation_mode=ObservationMode.DEBUG)
        logging.disable(logging.CRITICAL)
        account = app.script_runner.config.require_account(account_id)
        bundle = app.script_runner.build_connected_runtime_bundle(account=account)
        runtime = bundle.runtime
        observer = runtime.observation_service
        # Identity can be observed without changing the user's local roster config.
        observer.castle_roster_store = None
        executor = runtime.require_observed_action_executor("Visual navigation requires observed execution.")
        runtime.session.ensure_app_foregrounded()

        def observe(label: str, request: ObservationRequest | None = None) -> Observation:
            """Capture uniquely named evidence through the canonical observation service."""
            nonlocal capture_count
            capture_count += 1
            capture = observer.capture_observation(f"visual_{run_id}_{capture_count}_{label}", request=request)
            current = capture.observation
            recognizer = observer.observation_builder.visual_recognizer
            profiles = () if recognizer is None else recognizer.recognize(capture.screenshot.image).profile_ids
            record({"event": "observation", "state": summarize(current), "visual_profiles": profiles})
            return current

        current = observe("baseline")

        def step(action: ActionRequest) -> None:
            """Validate one bounded action, record intent, and retain executor evidence."""
            nonlocal current, action_count
            if action_count >= 16 or monotonic() - started > 600:
                raise RuntimeError("Read-only visual navigation exhausted its action/time budget.")
            if current.screen_type == ScreenType.UNKNOWN:
                raise RuntimeError("Visual navigation cannot act on an unknown screen.")
            if current.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON):
                raise RuntimeError("Required update reached; the read-only probe stops before confirming.")
            validate_probe_action(action)
            action_count += 1
            action_data = {"type": type(action).__name__, "reason": action.reason}
            if isinstance(action, TapAction):
                action_data["selector"] = action.selector_id.value
            record({"event": "pending_action", "index": action_count, "action": action_data, "before": summarize(current)})
            result = executor.execute_actions((action,), current, observe=observe)
            current = result.observation
            record({"event": "completed_action", "index": action_count, "after": summarize(current)})

        def reach(target: ScreenType, planner: Callable[[Observation], Sequence[ActionRequest]]) -> None:
            """Use existing flow planning one observed transition at a time."""
            nonlocal current
            for _ in range(6):
                if current.screen_type == target:
                    return
                if current.screen_type == ScreenType.PNC_POPUP or current.blocking_popup:
                    actions = runtime.flow_planner.close_blocking_popup(current)
                else:
                    actions = planner(current)
                if not actions:
                    break
                step(actions[0])
            if current.screen_type != target:
                raise RuntimeError(f"Read-only visual navigation did not reach {target.name}.")

        reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        reach(ScreenType.PNC_MORE_MENU, runtime.flow_planner.open_more_menu)
        reach(ScreenType.PNC_CASTLE_SELECTION, runtime.flow_planner.open_castle_selection)
        if current.current_castle is None:
            raise RuntimeError("Active castle identity was not observed; no castle switch is allowed.")
        active_castle = current.current_castle
        summary["active_identity_verified"] = True
        reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        step(TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_QUEST, observe_after=True, reason="inspect_quest", follow_up_request=ObservationRequest.daily_quest_follow_up()))
        if current.screen_type not in {ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}:
            raise RuntimeError("Quest navigation did not produce a supported Quest tab.")
        if current.screen_type != ScreenType.PNC_QUEST_DAILY:
            step(TapAction(selector_id=UiElementId.PNC_QUEST_TAB_DAILY, observe_after=True, reason="inspect_daily_tab", follow_up_request=ObservationRequest.daily_quest_follow_up()))
        if current.screen_type != ScreenType.PNC_QUEST_DAILY:
            raise RuntimeError("The Daily tab postcondition was not observed.")
        summary["daily_tab_verified"] = True
        reach(ScreenType.PNC_HOME_CITY, runtime.flow_planner.ensure_home_city)
        if current.current_castle is not None and current.current_castle != active_castle:
            raise RuntimeError("Observed castle identity changed during the read-only proof.")
        summary.update(status="passed", actions=action_count, final=summarize(current))
    except Exception as error:
        summary.update(status="failed", actions=action_count, error_type=type(error).__name__)
        record({"event": "failure", "error_type": type(error).__name__})
        summary_path.write_text(json.dumps(summary, indent=2))
        raise RuntimeError(f"Read-only proof failed; inspect {summary_path}") from error
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary_path


def main() -> int:
    """Parse one opt-in live navigation proof, with testing as the default target."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/accounts.yaml"))
    parser.add_argument("--account", default="testing")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/screen_recognition/live"))
    parser.add_argument("--replacement-core", action="store_true", help="Prove identity, then exercise the independent visual navigation core.")
    arguments = parser.parse_args()
    probe = run_replacement_probe if arguments.replacement_core else run_probe
    print(probe(arguments.config, arguments.account, arguments.output_dir))
    return 0


def run_replacement_probe(config: Path, account_id: str, output_root: Path) -> Path:
    """Use legacy identity preflight, then navigate with no legacy perception/retries."""
    logging.disable(logging.CRITICAL)
    directory = output_root / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_core_" + uuid4().hex[:8])
    directory.mkdir(parents=True, exist_ok=False)
    app = build_application_runner(config, observation_mode=ObservationMode.DEBUG)
    runtime = app.script_runner.build_connected_runtime(account=app.script_runner.config.require_account(account_id))
    observer = runtime.observation_service
    recognizer = observer.observation_builder.visual_recognizer
    if recognizer is None:
        raise RuntimeError("Replacement core requires the reviewed visual catalog.")
    perception = NavigationPerception(recognizer, observer.observation_builder.enricher)
    counter = 0
    trace = directory / "trace.jsonl"

    def record(entry: dict[str, object]) -> None:
        with trace.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")

    def observe(label: str, *, include_content: bool = False) -> Observation:
        nonlocal counter
        counter += 1
        screenshot = observer.screenshot_service.capture(
            runtime.session, artifact_directory=observer.artifact_directory,
            label=f"replacement_{directory.name}_{counter}_{label}", persist=True,
        )
        started = monotonic()
        observation = perception.build(screenshot, include_content=include_content)
        record({"event": "perception", "seconds": monotonic() - started, "state": summarize(observation)})
        return observation

    core = NavigationCore(
        runtime.require_observed_action_executor("Core probe requires the connected actuator.").action_executor,
        observe, reviewed_navigation_edges(), record=record,
    )
    summary: dict[str, object] = {"status": "running", "targets": []}
    try:
        # Return from a recognized map/modal through the new core before using
        # the retained identity parser. No target selection is part of either path.
        core.navigate(ScreenType.PNC_HOME_CITY)
        preflight = run_probe(config, account_id, output_root / "identity")
        summary["identity_preflight"] = str(preflight)
        for target in (
            ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_EXPANDED,
            ScreenType.PNC_WORLD_COORDINATE_DIALOG,
            ScreenType.PNC_WORLD_MAP_OVERVIEW, ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_QUEST_DAILY, ScreenType.PNC_QUEST_MAIN,
            ScreenType.PNC_HOME_CITY, ScreenType.PNC_BAG, ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_SETTINGS, ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_INSTITUTE, ScreenType.PNC_HOME_CITY,
        ):
            current = core.navigate(target)
            summary["targets"].append(target.name)
            print(f"Core confirmed {target.name}", flush=True)
        current = core.open_visible_building(
            HomeCityObjectId.GODDESS_STATUE,
            observe_content=lambda label: observe(label, include_content=True),
        )
        summary["targets"].append(current.screen_type.name)
        print(f"Core confirmed observed building {current.screen_type.name}", flush=True)
        current = core.navigate(ScreenType.PNC_HOME_CITY)
        summary.update(status="passed", final=summarize(current))
    except Exception as error:
        summary.update(status="failed", error_type=type(error).__name__, reason=str(error))
        raise RuntimeError(f"Replacement core proof failed; inspect {directory}") from error
    finally:
        (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    return directory / "summary.json"


if __name__ == "__main__":
    raise SystemExit(main())
