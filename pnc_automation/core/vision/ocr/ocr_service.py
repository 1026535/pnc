"""OCR integration contract and RapidOCR-backed implementation."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from threading import RLock
from time import perf_counter
from typing import Any, Protocol

from PIL import Image

from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.errors import ScreenClassificationError
from pnc_automation.core.vision.image.models import Bounds

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError:
    RapidOCR = None


@dataclass(frozen=True, slots=True)
class OcrWord:
    """Represents one OCR word localized to screenshot coordinates."""

    text: str
    bounds: Bounds
    confidence: float


@dataclass(frozen=True, slots=True)
class OcrLine:
    """Represents one OCR text line localized to screenshot coordinates."""

    text: str
    bounds: Bounds
    confidence: float
    words: tuple[OcrWord, ...] = ()


@dataclass(frozen=True, slots=True)
class OcrResult:
    """Groups the localized OCR line and word output for one screenshot region."""

    lines: tuple[OcrLine, ...]
    words: tuple[OcrWord, ...]


class OcrReadPurpose(StrEnum):
    """Names the owner of one frame-local OCR request."""

    GUARD = "guard"
    IDENTITY = "identity"
    CONTENT = "content"
    DEBUG = "debug"
    REGION_RESEGMENTATION = "region_resegmentation"


class OcrReadStatus(StrEnum):
    """Describes how one context-bound OCR request was served."""

    ENGINE = "engine"
    CACHE_HIT = "cache_hit"
    FULL_FRAME_REUSE = "full_frame_reuse"
    MISSING = "missing"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class OcrReadDiagnostic:
    """Immutable reason and outcome for one context-bound OCR request."""

    purpose: OcrReadPurpose
    status: OcrReadStatus
    region: Bounds | None
    detail: str | None = None


class OcrService(Protocol):
    """Reads OCR text from one screenshot or cropped region."""

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Returns localized OCR lines and words for the provided image region."""

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Returns localized OCR lines for the provided image region."""

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Returns OCR text for the provided region."""


@dataclass(frozen=True, slots=True)
class OcrContextMetrics:
    """Immutable counters for one frame-bound OCR context."""

    requests: int = 0
    engine_calls: int = 0
    processed_pixel_area: int = 0
    cache_hits: int = 0
    fullframe_reuses: int = 0
    engine_seconds: float = 0.0
    diagnostics: tuple[OcrReadDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class _OcrCacheEntry:
    """Stores either a successful OCR result or an explicit preprocessing miss."""

    result: OcrResult | None
    not_applicable: bool = False


_RAW_PREPROCESSING_ID = "__raw__"


@dataclass(slots=True, init=False)
class ObservationOcrContext:
    """Owns one captured image, its OCR cache, and frame-local measurements.

    The source image identity is retained only to reject accidental reads from a
    different capture. OCR always receives a private copy, and cache keys never
    contain image identity or dimensions. A successful raw full-frame result is
    pinned so repeated bounded-region discovery cannot evict the result needed by
    later diagnostics.
    """

    _source_image: Image.Image = field(init=False, repr=False)
    _backend: OcrService = field(init=False, repr=False)
    _frame_ref: FrameRef | None = field(init=False, repr=False)
    _backend_revision: str = field(init=False, repr=False)
    _max_entries: int = field(init=False, repr=False)
    _owned_image: Image.Image = field(init=False, repr=False)
    _cache: OrderedDict[tuple[Bounds | None, str, str], _OcrCacheEntry] = field(
        init=False, repr=False
    )
    _pinned_fullframe_key: tuple[Bounds | None, str, str] | None = field(
        default=None, init=False, repr=False
    )
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _requests: int = field(default=0, init=False, repr=False)
    _engine_calls: int = field(default=0, init=False, repr=False)
    _processed_pixel_area: int = field(default=0, init=False, repr=False)
    _cache_hits: int = field(default=0, init=False, repr=False)
    _fullframe_reuses: int = field(default=0, init=False, repr=False)
    _engine_seconds: float = field(default=0.0, init=False, repr=False)
    _diagnostics: list[OcrReadDiagnostic] = field(default_factory=list, init=False, repr=False)

    def __init__(
        self,
        image: Image.Image,
        backend: OcrService,
        frame_ref: FrameRef | None,
        backend_revision: str,
        max_entries: int = 64,
    ) -> None:
        """Captures a private snapshot and freezes the context's cache bindings."""

        if not isinstance(image, Image.Image):
            raise TypeError("ObservationOcrContext.image must be a PIL image.")
        if image.width <= 0 or image.height <= 0:
            raise ValueError("ObservationOcrContext.image must have positive dimensions.")
        if not isinstance(backend_revision, str) or not backend_revision.strip():
            raise ValueError("ObservationOcrContext.backend_revision must be non-empty.")
        if (
            not isinstance(max_entries, int)
            or isinstance(max_entries, bool)
            or max_entries <= 0
        ):
            raise ValueError("ObservationOcrContext.max_entries must be a positive integer.")
        if not hasattr(backend, "read_result"):
            raise TypeError("ObservationOcrContext.backend must implement read_result().")
        self._source_image = image
        self._backend = backend
        self._frame_ref = frame_ref
        self._backend_revision = backend_revision
        self._max_entries = max_entries
        self._owned_image = image.copy()
        self._cache = OrderedDict()
        self._pinned_fullframe_key = None
        self._lock = RLock()
        self._requests = 0
        self._engine_calls = 0
        self._processed_pixel_area = 0
        self._cache_hits = 0
        self._fullframe_reuses = 0
        self._engine_seconds = 0.0
        self._diagnostics = []

    @property
    def image(self) -> Image.Image:
        """Returns the source image object used for capture identity checks."""

        return self._source_image

    @property
    def backend(self) -> OcrService:
        """Returns the backend bound for this context's lifetime."""

        return self._backend

    @property
    def frame_ref(self) -> FrameRef | None:
        """Returns the immutable frame provenance bound to this context."""

        return self._frame_ref

    @property
    def backend_revision(self) -> str:
        """Returns the backend revision bound into every cache key."""

        return self._backend_revision

    @property
    def max_entries(self) -> int:
        """Returns the fixed cache capacity for this context."""

        return self._max_entries

    @property
    def metrics(self) -> OcrContextMetrics:
        """Returns an immutable snapshot of this context's OCR work."""

        with self._lock:
            return OcrContextMetrics(
                requests=self._requests,
                engine_calls=self._engine_calls,
                processed_pixel_area=self._processed_pixel_area,
                cache_hits=self._cache_hits,
                fullframe_reuses=self._fullframe_reuses,
                engine_seconds=self._engine_seconds,
                diagnostics=tuple(self._diagnostics),
            )

    @property
    def read_diagnostics(self) -> tuple[OcrReadDiagnostic, ...]:
        """Returns immutable reason/outcome records for this capture."""

        with self._lock:
            return tuple(self._diagnostics)

    def _record_diagnostic(
        self,
        *,
        purpose: OcrReadPurpose,
        status: OcrReadStatus,
        region: Bounds | None,
        detail: str | None,
    ) -> None:
        self._diagnostics.append(OcrReadDiagnostic(purpose, status, region, detail))

    def record_diagnostic(
        self,
        *,
        purpose: OcrReadPurpose,
        status: OcrReadStatus,
        region: Bounds | None = None,
        detail: str | None = None,
    ) -> None:
        """Records an application-owned outcome for a planned read."""

        with self._lock:
            self._record_diagnostic(
                purpose=purpose,
                status=status,
                region=region,
                detail=detail,
            )

    def validate_capture(self, image: Image.Image | None, frame_ref: FrameRef | None) -> None:
        """Rejects reads that do not refer to this context's exact capture proof."""

        # Do not use ``image is self._source_image`` alone without rejecting None:
        # ``None is None`` would accidentally validate an unbound offline read.
        if image is None or image is not self._source_image:
            raise ValueError("OCR context read used an image different from its captured frame.")
        if frame_ref != self._frame_ref:
            raise ValueError("OCR context read used a different frame provenance reference.")

    def read_result(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        reuse_full_frame: bool = True,
        purpose: OcrReadPurpose = OcrReadPurpose.CONTENT,
        detail: str | None = None,
    ) -> OcrResult:
        """Returns OCR for a full image or bounded region using this frame's cache."""

        with self._lock:
            self.validate_capture(image, self._frame_ref)
            validated_region = self._validate_region(region)
            self._requests += 1
            key = self._cache_key(validated_region, _RAW_PREPROCESSING_ID)
            cached = self._lookup_cached(key)
            if cached is not None:
                assert cached.result is not None
                self._record_diagnostic(
                    purpose=purpose,
                    status=OcrReadStatus.CACHE_HIT,
                    region=validated_region,
                    detail=detail,
                )
                return cached.result
            if validated_region is not None and reuse_full_frame:
                fullframe_key = self._cache_key(None, _RAW_PREPROCESSING_ID)
                fullframe = self._cache.get(fullframe_key)
                if fullframe is not None and fullframe.result is not None:
                    self._fullframe_reuses += 1
                    self._record_diagnostic(
                        purpose=purpose,
                        status=OcrReadStatus.FULL_FRAME_REUSE,
                        region=validated_region,
                        detail=detail,
                    )
                    return _contained_result(fullframe.result, validated_region)
            try:
                result = self._run_backend(
                    key=key,
                    region=validated_region,
                    prepare=None,
                    pin_fullframe=validated_region is None,
                )
            except Exception:
                self._record_diagnostic(
                    purpose=purpose,
                    status=OcrReadStatus.ERROR,
                    region=validated_region,
                    detail=detail,
                )
                raise
            self._record_diagnostic(
                purpose=purpose,
                status=OcrReadStatus.ENGINE,
                region=validated_region,
                detail=detail,
            )
            return result

    def read_lines(
        self,
        image: Image.Image,
        region: Bounds | None = None,
        *,
        reuse_full_frame: bool = True,
        purpose: OcrReadPurpose = OcrReadPurpose.CONTENT,
        detail: str | None = None,
    ) -> tuple[OcrLine, ...]:
        """Returns OCR lines through the frame-local result cache."""

        return self.read_result(
            image,
            region,
            reuse_full_frame=reuse_full_frame,
            purpose=purpose,
            detail=detail,
        ).lines

    def read_text(
        self,
        image: Image.Image,
        region: Bounds,
        *,
        reuse_full_frame: bool = True,
        purpose: OcrReadPurpose = OcrReadPurpose.CONTENT,
        detail: str | None = None,
    ) -> str:
        """Returns newline-joined OCR text through the frame-local result cache."""

        return "\n".join(
            line.text
            for line in self.read_result(
                image,
                region,
                reuse_full_frame=reuse_full_frame,
                purpose=purpose,
                detail=detail,
            ).lines
        )

    def read_preprocessed_result(
        self,
        image: Image.Image,
        region: Bounds,
        *,
        preprocessing_id: str,
        prepare: Callable[[Image.Image, Bounds], Image.Image | None],
        purpose: OcrReadPurpose = OcrReadPurpose.CONTENT,
        detail: str | None = None,
    ) -> OcrResult | None:
        """Runs one named preprocessing variant and projects its OCR back once.

        ``prepare`` receives a fresh full-image copy and the original ROI. A
        ``None`` result means the variant is not applicable and is cached as a
        successful no-engine outcome. Exceptions from preparation or the backend
        are never cached.
        """

        with self._lock:
            self.validate_capture(image, self._frame_ref)
            validated_region = self._validate_region(region)
            assert validated_region is not None
            if not isinstance(preprocessing_id, str) or not preprocessing_id.strip():
                raise ValueError("preprocessing_id must be non-empty.")
            if preprocessing_id.strip() == _RAW_PREPROCESSING_ID:
                raise ValueError(f"preprocessing_id '{_RAW_PREPROCESSING_ID}' is reserved.")
            if not callable(prepare):
                raise TypeError("prepare must be callable.")
            self._requests += 1
            key = self._cache_key(validated_region, preprocessing_id)
            cached = self._lookup_cached(key)
            if cached is not None:
                self._record_diagnostic(
                    purpose=purpose,
                    status=OcrReadStatus.MISSING if cached.not_applicable else OcrReadStatus.CACHE_HIT,
                    region=validated_region,
                    detail=detail,
                )
                return None if cached.not_applicable else cached.result
            try:
                result = self._run_backend(
                    key=key,
                    region=validated_region,
                    prepare=prepare,
                    pin_fullframe=False,
                )
            except Exception:
                self._record_diagnostic(
                    purpose=purpose,
                    status=OcrReadStatus.ERROR,
                    region=validated_region,
                    detail=detail,
                )
                raise
            self._record_diagnostic(
                purpose=purpose,
                status=OcrReadStatus.MISSING if result is None else OcrReadStatus.ENGINE,
                region=validated_region,
                detail=detail,
            )
            return result

    def _validate_region(self, region: Bounds | None) -> Bounds | None:
        """Validates a region against the owned screenshot without normalizing it."""

        if region is None:
            return None
        if not isinstance(region, Bounds):
            raise TypeError("OCR region must be a Bounds instance or None.")
        values = (region.x, region.y, region.width, region.height)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise TypeError("OCR region bounds must be integers.")
        if region.x < 0 or region.y < 0 or region.width <= 0 or region.height <= 0:
            raise ValueError("OCR region must have positive dimensions and non-negative origin.")
        if (
            region.x + region.width > self._owned_image.width
            or region.y + region.height > self._owned_image.height
        ):
            raise ValueError("OCR region must fit inside the captured image.")
        return region

    def _cache_key(
        self,
        region: Bounds | None,
        preprocessing_id: str,
    ) -> tuple[Bounds | None, str, str]:
        """Builds the frame-local cache key from region, variant, and backend revision."""

        return region, preprocessing_id, self.backend_revision

    def _lookup_cached(self, key: tuple[Bounds | None, str, str]) -> _OcrCacheEntry | None:
        """Returns and promotes a cached entry while counting a direct hit."""

        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache_hits += 1
        if key != self._pinned_fullframe_key:
            self._cache.move_to_end(key)
        return entry

    def _run_backend(
        self,
        *,
        key: tuple[Bounds | None, str, str],
        region: Bounds | None,
        prepare: Callable[[Image.Image, Bounds], Image.Image | None] | None,
        pin_fullframe: bool,
    ) -> OcrResult | None:
        """Prepares one owned input, runs the backend once, and caches only success."""

        if prepare is not None:
            assert region is not None
            source = prepare(self._owned_image.copy(), region)
            if source is None:
                self._store_cache(key, _OcrCacheEntry(result=None, not_applicable=True))
                return None
            if not isinstance(source, Image.Image) or source.width <= 0 or source.height <= 0:
                raise ValueError("prepare must return a non-empty PIL image or None.")
            source = source.copy()
        else:
            source = self._owned_image.copy()
        processed_pixel_area = (
            source.width * source.height
            if prepare is not None or region is None
            else region.width * region.height
        )
        self._engine_calls += 1
        self._processed_pixel_area += processed_pixel_area
        started = perf_counter()
        try:
            raw_result = self._backend.read_result(
                source,
                None if prepare is not None else region,
            )
        except Exception:
            self._engine_seconds += perf_counter() - started
            raise
        self._engine_seconds += perf_counter() - started
        if not isinstance(raw_result, OcrResult):
            raise TypeError("OCR backend must return OcrResult.")
        result = raw_result
        if region is not None and prepare is not None:
            result = _project_result(
                raw_result,
                region=region,
                processed_size=source.size,
            )
        self._store_cache(key, _OcrCacheEntry(result=result), pin=pin_fullframe)
        return result

    def _store_cache(
        self,
        key: tuple[Bounds | None, str, str],
        entry: _OcrCacheEntry,
        *,
        pin: bool = False,
    ) -> None:
        """Stores one successful result while preserving the pinned full-frame entry."""

        if key in self._cache:
            self._cache[key] = entry
            if pin:
                self._pinned_fullframe_key = key
            elif key != self._pinned_fullframe_key:
                self._cache.move_to_end(key)
            return
        if pin:
            while len(self._cache) >= self.max_entries:
                evicted = self._evict_oldest_unpinned()
                if not evicted:
                    break
            if len(self._cache) >= self.max_entries:
                # This can only occur if an impossible second pinned key is
                # introduced; leave the existing proof intact and skip caching.
                return
            self._cache[key] = entry
            self._pinned_fullframe_key = key
            return
        if self.max_entries <= 1:
            if self._pinned_fullframe_key is not None:
                return
            if self._cache:
                self._evict_oldest_unpinned()
            self._cache[key] = entry
            return
        while len(self._cache) >= self.max_entries:
            if not self._evict_oldest_unpinned():
                return
        self._cache[key] = entry

    def _evict_oldest_unpinned(self) -> bool:
        """Evicts the oldest non-pinned entry, if capacity is available for it."""

        for candidate in tuple(self._cache):
            if candidate == self._pinned_fullframe_key:
                continue
            del self._cache[candidate]
            return True
        return False


def _contained_result(result: OcrResult, region: Bounds) -> OcrResult:
    """Returns only whole OCR lines and words contained by a raw full-frame ROI."""

    lines = tuple(
        line
        for line in result.lines
        if region.contains_bounds(line.bounds)
        and all(region.contains_bounds(word.bounds) for word in line.words)
    )
    words = tuple(word for word in result.words if region.contains_bounds(word.bounds))
    return OcrResult(lines=lines, words=words)


def _project_result(
    result: OcrResult,
    *,
    region: Bounds,
    processed_size: tuple[int, int],
) -> OcrResult:
    """Projects transformed-crop coordinates back to the original ROI exactly once."""

    processed_width, processed_height = processed_size
    if processed_width <= 0 or processed_height <= 0:
        raise ValueError("Processed OCR image must have positive dimensions.")
    scale_x = region.width / processed_width
    scale_y = region.height / processed_height

    def project(bounds: Bounds) -> Bounds:
        """Projects one transformed bounds rectangle using endpoint scaling."""

        left = region.x + round(bounds.x * scale_x)
        top = region.y + round(bounds.y * scale_y)
        right = region.x + round((bounds.x + bounds.width) * scale_x)
        bottom = region.y + round((bounds.y + bounds.height) * scale_y)
        left = max(region.x, min(left, region.x + region.width - 1))
        top = max(region.y, min(top, region.y + region.height - 1))
        right = max(left + 1, min(right, region.x + region.width))
        bottom = max(top + 1, min(bottom, region.y + region.height))
        return Bounds(x=left, y=top, width=right - left, height=bottom - top)

    return OcrResult(
        lines=tuple(
            OcrLine(
                text=line.text,
                bounds=project(line.bounds),
                confidence=line.confidence,
                words=tuple(
                    OcrWord(
                        text=word.text,
                        bounds=project(word.bounds),
                        confidence=word.confidence,
                    )
                    for word in line.words
                ),
            )
            for line in result.lines
        ),
        words=tuple(
            OcrWord(
                text=word.text,
                bounds=project(word.bounds),
                confidence=word.confidence,
            )
            for word in result.words
        ),
    )


@dataclass(slots=True)
class RapidOcrService:
    """Runs OCR through the configured RapidOCR backend."""

    _engine: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Constructs the OCR backend or fails fast when the dependency is unavailable."""

        if RapidOCR is None:
            raise ScreenClassificationError("rapidocr_onnxruntime is required for OCR-backed observations.")
        self._engine = RapidOCR()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
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

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Returns OCR lines from the full screenshot or the requested crop."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Returns newline-joined OCR text for the requested region."""

        return "\n".join(line.text for line in self.read_lines(image, region))


class UnavailableOcrService:
    """Fail-fast OCR implementation used when no OCR backend is configured."""

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Raises because OCR-dependent observations are unsupported without a backend."""

        del image
        raise ScreenClassificationError(
            "OCR was requested but no OCR backend is configured.",
            region=region,
        )

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Raises because OCR-dependent observations are unsupported without a backend."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Raises because OCR-dependent selectors are unsupported without a backend."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _crop_image(image: Image.Image, region: Bounds | None) -> tuple[Image.Image, int, int]:
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
    bounds = Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))
    words = _to_ocr_words(str(text).strip(), bounds=bounds, confidence=float(confidence))
    return OcrLine(
        text=str(text).strip(),
        bounds=bounds,
        confidence=float(confidence),
        words=words,
    )


def _to_ocr_words(text: str, *, bounds: Bounds, confidence: float) -> tuple[OcrWord, ...]:
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
        word_bounds = Bounds(
            x=bounds.x + consumed_width,
            y=bounds.y,
            width=width,
            height=bounds.height,
        )
        words.append(OcrWord(text=word, bounds=word_bounds, confidence=confidence))
        consumed_width += width
    return tuple(words)
