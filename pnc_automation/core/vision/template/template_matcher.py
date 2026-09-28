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


# OpenCV's inner thread pool stays bounded to one thread: callers such as the
# Home-camera zoom sweep already own bounded parallelism across matcher calls,
# and a nested per-operation pool oversubscribes it (~2x measured camera
# cost).  ``cv2.setNumThreads`` is process-wide and not thread-safe, so it is
# applied once here at module import — before any matcher can run — and must
# never be toggled per match, per matcher, or inside a worker pool.
cv2.setNumThreads(1)

_MAX_ASPECT_RATIO_ERROR = 0.01
_MAX_COLOR_DELTA = 255.0
_MAX_CANDIDATES_TO_CHECK = 256
_DEFAULT_TEMPLATE_CACHE_SIZE = 128
# Coarse-to-fine search constants.  The proposal floor sits below the final
# threshold to retain native candidates on the qualified captures; coarse
# score changes and bounded candidate ranking can still omit candidates on
# unseen content. Proposals never qualify a match. Distinct neighborhoods are
# deduplicated at a coarse Chebyshev
# radius and bounded; overflow falls back to the exact full-resolution search
# rather than truncating a possible rival.
_PROPOSAL_THRESHOLD_MARGIN = 0.20
_PROPOSAL_NEIGHBORHOOD_PX = 3
_MAX_REFINEMENT_PROPOSALS = 8
# A coarse pixel maps through the frame-size ratio into native reference
# coordinates; this radius covers the resulting position quantization.
_REFINEMENT_RADIUS_PX = 6


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


@dataclass(frozen=True, slots=True)
class _MatchContext:
    """Shared prepared inputs for one bounded template search."""

    frame: PreparedFrame
    region: Bounds
    decoded: _DecodedTemplate
    source: np.ndarray
    response: np.ndarray


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
        template_scale: float = 1.0,
    ) -> TemplateMatch | None:
        """Return the best bounded candidate above ``threshold``.

        PIL frames are normalized to ``reference_size`` before matching.  A
        prepared frame reuses its existing normalization.  Search regions are
        in reference coordinates, while returned bounds are in original
        screenshot coordinates.  ``template_scale`` rescales the decoded
        template before matching so callers can probe a bounded camera-zoom
        hypothesis; returned bounds reflect the scaled on-screen size.
        Unsupported aspect ratios return ``None`` before template decoding.
        """

        _validate_threshold(threshold)
        context = self._match_context(
            image,
            template_path,
            search_region=search_region,
            reference_size=reference_size,
            template_scale=template_scale,
        )
        if context is None:
            return None
        qualified = _qualified_candidates(
            context.response,
            source=context.source,
            template=context.decoded.rgb,
            alpha=context.decoded.alpha,
            threshold=threshold,
        )
        if not qualified:
            return None
        match_x, match_y, _correlation, confidence = max(qualified, key=lambda item: item[3])
        template_height, template_width = context.decoded.rgb.shape[:2]
        return TemplateMatch(
            bounds=_match_bounds(
                frame=context.frame,
                region=context.region,
                x=match_x,
                y=match_y,
                width=template_width,
                height=template_height,
            ),
            confidence=confidence,
        )

    def find_matches(
        self,
        image: Image.Image | PreparedFrame,
        template_path: Path,
        *,
        threshold: float,
        search_region: Bounds | None = None,
        reference_size: tuple[int, int] | None = None,
        max_matches: int = 8,
    ) -> tuple[TemplateMatch, ...]:
        """Return up to ``max_matches`` non-overlapping candidates above ``threshold``.

        Every qualified candidate in the same bounded top-correlation set used
        by ``find_best_match`` is scored by confidence first; suppression and
        truncation then apply in descending confidence order. A candidate is
        suppressed when its center falls inside an accepted match's half-size
        neighborhood, so repeated glyphs must be separated by more than half a
        template edge. Results are deterministic for a given frame.
        """

        _validate_threshold(threshold)
        if isinstance(max_matches, bool) or not isinstance(max_matches, int) or max_matches <= 0:
            raise ValueError("max_matches must be a positive integer.")
        context = self._match_context(
            image,
            template_path,
            search_region=search_region,
            reference_size=reference_size,
        )
        if context is None:
            return ()
        qualified = _qualified_candidates(
            context.response,
            source=context.source,
            template=context.decoded.rgb,
            alpha=context.decoded.alpha,
            threshold=threshold,
        )
        template_height, template_width = context.decoded.rgb.shape[:2]
        half_width = template_width / 2.0
        half_height = template_height / 2.0
        ranked = sorted(
            qualified,
            key=lambda item: (-item[3], -item[2], item[1], item[0]),
        )
        accepted: list[tuple[int, int, float]] = []
        for match_x, match_y, _correlation, confidence in ranked:
            center_x = match_x + half_width
            center_y = match_y + half_height
            if any(
                abs(center_x - (other_x + half_width)) < half_width
                and abs(center_y - (other_y + half_height)) < half_height
                for other_x, other_y, _ in accepted
            ):
                continue
            accepted.append((match_x, match_y, confidence))
            if len(accepted) >= max_matches:
                break
        return tuple(
            TemplateMatch(
                bounds=_match_bounds(
                    frame=context.frame,
                    region=context.region,
                    x=match_x,
                    y=match_y,
                    width=template_width,
                    height=template_height,
                ),
                confidence=confidence,
            )
            for match_x, match_y, confidence in accepted
        )

    def prepare_proposal_frame(self, frame: PreparedFrame) -> PreparedFrame:
        """Returns a half-resolution proposal frame for coarse-to-fine matching.

        The proposal frame is a fresh immutable downsample of ``frame`` that
        keeps the original screenshot size, so coarse positions still project
        through the standard original/reference mapping.  One proposal frame
        serves every scale hypothesis of a localization; it carries no
        mutable scratch state — its pixels are owned and read-only like any
        prepared frame.
        """

        if not isinstance(frame, PreparedFrame):
            raise TypeError("frame must be a PreparedFrame")
        width = max(1, frame.reference_size[0] // 2)
        height = max(1, frame.reference_size[1] // 2)
        pixels = cv2.resize(
            frame.pixels, (width, height), interpolation=cv2.INTER_AREA
        )
        return PreparedFrame(
            pixels=pixels,
            original_size=frame.original_size,
            reference_size=(width, height),
        )

    def find_best_match_coarse_to_fine(
        self,
        image: PreparedFrame,
        proposal_frame: PreparedFrame,
        template_path: Path,
        *,
        threshold: float,
        template_scale: float = 1.0,
    ) -> TemplateMatch | None:
        """Returns the best bounded candidate via coarse proposals and native refinement.

        The coarse pass runs the same correlation and color machinery on the
        smaller ``proposal_frame`` at ``threshold - _PROPOSAL_THRESHOLD_MARGIN``
        to propose candidate neighborhoods; every distinct neighborhood is
        then refined by the exact bounded search on ``image`` at the unchanged
        ``threshold`` and ``template_scale``.  A proposal can never qualify a
        match by itself, and the returned bounds and confidence carry the same
        meaning as ``find_best_match``.

        Numerical limits, stated honestly:

        - Proposals come from the same bounded top-correlation set
          (``_MAX_CANDIDATES_TO_CHECK``) evaluated at the lowered floor, so a
          candidate that would qualify natively can be missed if its coarse
          score degrades beyond the measured margin or its coarse correlation
          rank falls outside that bounded set. Qualification therefore applies
          to the validated landmark content and scales, not arbitrary images.
        - Distinct proposal neighborhoods are deduplicated at Chebyshev
          radius ``_PROPOSAL_NEIGHBORHOOD_PX`` and bounded to
          ``_MAX_REFINEMENT_PROPOSALS``.  More distinct neighborhoods fall
          back to the exact full-resolution search for this template and
          scale, so no possible rival is silently truncated and the result
          keeps all proof consequences of the full search.
        - Proposal positions map through the actual frame-size ratio; a
          ``_REFINEMENT_RADIUS_PX`` window covers the resulting quantization.
        """

        _validate_threshold(threshold)
        if not isinstance(image, PreparedFrame) or not isinstance(
            proposal_frame, PreparedFrame
        ):
            raise TypeError("coarse-to-fine matching requires prepared frames")
        ratio_x = image.reference_size[0] / proposal_frame.reference_size[0]
        ratio_y = image.reference_size[1] / proposal_frame.reference_size[1]
        if not (
            math.isfinite(ratio_x)
            and math.isfinite(ratio_y)
            and ratio_x > 0.0
            and ratio_y > 0.0
            and _aspect_ratio_error(ratio_x, 1.0, ratio_y, 1.0)
            <= _MAX_ASPECT_RATIO_ERROR
        ):
            raise ValueError(
                "proposal_frame must be a same-aspect downscale of image"
            )
        context = self._match_context(
            proposal_frame,
            template_path,
            search_region=None,
            reference_size=None,
            template_scale=template_scale / ratio_x,
        )
        if context is None:
            # The scaled template cannot exist on the proposal frame; the
            # exact native search decides so edge semantics (e.g. an
            # oversized or undecodable template) stay identical.
            return self.find_best_match(
                image,
                template_path,
                threshold=threshold,
                template_scale=template_scale,
            )
        qualified = _qualified_candidates(
            context.response,
            source=context.source,
            template=context.decoded.rgb,
            alpha=context.decoded.alpha,
            threshold=max(0.0, threshold - _PROPOSAL_THRESHOLD_MARGIN),
        )
        if not qualified:
            return None
        ranked = sorted(
            qualified,
            key=lambda item: (-item[3], -item[2], item[1], item[0]),
        )
        positions: list[tuple[int, int]] = []
        for candidate_x, candidate_y, _correlation, _confidence in ranked:
            if any(
                abs(candidate_x - kept_x) <= _PROPOSAL_NEIGHBORHOOD_PX
                and abs(candidate_y - kept_y) <= _PROPOSAL_NEIGHBORHOOD_PX
                for kept_x, kept_y in positions
            ):
                continue
            positions.append((candidate_x, candidate_y))
        if len(positions) > _MAX_REFINEMENT_PROPOSALS:
            return self.find_best_match(
                image,
                template_path,
                threshold=threshold,
                template_scale=template_scale,
            )
        decoded = self._template_cache.get(template_path)
        if template_scale != 1.0:
            decoded_native = _scale_decoded_template(decoded, template_scale)
            if decoded_native is None:
                return None
            decoded = decoded_native
        template_height, template_width = decoded.rgb.shape[:2]
        native_width, native_height = image.reference_size
        best: TemplateMatch | None = None
        for candidate_x, candidate_y in positions:
            native_x = int(round(candidate_x * ratio_x))
            native_y = int(round(candidate_y * ratio_y))
            left = max(0, native_x - _REFINEMENT_RADIUS_PX)
            top = max(0, native_y - _REFINEMENT_RADIUS_PX)
            right = min(
                native_width,
                native_x + template_width + _REFINEMENT_RADIUS_PX,
            )
            bottom = min(
                native_height,
                native_y + template_height + _REFINEMENT_RADIUS_PX,
            )
            hit = self.find_best_match(
                image,
                template_path,
                threshold=threshold,
                search_region=Bounds(
                    x=left,
                    y=top,
                    width=right - left,
                    height=bottom - top,
                ),
                template_scale=template_scale,
            )
            if hit is not None and (best is None or hit.confidence > best.confidence):
                best = hit
        return best

    def _match_context(
        self,
        image: Image.Image | PreparedFrame,
        template_path: Path,
        *,
        search_region: Bounds | None,
        reference_size: tuple[int, int] | None,
        template_scale: float = 1.0,
    ) -> _MatchContext | None:
        """Resolve the shared frame, region, template, and correlation response."""

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
        if template_scale != 1.0:
            decoded = _scale_decoded_template(decoded, template_scale)
            if decoded is None:
                return None
        template_height, template_width = decoded.rgb.shape[:2]
        if template_width > region.width or template_height > region.height:
            return None
        source = frame.pixels[
            region.y : region.y + region.height,
            region.x : region.x + region.width,
        ]
        response = _correlation_response(source, decoded.rgb, decoded.alpha)
        return _MatchContext(
            frame=frame,
            region=region,
            decoded=decoded,
            source=source,
            response=response,
        )

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


def _scale_decoded_template(
    decoded: _DecodedTemplate,
    template_scale: float,
) -> _DecodedTemplate | None:
    """Rescale a decoded template for one bounded camera-zoom hypothesis.

    Returns ``None`` when the scaled template would be too small to match
    meaningfully; the caller treats that hypothesis as producing no
    candidate.  The input arrays stay untouched because ``cv2.resize``
    allocates fresh output.
    """

    if (
        isinstance(template_scale, bool)
        or not isinstance(template_scale, Real)
        or not math.isfinite(float(template_scale))
        or float(template_scale) <= 0.0
    ):
        raise ValueError("template_scale must be a positive finite number")
    scale = float(template_scale)
    height, width = decoded.rgb.shape[:2]
    scaled_width = max(1, int(round(width * scale)))
    scaled_height = max(1, int(round(height * scale)))
    if scaled_width < 4 or scaled_height < 4:
        return None
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    scaled_rgb = cv2.resize(
        decoded.rgb, (scaled_width, scaled_height), interpolation=interpolation
    )
    scaled_alpha = cv2.resize(
        decoded.alpha, (scaled_width, scaled_height), interpolation=interpolation
    )
    if not np.any(scaled_alpha):
        return None
    return _DecodedTemplate(rgb=scaled_rgb, alpha=scaled_alpha)


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


def _qualified_candidates(
    response: np.ndarray,
    *,
    source: np.ndarray,
    template: np.ndarray,
    alpha: np.ndarray,
    threshold: float,
) -> list[tuple[int, int, float, float]]:
    """Score every bounded candidate above ``threshold``.

    Returns ``(x, y, correlation, confidence)`` tuples in descending
    correlation order. Confidence is ``min(correlation, color_closeness)``,
    so callers that rank or suppress candidates must order by confidence,
    not by the correlation score alone.
    """

    finite_response = np.nan_to_num(response, nan=-1.0, posinf=-1.0, neginf=-1.0)
    flat = finite_response.ravel()
    if not flat.size:
        return []
    # Confidence is bounded by correlation, so no candidate can qualify when
    # the strongest response is already below the threshold.
    if float(finite_response.max()) < threshold:
        return []

    candidate_count = min(_MAX_CANDIDATES_TO_CHECK, flat.size)
    candidate_indices = np.argpartition(flat, -candidate_count)[-candidate_count:]
    candidate_indices = candidate_indices[np.argsort(flat[candidate_indices])[::-1]]

    qualified: list[tuple[int, int, float, float]] = []
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
        qualified.append((x, y, correlation, confidence))
    return qualified


def _match_bounds(
    *,
    frame: PreparedFrame,
    region: Bounds,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Bounds:
    """Project one accepted candidate into original screenshot coordinates."""

    reference_x = region.x + x
    reference_y = region.y + y
    if frame.original_size == frame.reference_size:
        return Bounds(x=reference_x, y=reference_y, width=width, height=height)
    return _project_bounds(
        x=reference_x,
        y=reference_y,
        width=width,
        height=height,
        original_size=frame.original_size,
        reference_size=frame.reference_size,
    )


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
