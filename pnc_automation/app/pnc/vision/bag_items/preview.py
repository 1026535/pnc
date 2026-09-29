"""Qualified chest-preview title and possible-reward publication."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from PIL import Image

from pnc_automation.app.pnc.domain.bag_items import (
    BagChestPreviewFacts,
    BagPreviewRewardFacts,
    treasure_identity_for_label,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.vision.bag_items.geometry import PREVIEW_REFERENCE_SIZE, scaled_region
from pnc_automation.app.pnc.vision.bag_items.parsing import _OWNED_PATTERN, join_lines, union_all
from pnc_automation.app.pnc.vision.numeric_parsing import parse_grouped_integer
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose

_REWARD_RANGE_PATTERN = re.compile(r"^[Xx]\s*(\d[\d,]*)\s*[~-]\s*(\d[\d,]*)\s*$")
_REWARD_SINGLE_PATTERN = re.compile(r"^[Xx]\s*(\d[\d,]*)\s*$")


@dataclass(frozen=True, slots=True)
class PreviewLayoutPlan:
    """Measured title and reward-row bands for one qualified preview layout."""

    title_region: Bounds
    row_regions: tuple[Bounds, ...]
    name_min_x: int
    content_bottom: int
    owned_offset_y: int


PREVIEW_LAYOUTS: dict[str, PreviewLayoutPlan] = {
    "bag_arena_chest_preview": PreviewLayoutPlan(
        title_region=Bounds(x=80, y=215, width=400, height=42),
        row_regions=(
            Bounds(x=45, y=310, width=450, height=115),
            Bounds(x=45, y=425, width=450, height=115),
            Bounds(x=45, y=540, width=450, height=115),
            Bounds(x=45, y=655, width=450, height=110),
        ),
        name_min_x=90,
        content_bottom=742,
        owned_offset_y=75,
    ),
    "bag_common_victory_preview": PreviewLayoutPlan(
        title_region=Bounds(x=90, y=135, width=365, height=60),
        row_regions=(
            Bounds(x=132, y=228, width=375, height=115),
            Bounds(x=132, y=341, width=375, height=115),
            Bounds(x=132, y=455, width=375, height=115),
            Bounds(x=132, y=569, width=375, height=110),
        ),
        name_min_x=0,
        content_bottom=662,
        owned_offset_y=82,
    ),
}


def preview_additions(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    layout_id: str,
) -> ObservationAdditions:
    """Publish title/source and possible reward rows for a known preview."""

    plan = PREVIEW_LAYOUTS.get(layout_id)
    if plan is None:
        return ObservationAdditions()
    title_lines = ocr_context.read_lines(
        image,
        scaled_region(plan.title_region, image, reference=PREVIEW_REFERENCE_SIZE),
        purpose=OcrReadPurpose.CONTENT,
        detail="bag_preview_title",
        required_fact="bag_preview_title",
    )
    title_text = join_lines(title_lines)
    entries = tuple(
        _reward_entry(
            image=image,
            region=region,
            row_index=index,
            name_min_x=plan.name_min_x,
            content_bottom=plan.content_bottom,
            owned_offset_y=plan.owned_offset_y,
            ocr_context=ocr_context,
        )
        for index, region in enumerate(plan.row_regions)
    )
    return ObservationAdditions(
        list_entries=entries,
        bag_preview=BagChestPreviewFacts(
            title_text=title_text,
            source_identity=treasure_identity_for_label(title_text),
            title_bounds=union_all(line.bounds for line in title_lines),
        ),
    )


def _reward_entry(
    *,
    image: Image.Image,
    region: Bounds,
    row_index: int,
    name_min_x: int,
    content_bottom: int,
    owned_offset_y: int,
    ocr_context: ObservationOcrContext,
) -> DetectedListEntry:
    """Publish one possible-reward row; ranges and Owned stay distinct."""

    clipped = region.y + region.height > content_bottom
    visible_region = replace(region, height=min(region.height, content_bottom - region.y))
    row_bounds = scaled_region(visible_region, image, reference=PREVIEW_REFERENCE_SIZE)
    text_region = (
        replace(visible_region, height=min(visible_region.height, owned_offset_y))
        if clipped
        else visible_region
    )
    lines = ocr_context.read_lines(
        image,
        scaled_region(text_region, image, reference=PREVIEW_REFERENCE_SIZE),
        purpose=OcrReadPurpose.CONTENT,
        detail=f"bag_preview_reward_{row_index}",
        required_fact="bag_preview_rewards",
    )
    name_parts: list[str] = []
    range_text: str | None = None
    quantity_min: int | None = None
    quantity_max: int | None = None
    displayed_owned: int | None = None
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        owned_match = _OWNED_PATTERN.fullmatch(text)
        if owned_match is not None:
            if not clipped:
                displayed_owned = parse_grouped_integer(owned_match.group(1))
            continue
        range_match = _REWARD_RANGE_PATTERN.fullmatch(text)
        if range_match is not None:
            range_text = text
            quantity_min = parse_grouped_integer(range_match.group(1))
            quantity_max = parse_grouped_integer(range_match.group(2))
            continue
        single_match = _REWARD_SINGLE_PATTERN.fullmatch(text)
        if single_match is not None:
            range_text = text
            quantity_min = quantity_max = parse_grouped_integer(single_match.group(1))
            continue
        if line.bounds.x - row_bounds.x >= _name_min_x_native(name_min_x, row_bounds, region):
            name_parts.append(text)
    name_text = " ".join(name_parts) or None
    return DetectedListEntry(
        kind=ListEntryKind.BAG_PREVIEW_REWARD,
        bounds=row_bounds,
        title_text=name_text,
        subtitle_text=range_text,
        row_status=(
            RowRecognitionStatus.CLIPPED
            if clipped
            else RowRecognitionStatus.NO_ACTION
            if name_text is not None
            else RowRecognitionStatus.UNREADABLE
        ),
        bag_reward_facts=BagPreviewRewardFacts(
            reward_name_text=name_text,
            range_text=range_text,
            quantity_min=quantity_min,
            quantity_max=quantity_max,
            displayed_owned_count=displayed_owned,
        ),
    )


def _name_min_x_native(name_min_x: int, row_bounds: Bounds, region: Bounds) -> int:
    if region.width <= 0:
        return 0
    return round(name_min_x * row_bounds.width / region.width)
