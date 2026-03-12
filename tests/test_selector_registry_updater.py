"""Offline selector-registry updater tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.vision.selector_catalog import (
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    write_selector_catalog_document,
)
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

    def test_load_selector_update_spec_rejects_duplicate_selector_ids(self) -> None:
        """Fails fast when one update spec repeats the same selector id."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_HOME_BUILD_BUTTON",
                                "screens": ["PNC_HOME_CITY"],
                                "status": "screenshot_seeded",
                                "detection_kind": "template",
                            },
                            {
                                "id": "PNC_HOME_BUILD_BUTTON",
                                "screens": ["PNC_BUILDING_DETAILS"],
                                "status": "click_mapped",
                                "detection_kind": "template",
                            },
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
                    catalog_path=self._write_catalog(
                        root,
                        selectors=(
                            SelectorCatalogEntry(
                                id="PNC_HOME_BUILD_BUTTON",
                                screens=("PNC_HOME_CITY",),
                                status="screenshot_seeded",
                                detection_kind="template",
                            ),
                        ),
                    ),
                    ui_element_id_path=self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",)),
                )

    def test_update_selector_registry_files_writes_catalog_and_ui_element_ids(self) -> None:
        """Writes both the static catalog and enum source for explicit selector additions."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            spec_path = root / "updates.yaml"
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                    SelectorCatalogEntry(
                        id="PNC_BUILDING_UPGRADE_BUTTON",
                        screens=("PNC_BUILDING_DETAILS",),
                        status="planned",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(
                root,
                selector_ids=("PNC_HOME_BUILD_BUTTON", "PNC_BUILDING_UPGRADE_BUTTON"),
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
                                "interaction_kind": "navigation",
                                "relative_bounds": {
                                    "x_ratio": 0.1,
                                    "y_ratio": 0.2,
                                    "width_ratio": 0.3,
                                    "height_ratio": 0.15,
                                },
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
            self.assertTrue(
                catalog_path.read_text(encoding="utf-8").startswith("# `relative_bounds` is always normalized"),
            )
            selector_by_id = {selector["id"]: selector for selector in catalog["selectors"]}
            self.assertEqual(
                selector_by_id["PNC_HOME_BUILD_BUTTON"]["screens"],
                ["PNC_HOME_CITY", "PNC_BUILDING_DETAILS"],
            )
            self.assertEqual(selector_by_id["PNC_HOME_BUILD_BUTTON"]["status"], "click_mapped")
            self.assertEqual(selector_by_id["PNC_HOME_BUILD_BUTTON"]["detection_kind"], "template")
            self.assertEqual(selector_by_id["PNC_HOME_BUILD_BUTTON"]["interaction_kind"], "navigation")
            self.assertEqual(
                selector_by_id["PNC_HOME_BUILD_BUTTON"]["relative_bounds"],
                {
                    "x_ratio": 0.1,
                    "y_ratio": 0.2,
                    "width_ratio": 0.3,
                    "height_ratio": 0.15,
                },
            )
            self.assertEqual(
                selector_by_id["PNC_HOME_BUILD_BUTTON"]["click"]["outcomes"][0]["target_screen"],
                "PNC_BUILDING_DETAILS",
            )
            self.assertEqual(selector_by_id["PNC_HOME_CASTLE_BUILDING"]["status"], "screenshot_seeded")
            self.assertIn(
                '    PNC_HOME_CASTLE_BUILDING = "PNC_HOME_CASTLE_BUILDING"',
                ui_element_id_path.read_text(encoding="utf-8"),
            )

    def test_update_selector_registry_files_writes_materialize_relative_bounds_override(self) -> None:
        """Persists explicit geometry-materialization overrides in the canonical catalog."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            spec_path = root / "updates.yaml"
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_MORE_MANAGE_CHAR",
                        screens=("PNC_MORE_MENU",),
                        status="click_mapped",
                        detection_kind="planned",
                        relative_bounds=SelectorCatalogRelativeBounds(
                            x_ratio=0.6,
                            y_ratio=0.1,
                            width_ratio=0.2,
                            height_ratio=0.05,
                        ),
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_MORE_MANAGE_CHAR",))
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_MORE_MANAGE_CHAR",
                                "screens": ["PNC_MORE_MENU"],
                                "status": "click_mapped",
                                "detection_kind": "planned",
                                "materialize_relative_bounds": False,
                            },
                        ]
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
                newline="\n",
            )

            update_selector_registry_files(
                spec_path=spec_path,
                catalog_path=catalog_path,
                ui_element_id_path=ui_element_id_path,
            )

            selector_by_id = {selector["id"]: selector for selector in yaml.safe_load(catalog_path.read_text(encoding="utf-8"))["selectors"]}
            self.assertFalse(selector_by_id["PNC_MORE_MANAGE_CHAR"]["materialize_relative_bounds"])

    def test_update_selector_registry_files_rejects_click_clearing(self) -> None:
        """Fails fast when an update tries to clear reviewed click metadata with `click: null`."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="click_mapped",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",))
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                "selectors:\n"
                "  - id: PNC_HOME_BUILD_BUTTON\n"
                "    screens: [PNC_HOME_CITY]\n"
                "    status: click_mapped\n"
                "    detection_kind: template\n"
                "    click: null\n",
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                update_selector_registry_files(
                    spec_path=spec_path,
                    catalog_path=catalog_path,
                    ui_element_id_path=ui_element_id_path,
                )

    def test_update_selector_registry_files_rejects_relative_bounds_clearing(self) -> None:
        """Fails fast when an update tries to clear relative geometry with `relative_bounds: null`."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="click_mapped",
                        detection_kind="template",
                        interaction_kind="action",
                        relative_bounds=SelectorCatalogRelativeBounds(
                            x_ratio=0.1,
                            y_ratio=0.2,
                            width_ratio=0.3,
                            height_ratio=0.15,
                        ),
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",))
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                "selectors:\n"
                "  - id: PNC_HOME_BUILD_BUTTON\n"
                "    screens: [PNC_HOME_CITY]\n"
                "    status: click_mapped\n"
                "    detection_kind: template\n"
                "    relative_bounds: null\n",
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                update_selector_registry_files(
                    spec_path=spec_path,
                    catalog_path=catalog_path,
                    ui_element_id_path=ui_element_id_path,
                )

    def test_update_selector_registry_files_rejects_unknown_interaction_kind(self) -> None:
        """Fails fast when an update uses an interaction kind outside the supported enum."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",))
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_HOME_BUILD_BUTTON",
                                "screens": ["PNC_HOME_CITY"],
                                "status": "screenshot_seeded",
                                "detection_kind": "template",
                                "interaction_kind": "not_supported",
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

    def test_update_selector_registry_files_rejects_unknown_click_outcome_screen(self) -> None:
        """Fails fast when a reviewed click outcome references an unknown screen."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",))
            spec_path = root / "updates.yaml"
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

    def test_update_selector_registry_files_rejects_unknown_verification_selector(self) -> None:
        """Fails fast when reviewed verification evidence references a selector missing from the final catalog."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_HOME_BUILD_BUTTON",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_HOME_BUILD_BUTTON",))
            spec_path = root / "updates.yaml"
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
                                    "outcomes": [
                                        {
                                            "target_screen": "PNC_BUILDING_DETAILS",
                                            "verification_selectors": ["PNC_BUILDING_UPGRADE_BUTTON"],
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

    def test_update_selector_registry_files_rejects_legacy_ocr_region_schema(self) -> None:
        """Fails fast when an update spec still uses the obsolete absolute OCR rectangle field."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_CASH_MALL_ENTRY_TITLE_REGION",
                        screens=("PNC_CASH_MALL",),
                        status="planned",
                        detection_kind="planned",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_CASH_MALL_ENTRY_TITLE_REGION",))
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                "selectors:\n"
                "  - id: PNC_CASH_MALL_ENTRY_TITLE_REGION\n"
                "    screens: [PNC_CASH_MALL]\n"
                "    status: screenshot_seeded\n"
                "    detection_kind: ocr_region\n"
                "    ocr_region:\n"
                "      x: 10\n"
                "      y: 20\n"
                "      width: 30\n"
                "      height: 12\n",
                encoding="utf-8",
                newline="\n",
            )

            with self.assertRaises(SelectorResolutionError):
                update_selector_registry_files(
                    spec_path=spec_path,
                    catalog_path=catalog_path,
                    ui_element_id_path=ui_element_id_path,
                )

    def test_update_selector_registry_files_rejects_verification_texts(self) -> None:
        """Fails fast when an update spec requests runtime text verification that is not implemented."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = self._write_catalog(
                root,
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_BAG",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            )
            ui_element_id_path = self._write_ui_element_ids(root, selector_ids=("PNC_BOTTOM_NAV_BAG",))
            spec_path = root / "updates.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "selectors": [
                            {
                                "id": "PNC_BOTTOM_NAV_BAG",
                                "screens": ["PNC_HOME_CITY"],
                                "status": "click_mapped",
                                "detection_kind": "template",
                                "interaction_kind": "navigation",
                                "click": {
                                    "outcomes": [
                                        {
                                            "target_screen": "PNC_BAG",
                                            "verification_texts": ["Bag"],
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

    def _write_catalog(self, root: Path, *, selectors: tuple[SelectorCatalogEntry, ...]) -> Path:
        """Writes one temporary selector catalog and returns its path."""

        catalog_path = root / "selector_registry.yaml"
        write_selector_catalog_document(catalog_path, SelectorCatalogDocument(selectors=selectors))
        return catalog_path

    def _write_ui_element_ids(self, root: Path, *, selector_ids: tuple[str, ...]) -> Path:
        """Writes one temporary `UiElementId` module and returns its path."""

        ui_element_id_path = root / "ui_element_id.py"
        ui_element_id_path.write_text(
            "\n".join(
                (
                    '"""Canonical selector identifiers."""',
                    "",
                    "from enum import StrEnum",
                    "",
                    "class UiElementId(StrEnum):",
                    *(f'    {selector_id} = "{selector_id}"' for selector_id in selector_ids),
                    "",
                )
            ),
            encoding="utf-8",
            newline="\n",
        )
        return ui_element_id_path


if __name__ == "__main__":
    unittest.main()
