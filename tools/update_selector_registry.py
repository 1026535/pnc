"""Offline entry point for applying explicit selector-registry updates."""

from __future__ import annotations

import argparse

from _script_bootstrap import ensure_repo_root_on_path

root = ensure_repo_root_on_path()

from pathlib import Path

from pnc_automation.vision.selector_catalog import default_selector_catalog_path
from pnc_automation.vision.selector_registry_updater import update_selector_registry_files


def main() -> int:
    """Parses arguments and applies one selector-registry update spec."""

    parser = argparse.ArgumentParser(description="Apply explicit selector-registry updates.")
    parser.add_argument("--spec", required=True, help="Path to the selector update spec YAML file.")
    parser.add_argument(
        "--catalog",
        default=str(default_selector_catalog_path()),
        help="Path to the static selector catalog YAML file.",
    )
    parser.add_argument(
        "--ui-element-ids",
        default=str(root / "pnc_automation" / "pnc" / "ui_element_id.py"),
        help="Path to the UiElementId enum source file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and summarize without writing files.")
    arguments = parser.parse_args()

    result = update_selector_registry_files(
        spec_path=Path(arguments.spec),
        catalog_path=Path(arguments.catalog),
        ui_element_id_path=Path(arguments.ui_element_ids),
        dry_run=arguments.dry_run,
    )
    print(f"added_selector_ids={len(result.added_selector_ids)}")
    print(f"updated_selector_ids={len(result.updated_selector_ids)}")
    print(f"added_ui_element_ids={len(result.added_ui_element_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
