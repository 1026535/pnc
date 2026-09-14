"""Coordinate rejection remains a bounded semantic fact on a proved World Map."""
from __future__ import annotations

import unittest
from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from tests.integration.vision.test_alliance_remaining_visual_contracts import (
    _builder, _capture, _perception,
)
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal, update_modal_lines


class _StatusOcr:
    """Return the seeded fact only inside its actual native semantic crop."""

    def __init__(self, lines, source_size):
        self.lines, self.source_size, self.calls = lines, source_size, []

    def read_result(self, image, region=None):
        if region is None:
            # The canonical coordinate reader also uses prepared smaller crops.
            assert image.size != self.source_size
            return OcrResult(lines=(), words=())
        assert region != Bounds(0, 0, *self.source_size)
        self.calls.append(region)
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=())


class WorldStatusPublicationTests(unittest.TestCase):
    def test_owned_status_survives_missing_coordinates_without_becoming_an_action(self):
        with Image.open(TEST_DATA_ROOT / "screen_recognition/world_map_core.png") as source:
            original = source.convert("RGB").resize((900, 1600))
        status = OcrLine("Invalid coordinates", Bounds(288, 180, 326, 38), 1.)
        for variant in ("status", "absent", "update"):
            image = with_update_modal(original) if variant == "update" else original
            lines = update_modal_lines(image.size) + (status,) if variant == "update" else (
                (status,) if variant == "status" else ()
            )
            for path in ("builder", "navigation"):
                with self.subTest(variant=variant, path=path):
                    backend = _StatusOcr(lines, image.size)
                    builder = _builder(backend)
                    capture = _capture(image, session_id=f"world-status:{variant}:{path}")
                    observation = builder.build(capture) if path == "builder" else (
                        _perception(builder).build(capture, include_content=True)
                    )
                    if variant == "update":
                        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                    else:
                        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
                    if variant == "status":
                        field = observation.require(UiElementId.PNC_STATUS_BANNER)
                        self.assertEqual(field.extracted_text, "Invalid coordinates")
                        self.assertIsNone(field.action_point)
                        self.assertFalse(field.identity_evidence)
                        self.assertEqual(field.frame_ref, capture.frame_ref)
                        self.assertEqual(field.source_layout_id, observation.decision.layout_id)
                        self.assertIn(Bounds(90, 160, 720, 160), backend.calls)
                    else:
                        self.assertFalse(observation.has(UiElementId.PNC_STATUS_BANNER))
                    if variant != "update":
                        self.assertTrue(observation.has(UiElementId.PNC_WORLD_HOME_NAV))

    def test_magnifier_is_a_measured_search_control_separate_from_coordinate_text(self):
        with Image.open(TEST_DATA_ROOT / "screen_recognition/world_map_core.png") as source:
            original = source.convert("RGB")
        erased = original.copy()
        erased.paste((15, 30, 45), (180, 76, 224, 118))
        for image in (original, erased):
            for path in ("builder", "navigation"):
                with self.subTest(visible=image is original, path=path):
                    backend = _StatusOcr((), image.size)
                    builder = _builder(backend)
                    capture = _capture(image, session_id=f"world-search:{path}")
                    observation = builder.build(capture) if path == "builder" else (
                        _perception(builder).build(capture)
                    )
                    self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
                    self.assertFalse(observation.has(UiElementId.PNC_WORLD_COORDINATE_BAR))
                    if image is original:
                        control = observation.require(UiElementId.PNC_WORLD_SEARCH_BUTTON)
                        self.assertTrue(Bounds(185, 81, 34, 32).contains_point(control.action_point))
                        self.assertEqual(control.source_kind.name, "TEMPLATE")
                        self.assertEqual(control.frame_ref, capture.frame_ref)
                        self.assertEqual(control.source_layout_id, observation.decision.layout_id)
                    else:
                        self.assertFalse(observation.has(UiElementId.PNC_WORLD_SEARCH_BUTTON))
