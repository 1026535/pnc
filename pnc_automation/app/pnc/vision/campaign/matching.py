"""Bounded Campaign template matching independent of the producer."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.selector_catalog import default_selector_asset_root
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame

from .constants import (
    _MAP_MAX_PADLOCKS, _MAP_PADLOCK_CLUSTER_RADIUS, _MAP_PADLOCK_SEARCH,
    _MAP_PADLOCK_TEMPLATES, _MAP_PADLOCK_THRESHOLD,
)
from .geometry import _to_reference_bounds


def _map_padlock_matches(
    frame: PreparedFrame,
    matcher: OpenCvTemplateMatcher,
) -> tuple[Bounds, ...]:
    """Return one strongest reference-space hit per observed map padlock."""

    hits: list[tuple[Bounds, float]] = []
    search_region = Bounds(*_MAP_PADLOCK_SEARCH)
    for template_name in _MAP_PADLOCK_TEMPLATES:
        for match in matcher.find_matches(
            frame,
            default_selector_asset_root() / template_name,
            threshold=_MAP_PADLOCK_THRESHOLD,
            search_region=search_region,
            max_matches=_MAP_MAX_PADLOCKS,
        ):
            hits.append((_to_reference_bounds(match.bounds, frame), match.confidence))
    hits.sort(key=lambda item: item[1], reverse=True)
    kept: list[Bounds] = []
    for bounds, _confidence in hits:
        center = bounds.center()
        if any(
            (center[0] - other.center()[0]) ** 2 + (center[1] - other.center()[1]) ** 2
            <= _MAP_PADLOCK_CLUSTER_RADIUS**2
            for other in kept
        ):
            continue
        kept.append(bounds)
    kept.sort(key=lambda bounds: (bounds.y, bounds.x))
    return tuple(kept)
