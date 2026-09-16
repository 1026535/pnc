"""Canonical Trial Challenge card and Applicable Stats content producer.

Under the independently proved ``trial_challenge_live`` layout the six fixed
card slots are reference layout regions only — each card's identity comes from
its own bounded title read, never from slot order. Field facts are independent
measurements: a countdown can coexist with a castle lock, a reward chest never
implies completion, and a weekday is observed text rather than an availability
decision. Only the measured Gear Stats chip is actionable; every other control
stays observation-only.

Glyph references (``.local-data/devin-v15/patches`` provenance):
``trial_lock_glyph``/``trial_reward_chest`` from lead-qualified card captures,
``trial_stats_chip`` from the 2026-09-16 mega_old_acc Stats qualification
source, and ``trial_button_chip`` from the same live source's Gear Trial chip.
Match margins: lock >= .93 vs <= .735, clock slot corroborates countdown OCR,
chest .645-1.0 vs <= .41, Stats chip >= .89 vs <= .77, Trial chip >= .988 vs
<= .435 across reference, completed, and independent live captures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.domain.trial_challenge import (
    TrialApplicableStat,
    TrialApplicableStatsDetail,
    TrialCardFacts,
    TrialCategory,
    TrialChallengeSummary,
    trial_category_for_label,
    trial_category_metadata,
    trial_category_title,
)
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
)
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

TRIAL_CHALLENGE_LAYOUT_ID = "trial_challenge_live"
TRIAL_STATS_LAYOUT_ID = "trial_applicable_stats"

_REFERENCE_SIZE = (900, 1600)

# Fixed card slots measured on the proved layout (plain interior borders; a
# glowing selection border can surround them). Slot order never assigns
# category identity — each title is read inside its own card.
_CARD_SLOTS = tuple(
    Bounds(x=23, y=top, width=852, height=206)
    for top in (261, 486, 711, 936, 1161, 1388)
)

# Bounded OCR/read regions inside one card slot, in reference coordinates.
_CARD_TEXT_REGION = Bounds(x=230, y=2, width=640, height=202)

# Matcher search regions for each measured glyph, card-relative in reference
# coordinates. A glyph match is evidence, never an action or state derivation.
_CHEST_SEARCH = Bounds(x=640, y=0, width=210, height=165)
_LOCK_SEARCH = Bounds(x=660, y=15, width=215, height=110)
_STATS_CHIP_SEARCH = Bounds(x=320, y=90, width=180, height=115)
_TRIAL_CHIP_SEARCH = Bounds(x=643, y=95, width=230, height=110)

_CHEST_THRESHOLD = 0.60
_LOCK_THRESHOLD = 0.90
_STATS_CHIP_THRESHOLD = 0.85
_TRIAL_CHIP_THRESHOLD = 0.70

_DATA_DIR = Path(__file__).resolve().parent / "data" / "screen_anchors"
_LOCK_TEMPLATE = _DATA_DIR / "trial_lock_glyph.png"
_CHEST_TEMPLATE = _DATA_DIR / "trial_reward_chest.png"
_STATS_CHIP_TEMPLATE = _DATA_DIR / "trial_stats_chip.png"
_TRIAL_CHIP_TEMPLATE = _DATA_DIR / "trial_button_chip.png"

# Toolbar wing counter beside Exchange, in reference coordinates.
_COUNTER_REGION = Bounds(x=55, y=140, width=150, height=60)

# Applicable Stats table and explanatory footer, in reference coordinates.
_STATS_TABLE_REGION = Bounds(x=100, y=130, width=700, height=570)
_STATS_FOOTER_REGION = Bounds(x=20, y=1440, width=860, height=150)
_STATS_LABEL_MAX_X = 500
_STATS_ROW_MAX_GAP = 30

_PROGRESS_SEARCH = re.compile(r"(\d+)\s*/\s*(\d+)")
_REQUIRED_LEVEL_SEARCH = re.compile(r"REQUIRESLV(\d+)CASTLE")
_COUNTDOWN_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_COUNTER_PATTERN = re.compile(r"^\d+$")
_PERCENT_SEARCH = re.compile(r"(\d+)\s*%|%\s*(\d+)")
_FOOTER_CATEGORY_SEARCH = re.compile(r"IN([A-Z]+)TRIALONLY")
_WEEKDAY_TOKENS = frozenset({"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"})


@dataclass(frozen=True, slots=True)
class TrialContentProducer:
    """Produce typed Trial Challenge rows and Applicable Stats detail facts."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)

    def additions_for_screen(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions | None:
        """Dispatch Trial screen content under its proved visual layout only."""

        if screen_type == ScreenType.PNC_TRIAL_CHALLENGE and layout_id == TRIAL_CHALLENGE_LAYOUT_ID:
            return self.challenge_additions(image=image, ocr_context=ocr_context)
        if screen_type == ScreenType.PNC_TRIAL_APPLICABLE_STATS and layout_id == TRIAL_STATS_LAYOUT_ID:
            return self.stats_detail_additions(image=image, ocr_context=ocr_context)
        return None

    def challenge_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish one measured row per fixed card slot plus the toolbar summary."""

        prepared = self.matcher.prepare_frame(image, reference_size=_REFERENCE_SIZE)
        if prepared is None:
            return ObservationAdditions()
        entries = tuple(
            self._card_entry(
                image=image,
                prepared=prepared,
                slot=slot,
                slot_index=slot_index,
                ocr_context=ocr_context,
            )
            for slot_index, slot in enumerate(_CARD_SLOTS)
        )
        return ObservationAdditions(
            list_entries=_mark_duplicate_categories(entries),
            trial_summary=self._summary(image=image, ocr_context=ocr_context),
        )

    def stats_detail_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish the measured Applicable Stats rows and footer category."""

        table_lines = ocr_context.read_lines(
            image,
            _scaled_region(_STATS_TABLE_REGION, image),
            purpose=OcrReadPurpose.CONTENT,
            detail="trial_stats_rows",
            required_fact="trial_stats_rows",
        )
        stats = _parse_stat_rows(
            table_lines,
            reference_scale_x=image.width / _REFERENCE_SIZE[0],
            reference_scale_y=image.height / _REFERENCE_SIZE[1],
        )
        footer_lines = ocr_context.read_lines(
            image,
            _scaled_region(_STATS_FOOTER_REGION, image),
            purpose=OcrReadPurpose.CONTENT,
            detail="trial_stats_footer",
            required_fact="trial_stats_footer",
        )
        footer_text = " ".join(line.text.strip() for line in footer_lines if line.text.strip()) or None
        category = _footer_category(footer_lines)
        return ObservationAdditions(
            trial_stats_detail=TrialApplicableStatsDetail(
                category=category,
                stats=stats,
                footer_text=footer_text,
            )
        )

    def _card_entry(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        slot: Bounds,
        slot_index: int,
        ocr_context: ObservationOcrContext,
    ) -> DetectedListEntry:
        """Measure one fixed card slot into a typed row with explicit unknowns."""

        slot_bounds = _scaled_region(slot, image)
        if not Bounds(0, 0, image.width, image.height).contains_bounds(slot_bounds):
            return DetectedListEntry(
                kind=ListEntryKind.TRIAL_CATEGORY,
                bounds=slot_bounds,
                row_status=RowRecognitionStatus.CLIPPED,
            )
        lines = ocr_context.read_lines(
            image,
            _scaled_region(_offset_region(_CARD_TEXT_REGION, slot), image),
            purpose=OcrReadPurpose.CONTENT,
            detail=f"trial_card_slot_{slot_index}",
            required_fact="trial_card_fields",
        )
        scale_x = image.width / _REFERENCE_SIZE[0]
        scale_y = image.height / _REFERENCE_SIZE[1]
        card_lines = [
            _CardLine(
                line=line,
                rel_x=(line.bounds.x - slot_bounds.x) / scale_x,
                rel_y=(line.bounds.y - slot_bounds.y) / scale_y,
            )
            for line in lines
        ]
        category, title_text = _resolve_title(card_lines)
        progress_current, progress_required = _progress_values(card_lines)
        stats_match = self._glyph_match(
            prepared, _STATS_CHIP_TEMPLATE, _offset_region(_STATS_CHIP_SEARCH, slot), _STATS_CHIP_THRESHOLD
        )
        facts = TrialCardFacts(
            category=category,
            progress_current=progress_current,
            progress_required=progress_required,
            required_castle_level=_required_castle_level(card_lines),
            countdown_text=_countdown_text(card_lines),
            weekday_text=_weekday_text(card_lines),
            locked=self._glyph_present(
                prepared, _LOCK_TEMPLATE, _offset_region(_LOCK_SEARCH, slot), _LOCK_THRESHOLD
            ),
            reward_chest_present=self._glyph_present(
                prepared, _CHEST_TEMPLATE, _offset_region(_CHEST_SEARCH, slot), _CHEST_THRESHOLD
            ),
            trial_button_present=self._glyph_present(
                prepared, _TRIAL_CHIP_TEMPLATE, _offset_region(_TRIAL_CHIP_SEARCH, slot), _TRIAL_CHIP_THRESHOLD
            ),
            stats_button_present=stats_match is not None,
        )
        if category is None:
            row_status = RowRecognitionStatus.UNREADABLE
        elif category == TrialCategory.GEAR and stats_match is not None:
            row_status = RowRecognitionStatus.COMPLETE
        else:
            row_status = RowRecognitionStatus.NO_ACTION
        actionable = row_status == RowRecognitionStatus.COMPLETE
        return DetectedListEntry(
            kind=ListEntryKind.TRIAL_CATEGORY,
            bounds=slot_bounds,
            title_text=title_text,
            timer_text=facts.countdown_text,
            metadata=trial_category_metadata(facts),
            row_status=row_status,
            action_bounds=stats_match.bounds if actionable else None,
            action_point=stats_match.bounds.center() if actionable else None,
            trial_card_facts=facts,
        )

    def _summary(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
    ) -> TrialChallengeSummary | None:
        """Read the toolbar wing counter once at screen level."""

        lines = ocr_context.read_lines(
            image,
            _scaled_region(_COUNTER_REGION, image),
            purpose=OcrReadPurpose.CONTENT,
            detail="trial_screen_counter",
            required_fact="trial_screen_counter",
        )
        for line in lines:
            if _COUNTER_PATTERN.match(normalize_ocr_text(line.text)):
                return TrialChallengeSummary(
                    observed_counter=int(normalize_ocr_text(line.text)),
                    counter_bounds=line.bounds,
                )
        return None

    def _glyph_present(
        self,
        prepared: PreparedFrame,
        template: Path,
        search_region: Bounds,
        threshold: float,
    ) -> bool:
        """Return whether one measured glyph appears in its card slot region."""

        return self._glyph_match(prepared, template, search_region, threshold) is not None

    def _glyph_match(
        self,
        prepared: PreparedFrame,
        template: Path,
        search_region: Bounds,
        threshold: float,
    ) -> TemplateMatch | None:
        """Return the bounded template hit inside one reference-coordinate slot."""

        return self.matcher.find_best_match(
            prepared,
            template,
            threshold=threshold,
            search_region=search_region,
        )


@dataclass(frozen=True, slots=True)
class _CardLine:
    """One OCR line positioned relative to its owning card slot."""

    line: OcrLine
    rel_x: int
    rel_y: int


def _offset_region(region: Bounds, slot: Bounds) -> Bounds:
    """Translate one card-relative reference region into its slot, clamped to the frame."""

    right = min(slot.x + region.x + region.width, _REFERENCE_SIZE[0])
    bottom = min(slot.y + region.y + region.height, _REFERENCE_SIZE[1])
    return Bounds(
        x=slot.x + region.x,
        y=slot.y + region.y,
        width=max(1, right - slot.x - region.x),
        height=max(1, bottom - slot.y - region.y),
    )


def _scaled_region(region: Bounds, image: Image.Image) -> Bounds:
    """Project reference-coordinate bounds into the current image space."""

    scale_x = image.width / _REFERENCE_SIZE[0]
    scale_y = image.height / _REFERENCE_SIZE[1]
    left = round(region.x * scale_x)
    top = round(region.y * scale_y)
    right = min(round((region.x + region.width) * scale_x), image.width)
    bottom = min(round((region.y + region.height) * scale_y), image.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _resolve_title(card_lines: list[_CardLine]) -> tuple[TrialCategory | None, str | None]:
    """Resolve card identity only from a bounded title-zone OCR line."""

    title_lines = [
        card_line
        for card_line in card_lines
        if 5 <= card_line.rel_y <= 70 and 200 <= card_line.rel_x <= 500
    ]
    for card_line in title_lines:
        category = trial_category_for_label(card_line.line.text)
        if category is not None:
            return category, trial_category_title(category)
    if title_lines:
        return None, title_lines[0].line.text.strip() or None
    return None, None


def _progress_values(card_lines: list[_CardLine]) -> tuple[int | None, int | None]:
    """Read the displayed progress fraction wherever the card shows it."""

    for card_line in card_lines:
        if "PROGRESS" not in normalize_ocr_text(card_line.line.text):
            continue
        match = _PROGRESS_SEARCH.search(card_line.line.text)
        if match is not None:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _required_castle_level(card_lines: list[_CardLine]) -> int | None:
    """Read the displayed castle-level requirement when the card shows one."""

    for card_line in card_lines:
        match = _REQUIRED_LEVEL_SEARCH.search(normalize_ocr_text(card_line.line.text))
        if match is not None:
            return int(match.group(1))
    return None


def _countdown_text(card_lines: list[_CardLine]) -> str | None:
    """Read the literal countdown text from the card's top-right schedule slot."""

    for card_line in card_lines:
        if card_line.rel_x < 560 or card_line.rel_y > 60:
            continue
        if _COUNTDOWN_PATTERN.match(card_line.line.text.strip()):
            return card_line.line.text.strip()
    return None


def _weekday_text(card_lines: list[_CardLine]) -> str | None:
    """Read a displayed weekday token from the schedule slot, else unknown."""

    for card_line in card_lines:
        if card_line.rel_x < 560 or card_line.rel_y > 60:
            continue
        text = card_line.line.text.strip()
        if normalize_ocr_text(text) in _WEEKDAY_TOKENS:
            return text
    return None


def _footer_category(footer_lines: tuple[OcrLine, ...]) -> TrialCategory | None:
    """Parse the category only from the bounded explanatory footer text."""

    normalized = normalize_ocr_text(" ".join(line.text for line in footer_lines))
    match = _FOOTER_CATEGORY_SEARCH.search(normalized)
    if match is None:
        return None
    return trial_category_for_label(f"{match.group(1)} Trial")


def _parse_stat_rows(
    table_lines: tuple[OcrLine, ...],
    *,
    reference_scale_x: float,
    reference_scale_y: float,
) -> tuple[TrialApplicableStat, ...]:
    """Pair each bounded label line with the percentage measured on its row.

    Line bounds are native image coordinates; the label/value split compares
    against a reference-space column boundary, so x positions are normalized.
    """

    labels = [line for line in table_lines if line.bounds.x / reference_scale_x < _STATS_LABEL_MAX_X]
    values = [line for line in table_lines if line.bounds.x / reference_scale_x >= _STATS_LABEL_MAX_X]
    stats: list[TrialApplicableStat] = []
    used: set[int] = set()
    for label in sorted(labels, key=lambda line: line.bounds.y):
        label_center = label.bounds.y + label.bounds.height // 2
        best_index: int | None = None
        for index, value in enumerate(values):
            if index in used:
                continue
            value_center = value.bounds.y + value.bounds.height // 2
            if abs(value_center - label_center) / reference_scale_y > _STATS_ROW_MAX_GAP:
                continue
            if best_index is None or value.bounds.x < values[best_index].bounds.x:
                best_index = index
        if best_index is None:
            continue
        used.add(best_index)
        value = values[best_index]
        stats.append(
            TrialApplicableStat(
                label_text=label.text.strip(),
                percent_text=value.text.strip(),
                percent_value=_percent_value(value.text),
                bounds=_union_bounds(label.bounds, value.bounds),
            )
        )
    return tuple(stats)


def _percent_value(text: str) -> int | None:
    """Parse one literal percent token, tolerating a misread leading sign."""

    match = _PERCENT_SEARCH.search(text)
    if match is None:
        return None
    return int(next(group for group in match.groups() if group is not None))


def _union_bounds(first: Bounds, second: Bounds) -> Bounds:
    """Return the smallest rectangle covering both measured line bounds."""

    left = min(first.x, second.x)
    top = min(first.y, second.y)
    right = max(first.x + first.width, second.x + second.width)
    bottom = max(first.y + first.height, second.y + second.height)
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)


def _mark_duplicate_categories(
    entries: tuple[DetectedListEntry, ...],
) -> tuple[DetectedListEntry, ...]:
    """Mark rows ambiguous when two slots resolve to the same category."""

    duplicates = {
        category
        for entry in entries
        if (category := (entry.trial_card_facts.category if entry.trial_card_facts else None)) is not None
        and sum(
            other.trial_card_facts is not None and other.trial_card_facts.category == category
            for other in entries
        ) > 1
    }
    if not duplicates:
        return entries
    return tuple(
        replace(
            entry,
            action_point=None,
            action_bounds=None,
            row_status=RowRecognitionStatus.AMBIGUOUS,
        )
        if entry.trial_card_facts is not None and entry.trial_card_facts.category in duplicates
        else entry
        for entry in entries
    )
