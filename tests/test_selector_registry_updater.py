"""Offline selector-registry updater tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.vision.selector_catalog import SelectorCatalogDocument, SelectorCatalogEntry, write_selector_catalog_document
from pnc_automation.vision.selector_registry_updater import (
    SelectorRegistryUpdate,
    apply_selector_updates,
    ensure_ui_element_ids,
    update_selector_registry_files,
)


class SelectorRegistryUpdaterTests(unittest.TestCase):
    """Validates the offline registry updater that edits the static selector sources."""

    def test_apply_selector_updates_rejects_status_regression(self) -> None:
        """Fails fast when an update tries to move an existing selector backward in status."""

        with self.assertRaises(SelectorResolutionError):
            apply_selector_updates(
                SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_HOME_BUILD_BUTTON",
                            screens=("PNC_HOME_CITY",),
                            status="click_mapped",
                            detection_kind="template",
                        ),
                    ),
                ),
                (
                    SelectorRegistryUpdate(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                        click=None,
                        update_click=False,
                        notes=(),
                        update_notes=False,
                    ),
                ),
            )

    def test_ensure_ui_element_ids_appends_missing_ids(self) -> None:
        """Adds missing enum members without duplicating selectors already declared."""

        source_text = "\n".join(
            (
                '"""Canonical selector identifiers."""',
                "",
                "from enum import StrEnum",
                "",
                "class UiElementId(StrEnum):",
                '    EXISTING = "EXISTING"',
                "",
            )
        )

        updated_text, added_ids = ensure_ui_element_ids(source_text, ("EXISTING", "NEW_SELECTOR"))

        self.assertEqual(added_ids, ("NEW_SELECTOR",))
        self.assertIn('    NEW_SELECTOR = "NEW_SELECTOR"', updated_text)
        self.assertEqual(updated_text.count('    EXISTING = "EXISTING"'), 1)

    def test_update_selector_registry_files_writes_catalog_and_ui_element_ids(self) -> None:
        """Writes both the static catalog and enum source for explicit selector additions."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = root / "selector_registry.yaml"
            ui_element_id_path = root / "ui_element_id.py"
            spec_path = root / "updates.yaml"

            write_selector_catalog_document(
                catalog_path,
                SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_HOME_BUILD_BUTTON",
                            screens=("PNC_HOME_CITY",),
                            status="screenshot_seeded",
                            detection_kind="template",
                        ),
                    ),
                ),
            )
            ui_element_id_path.write_text(
                "\n".join(
                    (
                        '"""Canonical selector identifiers."""',
                        "",
                        "from enum import StrEnum",
                        "",
                        "class UiElementId(StrEnum):",
                        '    PNC_HOME_BUILD_BUTTON = "PNC_HOME_BUILD_BUTTON"',
                        "",
                    )
                ),
                encoding="utf-8",
                newline="\n",
            )
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_HOME_BUILD_BUTTON",
                                "screens": ["PNC_HOME_CITY", "PNC_BUILDING_DETAILS"],
                                "status": "click_mapped",
                                "detection_kind": "template",
                                "click": {
                                    "anchor": "center",
                                    "outcomes": [
                                        {
                                            "target_screen": "PNC_BUILDING_DETAILS",
                                            "verification_selectors": ["PNC_BUILDING_UPGRADE_BUTTON"],
                                            "safe_to_click": True,
                                            "monetized": False,
                                        }
                                    ],
                                },
                            },
                            {
                                "id": "PNC_HOME_CASTLE_BUILDING",
                                "screens": ["PNC_HOME_CITY"],
                                "status": "screenshot_seeded",
                                "detection_kind": "template",
                            },
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
                newline="\n",
            )

            result = update_selector_registry_files(
                spec_path=spec_path,
                catalog_path=catalog_path,
                ui_element_id_path=ui_element_id_path,
            )

            self.assertEqual(result.added_selector_ids, ("PNC_HOME_CASTLE_BUILDING",))
            self.assertEqual(result.added_ui_element_ids, ("PNC_HOME_CASTLE_BUILDING",))

            catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
            selector_by_id = {selector["id"]: selector for selector in catalog["selectors"]}
            self.assertEqual(
                selector_by_id["PNC_HOME_BUILD_BUTTON"]["screens"],
                ["PNC_HOME_CITY", "PNC_BUILDING_DETAILS"],
            )
            self.assertEqual(selector_by_id["PNC_HOME_BUILD_BUTTON"]["status"], "click_mapped")
            self.assertEqual(selector_by_id["PNC_HOME_BUILD_BUTTON"]["detection_kind"], "template")
            self.assertEqual(
                selector_by_id["PNC_HOME_BUILD_BUTTON"]["click"]["outcomes"][0]["target_screen"],
                "PNC_BUILDING_DETAILS",
            )
            self.assertEqual(selector_by_id["PNC_HOME_CASTLE_BUILDING"]["status"], "screenshot_seeded")
            self.assertIn(
                '    PNC_HOME_CASTLE_BUILDING = "PNC_HOME_CASTLE_BUILDING"',
                ui_element_id_path.read_text(encoding="utf-8"),
            )

    def test_update_selector_registry_files_rejects_unknown_click_outcome_screen(self) -> None:
        """Fails fast when a reviewed click outcome references an unknown screen."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = root / "selector_registry.yaml"
            ui_element_id_path = root / "ui_element_id.py"
            spec_path = root / "updates.yaml"

            write_selector_catalog_document(
                catalog_path,
                SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_HOME_BUILD_BUTTON",
                            screens=("PNC_HOME_CITY",),
                            status="screenshot_seeded",
                            detection_kind="template",
                        ),
                    ),
                ),
            )
            ui_element_id_path.write_text(
                "\n".join(
                    (
                        '"""Canonical selector identifiers."""',
                        "",
                        "from enum import StrEnum",
                        "",
                        "class UiElementId(StrEnum):",
                        '    PNC_HOME_BUILD_BUTTON = "PNC_HOME_BUILD_BUTTON"',
                        "",
                    )
                ),
                encoding="utf-8",
                newline="\n",
            )
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_HOME_BUILD_BUTTON",
                                "screens": ["PNC_HOME_CITY"],
                                "status": "click_mapped",
                                "detection_kind": "template",
                                "click": {
                                    "outcomes": [
                                        {
                                            "target_screen": "NOT_A_SCREEN",
                                        }
                                    ]
                                },
                            }
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                update_selector_registry_files(
                    spec_path=spec_path,
                    catalog_path=catalog_path,
                    ui_element_id_path=ui_element_id_path,
                )


if __name__ == "__main__":
    unittest.main()
