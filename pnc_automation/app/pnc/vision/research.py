"""Research tree, node-detail, and queue content producer.

This module owns the Research semantic extraction that used to live inside
``pnc_observation_enricher``. It is invoked only under an independently
accepted screen identity: the visual profiles prove ``PNC_RESEARCH_TREE`` /
``PNC_RESEARCH_QUEUE`` and their layouts before any OCR fact is parsed, so
content here can describe nodes but can never establish or override identity.

Tree discovery is geometry-first: bounded blue-label connected components are
measured directly (lead-qualified morphology over the reviewed captures), then
each measured label and its icon-level region receive bounded OCR reads through
the shared ``ObservationOcrContext``. A row is actionable only when the full
icon+label tile lies inside the measured scroll viewport; boundary fragments
stay CLIPPED, complete tiles with unknown or partial text stay UNREADABLE, and
nothing is inferred from OCR text alone.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory, ResourceType
from pnc_automation.app.pnc.domain.research import (
    RESEARCH_CATEGORY_DEFINITIONS,
    ResearchDetail,
    ResearchNodeFacts,
    ResearchNodeId,
    ResearchQueueRow,
    ResearchQueueState,
    ResearchTextRecord,
    research_entry_category_metadata,
    research_category_for_layout,
    research_node_for_label,
    research_node_for_title,
    research_node_title,
)
from pnc_automation.app.pnc.domain.resource_cost import ResourceCost
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame


_RESEARCH_DETAIL_LAYOUT_ID = "research_tree_node_detail"
_RESEARCH_MAX_DETAIL_LAYOUT_ID = "research_tree_node_detail_max"

# Label tiles are blue rectangles; the same predicate proved the measured
# component bounds on all four Development captures at both supported sizes.
_LABEL_BLUE_MIN_BLUE = 70
_LABEL_BLUE_MIN_RED_DELTA = 25
_LABEL_BLUE_MIN_GREEN_DELTA = 15
# The fixed tree header occupies the top of the frame; node tiles scroll
# beneath it. Components above this band are chrome, not scroll content.
_HEADER_HEIGHT_RATIO = 0.065
# Reviewed full label height at both supported viewports (~55px at 900x1600,
# ~33px at 540x960). A materially shorter component is a boundary fragment.
_EXPECTED_LABEL_HEIGHT_RATIO = 55 / 1600
_PARTIAL_LABEL_HEIGHT_RATIO = 0.75
# Measured icon geometry relative to the real ~179px label: width 0.82,
# height 0.80, vertical gap 0.15 of the label width.
_ICON_WIDTH_RATIO = 0.82
_ICON_HEIGHT_RATIO = 0.80
_ICON_GAP_RATIO = 0.15
# The n/m counter sits at the icon's top-left inside its blue frame.
_LEVEL_REGION_WIDTH_RATIO = 0.62
_LEVEL_REGION_HEIGHT_RATIO = 0.30
_LEVEL_PATTERN = re.compile(r"^(\d+)\s*/\s*(\d+)$")

# The icon carries a blue square frame; a component that claims to be a node
# must show that frame (or, when locked, the padlock glyph) inside its
# measured icon region. Real tiles measure ~0.26-0.37 border blue; an empty
# or header-covered region falls near zero and is also rejected by viewport
# containment.
_ICON_FRAME_BORDER_RATIO = 0.07
_ICON_FRAME_MIN_BLUE_FRACTION = 0.20

_RESEARCH_CATEGORY_BY_HEADER = {
    normalize_ocr_text(item.title): item.category
    for item in RESEARCH_CATEGORY_DEFINITIONS
}
# The "Master Researcher" badge is achievement chrome next to the header, not
# a node tile; never publish it as a row even if a stray component matches.
_DECORATION_LABEL_PREFIXES = ("MASTERRESEARCHER",)

_DETAIL_TITLE_PATTERN = re.compile(r"^(?P<title>.+?)\s*\((?P<cur>\d+)\s*/\s*(?P<max>\d+)\s*\)\s*$")
_DETAIL_TIME_PATTERN = re.compile(r"^\d{1,3}:\d{2}:\d{2}$")
_DETAIL_COST_PATTERN = re.compile(r"^(\d{1,3}(?:,\d{3})*|\d+)\s*/\s*(\d{1,3}(?:,\d{3})*|\d+)$")
_DETAIL_GEM_COST_PATTERN = re.compile(r"^\d{1,4}$")

_QUEUE_ROW_TITLE_PATTERN = re.compile(r"^\d+(?:ST|ND|RD|TH)RESEARCHQUEUE$")
_QUEUE_TIMER_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_QUEUE_TIMER_SEARCH = re.compile(r"\d{1,2}:\d{2}:\d{2}")

_DATA_DIR = Path(__file__).resolve().parent / "data" / "screen_anchors"
# Glyph references qualified on the reviewed captures (provenance recorded in
# .local-data/devin-v04/): the locked-node padlock from the 2026-09-15 tour
# scroll capture and the food/wood cost icons from research_node_detail.png.
_PADLOCK_TEMPLATE = _DATA_DIR / "research_node_padlock.png"
_COST_ICON_TEMPLATES = (
    (ResourceType.FOOD, _DATA_DIR / "research_cost_food.png"),
    (ResourceType.WOOD, _DATA_DIR / "research_cost_wood.png"),
)
_GLYPH_REFERENCE_SIZE = (540, 960)
_GLYPH_MATCH_THRESHOLD = 0.82

# The gold Research Now button region inside the detail panel; premium
# geometry is read-only typed evidence, never a mutation entry point.
_PREMIUM_SEARCH_REGION_RATIO = (0.10, 0.43, 0.48, 0.12)
_PREMIUM_GOLD_MIN_RED = 130
_PREMIUM_GOLD_MIN_GREEN = 90
_PREMIUM_GOLD_RED_DELTA = 40
_PREMIUM_GOLD_GREEN_DELTA = 20
_PREMIUM_BUTTON_MIN_AREA_RATIO = 0.003
_COST_ICON_SLOT_RATIO = (0.10, 0.13)


@dataclass(frozen=True, slots=True)
class _NodeCandidate:
    """One measured label component and its resolved node identity."""

    label_bounds: Bounds
    raw_text: str
    node_id: ResearchNodeId | None
    title_text: str | None
    clipped: bool


@dataclass(frozen=True, slots=True)
class ResearchContentProducer:
    """Produce typed research rows, detail facts, and queue facts under proof."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)

    def additions_for_tree(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions:
        """Parse the accepted research-tree layout into typed screen facts.

        ``layout_id`` is supplied by the independent visual decision: the
        category grids publish row entries, the shared node-detail layout
        publishes detail facts, and anything else stays empty.
        """

        if layout_id in {_RESEARCH_DETAIL_LAYOUT_ID, _RESEARCH_MAX_DETAIL_LAYOUT_ID}:
            return self.detail_additions(
                image=image, lines=lines, ocr_context=ocr_context,
                max_level_panel=layout_id == _RESEARCH_MAX_DETAIL_LAYOUT_ID,
            )
        category = research_category_for_layout(layout_id)
        if category is not None:
            return self.tree_additions(
                image=image, lines=lines, ocr_context=ocr_context, category=category,
            )
        return ObservationAdditions()

    def tree_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        category: ResearchCategory | None = None,
    ) -> ObservationAdditions:
        """Publish measured tree rows under the independently proved category."""

        header_category = _header_category(lines, image=image)
        if category is None:
            category = header_category
        elif header_category is not None and header_category != category:
            return ObservationAdditions()
        rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
        prepared = self.matcher.prepare_frame(image, reference_size=_GLYPH_REFERENCE_SIZE)
        candidates = tuple(
            candidate
            for component in _discover_label_components(rgb)
            if (candidate := self._node_candidate(
                image=image,
                component=component,
                ocr_context=ocr_context,
                category=category,
            ))
            is not None
        )
        entries = tuple(
            self._node_entry(
                image=image,
                rgb=rgb,
                prepared=prepared,
                candidate=candidate,
                category=category,
                ocr_context=ocr_context,
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

    def _node_candidate(
        self,
        *,
        image: Image.Image,
        component: Bounds,
        ocr_context: ObservationOcrContext,
        category: ResearchCategory | None,
    ) -> _NodeCandidate | None:
        """Resolve one measured label component to a node candidate or drop chrome."""

        label_lines = ocr_context.read_lines(
            image,
            _inset_bounds(component, padding=2, image=image),
            purpose=OcrReadPurpose.CONTENT,
            detail="research_node_label",
            required_fact="research_node_label",
        )
        raw_text = _join_label_text(label_lines)
        normalized = normalize_ocr_text(raw_text)
        if any(normalized.startswith(prefix) for prefix in _DECORATION_LABEL_PREFIXES):
            return None
        node_id = research_node_for_label(raw_text, category=category)
        clipped = _component_is_partial(component, image=image)
        if node_id is None and not clipped:
            # Native Economy borders caused rotated/fragmented OCR on Wood/Iron
            # Output. A bounded 2x text crop restores the observed label words.
            label_result = ocr_context.read_preprocessed_result(
                image, _inset_bounds(component, padding=6, image=image),
                preprocessing_id="research_node_label_rgb_2x",
                prepare=_prepare_research_text_2x,
                purpose=OcrReadPurpose.CONTENT, detail="research_node_label_inset",
                required_fact="research_node_label",
            )
            label_lines = () if label_result is None else label_result.lines
            raw_text = _join_label_text(label_lines) or raw_text
            node_id = research_node_for_label(raw_text, category=category)
        return _NodeCandidate(
            label_bounds=component,
            raw_text=raw_text,
            node_id=node_id,
            title_text=(
                research_node_title(node_id)
                if node_id is not None
                else (raw_text or None)
            ),
            clipped=clipped,
        )

    def _node_entry(
        self,
        *,
        image: Image.Image,
        rgb: np.ndarray,
        prepared: PreparedFrame | None,
        candidate: _NodeCandidate,
        category: ResearchCategory | None,
        ocr_context: ObservationOcrContext,
    ) -> DetectedListEntry:
        """Build one honest research row from its measured tile and bounded reads."""

        facts = ResearchNodeFacts(category=category, node_id=candidate.node_id)
        metadata: dict[str, object] = dict(research_entry_category_metadata(facts))
        icon_bounds = _derive_icon_bounds(candidate.label_bounds)
        viewport = _scroll_viewport(image)
        if (
            candidate.clipped
            or not viewport.contains_bounds(icon_bounds)
            or not viewport.contains_bounds(candidate.label_bounds)
        ):
            metadata["unresolved_reason"] = (
                "clipped_or_partial_node_label"
                if candidate.clipped
                else "incomplete_node_tile_geometry"
            )
            return DetectedListEntry(
                kind=ListEntryKind.RESEARCH,
                bounds=(
                    candidate.label_bounds
                    if candidate.clipped
                    else _union_bounds(candidate.label_bounds, _clip_bounds(icon_bounds, viewport))
                ),
                title_text=candidate.title_text,
                row_status=RowRecognitionStatus.CLIPPED,
                metadata=metadata,
                research_facts=facts,
            )
        if not _icon_has_visible_frame(rgb=rgb, icon_bounds=icon_bounds):
            # The full tile sits inside the viewport but its icon frame is
            # unproved: that is an unreadable tile, not an edge clip.
            metadata["unresolved_reason"] = "unproved_node_icon_geometry"
            return DetectedListEntry(
                kind=ListEntryKind.RESEARCH,
                bounds=_union_bounds(icon_bounds, candidate.label_bounds),
                title_text=candidate.title_text,
                row_status=RowRecognitionStatus.UNREADABLE,
                metadata=metadata,
                research_facts=facts,
            )
        levels = self._read_node_level(image=image, icon_bounds=icon_bounds, ocr_context=ocr_context)
        locked = self._detect_node_lock(image=image, prepared=prepared, icon_bounds=icon_bounds)
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
                bounds=_union_bounds(icon_bounds, candidate.label_bounds),
                title_text=candidate.title_text,
                row_status=RowRecognitionStatus.UNREADABLE,
                metadata=metadata,
                research_facts=facts,
            )
        return DetectedListEntry(
            kind=ListEntryKind.RESEARCH,
            bounds=_union_bounds(icon_bounds, candidate.label_bounds),
            title_text=candidate.title_text,
            action_point=icon_bounds.center(),
            action_bounds=icon_bounds,
            row_status=RowRecognitionStatus.COMPLETE,
            metadata=metadata,
            research_facts=facts,
        )

    def _read_node_level(
        self,
        *,
        image: Image.Image,
        icon_bounds: Bounds,
        ocr_context: ObservationOcrContext,
    ) -> tuple[int | None, int | None, bool] | None:
        """Read one coherent n/m or MAX badge without inventing a numeric cap."""

        level_region = _clip_bounds(
            Bounds(
                icon_bounds.x,
                icon_bounds.y,
                max(1, round(icon_bounds.width * _LEVEL_REGION_WIDTH_RATIO)),
                max(1, round(icon_bounds.height * _LEVEL_REGION_HEIGHT_RATIO)),
            ),
            Bounds(0, 0, image.width, image.height),
        )
        readings: set[tuple[int | None, int | None, bool]] = set()
        for line in ocr_context.read_lines(
            image,
            level_region,
            purpose=OcrReadPurpose.CONTENT,
            detail="research_node_level",
            required_fact="research_node_level",
        ):
            match = _LEVEL_PATTERN.match(line.text.strip())
            if match is not None:
                current, maximum = int(match.group(1)), int(match.group(2))
                if current <= maximum:
                    readings.add((current, maximum, current == maximum))
            elif normalize_ocr_text(line.text) == "MAX":
                readings.add((None, None, True))
        return next(iter(readings)) if len(readings) == 1 else None

    def _detect_node_lock(
        self, *, image: Image.Image, prepared: PreparedFrame | None, icon_bounds: Bounds,
    ) -> bool | None:
        """Qualify a padlock glyph inside the icon; never infer lock from level."""

        if prepared is None or not _PADLOCK_TEMPLATE.exists():
            return None
        search = _project_bounds_to_reference(
            _inset_bounds(icon_bounds, padding=-max(2, round(icon_bounds.width * 0.08)), image=image),
            original_size=image.size,
            reference_size=_GLYPH_REFERENCE_SIZE,
        )
        return (
            self.matcher.find_best_match(
                prepared,
                _PADLOCK_TEMPLATE,
                threshold=_GLYPH_MATCH_THRESHOLD,
                search_region=search,
            )
            is not None
        )

    def detail_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
        max_level_panel: bool = False,
    ) -> ObservationAdditions:
        """Parse the accepted node-detail panel into read-only typed facts."""

        title_text: str | None = None
        current_level: int | None = None
        max_level: int | None = None
        title_line = next(
            (line for line in lines if _DETAIL_TITLE_PATTERN.match(line.text.strip()) is not None),
            None,
        )
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
            # The small chart icon was read as an "il" prefix on real Economy
            # and Military headers. Re-read only the measured header text band.
            left = max(title_line.bounds.x, round(image.width * 0.10))
            right = title_line.bounds.x + title_line.bounds.width + 6
            title_region = _clip_bounds(
                Bounds(left, max(0, title_line.bounds.y - 6), max(1, right - left),
                       max(round(image.height * 0.04), title_line.bounds.height + 12)),
                Bounds(0, 0, image.width, image.height),
            )
            title_result = ocr_context.read_preprocessed_result(
                image, title_region, preprocessing_id="research_title_rgb_2x",
                prepare=_prepare_research_text_2x, purpose=OcrReadPurpose.CONTENT,
                detail="research_detail_title", required_fact="research_detail_title",
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
            # This independently proved layout has only a title and effects.
            # Its gold Max banner is not a premium action or queue evidence.
            return ObservationAdditions(
                research_detail=ResearchDetail(
                    title_text=title_text, node_id=node_id,
                    current_level=current_level, max_level=max_level,
                    effect_records=effect_records,
                    queue_state=ResearchQueueState.UNKNOWN,
                ),
            )
        prepared = self.matcher.prepare_frame(image, reference_size=_GLYPH_REFERENCE_SIZE)
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
                    resource_type=self._match_cost_resource(image=image, prepared=prepared, line=line),
                    available=int(match.group(1).replace(",", "")),
                    required=int(match.group(2).replace(",", "")),
                    text_bounds=line.bounds,
                ),
            )
        )
        original_label = next((line for line in lines if normalize_ocr_text(line.text) == "ORIGINALTIME"), None)
        actual_label = next((line for line in lines if normalize_ocr_text(line.text) == "ACTUALTIME"), None)
        time_lines = [line for line in lines if _DETAIL_TIME_PATTERN.match(line.text.strip())]
        original_time = _time_below(original_label, time_lines)
        actual_time = _time_below(actual_label, time_lines)
        no_idle = next((line for line in lines if "NOIDLEQUEUE" in normalize_ocr_text(line.text)), None)
        queue_timer = _queue_timer_after(no_idle, time_lines) if no_idle is not None else None
        premium = self._measure_premium_button(image=image, lines=lines, ocr_context=ocr_context)
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

    def _match_cost_resource(
        self, *, image: Image.Image, prepared: PreparedFrame | None, line: OcrLine,
    ) -> ResourceType | None:
        """Match the small resource icon left of a cost row when visually supported."""

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
        search = _project_bounds_to_reference(
            _clip_bounds(slot, Bounds(0, 0, image.width, image.height)),
            original_size=image.size,
            reference_size=_GLYPH_REFERENCE_SIZE,
        )
        best: tuple[ResourceType, float] | None = None
        for resource_type, template in _COST_ICON_TEMPLATES:
            if not template.exists():
                continue
            match = self.matcher.find_best_match(
                prepared,
                template,
                threshold=_GLYPH_MATCH_THRESHOLD,
                search_region=search,
            )
            if match is not None and (best is None or match.confidence > best[1]):
                best = (resource_type, match.confidence)
        return None if best is None else best[0]

    def _measure_premium_button(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        ocr_context: ObservationOcrContext,
    ) -> tuple[Bounds, int | None] | None:
        """Measure the gold Research Now button and any visible gem count."""

        premium_text = next(
            (line for line in lines if "RESEARCHNOW" in normalize_ocr_text(line.text)),
            None,
        )
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
            (
                int(line.text.strip())
                for line in lines
                if _DETAIL_GEM_COST_PATTERN.match(line.text.strip()) is not None
                and button.contains_bounds(line.bounds)
            ),
            None,
        )
        if gem_cost is None:
            gem_cost = self._read_button_gem_cost(
                image=image, button=button, ocr_context=ocr_context
            )
        return button, gem_cost

    def _read_button_gem_cost(
        self,
        *,
        image: Image.Image,
        button: Bounds,
        ocr_context: ObservationOcrContext,
    ) -> int | None:
        """Read the small gem count printed inside the measured premium button."""

        for line in ocr_context.read_lines(
            image,
            _inset_bounds(button, padding=4, image=image),
            purpose=OcrReadPurpose.CONTENT,
            detail="research_premium_gem_cost",
            required_fact="research_premium_gem_cost",
        ):
            for token in re.findall(r"\d{1,4}", line.text):
                return int(token)
        return None

    def queue_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> ObservationAdditions:
        """Parse the accepted research-queue panel into explicit row states."""

        header = next(
            (
                line
                for line in lines
                if normalize_ocr_text(line.text) == "RESEARCHQUEUE"
            ),
            None,
        )
        rows: list[ResearchQueueRow] = []
        if header is not None:
            body = sorted(
                (line for line in lines if line.bounds.y > header.bounds.y),
                key=lambda line: (line.bounds.y, line.bounds.x),
            )
            title_lines = [
                line
                for line in body
                if _QUEUE_ROW_TITLE_PATTERN.match(normalize_ocr_text(line.text)) is not None
            ]
            for index, title_line in enumerate(title_lines):
                next_top = (
                    title_lines[index + 1].bounds.y
                    if index + 1 < len(title_lines)
                    else image.height
                )
                row_lines = tuple(
                    line for line in body if title_line.bounds.y <= line.bounds.y < next_top
                )
                rows.append(_queue_row(image=image, title_line=title_line, row_lines=row_lines))
        return ObservationAdditions(research_queue_rows=tuple(rows))


def _prepare_research_text_2x(image: Image.Image, region: Bounds) -> Image.Image:
    """Enlarge one bounded text region; the OCR context restores native bounds."""
    crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height))
    return crop.convert("RGB").resize((crop.width * 2, crop.height * 2), Image.Resampling.BICUBIC)


def _header_category(lines: tuple[OcrLine, ...], *, image: Image.Image) -> ResearchCategory | None:
    """Resolve the proved tree's category from its bounded header read."""

    header_bottom = image.height * (_HEADER_HEIGHT_RATIO + 0.02)
    for line in lines:
        if line.bounds.y > header_bottom:
            continue
        normalized = normalize_ocr_text(line.text)
        for text, category in _RESEARCH_CATEGORY_BY_HEADER.items():
            if normalized == text or normalized.endswith(text):
                return category
    return None


def _discover_label_components(array: np.ndarray) -> tuple[Bounds, ...]:
    """Measure blue node-label rectangles without consulting OCR text.

    Qualified on the four reviewed Development captures at both supported
    sizes: horizontal closing bridges glyph holes, opening removes thin
    branch/frame strokes, and size-qualified components keep only real label
    tiles, including honest boundary fragments. Accepts the caller's one
    int16 RGB frame array.
    """

    height, width = array.shape[:2]
    mask = (
        (array[:, :, 2] >= _LABEL_BLUE_MIN_BLUE)
        & (array[:, :, 2] >= array[:, :, 0] + _LABEL_BLUE_MIN_RED_DELTA)
        & (array[:, :, 2] >= array[:, :, 1] + _LABEL_BLUE_MIN_GREEN_DELTA)
    ).astype(np.uint8) * 255
    mask[: round(height * _HEADER_HEIGHT_RATIO)] = 0
    closed = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, np.ones((1, max(3, round(width * 0.025))), np.uint8)
    )
    opened = cv2.morphologyEx(
        closed,
        cv2.MORPH_OPEN,
        np.ones((max(3, round(height * 0.0075)), max(3, round(width * 0.08))), np.uint8),
    )
    _, _, stats, _ = cv2.connectedComponentsWithStats(opened)
    return tuple(
        Bounds(int(stat[0]), int(stat[1]), int(stat[2]), int(stat[3]))
        for stat in stats[1:]
        # Qualified labels span about 20% of the viewport at either size.
        # Narrower blue components belong to Military/Fortification icon art.
        if width * 0.19 <= stat[2] <= width * 0.27 and height * 0.008 <= stat[3] <= height * 0.07
    )


def _component_is_partial(component: Bounds, *, image: Image.Image) -> bool:
    """Keep honest boundary fragments clipped instead of repairing them."""

    expected_height = image.height * _EXPECTED_LABEL_HEIGHT_RATIO
    return (
        component.height < expected_height * _PARTIAL_LABEL_HEIGHT_RATIO
        or component.x <= 0
        or component.y <= 0
        or component.x + component.width >= image.width
        or component.y + component.height >= image.height
    )


def _scroll_viewport(image: Image.Image) -> Bounds:
    """Return the measured node scroll viewport below the fixed header."""

    top = round(image.height * _HEADER_HEIGHT_RATIO)
    return Bounds(0, top, image.width, image.height - top)


def _derive_icon_bounds(label_bounds: Bounds) -> Bounds:
    """Derive the selectable icon square above a measured label rectangle."""

    icon_width = max(1, round(label_bounds.width * _ICON_WIDTH_RATIO))
    icon_height = max(1, round(label_bounds.width * _ICON_HEIGHT_RATIO))
    gap = max(1, round(label_bounds.width * _ICON_GAP_RATIO))
    return Bounds(
        x=label_bounds.x + (label_bounds.width - icon_width) // 2,
        y=label_bounds.y - gap - icon_height,
        width=icon_width,
        height=icon_height,
    )


def _icon_has_visible_frame(*, rgb: np.ndarray, icon_bounds: Bounds) -> bool:
    """Confirm the derived icon region shows the blue square frame/body pixels."""

    array = rgb
    border = max(2, round(icon_bounds.width * _ICON_FRAME_BORDER_RATIO))
    x0, y0 = icon_bounds.x, icon_bounds.y
    x1, y1 = x0 + icon_bounds.width, y0 + icon_bounds.height
    strips = (
        array[y0:y0 + border, x0:x1],
        array[y1 - border:y1, x0:x1],
        array[y0:y1, x0:x0 + border],
        array[y0:y1, x1 - border:x1],
    )
    fractions = []
    for strip in strips:
        if strip.size == 0:
            continue
        blue = (
            (strip[:, :, 2] >= _LABEL_BLUE_MIN_BLUE)
            & (strip[:, :, 2] >= strip[:, :, 0] + _LABEL_BLUE_MIN_RED_DELTA)
            & (strip[:, :, 2] >= strip[:, :, 1] + _LABEL_BLUE_MIN_GREEN_DELTA)
        )
        fractions.append(float(blue.mean()))
    return bool(fractions) and sum(fractions) / len(fractions) >= _ICON_FRAME_MIN_BLUE_FRACTION


def _join_label_text(lines: tuple[OcrLine, ...]) -> str:
    """Join a tile's OCR lines, preferring the full label over one fragment."""

    if not lines:
        return ""
    ordered = sorted(lines, key=lambda line: (line.bounds.y, line.bounds.x))
    merged = ordered[0]
    for line in ordered[1:]:
        merged = merge_ocr_lines(merged, line)
    return merged.text


def _queue_row(
    *,
    image: Image.Image,
    title_line: OcrLine,
    row_lines: tuple[OcrLine, ...],
) -> ResearchQueueRow:
    """Build one measured queue row with explicit idle/active/unknown state."""

    top = max(0, title_line.bounds.y - 6)
    bottom = min(
        image.height,
        max(line.bounds.y + line.bounds.height for line in row_lines) + 8,
    )
    state = ResearchQueueState.UNKNOWN
    timer_text: str | None = None
    for line in row_lines:
        normalized = normalize_ocr_text(line.text)
        if normalized == "IDLE":
            state = ResearchQueueState.IDLE
        elif _QUEUE_TIMER_PATTERN.match(line.text.strip()) is not None:
            state = ResearchQueueState.ACTIVE
            timer_text = line.text.strip()
        elif normalized == "SPEEDUP":
            state = ResearchQueueState.ACTIVE
    return ResearchQueueRow(
        bounds=Bounds(0, top, image.width, max(1, bottom - top)),
        title_text=title_line.text.strip(),
        state=state,
        timer_text=timer_text,
    )


def _time_below(label: OcrLine | None, time_lines: list[OcrLine]) -> str | None:
    """Return the first measured time value under one label column."""

    if label is None:
        return None
    candidates = [
        line for line in time_lines
        if line.bounds.y >= label.bounds.y + label.bounds.height
        and abs(line.bounds.x - label.bounds.x) <= label.bounds.width
    ]
    candidates.sort(key=lambda line: (line.bounds.y, line.bounds.x))
    return candidates[0].text.strip() if candidates else None


def _queue_timer_after(anchor: OcrLine | None, time_lines: list[OcrLine]) -> str | None:
    """Return the timer shown with one queue-status anchor.

    Live OCR merges ``No idle queue 00:44:45`` into one line, so the anchor's
    own text is checked first before falling back to a nearby time line.
    """

    if anchor is None:
        return None
    embedded = _QUEUE_TIMER_SEARCH.search(anchor.text)
    if embedded is not None:
        return embedded.group(0)
    candidates = [
        line for line in time_lines if abs(line.bounds.y - anchor.bounds.y) <= anchor.bounds.height * 2
    ]
    candidates.sort(key=lambda line: (abs(line.bounds.y - anchor.bounds.y), line.bounds.x))
    return candidates[0].text.strip() if candidates else None


def _inset_bounds(bounds: Bounds, *, padding: int, image: Image.Image) -> Bounds:
    """Pad (or shrink, for negative padding) bounds inside the image."""

    return _clip_bounds(
        Bounds(
            bounds.x - padding,
            bounds.y - padding,
            bounds.width + 2 * padding,
            bounds.height + 2 * padding,
        ),
        Bounds(0, 0, image.width, image.height),
    )


def _clip_bounds(bounds: Bounds, viewport: Bounds) -> Bounds:
    """Clip bounds to a viewport rectangle."""

    left = max(bounds.x, viewport.x)
    top = max(bounds.y, viewport.y)
    right = min(bounds.x + bounds.width, viewport.x + viewport.width)
    bottom = min(bounds.y + bounds.height, viewport.y + viewport.height)
    return Bounds(left, top, max(1, right - left), max(1, bottom - top))


def _union_bounds(left: Bounds, right: Bounds) -> Bounds:
    """Return the smallest rectangle containing two bounds."""

    x0 = min(left.x, right.x)
    y0 = min(left.y, right.y)
    x1 = max(left.x + left.width, right.x + right.width)
    y1 = max(left.y + left.height, right.y + right.height)
    return Bounds(x0, y0, x1 - x0, y1 - y0)


def _project_bounds_to_reference(
    bounds: Bounds,
    *,
    original_size: tuple[int, int],
    reference_size: tuple[int, int],
) -> Bounds:
    """Project image-space bounds into a prepared frame's reference space."""

    if original_size == reference_size:
        return bounds
    scale_x = reference_size[0] / original_size[0]
    scale_y = reference_size[1] / original_size[1]
    return Bounds(
        round(bounds.x * scale_x),
        round(bounds.y * scale_y),
        max(1, round(bounds.width * scale_x)),
        max(1, round(bounds.height * scale_y)),
    )


__all__ = [
    "ResearchContentProducer",
    "ResearchDetail",
    "ResearchNodeFacts",
    "ResearchNodeId",
    "ResearchQueueRow",
    "ResearchQueueState",
]
