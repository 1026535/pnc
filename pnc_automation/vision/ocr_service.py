"""OCR integration contract and RapidOCR-backed implementation."""

from __future__ import annotations

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
class OcrLine:
    """Represents one OCR text line localized to screenshot coordinates."""

    text: str
    bounds: Region
    confidence: float


class OcrService(Protocol):
    """Reads OCR text from one screenshot or cropped region."""

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns localized OCR lines for the provided image region."""

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns OCR text for the provided region."""


@dataclass(slots=True)
class RapidOcrService:
    """Runs OCR through the configured RapidOCR backend."""

    _engine: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Constructs the OCR backend or fails fast when the dependency is unavailable."""

        if RapidOCR is None:
            raise ScreenClassificationError("rapidocr_onnxruntime is required for OCR-backed observations.")
        self._engine = RapidOCR()

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Returns OCR lines from the full screenshot or the requested crop."""

        crop, offset_x, offset_y = _crop_image(image, region)
        payload = _encode_image(crop)
        raw_lines, _ = self._engine(payload)
        if raw_lines is None:
            return ()
        return tuple(
            _to_ocr_line(points, text, confidence, offset_x=offset_x, offset_y=offset_y)
            for points, text, confidence in raw_lines
            if str(text).strip() != ""
        )

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))


class UnavailableOcrService:
    """Fail-fast OCR implementation used when no OCR backend is configured."""

    def read_lines(self, image: Image.Image, region: Region | None = None) -> tuple[OcrLine, ...]:
        """Raises because OCR-dependent observations are unsupported without a backend."""

        del image
        raise ScreenClassificationError(
            "OCR was requested but no OCR backend is configured.",
            region=region,
        )

    def read_text(self, image: Image.Image, region: Region) -> str:
        """Raises because OCR-dependent selectors are unsupported without a backend."""

        del image
        raise ScreenClassificationError(
            "OCR was requested but no OCR backend is configured.",
            region=region,
        )


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
    return OcrLine(
        text=str(text).strip(),
        bounds=Region(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top)),
        confidence=float(confidence),
    )
