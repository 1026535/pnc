"""Run one bounded, read-only canary per explicitly requested navigation selector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from _script_bootstrap import ensure_repo_root_on_path
except ModuleNotFoundError:
    from tools._script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.selector_catalog import default_selector_catalog_path
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from tools.validate_visual_navigation import (
    ProbeRoute,
    run_probe,
    validate_navigation_selector_ids,
)


def _require_ui_element_id(raw_value: str) -> UiElementId:
    """Parse one requested selector identifier before creating any runtime."""

    if raw_value in UiElementId.__members__:
        return UiElementId[raw_value]
    try:
        return UiElementId(raw_value)
    except ValueError as error:
        raise SelectorResolutionError(
            "Unknown UiElementId passed to the navigation-selector validator.",
            selector_id=raw_value,
        ) from error


def _require_screen_type(raw_value: str) -> ScreenType:
    """Parse one reviewed source screen before creating any runtime."""

    if raw_value in ScreenType.__members__:
        return ScreenType[raw_value]
    try:
        return ScreenType(raw_value)
    except ValueError as error:
        raise ValueError(f"Unknown reviewed source screen '{raw_value}'.") from error


def main() -> int:
    """Validate each explicit selector through the shared bounded visual preflight."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(root / "config" / "accounts.yaml"))
    parser.add_argument("--catalog", default=str(default_selector_catalog_path()))
    parser.add_argument("--account", required=True)
    parser.add_argument(
        "--selector",
        action="append",
        required=True,
        help="UiElementId name or value; each selector gets an independent canary run.",
    )
    parser.add_argument(
        "--source-screen",
        action="append",
        help="Reviewed source ScreenType name or value; omit to run every declared source independently.",
    )
    parser.add_argument("--output-dir", default=str(root / ".local-data" / "reports" / "navigation_selector_validation"))
    arguments = parser.parse_args()

    catalog_path = Path(arguments.catalog)
    selector_ids = validate_navigation_selector_ids(
        tuple(_require_ui_element_id(item) for item in arguments.selector),
        catalog_path=catalog_path,
    )
    registry = build_default_selector_registry(catalog_path=catalog_path)
    requested_sources = (
        tuple(_require_screen_type(item) for item in arguments.source_screen)
        if arguments.source_screen
        else None
    )
    cases: list[tuple[UiElementId, ScreenType]] = []
    for selector_id in selector_ids:
        declared_sources = registry.require(selector_id).screens
        sources = declared_sources if requested_sources is None else requested_sources
        for source_screen in sources:
            if source_screen not in declared_sources:
                raise ValueError(
                    f"Selector '{selector_id.value}' is not reviewed from source screen "
                    f"'{source_screen.name}'."
                )
            cases.append((selector_id, source_screen))
    statuses: list[bool] = []
    for selector_id, source_screen in cases:
        try:
            summary_path = run_probe(
                Path(arguments.config),
                arguments.account,
                Path(arguments.output_dir),
                route=ProbeRoute.NAVIGATION_SELECTORS,
                navigation_selectors=(selector_id,),
                navigation_source_screen=source_screen,
                catalog_path=catalog_path,
            )
        except Exception as error:
            print(f"failed:{selector_id.value}:{type(error).__name__}:{error}")
            return 1
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        passed = summary.get("status") == "passed"
        statuses.append(passed)
        print(
            f"{'passed' if passed else 'failed'}:{selector_id.value}:"
            f"source={source_screen.name}:"
            f"summary={summary_path}:report={summary.get('navigation_report')}"
        )
    return 0 if all(statuses) else 1


if __name__ == "__main__":
    raise SystemExit(main())
