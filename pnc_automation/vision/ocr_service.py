"""OCR integration contract and RapidOCR-backed implementation."""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Protocol

from PIL import Image

from pnc_automation.errors import ScreenClassificationError
from pnc_automation.vision.selectors import Region

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    RapidOCR = None


@dataclass(frozen=True, slots=True)
class OcrWord:
    """Represents one OCR word localized to screenshot coordinates."""

    text: str
    bounds: Region
    confidence: float


@dataclass(frozen=True, slots=True)
class OcrLine:
    """Represents one OCR text line localized to screenshot coordinates."""

    text: str
    bounds: Region
    confidence: float
    words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrResult:
    """Groups the localized OCR line and word output for one screenshot region."""

    lines: tuple[OcrLine, ...]
    words: tuple[OcrWord, ...]


class OcrService(Protocol):
    """Reads OCR text from one screenshot or cropped region."""

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns localized OCR lines and words for the provided image region."""

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns localized OCR lines for the provided image region."""

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns OCR text for the provided region."""


@dataclass(slots=True)
class CachedOcrService:
    """Caches the most recent OCR result so adjacent pipeline stages can reuse one screenshot read."""

    inner: OcrService
    _last_image_ref: weakref.ReferenceType[Image.Image] | None = field(default=None, init=False, repr=False)
    _last_region_key: tuple[int, int, int, int] | None = field(default=None, init=False, repr=False)
    _last_result: OcrResult | None = field(default=None, init=False, repr=False)

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns cached OCR output when the same image and region are requested consecutively."""

        region_key = None if region is None else (region.x, region.y, region.width, region.height)
        last_image = None if self._last_image_ref is None else self._last_image_ref()
        if last_image is image and self._last_region_key == region_key and self._last_result is not None:
            return self._last_result
        result = self.inner.read_result(image, region)
        self._last_image_ref = weakref.ref(image)
        self._last_region_key = region_key
        self._last_result = result
        return result

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns OCR lines while reusing the cached result path when available."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns OCR text while reusing the cached result path when available."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


@dataclass(slots=True)
class RapidOcrService:
    """Runs OCR through the configured RapidOCR backend."""

    _engine: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Constructs the OCR backend or fails fast when the dependency is unavailable."""

        if RapidOCR is None:
            raise ScreenClassificationError("rapidocr_onnxruntime is required for OCR-backed observations.")
        self._engine = RapidOCR()

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Returns OCR lines and synthesized words from the full screenshot or the requested crop."""

        crop, offset_x, offset_y = _crop_image(image, region)
        payload = _encode_image(crop)
        raw_lines, _ = self._engine(payload)
        if raw_lines is None:
            return OcrResult(lines=(), words=())
        lines = tuple(
            _to_ocr_line(points, text, confidence, offset_x=offset_x, offset_y=offset_y)
            for points, text, confidence in raw_lines
            if str(text).strip() != ""
        )
        words = tuple(word for line in lines for word in line.words)
        return OcrResult(lines=lines, words=words)

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns OCR lines from the full screenshot or the requested crop."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))


class UnavailableOcrService:
    """Fail-fast OCR implementation used when no OCR backend is configured."""

    def read_result(self, image: Image.Image, region: Region | None = None) -> OcrResult:
        """Raises because OCR-dependent observations are unsupported without a backend."""

        del image
        raise ScreenClassificationError(
            "OCR was requested but no OCR backend is configured.",
            region=region,
        )

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Raises because OCR-dependent observations are unsupported without a backend."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Raises because OCR-dependent selectors are unsupported without a backend."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _crop_image(image: Image.Image, region: Region | None) -> tuple[Image.Image, int, int]:
    """Returns the cropped image and its coordinate offset within the screenshot."""

    if region is None:
        return image, 0, 0
    return image.crop((region.x, region.y, region.x + region.width, region.y + region.height)), region.x, region.y


def _encode_image(image: Image.Image) -> bytes:
    """Encodes one PIL image into PNG bytes consumable by RapidOCR."""

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _to_ocr_line(
    points: list[list[float]],
    text: Any,
    confidence: Any,
    *,
    offset_x: int,
    offset_y: int,
) -> OcrLine:
    """Converts one RapidOCR result row into the canonical OCR line model."""

    xs = [int(round(point[0])) for point in points]
    ys = [int(round(point[1])) for point in points]
    left = min(xs) + offset_x
    top = min(ys) + offset_y
    right = max(xs) + offset_x
    bottom = max(ys) + offset_y
    bounds = Region(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))
    words = _to_ocr_words(str(text).strip(), bounds=bounds, confidence=float(confidence))
    return OcrLine(
        text=str(text).strip(),
        bounds=bounds,
        confidence=float(confidence),
        words=words,
    )


def _to_ocr_words(text: str, *, bounds: Region, confidence: float) -> tuple[OcrWord, ...]:
    """Synthesizes conservative word boxes from one OCR line when the backend is line-only."""

    raw_words = [word for word in text.split() if word.strip() != ""]
    if not raw_words:
        return ()

    total_characters = sum(len(word) for word in raw_words)
    if total_characters <= 0:
        return ()

    consumed_width = 0
    words: list[OcrWord] = []
    for index, word in enumerate(raw_words):
        if index == len(raw_words) - 1:
            width = max(1, bounds.width - consumed_width)
        else:
            width = max(1, round(bounds.width * (len(word) / total_characters)))
        word_bounds = Region(
            x=bounds.x + consumed_width,
            y=bounds.y,
            width=width,
            height=bounds.height,
        )
        words.append(OcrWord(text=word, bounds=word_bounds, confidence=confidence))
        consumed_width += width
    return tuple(words)
