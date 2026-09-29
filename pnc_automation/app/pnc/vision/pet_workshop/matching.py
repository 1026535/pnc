"""Template matching primitives shared by Workshop readers."""

from __future__ import annotations

from pathlib import Path

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

from .constants import _DATA_DIR


def best(
    matcher: OpenCvTemplateMatcher,
    prepared: PreparedFrame,
    templates: tuple[Path, ...],
    region: Bounds,
    threshold: float,
) -> tuple[TemplateMatch, int] | None:
    """Return the highest-confidence family match."""

    result: tuple[TemplateMatch, int] | None = None
    for index, template in enumerate(templates):
        match = matcher.find_best_match(
            prepared, template, threshold=threshold, search_region=region
        )
        if match is not None and (result is None or match.confidence > result[0].confidence):
            result = (match, index)
    return result


def control(
    matcher: OpenCvTemplateMatcher,
    prepared: PreparedFrame,
    template: Path,
    region: Bounds,
    threshold: float,
) -> Bounds | None:
    """Return the matched control bounds in image coordinates."""

    match = matcher.find_best_match(
        prepared, template, threshold=threshold, search_region=region
    )
    return match.bounds if match is not None else None


def icons(
    matcher: OpenCvTemplateMatcher,
    prepared: PreparedFrame,
    *,
    templates: tuple[tuple[str, object], ...],
    region: Bounds,
    threshold: float,
) -> list[tuple[object, TemplateMatch]]:
    """Return deduplicated icon matches in one bounded region."""

    accepted: list[tuple[object, TemplateMatch]] = []
    for name, value in templates:
        for match in matcher.find_matches(
            prepared,
            _DATA_DIR / name,
            threshold=threshold,
            search_region=region,
        ):
            if any(
                other.bounds.contains_point(match.bounds.center())
                or match.bounds.contains_point(other.bounds.center())
                for _value, other in accepted
            ):
                continue
            accepted.append((value, match))
    accepted.sort(key=lambda item: (item[1].bounds.x, item[1].bounds.y))
    return accepted
