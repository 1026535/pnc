"""OpenCV-backed template matching for screenshot anchors."""

from __future__ import annotations

import math
import os
from collections import OrderedDict
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from threading import RLock
from typing import Callable

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch


_MAX_ASPECT_RATIO_ERROR = 0.01
_MAX_COLOR_DELTA = 255.0
_MAX_CANDIDATES_TO_CHECK = 256
_DEFAULT_TEMPLATE_CACHE_SIZE = 128


@dataclass(frozen=True, slots=True)
class PreparedFrame:
    """An immutable RGB frame normalized to one matching coordinate space."""

    pixels: np.ndarray
    original_size: tuple[int, int]
    reference_size: tuple[int, int]

    def __post_init__(self) -> None:
        pixels = np.asarray(self.pixels, dtype=np.uint8)
        if pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError("PreparedFrame pixels must have shape (height, width, 3)")
        if (
            len(self.original_size) != 2
            or len(self.reference_size) != 2
            or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in (*self.original_size, *self.reference_size)
            )
        ):
            raise ValueError("PreparedFrame sizes must contain positive integer dimensions")
        expected_shape = (self.reference_size[1], self.reference_size[0], 3)
        if pixels.shape != expected_shape:
            raise ValueError(
                "PreparedFrame pixels do not match its reference_size "
                f"({pixels.shape[:2]} != {expected_shape[:2]})"
            )
        contiguous = np.ascontiguousarray(pixels, dtype=np.uint8)
        # A read-only NumPy view backed by immutable bytes cannot be made
        # writeable again with ``setflags(write=True)``.
        owned = np.frombuffer(contiguous.tobytes(), dtype=np.uint8).reshape(contiguous.shape)
        owned.setflags(write=False)
        object.__setattr__(self, "pixels", owned)


@dataclass(frozen=True, slots=True)
class _DecodedTemplate:
    """Cached template channels and alpha mask, all owned and read-only."""

    rgb: np.ndarray
    alpha: np.ndarray

    def __post_init__(self) -> None:
        rgb = np.asarray(self.rgb, dtype=np.uint8)
        alpha = np.asarray(self.alpha, dtype=np.uint8)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("decoded template RGB data must have shape (height, width, 3)")
        if alpha.shape != rgb.shape[:2]:
            raise ValueError("decoded template alpha data must match RGB dimensions")
        rgb_contiguous = np.ascontiguousarray(rgb, dtype=np.uint8)
        alpha_contiguous = np.ascontiguousarray(alpha, dtype=np.uint8)
        rgb_owned = np.frombuffer(rgb_contiguous.tobytes(), dtype=np.uint8).reshape(
            rgb_contiguous.shape
        )
        alpha_owned = np.frombuffer(alpha_contiguous.tobytes(), dtype=np.uint8).reshape(
            alpha_contiguous.shape
        )
        rgb_owned.setflags(write=False)
        alpha_owned.setflags(write=False)
        object.__setattr__(self, "rgb", rgb_owned)
        object.__setattr__(self, "alpha", alpha_owned)


class DecodedTemplateCache:
    """Thread-safe bounded cache for successfully decoded template images."""

    def __init__(self, max_size: int = _DEFAULT_TEMPLATE_CACHE_SIZE) -> None:
        if isinstance(max_size, bool) or not isinstance(max_size, int) or max_size <= 0:
            raise ValueError("template cache max_size must be a positive integer")
        self._max_size = max_size
        self._entries: OrderedDict[
            tuple[Path, int, int], _DecodedTemplate
        ] = OrderedDict()
        self._lock = RLock()

    def get(
        self,
        path: Path,
        loader: Callable[[Path], _DecodedTemplate] = lambda path: _decode_template(path),
    ) -> _DecodedTemplate:
        """Return a decoded template, loading it once for its current file key."""

        resolved = _validate_template_path(path)
        stat = _stat_template(resolved)
        key = (resolved, stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached
            for old_key in tuple(self._entries):
                if old_key[0] == resolved:
                    del self._entries[old_key]
            decoded = loader(resolved)
            self._entries[key] = decoded
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_size:
                self._entries.popitem(last=False)
            return decoded

    def clear(self) -> None:
        """Discard all decoded templates held by this cache."""

        with self._lock:
            self._entries.clear()

    @property
    def max_size(self) -> int:
        """Return the configured maximum number of cached templates."""

        return self._max_size


class OpenCvTemplateMatcher:
    """Find templates with normalized correlation and an absolute-color guard.

    Confidence is ``min(correlation, color_closeness)``.  Correlation comes
    from OpenCV's normalized methods; color closeness is ``1 - mean(abs(
    candidate - template)) / 255`` over non-transparent pixels.  This is a
    deterministic similarity score, not a probability.  The color guard
    evaluates the 256 highest-correlation candidates, so the result is the
    best accepted candidate within that bounded set.
    """

    def __init__(self, template_cache: DecodedTemplateCache | None = None) -> None:
        self._template_cache = template_cache or DecodedTemplateCache()

    def prepare_frame(
        self,
        image: Image.Image,
        *,
        reference_size: tuple[int, int] | None = None,
    ) -> PreparedFrame | None:
        """Normalize ``image`` once for repeated template matching.

        An aspect-ratio mismatch beyond one percent returns ``None`` before
        any template path is inspected.  The normalized pixels are an owned,
        read-only copy, so later mutation of the PIL image cannot change
        matching results.
        """

        _validate_image(image)
        normalized_reference_size = _validate_reference_size(reference_size)
        original_size = image.size
        if normalized_reference_size is not None and _aspect_ratio_error(
            *original_size,
            *normalized_reference_size,
        ) > _MAX_ASPECT_RATIO_ERROR:
            return None
        working_image = image.convert("RGB")
        if normalized_reference_size is not None and working_image.size != normalized_reference_size:
            working_image = working_image.resize(
                normalized_reference_size,
                Image.Resampling.LANCZOS,
            )
        if normalized_reference_size is None:
            normalized_reference_size = working_image.size
        pixels = np.asarray(working_image, dtype=np.uint8)
        return PreparedFrame(
            pixels=pixels,
            original_size=original_size,
            reference_size=normalized_reference_size,
        )

    def find_best_match(
        self,
        image: Image.Image | PreparedFrame,
        template_path: Path,
        *,
        threshold: float,
        search_region: Bounds | None = None,
        reference_size: tuple[int, int] | None = None,
    ) -> TemplateMatch | None:
        """Return the best bounded candidate above ``threshold``.

        PIL frames are normalized to ``reference_size`` before matching.  A
        prepared frame reuses its existing normalization.  Search regions are
        in reference coordinates, while returned bounds are in original
        screenshot coordinates.  Unsupported aspect ratios return ``None``
        before template decoding.
        """

        _validate_threshold(threshold)
        frame = self._coerce_frame(image, reference_size=reference_size)
        if frame is None:
            return None
        region = _validate_search_region(
            search_region,
            width=frame.reference_size[0],
            height=frame.reference_size[1],
        )
        if region is None:
            region = Bounds(
                x=0,
                y=0,
                width=frame.reference_size[0],
                height=frame.reference_size[1],
            )
        decoded = self._template_cache.get(template_path)
        template_height, template_width = decoded.rgb.shape[:2]
        if template_width > region.width or template_height > region.height:
            return None

        source = frame.pixels[
            region.y : region.y + region.height,
            region.x : region.x + region.width,
        ]
        response = _correlation_response(source, decoded.rgb, decoded.alpha)
        best = _select_best_candidate(
            response,
            source=source,
            template=decoded.rgb,
            alpha=decoded.alpha,
            threshold=threshold,
        )
        if best is None:
            return None

        match_x, match_y, confidence = best
        reference_x = region.x + match_x
        reference_y = region.y + match_y
        if frame.original_size == frame.reference_size:
            bounds = Bounds(
                x=reference_x,
                y=reference_y,
                width=template_width,
                height=template_height,
            )
        else:
            bounds = _project_bounds(
                x=reference_x,
                y=reference_y,
                width=template_width,
                height=template_height,
                original_size=frame.original_size,
                reference_size=frame.reference_size,
            )
        return TemplateMatch(bounds=bounds, confidence=confidence)

    def _coerce_frame(
        self,
        image: Image.Image | PreparedFrame,
        *,
        reference_size: tuple[int, int] | None,
    ) -> PreparedFrame | None:
        if isinstance(image, PreparedFrame):
            if reference_size is not None:
                validated_reference_size = _validate_reference_size(reference_size)
                if validated_reference_size != image.reference_size:
                    raise ValueError("reference_size cannot change an already prepared frame")
            return image
        return self.prepare_frame(image, reference_size=reference_size)


def _validate_threshold(threshold: float) -> None:
    if isinstance(threshold, bool) or not isinstance(threshold, Real):
        raise TypeError("threshold must be a finite number between 0.0 and 1.0")
    if not math.isfinite(float(threshold)) or not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("threshold must be a finite number between 0.0 and 1.0")


def _validate_image(image: Image.Image) -> None:
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL.Image.Image instance")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise ValueError("image must have positive width and height")
    try:
        image.load()
    except Exception as exc:
        raise ValueError("image could not be loaded as a valid PIL image") from exc


def _validate_reference_size(reference_size: tuple[int, int] | None) -> tuple[int, int] | None:
    if reference_size is None:
        return None
    if (
        not isinstance(reference_size, tuple)
        or len(reference_size) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in reference_size)
    ):
        raise TypeError("reference_size must be a (width, height) tuple of integers")
    width, height = reference_size
    if width <= 0 or height <= 0:
        raise ValueError("reference_size must have positive width and height")
    return reference_size


def _validate_search_region(
    search_region: Bounds | None,
    *,
    width: int,
    height: int,
) -> Bounds | None:
    if search_region is None:
        return None
    if not isinstance(search_region, Bounds):
        raise TypeError("search_region must be a Bounds instance or None")
    values = (search_region.x, search_region.y, search_region.width, search_region.height)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise TypeError("search_region bounds must be integers")
    if search_region.x < 0 or search_region.y < 0:
        raise ValueError("search_region x and y must be non-negative")
    if search_region.width <= 0 or search_region.height <= 0:
        raise ValueError("search_region width and height must be positive")
    if (
        search_region.x + search_region.width > width
        or search_region.y + search_region.height > height
    ):
        raise ValueError(f"search_region must fit within the {width}x{height} matching image")
    return search_region


def _validate_template_path(path: Path) -> Path:
    if not isinstance(path, Path):
        raise TypeError("template_path must be a pathlib.Path")
    return path.resolve()


def _stat_template(path: Path) -> os.stat_result:
    try:
        stat = path.stat()
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"template image does not exist: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"template image does not exist: {path}")
    return stat


def _decode_template(path: Path) -> _DecodedTemplate:
    try:
        with Image.open(path) as opened:
            template = opened.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"template image could not be decoded: {path}") from exc

    if template.width <= 0 or template.height <= 0:
        raise ValueError(f"template image must have positive dimensions: {path}")
    rgba = np.array(template, dtype=np.uint8, copy=True, order="C")
    alpha = rgba[..., 3]
    if not np.any(alpha):
        raise ValueError("template image must contain at least one non-transparent pixel")
    return _DecodedTemplate(rgb=rgba[..., :3], alpha=alpha)


def _aspect_ratio_error(
    image_width: int,
    image_height: int,
    reference_width: int,
    reference_height: int,
) -> float:
    image_ratio = image_width / image_height
    reference_ratio = reference_width / reference_height
    return abs(image_ratio / reference_ratio - 1.0)


def _correlation_response(
    source: np.ndarray,
    template: np.ndarray,
    alpha: np.ndarray,
) -> np.ndarray:
    template_values = template.astype(np.float32)
    if np.all(alpha == 255):
        template_variance = float(np.max(np.var(template_values, axis=(0, 1))))
        if template_variance <= 1e-6:
            result = cv2.matchTemplate(source, template, cv2.TM_SQDIFF_NORMED)
            return np.clip(1.0 - result, 0.0, 1.0)
        result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        return np.clip(np.nan_to_num(result, nan=-1.0), 0.0, 1.0)

    if float(np.sum(alpha)) <= 0.0:
        raise ValueError("template mask must contain at least one visible pixel")
    weights = alpha[..., None] / 255.0
    template_means = np.sum(template_values * weights, axis=(0, 1)) / np.sum(
        weights, axis=(0, 1)
    )
    template_variance = float(np.sum((template_values - template_means) ** 2 * weights))
    if template_variance <= 1e-6:
        result = cv2.matchTemplate(source, template, cv2.TM_SQDIFF_NORMED, mask=alpha)
        return np.clip(1.0 - result, 0.0, 1.0)

    result = cv2.matchTemplate(source, template, cv2.TM_CCORR_NORMED, mask=alpha)
    return np.clip(np.nan_to_num(result, nan=-1.0), 0.0, 1.0)


def _select_best_candidate(
    response: np.ndarray,
    *,
    source: np.ndarray,
    template: np.ndarray,
    alpha: np.ndarray,
    threshold: float,
) -> tuple[int, int, float] | None:
    finite_response = np.nan_to_num(response, nan=-1.0, posinf=-1.0, neginf=-1.0)
    flat = finite_response.ravel()
    if not flat.size:
        return None

    candidate_count = min(_MAX_CANDIDATES_TO_CHECK, flat.size)
    candidate_indices = np.argpartition(flat, -candidate_count)[-candidate_count:]
    candidate_indices = candidate_indices[np.argsort(flat[candidate_indices])[::-1]]

    best: tuple[int, int, float] | None = None
    response_width = response.shape[1]
    for index in candidate_indices:
        y, x = divmod(int(index), response_width)
        correlation = float(finite_response[y, x])
        if correlation < threshold:
            continue
        candidate = source[y : y + template.shape[0], x : x + template.shape[1]]
        color_closeness = _color_closeness(candidate, template, alpha)
        confidence = min(correlation, color_closeness)
        if confidence < threshold:
            continue
        if best is None or confidence > best[2]:
            best = (x, y, confidence)
    return best


def _color_closeness(candidate: np.ndarray, template: np.ndarray, alpha: np.ndarray) -> float:
    weights = alpha.astype(np.float32) / 255.0
    total_weight = float(np.sum(weights))
    if total_weight <= 0.0:
        return 0.0
    mean_absolute_delta = float(
        np.sum(
            np.abs(candidate.astype(np.float32) - template.astype(np.float32))
            * weights[..., None]
        )
        / (total_weight * 3.0)
    )
    return float(np.clip(1.0 - mean_absolute_delta / _MAX_COLOR_DELTA, 0.0, 1.0))


def _project_bounds(
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    original_size: tuple[int, int],
    reference_size: tuple[int, int],
) -> Bounds:
    original_width, original_height = original_size
    reference_width, reference_height = reference_size
    left = round(x * original_width / reference_width)
    top = round(y * original_height / reference_height)
    right = round((x + width) * original_width / reference_width)
    bottom = round((y + height) * original_height / reference_height)
    left = min(max(left, 0), original_width)
    top = min(max(top, 0), original_height)
    right = min(max(right, left + 1), original_width)
    bottom = min(max(bottom, top + 1), original_height)
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)
