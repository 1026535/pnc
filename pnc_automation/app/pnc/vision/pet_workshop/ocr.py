"""Bounded OCR normalization for Pet Workshop screens.

These helpers keep text joining, numeric token extraction, and count-zone
preprocessing independent from board and order geometry. They intentionally
accept the repository's OCR line objects rather than caching any recognition
result.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from PIL import Image

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
)

_NUMERIC_TOKEN = re.compile(r"\d+(?:,\d{3})*")
_COUNT_ZONE_UPSCALE = 3


def join_region_lines(lines: Iterable[OcrLine]) -> str:
    """Join bounded OCR lines while resolving measured edge overlap."""

    parts: list[str] = []
    previous: Bounds | None = None
    previous_text = ""
    for line in lines:
        text = line.text
        bounds = line.bounds
        shared_glyphs = False
        if (
            previous is not None
            and previous.x < bounds.x < previous.x + previous.width
            and bounds.x + bounds.width > previous.x + previous.width
            and min(previous.y + previous.height, bounds.y + bounds.height)
            - max(previous.y, bounds.y) >= min(previous.height, bounds.height) / 2
        ):
            overlap = previous.x + previous.width - bounds.x
            dropped = min(len(text), round(overlap * len(text) / bounds.width))
            if dropped and not previous_text.endswith(text[:dropped]):
                return ""
            shared_glyphs = dropped > 0
            text = text[dropped:]
        if text:
            if shared_glyphs:
                parts[-1] += text
            else:
                parts.append(text)
        previous = bounds
        previous_text = line.text
    return " ".join(parts)


def count_zone_ocr_image(image: Image.Image, bounds: Bounds) -> Image.Image:
    """Crop and upscale one measured count badge for the bounded retry."""

    crop = image.crop((bounds.x, bounds.y, bounds.x + bounds.width, bounds.y + bounds.height))
    return crop.resize(
        (crop.width * _COUNT_ZONE_UPSCALE, crop.height * _COUNT_ZONE_UPSCALE),
        Image.LANCZOS,
    )


def numeric_tokens(lines: Iterable[OcrLine]) -> list[tuple[int, Bounds, str]]:
    """Extract numeric values with their original OCR bounds and text."""

    tokens: list[tuple[int, Bounds, str]] = []
    for line in lines:
        for word in line.words:
            digits = _NUMERIC_TOKEN.search(word.text)
            if digits:
                tokens.append((int(digits.group(0).replace(",", "")), word.bounds, word.text))
        if not line.words:
            digits = _NUMERIC_TOKEN.search(line.text)
            if digits:
                tokens.append((int(digits.group(0).replace(",", "")), line.bounds, line.text))
    return tokens


def read_lines(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    region: Bounds,
    detail: str,
) -> tuple[OcrLine, ...]:
    """Read one bounded content region in image coordinates."""

    from . import geometry

    return ocr_context.read_lines(
        image,
        geometry.scaled_region(region, image),
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
    )


def read_region_text(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    region: Bounds,
    detail: str,
) -> str:
    """Read and join one bounded OCR region."""

    return join_region_lines(
        read_lines(image=image, ocr_context=ocr_context, region=region, detail=detail)
    )


def zone_quantity(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    region: Bounds | None,
    detail: str,
) -> int | None:
    """Read one measured count zone with one bounded upscale retry."""

    if region is None or region.width < 8 or region.height < 6:
        return None
    values = {
        value
        for value, _bounds, _text in numeric_tokens(
            read_lines(image=image, ocr_context=ocr_context, region=region, detail=detail)
        )
    }
    if len(values) == 1:
        return values.pop()
    if values:
        return None
    from . import geometry

    result = ocr_context.read_preprocessed_result(
        image,
        geometry.scaled_region(region, image),
        preprocessing_id="pet-workshop-count-3x",
        prepare=count_zone_ocr_image,
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
    )
    if result is None:
        return None
    values = {value for value, _bounds, _text in numeric_tokens(result.lines)}
    return values.pop() if len(values) == 1 else None
