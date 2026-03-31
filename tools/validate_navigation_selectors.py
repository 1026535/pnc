"""Live validator for reviewed navigation selectors in the canonical selector registry."""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.vision.navigation_selector_validator import (
    NavigationSelectorValidator,
    write_navigation_selector_validation_report,
)
from pnc_automation.app.pnc.vision.selector_catalog import default_selector_catalog_path
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.storage.path_segments import sanitize_artifact_segment


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
    runtime = script_runner.build_connected_runtime(account=account)
    raw_action_executor = ActionExecutor(
        session=runtime.session,
        stable_click_delay_ms=script_runner.config.defaults.stable_click_delay_ms,
        post_action_observe_delay_ms=script_runner.config.defaults.post_action_observe_delay_ms,
        logger=logging.LoggerAdapter(script_runner.logger.logger, extra={}),
    )
    validator = NavigationSelectorValidator(
        selector_registry=script_runner.observation_builder.selector_registry,
        observation_service=runtime.observation_service,
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
