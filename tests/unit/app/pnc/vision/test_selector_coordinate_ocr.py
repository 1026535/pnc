"""Selector coordinate ocr."""

from __future__ import annotations

from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine
from pnc_automation.app.pnc.vision.selector_catalog import (
    SelectorCatalogDocument,
    SelectorCatalogEntry,
    SelectorCatalogRelativeBounds,
    write_selector_catalog_document,
)
from pnc_automation.app.pnc.vision.selectors import RelativeBounds, build_default_selector_registry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.coordinate_bar_filtering_ocr_service import (
    _CoordinateBarFilteringOcrService,
)
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class SelectorCoordinateOcrTests(unittest.TestCase):
    """Proves selector coordinate ocr."""

    def test_pillow_selector_engine_detects_catalog_backed_ocr_regions(self) -> None:
        """Resolves catalog-defined normalized OCR regions through the runtime selector engine."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            catalog_path = root / "selector_registry.yaml"
            write_selector_catalog_document(
                catalog_path,
                SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_CASH_MALL_ENTRY_TITLE_REGION",
                            screens=("PNC_CASH_MALL",),
                            status="screenshot_seeded",
                            detection_kind="ocr_region",
                            relative_bounds=SelectorCatalogRelativeBounds(
                                x_ratio=0.1,
                                y_ratio=0.2,
                                width_ratio=0.4,
                                height_ratio=0.18,
                            ),
                            materialize_relative_bounds=False,
                        ),
                    )
                ),
            )
            registry = build_default_selector_registry(catalog_path=catalog_path, asset_root=root)
            selector_engine = ImageSelectorEngine(
                template_matcher=OpenCvTemplateMatcher(),
            )
            image = Image.new("RGB", (100, 100), (0, 0, 0))
            ocr_context = ObservationOcrContext(
                image,
                _FakeOcrService(lines=(_ocr_line("Daily Sale", x=12, y=22, width=32, height=12),)),
                None,
                "test",
            )

            matches = selector_engine.detect(image, registry, ocr_context=ocr_context)

            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].selector_id, UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION)
            self.assertEqual(matches[0].source_kind, VisibleElementSourceKind.OCR)
            self.assertEqual(matches[0].extracted_text, "Daily Sale")
            self.assertEqual(
                registry.require(UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION).relative_bounds,
                RelativeBounds(x_ratio=0.1, y_ratio=0.2, width_ratio=0.4, height_ratio=0.18),
            )

    def test_pillow_selector_engine_rejects_non_world_text_for_world_map_ocr_regions(self) -> None:
        """Does not mark world-map OCR selectors visible when their crop only contains unrelated home-city text."""

        registry = build_default_selector_registry()
        selector_engine = ImageSelectorEngine(
            template_matcher=OpenCvTemplateMatcher(),
        )
        image = Image.new("RGB", (540, 960), (0, 0, 0))
        ocr_context = ObservationOcrContext(
            image,
            _FakeOcrService(lines=()),
            None,
            "test",
        )

        matches = selector_engine.detect(
            image,
            registry,
            selector_ids=(UiElementId.PNC_WORLD_COORDINATE_BAR, UiElementId.PNC_WORLD_HOME_NAV),
            ocr_context=ocr_context,
        )

        self.assertEqual(matches, [])

    def test_pillow_selector_engine_prefers_blue_filtered_world_coordinate_bar_ocr(self) -> None:
        """Uses the coordinate bar's blue-text-isolated OCR path so background castle labels do not block world-map proof."""

        registry = build_default_selector_registry()
        selector_engine = ImageSelectorEngine(
            template_matcher=OpenCvTemplateMatcher(),
        )
        image = Image.new("RGB", (540, 960), (18, 24, 40))
        coordinate_region = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate_region is not None
        bounds = coordinate_region.materialize_region(image_size=image.size)
        for x in range(bounds.x + 8, bounds.x + bounds.width - 8):
            for y in range(bounds.y + 8, bounds.y + bounds.height - 8):
                image.putpixel((x, y), (42, 198, 224))

        ocr_context = ObservationOcrContext(
            image,
            _CoordinateBarFilteringFullOcrService(
                raw_text="X:272-kV.498",
                filtered_text="X:272 Y:498",
            ),
            None,
            "test",
        )

        matches = selector_engine.detect(
            image,
            registry,
            selector_ids=(UiElementId.PNC_WORLD_COORDINATE_BAR,),
            ocr_context=ocr_context,
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].selector_id, UiElementId.PNC_WORLD_COORDINATE_BAR)
        self.assertEqual(matches[0].extracted_text, "X:272 Y:498")
