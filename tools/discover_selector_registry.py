"""Discovery entry point for staging reviewed selector-registry draft updates."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import ApplicationRunner, build_application_runner
from pnc_automation.artifact_naming import sanitize_artifact_segment
from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.action_requests import ActionRequest, KeyEventAction, TapAction
from pnc_automation.pnc.observation import Observation
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import CapturedObservation, ObservationBuilder, ObservationService
from pnc_automation.vision.selector_catalog import default_selector_catalog_path, load_selector_catalog_document
from pnc_automation.vision.selector_discovery import (
    SelectorDiscoveryAnalyzer,
    SelectorDiscoveryProbe,
    SelectorDiscoverySnapshot,
    load_artifact_paths,
    write_selector_discovery_report,
    write_selector_discovery_spec,
)


@dataclass(frozen=True, slots=True)
class SelectorDiscoveryRuntime:
    """Owns the shared runtime services used by discovery modes."""

    application: ApplicationRunner
    analyzer: SelectorDiscoveryAnalyzer


@dataclass(frozen=True, slots=True)
class SelectorDiscoverySession:
    """Captures the live discovery evidence gathered from one connected run."""

    snapshots: tuple[SelectorDiscoverySnapshot, ...]
    probes: tuple[SelectorDiscoveryProbe, ...]


def main() -> int:
    """Parses arguments and produces one reviewed discovery report plus draft spec."""

    parser = argparse.ArgumentParser(description="Discover reviewed selector-registry draft updates.")
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Path to the runtime config file.")
    parser.add_argument(
        "--catalog",
        default=str(default_selector_catalog_path()),
        help="Path to the selector catalog used by both runtime observation and draft suppression.",
    )
    parser.add_argument("--account", help="Configured account id to use for live connected discovery.")
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Saved screenshot artifact path to analyze. May be provided multiple times.",
    )
    parser.add_argument("--artifact-dir", help="Directory of saved screenshot artifacts to analyze recursively.")
    parser.add_argument("--settle-home-city", action="store_true", help="For live mode, settle the session to home city before probes.")
    parser.add_argument(
        "--probe-selector",
        action="append",
        default=[],
        help="UiElementId name to tap during live discovery. May be provided multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(root / "selector_discovery_output"),
        help="Directory where the report and draft spec should be written.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose runtime logging.")
    arguments = parser.parse_args()

    has_artifact_inputs = bool(arguments.artifact) or arguments.artifact_dir is not None
    if arguments.account is None and not has_artifact_inputs:
        raise SelectorResolutionError("Discovery requires artifact inputs, --account, or both.")
    if arguments.account is None and (arguments.settle_home_city or arguments.probe_selector):
        raise SelectorResolutionError("Live-only discovery flags require --account.", account_id=arguments.account)

    runtime = _build_runtime(config_path=Path(arguments.config), catalog_path=Path(arguments.catalog), verbose=arguments.verbose)
    snapshots = []
    probes: list[SelectorDiscoveryProbe] = []

    if has_artifact_inputs:
        artifact_paths = load_artifact_paths(
            artifact_paths=tuple(Path(path) for path in arguments.artifact),
            artifact_directory=None if arguments.artifact_dir is None else Path(arguments.artifact_dir),
        )
        snapshots.extend(runtime.analyzer.analyze_artifact_path(path) for path in artifact_paths)

    if arguments.account is not None:
        live_session = _run_live_discovery(
            runtime=runtime,
            account_id=arguments.account,
            settle_home_city=arguments.settle_home_city,
            probe_selectors=tuple(arguments.probe_selector),
        )
        snapshots.extend(live_session.snapshots)
        probes.extend(live_session.probes)

    report = runtime.analyzer.build_report(snapshots=tuple(snapshots), probes=tuple(probes))
    output_prefix = _build_output_prefix(
        base_directory=Path(arguments.output_dir),
        stem=_build_output_stem(account_id=arguments.account, includes_artifacts=has_artifact_inputs),
    )

    report_path = output_prefix.with_name(f"{output_prefix.name}_report.yaml")
    spec_path = output_prefix.with_name(f"{output_prefix.name}_spec.yaml")
    write_selector_discovery_report(report_path, report)
    write_selector_discovery_spec(spec_path, report)

    print(f"report={report_path}")
    print(f"spec={spec_path}")
    print(f"snapshots={len(report.snapshots)}")
    print(f"probes={len(report.probes)}")
    print(f"draft_selectors={len(report.draft_selectors)}")
    return 0


def _build_runtime(*, config_path: Path, catalog_path: Path, verbose: bool) -> SelectorDiscoveryRuntime:
    """Builds the shared discovery runtime used by artifact and live discovery."""

    application = build_application_runner(config_path, verbose=verbose, catalog_path=catalog_path)
    return SelectorDiscoveryRuntime(
        application=application,
        analyzer=SelectorDiscoveryAnalyzer(
            observation_builder=application.script_runner.observation_builder,
            ocr_service=_resolve_runtime_ocr_service(application.script_runner.observation_builder),
            catalog=load_selector_catalog_document(catalog_path),
        ),
    )


def _resolve_runtime_ocr_service(observation_builder: ObservationBuilder) -> object:
    """Returns the shared OCR service already used by the runtime observation pipeline."""

    selector_engine_ocr_service = getattr(observation_builder.selector_engine, "ocr_service", None)
    enricher_ocr_service = getattr(observation_builder.enricher, "ocr_service", None)
    if selector_engine_ocr_service is None and enricher_ocr_service is None:
        raise SelectorResolutionError("Selector discovery runtime requires an OCR service on the observation pipeline.")
    if (
        selector_engine_ocr_service is not None
        and enricher_ocr_service is not None
        and selector_engine_ocr_service is not enricher_ocr_service
    ):
        raise SelectorResolutionError("Selector discovery runtime requires one shared OCR service instance.")
    return selector_engine_ocr_service if selector_engine_ocr_service is not None else enricher_ocr_service


def _run_live_discovery(
    *,
    runtime: SelectorDiscoveryRuntime,
    account_id: str,
    settle_home_city: bool,
    probe_selectors: tuple[str, ...],
 ) -> SelectorDiscoverySession:
    """Runs one live connected discovery session and returns the gathered evidence."""

    script_runner = runtime.application.script_runner
    account = script_runner.config.require_account(account_id)
    instance_config = script_runner.config.require_instance(account.instance_id)
    session = BlueStacksSession(
        adb_client=script_runner.adb_client,
        instance=BlueStacksInstance.from_config(instance_config),
    )
    session.connect()
    session.ensure_responsive()

    observation_service = ObservationService(
        screenshot_service=script_runner.screenshot_service,
        observation_builder=script_runner.observation_builder,
        session=session,
        artifact_directory=account.artifact_directory_name,
        pnc_account_id=account.pnc_account_id,
        castle_roster_store=script_runner.castle_roster_store,
    )
    action_executor = ActionExecutor(
        session=session,
        stable_click_delay_ms=script_runner.config.defaults.stable_click_delay_ms,
        post_action_observe_delay_ms=script_runner.config.defaults.post_action_observe_delay_ms,
        logger=logging.LoggerAdapter(script_runner.logger.logger, extra={}),
    )
    flows = ScreenFlowPlanner()

    snapshots = []
    probes: list[SelectorDiscoveryProbe] = []
    latest_capture: CapturedObservation | None = None

    def capture(label: str) -> CapturedObservation:
        nonlocal latest_capture
        latest_capture = observation_service.capture_observation(label)
        snapshots.append(runtime.analyzer.analyze_captured_observation(latest_capture))
        return latest_capture

    current_capture = capture("discovery_start")
    if settle_home_city:
        current_capture = _settle_to_home_city(
            current_capture=current_capture,
            capture=capture,
            action_executor=action_executor,
            flows=flows,
            session=session,
        )

    for selector_name in probe_selectors:
        selector_id = _require_ui_element_id(selector_name)
        if settle_home_city and current_capture.observation.screen_type != ScreenType.PNC_HOME_CITY:
            current_capture = _settle_to_home_city(
                current_capture=current_capture,
                capture=capture,
                action_executor=action_executor,
                flows=flows,
                session=session,
            )
        latest_capture = None
        action_executor.execute_actions(
            (
                TapAction(
                    selector_id=selector_id,
                    reason="selector_discovery_probe",
                    observe_after=True,
                ),
            ),
            current_capture.observation,
            observe=lambda label, selector_id=selector_id: capture(f"probe_{selector_id.value.lower()}_{label}").observation,
        )
        if latest_capture is None:
            raise SelectorResolutionError("Live selector discovery probes must end with a captured destination observation.", selector_id=selector_id)
        probes.append(
            runtime.analyzer.build_probe_draft(
                selector_id=selector_id,
                source_observation=current_capture.observation,
                destination_observation=latest_capture.observation,
                source_artifact_path=current_capture.screenshot.artifact.path,
                destination_artifact_path=latest_capture.screenshot.artifact.path,
            )
        )
        current_capture = latest_capture

    return SelectorDiscoverySession(snapshots=tuple(snapshots), probes=tuple(probes))


def _settle_to_home_city(
    *,
    current_capture: CapturedObservation,
    capture: Callable[[str], CapturedObservation],
    action_executor: ActionExecutor,
    flows: ScreenFlowPlanner,
    session: BlueStacksSession,
    max_steps: int = 10,
) -> CapturedObservation:
    """Settles a live discovery session onto the home-city root before probes."""

    latest_capture = current_capture
    for index in range(max_steps):
        observation = latest_capture.observation
        if observation.screen_type == ScreenType.PNC_HOME_CITY and not observation.blocking_popup:
            return latest_capture
        planned_actions = _plan_settle_actions(observation=observation, flows=flows, session=session)
        if not planned_actions:
            raise SelectorResolutionError(
                "Live discovery could not derive a home-city recovery path.",
                screen_type=observation.screen_type,
                artifact_path=str(observation.artifact_path) if observation.artifact_path else None,
            )
        candidate_capture: CapturedObservation | None = None

        def observe_callback(label: str) -> object:
            nonlocal candidate_capture
            candidate_capture = capture(f"settle_home_{index + 1}_{label}")
            return candidate_capture.observation

        action_executor.execute_actions(planned_actions, observation, observe=observe_callback)
        if candidate_capture is None:
            raise SelectorResolutionError("Live discovery settle steps must capture a destination observation.")
        latest_capture = candidate_capture
    raise SelectorResolutionError(
        "Live discovery could not settle to home city within the configured step budget.",
        max_steps=max_steps,
        screen_type=latest_capture.observation.screen_type,
        artifact_path=str(latest_capture.observation.artifact_path) if latest_capture.observation.artifact_path else None,
    )


def _plan_settle_actions(
    *,
    observation: Observation,
    flows: ScreenFlowPlanner,
    session: BlueStacksSession,
) -> list[ActionRequest]:
    """Builds a conservative recovery step for discovery-only home-city settling."""

    if observation.screen_type == ScreenType.UNKNOWN and not observation.blocking_popup:
        if session.is_app_foregrounded():
            return [KeyEventAction(key_code="KEYCODE_BACK", reason="discovery_unknown_back", observe_after=True)]
        return flows.ensure_pnc_foreground(observation)
    return flows.ensure_home_city(observation)


def _require_ui_element_id(raw_value: str) -> UiElementId:
    """Parses one selector identifier from either its enum member name or enum value."""

    if raw_value in UiElementId.__members__:
        return UiElementId[raw_value]
    try:
        return UiElementId(raw_value)
    except ValueError as error:
        raise SelectorResolutionError("Unknown UiElementId passed to live selector discovery.", selector_id=raw_value) from error


def _build_output_stem(*, account_id: str | None, includes_artifacts: bool) -> str:
    """Returns the output stem describing the evidence sources used by the run."""

    if account_id is None:
        return "artifact_discovery"
    if includes_artifacts:
        return f"mixed_{sanitize_artifact_segment(account_id)}"
    return f"live_{sanitize_artifact_segment(account_id)}"


def _build_output_prefix(*, base_directory: Path, stem: str) -> Path:
    """Returns the timestamped output prefix used for discovery report and spec files."""

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    base_directory.mkdir(parents=True, exist_ok=True)
    return base_directory / f"{timestamp}_{sanitize_artifact_segment(stem)}"


if __name__ == "__main__":
    raise SystemExit(main())
