"""Research node-detail title, level, costs and read-only controls."""

from __future__ import annotations

import re

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.policy_models import ResourceType
from pnc_automation.app.pnc.domain.research import ResearchDetail, ResearchQueueState, ResearchTextRecord, research_node_for_title
from pnc_automation.app.pnc.domain.resource_cost import ResourceCost
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.research.geometry import (
    _COST_ICON_SLOT_RATIO,
    _COST_ICON_TEMPLATES,
    _GLYPH_MATCH_THRESHOLD,
    _GLYPH_REFERENCE_SIZE,
    _PREMIUM_BUTTON_MIN_AREA_RATIO,
    _PREMIUM_GOLD_GREEN_DELTA,
    _PREMIUM_GOLD_MIN_GREEN,
    _PREMIUM_GOLD_MIN_RED,
    _PREMIUM_GOLD_RED_DELTA,
    _PREMIUM_SEARCH_REGION_RATIO,
    clip_bounds,
    inset_bounds,
    prepare_research_text_2x,
    project_bounds_to_reference,
)
from pnc_automation.app.pnc.vision.research.parsing import (
    _DETAIL_COST_PATTERN,
    _DETAIL_GEM_COST_PATTERN,
    _DETAIL_TIME_PATTERN,
    _DETAIL_TITLE_PATTERN,
    queue_timer_after,
    time_below,
)
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrReadPurpose
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


def detail_additions(*, image: Image.Image, lines: tuple[OcrLine, ...], ocr_context: ObservationOcrContext, max_level_panel: bool, matcher: OpenCvTemplateMatcher) -> ObservationAdditions:
    """Parse the accepted node-detail panel into read-only typed facts."""

    title_text: str | None = None
    current_level: int | None = None
    max_level: int | None = None
    title_line = next((line for line in lines if _DETAIL_TITLE_PATTERN.match(line.text.strip()) is not None), None)
    if title_line is not None:
        match = _DETAIL_TITLE_PATTERN.match(title_line.text.strip())
        assert match is not None
        title_text = match.group("title").strip() or None
        current_level = int(match.group("cur"))
        max_level = int(match.group("max"))
    elif lines:
        title_text = lines[0].text.strip() or None
    node_id = None if title_text is None else research_node_for_title(title_text)
    if node_id is None and title_line is not None:
        left = max(title_line.bounds.x, round(image.width * 0.10))
        right = title_line.bounds.x + title_line.bounds.width + 6
        title_region = clip_bounds(
            Bounds(
                left,
                max(0, title_line.bounds.y - 6),
                max(1, right - left),
                max(round(image.height * 0.04), title_line.bounds.height + 12),
            ),
            Bounds(0, 0, image.width, image.height),
        )
        title_result = ocr_context.read_preprocessed_result(
            image,
            title_region,
            preprocessing_id="research_title_rgb_2x",
            prepare=prepare_research_text_2x,
            purpose=OcrReadPurpose.CONTENT,
            detail="research_detail_title",
            required_fact="research_detail_title",
        )
        title_parts = () if title_result is None else title_result.lines
        measured_title = " ".join(part.text for part in sorted(title_parts, key=lambda part: part.bounds.x))
        match = _DETAIL_TITLE_PATTERN.match(measured_title.strip())
        if match is not None:
            measured_node = research_node_for_title(match.group("title"))
            if measured_node is not None:
                title_text = match.group("title").strip()
                node_id = measured_node
                current_level, max_level = int(match.group("cur")), int(match.group("max"))
    effect_records = tuple(
        ResearchTextRecord(line.text.strip(), line.bounds)
        for line in lines
        if title_line is not None
        and title_line.bounds.y + title_line.bounds.height <= line.bounds.y
        and line.bounds.y < image.height * (0.63 if max_level_panel else 0.44)
        and normalize_ocr_text(line.text) not in {"RESEARCH", "RESEARCHNOW", "MAX"}
        and _DETAIL_TIME_PATTERN.match(line.text.strip()) is None
    )
    if max_level_panel:
        return ObservationAdditions(
            research_detail=ResearchDetail(
                title_text=title_text,
                node_id=node_id,
                current_level=current_level,
                max_level=max_level,
                effect_records=effect_records,
                queue_state=ResearchQueueState.UNKNOWN,
            ),
        )
    prepared = matcher.prepare_frame(image, reference_size=_GLYPH_REFERENCE_SIZE)
    prerequisite = next(
        (
            ResearchTextRecord(line.text.strip(), line.bounds)
            for line in lines
            if "INSTITUTE" in normalize_ocr_text(line.text) and "LV" in normalize_ocr_text(line.text)
        ),
        None,
    )
    costs = tuple(
        cost
        for line in lines
        if (match := _DETAIL_COST_PATTERN.match(line.text.strip())) is not None
        and "/" in line.text
        and ":" not in line.text
        for cost in (
            ResourceCost(
                resource_type=match_cost_resource(image=image, prepared=prepared, line=line, matcher=matcher),
                available=int(match.group(1).replace(",", "")),
                required=int(match.group(2).replace(",", "")),
                text_bounds=line.bounds,
            ),
        )
    )
    original_label = next((line for line in lines if normalize_ocr_text(line.text) == "ORIGINALTIME"), None)
    actual_label = next((line for line in lines if normalize_ocr_text(line.text) == "ACTUALTIME"), None)
    time_lines = [line for line in lines if _DETAIL_TIME_PATTERN.match(line.text.strip())]
    original_time = time_below(original_label, time_lines)
    actual_time = time_below(actual_label, time_lines)
    no_idle = next((line for line in lines if "NOIDLEQUEUE" in normalize_ocr_text(line.text)), None)
    queue_timer = queue_timer_after(no_idle, time_lines) if no_idle is not None else None
    premium = measure_premium_button(image=image, lines=lines, ocr_context=ocr_context)
    return ObservationAdditions(
        research_detail=ResearchDetail(
            title_text=title_text,
            node_id=node_id,
            current_level=current_level,
            max_level=max_level,
            effect_records=effect_records,
            prerequisite_record=prerequisite,
            costs=costs,
            original_time_text=original_time,
            actual_time_text=actual_time,
            premium_gem_cost=premium[1] if premium is not None else None,
            premium_button_bounds=premium[0] if premium is not None else None,
            queue_state=ResearchQueueState.ACTIVE if no_idle is not None else ResearchQueueState.UNKNOWN,
            queue_timer_text=queue_timer,
        )
    )


def match_cost_resource(*, image: Image.Image, prepared, line: OcrLine, matcher: OpenCvTemplateMatcher) -> ResourceType | None:
    """Match the small resource icon left of a cost row when supported."""

    if prepared is None:
        return None
    half_height = max(1, round(line.bounds.height * 1.8))
    center_y = line.bounds.y + line.bounds.height // 2
    slot = Bounds(
        round(image.width * _COST_ICON_SLOT_RATIO[0]),
        center_y - half_height,
        round(image.width * _COST_ICON_SLOT_RATIO[1]),
        2 * half_height,
    )
    search = project_bounds_to_reference(
        clip_bounds(slot, Bounds(0, 0, image.width, image.height)),
        original_size=image.size,
        reference_size=_GLYPH_REFERENCE_SIZE,
    )
    best: tuple[ResourceType, float] | None = None
    for resource_type, template in _COST_ICON_TEMPLATES:
        if not template.exists():
            continue
        match = matcher.find_best_match(prepared, template, threshold=_GLYPH_MATCH_THRESHOLD, search_region=search)
        if match is not None and (best is None or match.confidence > best[1]):
            best = (resource_type, match.confidence)
    return None if best is None else best[0]


def measure_premium_button(*, image: Image.Image, lines: tuple[OcrLine, ...], ocr_context: ObservationOcrContext) -> tuple[Bounds, int | None] | None:
    """Measure the gold Research Now button and any visible gem count."""

    premium_text = next((line for line in lines if "RESEARCHNOW" in normalize_ocr_text(line.text)), None)
    if premium_text is None:
        return None
    region = Bounds(
        round(image.width * _PREMIUM_SEARCH_REGION_RATIO[0]),
        round(image.height * _PREMIUM_SEARCH_REGION_RATIO[1]),
        round(image.width * _PREMIUM_SEARCH_REGION_RATIO[2]),
        round(image.height * _PREMIUM_SEARCH_REGION_RATIO[3]),
    )
    pixels = np.asarray(image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("RGB"), dtype=np.int16)
    gold = (
        (pixels[:, :, 0] >= _PREMIUM_GOLD_MIN_RED)
        & (pixels[:, :, 1] >= _PREMIUM_GOLD_MIN_GREEN)
        & (pixels[:, :, 0] >= pixels[:, :, 2] + _PREMIUM_GOLD_RED_DELTA)
        & (pixels[:, :, 1] >= pixels[:, :, 2] + _PREMIUM_GOLD_GREEN_DELTA)
    ).astype(np.uint8) * 255
    count, _, stats, _ = cv2.connectedComponentsWithStats(gold)
    if count <= 1:
        return None
    index = max(range(1, count), key=lambda i: stats[i][4])
    if stats[index][4] < image.width * image.height * _PREMIUM_BUTTON_MIN_AREA_RATIO:
        return None
    left, top, width, height, _ = (int(value) for value in stats[index])
    button = Bounds(region.x + left, region.y + top, width, height)
    gem_cost = next(
        (int(line.text.strip()) for line in lines if _DETAIL_GEM_COST_PATTERN.match(line.text.strip()) is not None and button.contains_bounds(line.bounds)),
        None,
    )
    if gem_cost is None:
        gem_cost = read_button_gem_cost(image=image, button=button, ocr_context=ocr_context)
    return button, gem_cost


def read_button_gem_cost(*, image: Image.Image, button: Bounds, ocr_context: ObservationOcrContext) -> int | None:
    """Read the small gem count printed inside the measured premium button."""

    for line in ocr_context.read_lines(
        image,
        inset_bounds(button, padding=4, image=image),
        purpose=OcrReadPurpose.CONTENT,
        detail="research_premium_gem_cost",
        required_fact="research_premium_gem_cost",
    ):
        for token in re.findall(r"\d{1,4}", line.text):
            return int(token)
    return None
