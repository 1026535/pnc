"""Shared home camera doubles doubles and fixtures."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import numpy as np

from PIL import Image

from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
)
from pnc_automation.app.pnc.domain.observation import Bounds
from pnc_automation.app.pnc.vision.home_city_camera import (
    HomeCityCameraCatalog,
    HomeCityCameraLocalizer,
    load_home_city_camera_catalog,
)
from pnc_automation.core.vision.image.models import TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)


class _ZoomScriptedMatcher:
    """Matcher stub that simulates scene content rendered at a true zoom.

    A hit is returned only while the evaluated ``template_scale`` stays within
    ``tolerance`` of that file's true scene zoom, and the scripted position
    always carries the true scale -- like a real resized-template correlation.
    """

    _TOLERANCE = 0.04

    def __init__(
        self,
        matches: dict[str, TemplateMatch | None],
        *,
        zoom_by_file: dict[str, float],
    ) -> None:
        self._matches = matches
        self._zoom_by_file = zoom_by_file

    def prepare_frame(self, image: Image.Image, *, reference_size=None) -> PreparedFrame:
        del image
        return PreparedFrame(
            pixels=np.zeros((1600, 900, 3), dtype=np.uint8),
            original_size=(900, 1600),
            reference_size=(900, 1600),
        )

    def prepare_proposal_frame(self, frame: PreparedFrame) -> PreparedFrame:
        return frame

    def find_best_match_coarse_to_fine(
        self,
        frame,
        proposal_frame,
        template_path: Path,
        *,
        threshold: float,
        **kwargs,
    ):
        del proposal_frame
        return self.find_best_match(
            frame, template_path, threshold=threshold, **kwargs
        )

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        true_zoom = self._zoom_by_file.get(template_path.name)
        if true_zoom is None or abs(scale - true_zoom) > self._TOLERANCE:
            return None
        return self._matches.get(template_path.name)


class _ScaleAwareScriptedMatcher(_ZoomScriptedMatcher):
    """Matcher stub returning evaluated-scale bounds anchored on the feature.

    A real resized template is ``evaluated_scale * reference`` sized while
    its correlation peak keeps the crop center on the same physical feature
    at ``true_zoom * reference_center + offset``.  Neighboring scales
    therefore return differently sized matches whose centers agree and whose
    top-lefts carry a size-dependent bias -- the live010 false-conflict
    geometry.
    """

    _TOLERANCE = 0.35

    def __init__(
        self,
        placements: dict[str, tuple[float, tuple[float, float]]],
        bounds_by_file: dict[str, Bounds],
        *,
        score: float = 0.95,
    ) -> None:
        self._placements = placements
        self._bounds_by_file = bounds_by_file
        self._score = score

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        placement = self._placements.get(template_path.name)
        if placement is None or abs(scale - placement[0]) > self._TOLERANCE:
            return None
        true_zoom, offset = placement
        bounds = self._bounds_by_file[template_path.name]
        width = int(round(scale * bounds.width))
        height = int(round(scale * bounds.height))
        center_x = true_zoom * (bounds.x + bounds.width / 2) + offset[0]
        center_y = true_zoom * (bounds.y + bounds.height / 2) + offset[1]
        return TemplateMatch(
            bounds=Bounds(
                x=int(round(center_x - width / 2)),
                y=int(round(center_y - height / 2)),
                width=width,
                height=height,
            ),
            confidence=self._score,
        )


def _scripted_localizer(
    placements: dict[str, tuple[int, int] | None],
    *,
    score: float = 0.95,
) -> HomeCityCameraLocalizer:
    """Builds a localizer over zoom-1.0 content at reference position + offset."""

    catalog = load_home_city_camera_catalog()
    matches: dict[str, TemplateMatch | None] = {}
    zoom_by_file: dict[str, float] = {}
    for landmark in catalog.landmarks:
        offset = placements.get(landmark.id)
        if offset is None:
            matches[landmark.file_name] = None
            continue
        zoom_by_file[landmark.file_name] = 1.0
        matches[landmark.file_name] = TemplateMatch(
            bounds=replace(
                landmark.reference_bounds,
                x=landmark.reference_bounds.x + offset[0],
                y=landmark.reference_bounds.y + offset[1],
            ),
            confidence=score,
        )
    return HomeCityCameraLocalizer(
        matcher=_ZoomScriptedMatcher(matches, zoom_by_file=zoom_by_file),
        catalog=catalog,
    )


def _zoomed_localizer(
    placements: dict[str, tuple[float, tuple[int, int]]],
    *,
    score: float = 0.95,
    catalog: HomeCityCameraCatalog | None = None,
) -> HomeCityCameraLocalizer:
    """Builds a localizer over content rendered at per-file ``(zoom, offset)``.

    ``placements`` maps a template file name to its true scene zoom and image
    translation; the scripted match lands at ``zoom * reference + offset``.
    """

    catalog = catalog or load_home_city_camera_catalog()
    bounds_by_file = {
        item.file_name: item.reference_bounds
        for item in (*catalog.landmarks, *catalog.targets)
    }
    matches: dict[str, TemplateMatch | None] = {}
    zoom_by_file: dict[str, float] = {}
    for file_name, bounds in bounds_by_file.items():
        placement = placements.get(file_name)
        if placement is None:
            matches[file_name] = None
            continue
        zoom, offset = placement
        zoom_by_file[file_name] = zoom
        # Center-anchored bounds mimic a real match: the resized template's
        # correlation peaks with its center on the physical feature at
        # ``zoom * reference_center + offset``, independent of crop size.
        width = int(round(zoom * bounds.width))
        height = int(round(zoom * bounds.height))
        matches[file_name] = TemplateMatch(
            bounds=Bounds(
                x=int(round(zoom * (bounds.x + bounds.width / 2) + offset[0] - width / 2)),
                y=int(round(zoom * (bounds.y + bounds.height / 2) + offset[1] - height / 2)),
                width=width,
                height=height,
            ),
            confidence=score,
        )
    return HomeCityCameraLocalizer(
        matcher=_ZoomScriptedMatcher(matches, zoom_by_file=zoom_by_file),
        catalog=catalog,
    )


class _AnchorScriptedMatcher(_ZoomScriptedMatcher):
    """Matcher stub scripting anchor-template hits per evaluated scale.

    ``hits`` maps ``(template file name, template_scale)`` to the match a real
    resized-template search would return; matching the anchor spec's scale
    sweep therefore exercises the same correspondence, lane, viewport and HUD
    checks the production matcher feeds.
    """

    def __init__(self, hits: dict[tuple[str, float], TemplateMatch | None]) -> None:
        self._hits = hits

    def find_best_match(self, frame, template_path: Path, *, threshold: float, **kwargs):
        del frame, threshold
        scale = kwargs.get("template_scale", 1.0)
        return self._hits.get((template_path.name, scale))


def _anchor_hit(
    center: tuple[float, float],
    *,
    scale: float = 1.0,
    size: tuple[int, int] = (170, 200),
    score: float = 0.95,
) -> TemplateMatch:
    """Builds a scaled patch match whose bounds stay centered on the scripted feature."""

    width = int(round(scale * size[0]))
    height = int(round(scale * size[1]))
    return TemplateMatch(
        bounds=Bounds(
            x=int(round(center[0] - width / 2)),
            y=int(round(center[1] - height / 2)),
            width=width,
            height=height,
        ),
        confidence=score,
    )


def _view_on_scripted_matcher(
    matcher: _ZoomScriptedMatcher,
    *,
    proof: HomeCityCameraProof | None = None,
) -> HomeCityViewEvidence:
    """Analyzes one scripted frame under a non-localized proof."""

    localizer = HomeCityCameraLocalizer(
        matcher=matcher,
        catalog=load_home_city_camera_catalog(),
    )
    image = Image.new("RGB", (900, 1600))
    camera_proof = proof or HomeCityCameraProof(
        status=HomeCityCameraStatus.INSUFFICIENT,
        reason="scripted view test",
        frame_size=(900, 1600),
    )
    return localizer.analyze_view(image, camera_proof=camera_proof)


class _PrepareCountingMatcher(OpenCvTemplateMatcher):
    """Matcher wrapper counting frame preparations for producer-once checks."""

    def __init__(self) -> None:
        super().__init__()
        self.prepare_frame_calls = 0
        self.prepare_proposal_frame_calls = 0

    def prepare_frame(self, image: Image.Image, *, reference_size=None):
        self.prepare_frame_calls += 1
        return super().prepare_frame(image, reference_size=reference_size)

    def prepare_proposal_frame(self, frame: PreparedFrame):
        self.prepare_proposal_frame_calls += 1
        return super().prepare_proposal_frame(frame)
