"""Research tree/node discovery and measured row publication."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import ResearchNodeFacts, ResearchNodeId, research_entry_category_metadata, research_node_for_label, research_node_title
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.research.geometry import (
    _GLYPH_MATCH_THRESHOLD,
    _GLYPH_REFERENCE_SIZE,
    _LEVEL_REGION_HEIGHT_RATIO,
    _LEVEL_REGION_WIDTH_RATIO,
    _LEVEL_TEXT_HEIGHT_RATIO,
    _PADLOCK_TEMPLATE,
    component_is_partial,
    derive_icon_bounds,
    discover_label_components,
    icon_has_visible_frame,
    inset_bounds,
    project_bounds_to_reference,
    scroll_viewport,
    clip_bounds,
    union_bounds,
    prepare_research_text_2x,
)
from pnc_automation.app.pnc.vision.research.parsing import (
    _DECORATION_LABEL_PREFIXES,
    join_label_text,
    node_level_readings,
)
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose, OcrTextOrientation, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame


@dataclass(frozen=True, slots=True)
class NodeCandidate:
    """One measured label component and its resolved node identity."""

    label_bounds: Bounds
    raw_text: str
    node_id: ResearchNodeId | None
    title_text: str | None
    clipped: bool


def node_candidate(
    *,
    image: Image.Image,
    component: Bounds,
    ocr_context: ObservationOcrContext,
    category: ResearchCategory | None,
) -> NodeCandidate | None:
    """Resolve one measured label component to a node candidate."""

    region = inset_bounds(component, padding=2, image=image)
    label_lines = ocr_context.read_lines(
        image,
        region,
        purpose=OcrReadPurpose.CONTENT,
        detail="research_node_label",
        required_fact="research_node_label",
        orientation=OcrTextOrientation.UPRIGHT,
    )
    raw_text = join_label_text(label_lines)
    normalized = normalize_ocr_text(raw_text)
    if any(normalized.startswith(prefix) for prefix in _DECORATION_LABEL_PREFIXES):
        return None
    node_id = research_node_for_label(raw_text, category=category)
    clipped = component_is_partial(component, image=image)
    if node_id is None and not clipped:
        label_result = ocr_context.read_preprocessed_result(
            image,
            inset_bounds(component, padding=6, image=image),
            preprocessing_id="research_node_label_rgb_2x",
            prepare=prepare_research_text_2x,
            purpose=OcrReadPurpose.CONTENT,
            detail="research_node_label_inset",
            required_fact="research_node_label",
            orientation=OcrTextOrientation.UPRIGHT,
        )
        label_lines = () if label_result is None else label_result.lines
        raw_text = join_label_text(label_lines) or raw_text
        node_id = research_node_for_label(raw_text, category=category)
    return NodeCandidate(
        label_bounds=component,
        raw_text=raw_text,
        node_id=node_id,
        title_text=research_node_title(node_id) if node_id is not None else (raw_text or None),
        clipped=clipped,
    )


def read_node_level(*, image: Image.Image, icon_bounds: Bounds, ocr_context: ObservationOcrContext) -> tuple[int | None, int | None, bool] | None:
    """Read one coherent n/m or MAX badge without inventing a numeric cap."""

    level_region = clip_bounds(
        Bounds(
            icon_bounds.x,
            icon_bounds.y,
            max(1, round(icon_bounds.width * _LEVEL_REGION_WIDTH_RATIO)),
            max(1, round(icon_bounds.height * _LEVEL_REGION_HEIGHT_RATIO)),
        ),
        Bounds(0, 0, image.width, image.height),
    )
    lines = ocr_context.read_lines(
        image,
        level_region,
        purpose=OcrReadPurpose.CONTENT,
        detail="research_node_level",
        required_fact="research_node_level",
    )
    readings = node_level_readings(lines)
    if not readings:
        readings = node_level_readings(ocr_context.read_lines(
            image,
            Bounds(
                level_region.x,
                level_region.y,
                level_region.width,
                min(level_region.height, max(1, round(icon_bounds.height * _LEVEL_TEXT_HEIGHT_RATIO))),
            ),
            purpose=OcrReadPurpose.CONTENT,
            detail="research_node_level_retry",
            required_fact="research_node_level",
        ))
    return next(iter(readings)) if len(readings) == 1 else None


def detect_node_lock(*, image: Image.Image, prepared: PreparedFrame | None, icon_bounds: Bounds, matcher: OpenCvTemplateMatcher) -> bool | None:
    """Qualify a padlock glyph inside the icon; never infer lock from level."""

    if prepared is None or not _PADLOCK_TEMPLATE.exists():
        return None
    search = project_bounds_to_reference(
        inset_bounds(icon_bounds, padding=-max(2, round(icon_bounds.width * 0.08)), image=image),
        original_size=image.size,
        reference_size=_GLYPH_REFERENCE_SIZE,
    )
    return matcher.find_best_match(prepared, _PADLOCK_TEMPLATE, threshold=_GLYPH_MATCH_THRESHOLD, search_region=search) is not None


def build_tree_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    ocr_context: ObservationOcrContext,
    category: ResearchCategory | None,
    matcher: OpenCvTemplateMatcher,
) -> ObservationAdditions:
    """Publish measured tree rows under the independently proved category."""

    from pnc_automation.app.pnc.vision.research.parsing import header_category

    resolved_header = header_category(lines, image=image)
    if category is None:
        category = resolved_header
    elif resolved_header is not None and resolved_header != category:
        return ObservationAdditions()
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    prepared = matcher.prepare_frame(image, reference_size=_GLYPH_REFERENCE_SIZE)
    candidates = tuple(
        candidate
        for component in discover_label_components(rgb)
        if (candidate := node_candidate(image=image, component=component, ocr_context=ocr_context, category=category)) is not None
    )
    entries = tuple(
        _node_entry(
            image=image,
            rgb=rgb,
            prepared=prepared,
            candidate=candidate,
            category=category,
            ocr_context=ocr_context,
            matcher=matcher,
        )
        for candidate in candidates
    )
    duplicate_titles = {
        title
        for title in (entry.title_text for entry in entries)
        if title is not None and sum(other.title_text == title for other in entries) > 1
    }
    if duplicate_titles:
        entries = tuple(
            replace(
                entry,
                action_point=None,
                action_bounds=None,
                row_status=RowRecognitionStatus.AMBIGUOUS,
                metadata={**entry.metadata, "unresolved_reason": "duplicate_node_label"},
            )
            if entry.title_text in duplicate_titles
            else entry
            for entry in entries
        )
    return ObservationAdditions(list_entries=entries)


def _node_entry(*, image: Image.Image, rgb: np.ndarray, prepared: PreparedFrame | None, candidate: NodeCandidate, category: ResearchCategory | None, ocr_context: ObservationOcrContext, matcher: OpenCvTemplateMatcher) -> DetectedListEntry:
    facts = ResearchNodeFacts(category=category, node_id=candidate.node_id)
    metadata: dict[str, object] = dict(research_entry_category_metadata(facts))
    icon_bounds = derive_icon_bounds(candidate.label_bounds)
    viewport = scroll_viewport(image)
    if candidate.clipped or not viewport.contains_bounds(icon_bounds) or not viewport.contains_bounds(candidate.label_bounds):
        metadata["unresolved_reason"] = "clipped_or_partial_node_label" if candidate.clipped else "incomplete_node_tile_geometry"
        return DetectedListEntry(
            kind=ListEntryKind.RESEARCH,
            bounds=candidate.label_bounds if candidate.clipped else union_bounds(candidate.label_bounds, clip_bounds(icon_bounds, viewport)),
            title_text=candidate.title_text,
            row_status=RowRecognitionStatus.CLIPPED,
            metadata=metadata,
            research_facts=facts,
        )
    if not icon_has_visible_frame(rgb=rgb, icon_bounds=icon_bounds):
        metadata["unresolved_reason"] = "unproved_node_icon_geometry"
        return DetectedListEntry(
            kind=ListEntryKind.RESEARCH,
            bounds=union_bounds(icon_bounds, candidate.label_bounds),
            title_text=candidate.title_text,
            row_status=RowRecognitionStatus.UNREADABLE,
            metadata=metadata,
            research_facts=facts,
        )
    levels = read_node_level(image=image, icon_bounds=icon_bounds, ocr_context=ocr_context)
    locked = detect_node_lock(image=image, prepared=prepared, icon_bounds=icon_bounds, matcher=matcher)
    facts = ResearchNodeFacts(
        category=category,
        node_id=candidate.node_id,
        current_level=None if levels is None else levels[0],
        max_level=None if levels is None else levels[1],
        maximum_reached=None if levels is None else levels[2],
        locked=locked,
    )
    if candidate.node_id is None or category is None:
        metadata["unresolved_reason"] = "unknown_or_partial_node_label"
        return DetectedListEntry(
            kind=ListEntryKind.RESEARCH,
            bounds=union_bounds(icon_bounds, candidate.label_bounds),
            title_text=candidate.title_text,
            row_status=RowRecognitionStatus.UNREADABLE,
            metadata=metadata,
            research_facts=facts,
        )
    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=union_bounds(icon_bounds, candidate.label_bounds),
        title_text=candidate.title_text,
        action_point=icon_bounds.center(),
        action_bounds=icon_bounds,
        row_status=RowRecognitionStatus.COMPLETE,
        metadata=metadata,
        research_facts=facts,
    )
