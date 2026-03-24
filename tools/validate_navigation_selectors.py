"""Live validator for reviewed navigation selectors in the canonical selector registry."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.artifact_naming import sanitize_artifact_segment
from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.automation.observed_action_executor import ObservedActionExecutor
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.navigation_selector_validator import (
    NavigationSelectorValidator,
    write_navigation_selector_validation_report,
)
from pnc_automation.vision.observation_builder import ObservationService
from pnc_automation.vision.selector_catalog import default_selector_catalog_path


def main() -> int:
    """Parses arguments, runs the live validator, and writes a YAML report."""

    parser = argparse.ArgumentParser(description="Validate reviewed navigation selectors against a live session.")
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"), help="Path to the runtime config file.")
    parser.add_argument(
        "--catalog",
        default=str(default_selector_catalog_path()),
        help="Path to the selector catalog used by the runtime.",
    )
    parser.add_argument("--account", required=True, help="Configured account id to validate.")
    parser.add_argument(
        "--selector",
        action="append",
        default=[],
        help="UiElementId name or value to validate. May be provided multiple times. Defaults to all navigation selectors.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(root / "navigation_selector_validation_output"),
        help="Directory where the YAML validation report should be written.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose structured logging.")
    arguments = parser.parse_args()

    application = build_application_runner(
        Path(arguments.config),
        verbose=arguments.verbose,
        catalog_path=Path(arguments.catalog),
    )
    script_runner = application.script_runner
    account = script_runner.config.require_account(arguments.account)
    session = _build_live_session(config_account=account, script_runner=script_runner)
    observation_service = _build_observation_service(
        config_account=account,
        script_runner=script_runner,
        session=session,
    )
    raw_action_executor = ActionExecutor(
        session=session,
        stable_click_delay_ms=script_runner.config.defaults.stable_click_delay_ms,
        post_action_observe_delay_ms=script_runner.config.defaults.post_action_observe_delay_ms,
        logger=logging.LoggerAdapter(script_runner.logger.logger, extra={}),
    )
    validator = NavigationSelectorValidator(
        selector_registry=script_runner.observation_builder.selector_registry,
        observation_service=observation_service,
        action_executor=ObservedActionExecutor(
            selector_registry=script_runner.observation_builder.selector_registry,
            action_executor=raw_action_executor,
            logger=logging.LoggerAdapter(script_runner.logger.logger, extra={}),
        ),
        screen_flows=ScreenFlowPlanner(),
        logger=logging.LoggerAdapter(script_runner.logger.logger, extra={}),
    )
    report = validator.validate(
        selector_ids=None if not arguments.selector else tuple(_require_ui_element_id(item) for item in arguments.selector)
    )
    report_path = _build_output_path(
        base_directory=Path(arguments.output_dir),
        account_id=arguments.account,
    )
    write_navigation_selector_validation_report(report_path, report)

    print(f"report={report_path}")
    print(f"passed={report.passed_count}")
    print(f"failed={report.failed_count}")
    print(f"skipped={report.skipped_count}")
    for result in report.results:
        if result.status.value == "passed":
            continue
        print(
            f"{result.status.value}:{result.selector_id.value}:{result.source_screen.name}:{result.reason}",
        )
    return 0 if report.failed_count == 0 else 1


def _build_live_session(*, config_account: object, script_runner: object) -> BlueStacksSession:
    """Creates and connects one live BlueStacks session using the authoritative application wiring."""

    build_connected_session = getattr(script_runner, "build_connected_session", None)
    if not callable(build_connected_session):
        raise AssertionError("Navigation validation requires ScriptRunner.build_connected_session().")
    session = build_connected_session(account=config_account)
    if not isinstance(session, BlueStacksSession):
        raise AssertionError("Navigation validation requires ScriptRunner.build_connected_session() to return a BlueStacksSession.")
    return session


def _build_observation_service(
    *,
    config_account: object,
    script_runner: object,
    session: BlueStacksSession,
) -> ObservationService:
    """Builds one live observation service from the same runtime components used by automation runs."""

    return ObservationService(
        screenshot_service=script_runner.screenshot_service,
        observation_builder=script_runner.observation_builder,
        session=session,
        artifact_directory=config_account.artifact_directory_name,
        pnc_account_id=config_account.pnc_account_id,
        castle_roster_store=script_runner.castle_roster_store,
    )


def _require_ui_element_id(raw_value: str) -> UiElementId:
    """Parses one requested selector identifier from either its enum member name or value."""

    if raw_value in UiElementId.__members__:
        return UiElementId[raw_value]
    try:
        return UiElementId(raw_value)
    except ValueError as error:
        raise SelectorResolutionError(
            "Unknown UiElementId passed to the navigation-selector validator.",
            selector_id=raw_value,
        ) from error


def _build_output_path(*, base_directory: Path, account_id: str) -> Path:
    """Returns the timestamped validation-report path for one live run."""

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    base_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp}_{sanitize_artifact_segment(account_id)}_navigation_validation.yaml"
    return base_directory / filename


if __name__ == "__main__":
    raise SystemExit(main())
