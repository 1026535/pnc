"""Focused tests for the explicit selector-catalog strategy and asset schema."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml
from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selector_catalog import (
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    SelectorCatalogTemplateAsset,
    load_selector_catalog_document,
)
from pnc_automation.app.pnc.vision.selectors import (
    DetectionKind,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
    build_default_selector_registry,
)
from pnc_automation.core.errors import SelectorResolutionError


class SelectorCatalogSchemaTests(unittest.TestCase):
    """Verifies explicit strategy metadata without relying on the production catalog migration."""

    def test_template_asset_round_trips_and_registry_uses_explicit_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            asset = root / "control_anchors" / "gift.png"
            asset.parent.mkdir()
            Image.new("RGBA", (12, 10), (20, 30, 40, 255)).save(asset)
            catalog_path = self._write_catalog(
                root,
                {
                    "id": UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON.name,
                    "screens": ["PNC_HOME_CITY"],
                    "status": "screenshot_seeded",
                    "detection_kind": "template",
                    "template_asset": {
                        "path": "control_anchors/gift.png",
                        "reference_size": [540, 960],
                        "search_region": {"x": 400, "y": 20, "width": 100, "height": 200},
                        "threshold": 0.93,
                        "mask": "embedded_alpha",
                    },
                    "materialize_relative_bounds": False,
                },
            )

            document = load_selector_catalog_document(catalog_path, asset_root=root)
            loaded_asset = document.selectors[0].template_asset
            self.assertIsNotNone(loaded_asset)
            assert loaded_asset is not None
            self.assertEqual(loaded_asset.path, "control_anchors/gift.png")
            self.assertEqual(loaded_asset.reference_size, (540, 960))
            self.assertEqual(loaded_asset.search_region.x, 400)
            registry = build_default_selector_registry(catalog_path=catalog_path, asset_root=root)
            selector = registry.require(UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON)
            self.assertEqual(selector.detection_kind, DetectionKind.TEMPLATE)
            self.assertEqual(selector.template_path, asset.resolve())
            self.assertEqual(selector.threshold, 0.93)
            self.assertEqual(selector.template_reference_size, (540, 960))

    def test_materialization_requires_guarded_geometry_strategy(self) -> None:
        document = SelectorCatalogDocument(
            selectors=(
                SelectorCatalogEntry(
                    id="PNC_BOTTOM_NAV_HOME",
                    screens=("PNC_HOME_CITY",),
                    status="task_validated",
                    detection_kind="semantic",
                    relative_bounds=_bounds(),
                    materialize_relative_bounds=False,
                ),
                SelectorCatalogEntry(
                    id="PNC_BOTTOM_NAV_HERO",
                    screens=("PNC_HOME_CITY",),
                    status="task_validated",
                    detection_kind="guarded_geometry",
                    relative_bounds=_bounds(),
                ),
            )
        )
        self.assertEqual(document.selectors[0].detection_kind, "semantic")
        self.assertEqual(document.selectors[0].status, "task_validated")
        self.assertEqual(DetectionKind.GUARDED_GEOMETRY.value, "guarded_geometry")

        with TemporaryDirectory() as temporary_directory:
            path = self._write_document(temporary_directory, document)
            registry = build_default_selector_registry(catalog_path=path, asset_root=Path(temporary_directory))
            elements = registry.materialize_for_screen(
                ScreenType.PNC_HOME_CITY,
                image_size=(540, 960),
            )
        self.assertEqual([element.selector_id for element in elements], [UiElementId.PNC_BOTTOM_NAV_HERO])

    def test_legacy_detection_kinds_are_rejected(self) -> None:
        for detection_kind in ("planned", "collection", "anchored_region"):
            with self.subTest(detection_kind=detection_kind):
                with self.assertRaises(SelectorResolutionError):
                    SelectorCatalogDocument(
                        selectors=(
                            SelectorCatalogEntry(
                                id="PNC_BOTTOM_NAV_HOME",
                                screens=("PNC_HOME_CITY",),
                                status="planned",
                                detection_kind=detection_kind,
                            ),
                        )
                    )

    def test_template_asset_validation_rejects_bad_path_and_image(self) -> None:
        cases = (
            ("../gift.png", "path traversal"),
            ("/absolute/gift.png", "absolute path"),
        )
        for path, label in cases:
            with self.subTest(label=label):
                with self.assertRaises(SelectorResolutionError):
                    SelectorCatalogTemplateAsset(path=path, reference_size=(540, 960), threshold=0.93)

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "broken.png").write_bytes(b"not an image")
            with self.assertRaises(SelectorResolutionError):
                load_selector_catalog_document(
                    self._write_catalog(
                        root,
                        {
                            "id": "PNC_BOTTOM_NAV_HOME",
                            "screens": ["PNC_HOME_CITY"],
                            "status": "screenshot_seeded",
                            "detection_kind": "template",
                            "template_asset": {
                                "path": "broken.png",
                                "reference_size": [540, 960],
                                "threshold": 0.93,
                                "mask": "embedded_alpha",
                            },
                        },
                    ),
                    asset_root=root,
                )

    def test_template_threshold_and_search_region_are_actionable(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogTemplateAsset(path="gift.png", reference_size=(540, 960), threshold=0)

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            Image.new("RGBA", (12, 10), (20, 30, 40, 255)).save(root / "gift.png")
            with self.assertRaises(SelectorResolutionError):
                load_selector_catalog_document(
                    self._write_catalog(
                        root,
                        {
                            "id": "PNC_BOTTOM_NAV_HOME",
                            "screens": ["PNC_HOME_CITY"],
                            "status": "screenshot_seeded",
                            "detection_kind": "template",
                            "template_asset": {
                                "path": "gift.png",
                                "reference_size": [540, 960],
                                "search_region": {"x": 0, "y": 0, "width": 11, "height": 10},
                                "threshold": 0.93,
                                "mask": "embedded_alpha",
                            },
                        },
                    ),
                    asset_root=root,
                )

    def test_alpha_asset_must_have_visible_pixels(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            Image.new("RGBA", (12, 10), (20, 30, 40, 0)).save(root / "transparent.png")
            with self.assertRaises(SelectorResolutionError):
                load_selector_catalog_document(
                    self._write_catalog(
                        root,
                        {
                            "id": "PNC_BOTTOM_NAV_HOME",
                            "screens": ["PNC_HOME_CITY"],
                            "status": "screenshot_seeded",
                            "detection_kind": "template",
                            "template_asset": {
                                "path": "transparent.png",
                                "reference_size": [540, 960],
                                "threshold": 0.93,
                                "mask": "embedded_alpha",
                            },
                        },
                    ),
                    asset_root=root,
                )

    def test_external_mask_path_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            Image.new("RGBA", (12, 10), (20, 30, 40, 255)).save(root / "gift.png")
            with self.assertRaises(SelectorResolutionError):
                load_selector_catalog_document(
                    self._write_catalog(
                        root,
                        {
                            "id": "PNC_BOTTOM_NAV_HOME",
                            "screens": ["PNC_HOME_CITY"],
                            "status": "screenshot_seeded",
                            "detection_kind": "template",
                            "template_asset": {
                                "path": "gift.png",
                                "reference_size": [540, 960],
                                "threshold": 0.93,
                                "mask": "embedded_alpha",
                                "mask_path": "mask.png",
                            },
                        },
                    ),
                    asset_root=root,
                )

    def test_template_without_asset_is_rejected_regardless_of_status(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_HOME",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                )
            )

    def test_ocr_and_geometry_require_bounds_regardless_of_status(self) -> None:
        for detection_kind in ("ocr_region", "guarded_geometry"):
            with self.subTest(detection_kind=detection_kind):
                with self.assertRaises(SelectorResolutionError):
                    SelectorCatalogDocument(
                        selectors=(
                            SelectorCatalogEntry(
                                id="PNC_BOTTOM_NAV_HOME",
                                screens=("PNC_HOME_CITY",),
                                status="planned",
                                detection_kind=detection_kind,
                            ),
                        )
                    )

    def test_unsupported_strategy_requires_reason(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_HOME",
                        screens=("PNC_HOME_CITY",),
                        status="planned",
                        detection_kind="unsupported",
                    ),
                )
            )
        document = SelectorCatalogDocument(
            selectors=(
                SelectorCatalogEntry(
                    id="PNC_BOTTOM_NAV_HOME",
                    screens=("PNC_HOME_CITY",),
                    status="planned",
                    detection_kind="unsupported",
                    notes=("No reviewed producer yet.",),
                    materialize_relative_bounds=False,
                ),
            )
        )
        self.assertEqual(document.selectors[0].status, "planned")
        with self.assertRaises(SelectorResolutionError):
            SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_HOME",
                        screens=("PNC_HOME_CITY",),
                        status="planned",
                        detection_kind="template",
                    ),
                )
            )

    def test_require_supported_reports_explicit_unsupported_reason(self) -> None:
        selector_id = UiElementId.PNC_HOME_CHARACTER_PANEL
        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=selector_id,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.UNSUPPORTED,
                    status=SelectorStatus.PLANNED,
                    notes=("No reviewed producer yet.",),
                ),
            )
        )
        with self.assertRaisesRegex(SelectorResolutionError, "No reviewed producer yet"):
            registry.require_supported(selector_id)

    @staticmethod
    def _write_catalog(root: Path, selector: dict[str, object]) -> Path:
        path = root / "selector_registry.yaml"
        path.write_text(yaml.safe_dump({"selectors": [selector]}), encoding="utf-8")
        return path

    @staticmethod
    def _write_document(root: str, document: SelectorCatalogDocument) -> Path:
        path = Path(root) / "selector_registry.yaml"
        path.write_text(yaml.safe_dump(document.to_document()), encoding="utf-8")
        return path


def _bounds() -> SelectorCatalogRelativeBounds:
    """Returns a compact valid normalized region for schema-only tests."""

    return SelectorCatalogRelativeBounds(x_ratio=0.1, y_ratio=0.1, width_ratio=0.1, height_ratio=0.1)


if __name__ == "__main__":
    unittest.main()
