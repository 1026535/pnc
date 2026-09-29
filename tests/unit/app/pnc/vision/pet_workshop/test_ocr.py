"""Direct bounded OCR regressions for Pet Workshop readers."""

from __future__ import annotations

import unittest
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.vision.pet_workshop.board import read_header
from pnc_automation.app.pnc.vision.pet_workshop.ocr import join_region_lines
from pnc_automation.app.pnc.vision.pet_workshop.ocr import zone_quantity
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from tests.support.paths import TEST_DATA_ROOT

FIXTURES = TEST_DATA_ROOT / "screen_recognition"


class _ScriptedEnergyOcrContext:
    def __init__(
        self,
        energy_text: str | None = None,
        *,
        energy_lines: tuple[OcrLine, ...] | None = None,
    ) -> None:
        self._energy_text = energy_text
        self._energy_lines = energy_lines

    def read_lines(self, image: Image.Image, region: Bounds, **kwargs: Any):
        if kwargs.get("detail") == "workshop_energy":
            if self._energy_lines is not None:
                return self._energy_lines
            return (OcrLine(text=self._energy_text, bounds=region, confidence=1.0),)
        return ()

    def read_preprocessed_result(self, image: Image.Image, region: Bounds, **kwargs: Any):
        return None


class _ScriptedCountOcrContext:
    def __init__(
        self, prepared_lines: tuple[OcrLine, ...] | None, *, raw_lines: tuple[OcrLine, ...] = ()
    ) -> None:
        self._prepared_lines = prepared_lines
        self._raw_lines = raw_lines

    def read_lines(self, image: Image.Image, region: Bounds, **kwargs: Any):
        return self._raw_lines

    def read_preprocessed_result(self, image: Image.Image, region: Bounds, **kwargs: Any):
        if self._prepared_lines is None:
            return None
        return OcrResult(lines=self._prepared_lines, words=())


class PetWorkshopHeaderOcrUnitTests(unittest.TestCase):
    def _energy(self, context: _ScriptedEnergyOcrContext, *, fixture: str = "pet_workshop.png"):
        with Image.open(FIXTURES / fixture) as source:
            image = source.copy()
        return read_header(image=image, ocr_context=context)[2]

    def test_energy_gauge_requires_positive_capacity(self) -> None:
        cases = {"0/0": (None, None), "200/0": (None, None), "0/200": (0, 200), "240/200": (240, 200)}
        for text, expected in cases.items():
            with self.subTest(gauge=text):
                energy = self._energy(_ScriptedEnergyOcrContext(text))
                self.assertEqual(expected, (energy.current, energy.capacity))

    def test_energy_gauge_drops_overlap_duplicated_digit(self) -> None:
        energy = self._energy(
            _ScriptedEnergyOcrContext(
                energy_lines=(
                    OcrLine(text="139", bounds=Bounds(x=699, y=10, width=68, height=30), confidence=1.0),
                    OcrLine(text="9/200", bounds=Bounds(x=748, y=10, width=93, height=30), confidence=1.0),
                )
            )
        )
        self.assertEqual((139, 200), (energy.current, energy.capacity))

    def test_saved_energy_fragments_remain_contiguous(self) -> None:
        cases = (
            (162, Bounds(700, 21, 27, 33), Bounds(714, 17, 128, 42)),
            (163, Bounds(703, 24, 23, 28), Bounds(708, 17, 134, 42)),
        )
        for current, prefix_bounds, gauge_bounds in cases:
            with self.subTest(current=current):
                lines = (
                    OcrLine(text="1", bounds=prefix_bounds, confidence=1.0),
                    OcrLine(text=f"{current}/200", bounds=gauge_bounds, confidence=1.0),
                )
                self.assertEqual(f"{current}/200", join_region_lines(lines))

    def test_overlapping_gauge_conflict_abstains(self) -> None:
        energy = self._energy(
            _ScriptedEnergyOcrContext(
                energy_lines=(
                    OcrLine(text="139", bounds=Bounds(x=699, y=10, width=68, height=30), confidence=1.0),
                    OcrLine(text="8/200", bounds=Bounds(x=748, y=10, width=93, height=30), confidence=1.0),
                )
            ),
            fixture="pet_workshop_board_20260924_native_rgba.png",
        )
        self.assertEqual((None, None), (energy.current, energy.capacity))

    def test_region_text_preserves_vertically_separate_lines(self) -> None:
        lines = (
            OcrLine(text="139", bounds=Bounds(x=699, y=10, width=68, height=12), confidence=1.0),
            OcrLine(text="9/200", bounds=Bounds(x=748, y=28, width=93, height=12), confidence=1.0),
        )
        self.assertEqual("139 9/200", join_region_lines(lines))


class PetWorkshopRewardCountUnitTests(unittest.TestCase):
    def _quantity(
        self,
        prepared_lines: tuple[OcrLine, ...] | None,
        *,
        raw_lines: tuple[OcrLine, ...] = (),
    ) -> int | None:
        with Image.open(FIXTURES / "pet_workshop.png") as source:
            image = source.copy()
        return zone_quantity(
            image=image,
            ocr_context=_ScriptedCountOcrContext(prepared_lines, raw_lines=raw_lines),
            region=Bounds(x=120, y=120, width=32, height=20),
            detail="workshop_unit_count",
        )

    def test_count_zone_retry_abstains_on_conflicting_values(self) -> None:
        value = self._quantity(
            (
                OcrLine(text="12", bounds=Bounds(0, 0, 8, 8), confidence=1.0),
                OcrLine(text="34", bounds=Bounds(12, 0, 8, 8), confidence=1.0),
            )
        )
        self.assertIsNone(value)

    def test_count_zone_retry_abstains_when_not_applicable(self) -> None:
        self.assertIsNone(self._quantity(None))

    def test_count_retry_cannot_override_conflicting_raw_readings(self) -> None:
        value = self._quantity(
            (OcrLine(text="1", bounds=Bounds(0, 0, 8, 8), confidence=1.0),),
            raw_lines=(
                OcrLine(text="12", bounds=Bounds(0, 0, 8, 8), confidence=1.0),
                OcrLine(text="34", bounds=Bounds(12, 0, 8, 8), confidence=1.0),
            ),
        )
        self.assertIsNone(value)
