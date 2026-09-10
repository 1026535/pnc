"""OpenCV-backed template matching for screenshot anchors."""

from __future__ import annotations

import math
from numbers import Real
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch


_MAX_ASPECT_RATIO_ERROR = 0.01
_MAX_COLOR_DELTA = 255.0
_MAX_CANDIDATES_TO_CHECK = 256


class OpenCvTemplateMatcher:
    """Finds a template with normalized correlation and a color guard.

    The returned confidence is ``min(correlation, color_closeness)``.  The
    correlation component comes from OpenCV's normalized correlation methods,
    while color closeness is ``1 - mean(abs(candidate - template)) / 255``
    over the template's non-transparent pixels.  A hit therefore needs both
    the expected local texture and sufficiently close absolute colors; the
    value is a deterministic similarity score, not a probability.  The color
    guard evaluates the 256 highest-correlation candidate locations, so the
    result is the best accepted candidate within that bounded set.
    """

    def find_best_match(
        self,
        image: Image.Image,
        template_path: Path,
        *,
        threshold: float,
        search_region: Bounds | None = None,
        reference_size: tuple[int, int] | None = None,
    ) -> TemplateMatch | None:
        """Return the best bounded candidate above ``threshold``.

        ``reference_size`` gives the coordinate space in which the template
        and optional ``search_region`` are authored.  The screenshot is
        normalized to that size before matching and the result is projected
        back to the screenshot's original pixels.  A reference and screenshot
        whose aspect ratios differ by more than one percent are unsupported
        and return no match.
        """

        _validate_threshold(threshold)
        _validate_image(image)
        normalized_reference_size = _validate_reference_size(reference_size)

        original_width, original_height = image.size
        if normalized_reference_size is not None and _aspect_ratio_error(
            original_width,
            original_height,
            *normalized_reference_size,
        ) > _MAX_ASPECT_RATIO_ERROR:
            return None

        template, alpha = _load_template(template_path)

        working_image = image.convert("RGB")
        if normalized_reference_size is not None:
            reference_width, reference_height = normalized_reference_size
            if working_image.size != normalized_reference_size:
                working_image = working_image.resize(
                    normalized_reference_size,
                    Image.Resampling.LANCZOS,
                )
        else:
            reference_width, reference_height = working_image.size

        region = _validate_search_region(
            search_region,
            width=reference_width,
            height=reference_height,
        )
        if region is None:
            region = Bounds(x=0, y=0, width=reference_width, height=reference_height)

        template_width, template_height = template.size
        if template_width > region.width or template_height > region.height:
            return None

        source = np.asarray(working_image, dtype=np.uint8)
        source = source[region.y : region.y + region.height, region.x : region.x + region.width]
        template_rgb = np.asarray(template, dtype=np.uint8)[..., :3]
        alpha_values = np.asarray(alpha, dtype=np.uint8)
        template_mask = alpha_values if not np.all(alpha_values == 255) else None

        response = _correlation_response(source, template_rgb, template_mask)
        best = _select_best_candidate(
            response,
            source=source,
            template=template_rgb,
            alpha=alpha_values,
            threshold=threshold,
        )
        if best is None:
            return None

        match_x, match_y, confidence = best
        reference_x = region.x + match_x
        reference_y = region.y + match_y
        if normalized_reference_size is None:
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
                original_size=(original_width, original_height),
                reference_size=normalized_reference_size,
            )
        return TemplateMatch(bounds=bounds, confidence=confidence)


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
    except Exception as exc:  # Pillow uses several exception types for closed/bad images.
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
        raise ValueError(
            f"search_region must fit within the {width}x{height} matching image"
        )
    return search_region


def _load_template(path: Path) -> tuple[Image.Image, Image.Image]:
    if not isinstance(path, Path):
        raise TypeError("template_path must be a pathlib.Path")
    if not path.is_file():
        raise FileNotFoundError(f"template image does not exist: {path}")
    try:
        with Image.open(path) as opened:
            template = opened.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"template image could not be decoded: {path}") from exc

    if template.width <= 0 or template.height <= 0:
        raise ValueError(f"template image must have positive dimensions: {path}")
    alpha = template.getchannel("A")
    if not np.any(np.asarray(alpha, dtype=np.uint8)):
        raise ValueError("template image must contain at least one non-transparent pixel")
    return template, alpha


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
    mask: np.ndarray | None,
) -> np.ndarray:
    template_values = template.astype(np.float32)
    if mask is None:
        template_variance = float(np.max(np.var(template_values, axis=(0, 1))))
        if template_variance <= 1e-6:
            result = cv2.matchTemplate(
                source,
                template,
                cv2.TM_SQDIFF_NORMED,
            )
            return np.clip(1.0 - result, 0.0, 1.0)
        result = cv2.matchTemplate(
            source,
            template,
            cv2.TM_CCOEFF_NORMED,
        )
        return np.clip(np.nan_to_num(result, nan=-1.0), 0.0, 1.0)

    if float(np.sum(mask)) <= 0.0:
        raise ValueError("template mask must contain at least one visible pixel")
    weights = mask[..., None] / 255.0
    template_means = np.sum(template_values * weights, axis=(0, 1)) / np.sum(weights, axis=(0, 1))
    template_variance = float(
        np.sum(
            (template_values - template_means) ** 2 * weights
        )
    )
    if template_variance <= 1e-6:
        result = cv2.matchTemplate(
            source,
            template,
            cv2.TM_SQDIFF_NORMED,
            mask=mask,
        )
        return np.clip(1.0 - result, 0.0, 1.0)

    # OpenCV's masked normalized cross-correlation is the supported masked
    # operation. The absolute-color guard below supplies the stricter color
    # requirement and prevents brightness-only anchors from passing.
    result = cv2.matchTemplate(
        source,
        template,
        cv2.TM_CCORR_NORMED,
        mask=mask,
    )
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
