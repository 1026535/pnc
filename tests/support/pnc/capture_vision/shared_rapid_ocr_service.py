"""Synthetic shared_rapid_ocr_service fixture."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from functools import cache
from hashlib import blake2b
from threading import RLock

from PIL import Image

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrResult,
    OcrService,
    OcrTextOrientation,
    RapidOcrService,
)


_OcrRequestKey = tuple[
    str,
    tuple[int, int],
    bytes,
    tuple[int, int, int, int] | None,
    OcrTextOrientation,
]


@dataclass(slots=True)
class _MemoizingOcrService:
    """Reuse exact real OCR requests across duplicate test publisher paths."""

    delegate: OcrService
    max_cache_entries: int = 256
    _results: OrderedDict[_OcrRequestKey, OcrResult] = field(
        default_factory=OrderedDict,
        init=False,
        repr=False,
    )
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _cache_hits: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_cache_entries, bool)
            or not isinstance(self.max_cache_entries, int)
            or self.max_cache_entries <= 0
        ):
            raise ValueError("max_cache_entries must be a positive integer")

    @property
    def cache_hits(self) -> int:
        """Returns how many exact requests reused a result in this process."""

        with self._lock:
            return self._cache_hits

    def read_result(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> OcrResult:
        """Return a cached result only for identical pixels and OCR settings."""

        key = _request_key(image, region, orientation)
        if key is None:
            return self.delegate.read_result(image, region, orientation=orientation)

        with self._lock:
            if key in self._results:
                self._cache_hits += 1
                self._results.move_to_end(key)
                return self._results[key]

        result = self.delegate.read_result(image, region, orientation=orientation)
        with self._lock:
            self._results[key] = result
            self._results.move_to_end(key)
            while len(self._results) > self.max_cache_entries:
                self._results.popitem(last=False)
        return result

    def read_lines(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> tuple[OcrLine, ...]:
        """Return OCR lines through the same exact-request cache."""

        return self.read_result(image, region, orientation=orientation).lines

    def read_text(
        self,
        image: Image.Image,
        region: Bounds,
        *,
        orientation: OcrTextOrientation = OcrTextOrientation.AUTO,
    ) -> str:
        """Return OCR text through the same exact-request cache."""

        return "\n".join(
            line.text
            for line in self.read_lines(image, region, orientation=orientation)
        )


def _request_key(
    image: Image.Image,
    region: Bounds | None,
    orientation: OcrTextOrientation,
) -> _OcrRequestKey | None:
    """Build a key only for valid input types; let the delegate validate others."""

    if (
        not isinstance(image, Image.Image)
        or (region is not None and not isinstance(region, Bounds))
        or not isinstance(orientation, OcrTextOrientation)
    ):
        return None
    bounds_key = (
        None
        if region is None
        else (region.x, region.y, region.width, region.height)
    )
    pixels = (
        image.convert("RGBA").tobytes()
        if image.mode in {"P", "PA"}
        else image.tobytes()
    )
    return (
        image.mode,
        image.size,
        blake2b(pixels, digest_size=16).digest(),
        bounds_key,
        orientation,
    )



@cache
def _shared_rapid_ocr_service() -> _MemoizingOcrService:
    """Returns one real OCR engine with a bounded exact-request cache for tests."""

    return _MemoizingOcrService(RapidOcrService())
