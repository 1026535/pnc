"""Canonical Bag Speedup/Treasure card and qualified chest-preview content producer.

Under the proved ``bag`` layout the shared card bands carry semantic rows only
when the Speedup or Treasure subtab is positively selected. Card identity is
read from each card's own bounded name/description, never from slot order or
artwork: similar art families (Demon chest levels, minute speedups) require the
displayed text to distinguish variants. The measured magnifier glyph in the
artwork's top-right corner is the only inspection affordance; Use/Use-in-bulk
controls are measured but never actionable here.

Qualified chest previews (``bag_arena_chest_preview`` and
``bag_common_victory_preview``) publish their reward rows as possible-result
ranges plus the preview's own displayed Owned label — never Bag inventory and
never a guarantee. The preview title independently resolves its source
TreasureIdentity so a wrong/mismatched popup cannot satisfy a requested source.

Glyph reference (``.local-data/devin-v10-v11`` provenance): ``bag_item_magnifier``
was authored on the 900x1600 Treasure fixture and measured .861-1.0 on magnifier
corners versus <=.53 on non-magnifier corners, speedup art, and unrelated
surfaces; the .85 floor applies only inside the card artwork corner region.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagChestPreviewFacts,
    BagItemApplicability,
    BagItemFacts,
    BagItemIdentity,
    BagPreviewRewardFacts,
    MilitaryItemIdentity,
    MilitaryKind,
    MiscItemIdentity,
    MiscKind,
    SpeedBonusIdentity,
    TimeReductionIdentity,
    TreasureIdentity,
    bag_chest_preview_layouts,
    bag_item_facts_metadata,
    bag_item_identity_key,
    bag_item_inspection_supported,
    treasure_identity_for_label,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.bag_layout import detect_bag_card_geometry
from pnc_automation.app.pnc.vision.numeric_parsing import parse_grouped_integer
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

BAG_LAYOUT_ID = "bag"
_REFERENCE_SIZE = (900, 1600)
_PREVIEW_REFERENCE_SIZE = (540, 960)

_DATA_DIR = Path(__file__).resolve().parent / "data" / "screen_anchors"
_MAGNIFIER_TEMPLATE = _DATA_DIR / "bag_item_magnifier.png"
_MAGNIFIER_THRESHOLD = 0.85
# Card-relative reference region around the artwork's top-right corner.
_MAGNIFIER_SEARCH = Bounds(x=130, y=-5, width=90, height=115)

# One bounded read covering name, description and Owned text, card-relative.
_CARD_TEXT_REGION = Bounds(x=28, y=5, width=597, height=195)
_TEXT_COLUMN_MIN_X = 190
_NAME_MAX_Y = 70
# Bounded retry window for the name column only; the wide card read can merge
# name glyphs with neighbouring pixels that the focused column read separates.
_CARD_NAME_REGION = Bounds(x=190, y=0, width=435, height=75)

_OWNED_PATTERN = re.compile(r"^[O0D]?wned\s*:\s*(.+)$", re.IGNORECASE)
_SPEED_BONUS_NAME_PATTERN = re.compile(r"^(\d+)(BUILD|RESEARCH|TRAINING|HEAL)SPEEDUP$")
_SPEED_BONUS_DESC_PATTERN = re.compile(r"(BUILD|RESEARCH|TRAINING|HEAL)SPEEDBY(\d+)FOR(\d+)HRS?")
_TIME_NAME_PATTERN = re.compile(r"^(\d+)(MIN|HRS?)(BUILD|RESEARCH|TRAINING|HEAL)?SPEEDUP$")
_TIME_DESC_PATTERN = re.compile(r"(BUILD|RESEARCH|TRAINING|HEAL)?(?:REMAINING)?TIMEBY(\d+)(MIN|HRS?)")

# Military names carry the timed duration (N-hr) or the boost percent; the
# bounded description confirms or supplies the remaining field.
# The accepted OCR backend systematically confuses O/0 in this font
# (``Tro0p``, ``B00st``); tolerate it only inside the evidenced words.
# The leading magnitude may drop entirely, in which case the bounded
# description must supply it.
_MILITARY_TIMED_NAME_PATTERN = re.compile(r"^(\d*)HR(ANTISC[O0]UT|SHIELDOFGRACE)$")
_MILITARY_BOOST_NAME_PATTERN = re.compile(r"^(\d*)TR[O0]{2}P(ATK|DEF|SIZE)B[O0]{2}ST$")
_MILITARY_BOOST_DESC_PATTERN = re.compile(r"TR[O0]{2}P(ATK|DEF|SIZE)BY(\d+)F[O0]R(\d+)HRS?")
_MILITARY_DURATION_PATTERN = re.compile(r"F[O0]R(\d+)HRS?")
_MILITARY_TIMED_KINDS = {
    "ANTISCOUT": MilitaryKind.ANTI_SCOUT,
    "SHIELDOFGRACE": MilitaryKind.SHIELD_OF_GRACE,
}
_MILITARY_BOOST_KINDS = {
    "ATK": MilitaryKind.TROOP_ATK_BOOST,
    "DEF": MilitaryKind.TROOP_DEF_BOOST,
    "SIZE": MilitaryKind.TROOP_SIZE_BOOST,
}

# Misc names resolve directly; only Lord EXP carries a displayed amount, which
# the description may independently confirm.
_MISC_EXP_NAME_PATTERN = re.compile(r"^(\d+)LORDEXP$")
_MISC_EXP_DESC_PATTERN = re.compile(r"ADDS?(\d+)LORDEXP")
_MISC_KIND_LABELS = {
    "SANDSEAMININGSHOVEL": MiscKind.SANDSEA_MINING_SHOVEL,
    "PICKAXE": MiscKind.PICKAXE,
    "CHALLENGEKEY": MiscKind.CHALLENGE_KEY,
    "WISHCRYSTAL": MiscKind.WISH_CRYSTAL,
    "BOWANDARROW": MiscKind.BOW_AND_ARROW,
}

_APPLICABILITY_LABELS = {
    "BUILD": BagItemApplicability.BUILD,
    "RESEARCH": BagItemApplicability.RESEARCH,
    "TRAINING": BagItemApplicability.TRAINING,
    "HEAL": BagItemApplicability.HEAL,
}

# Reward-row value forms: an "xA~B" possible range or a single "xA" offer.
_REWARD_RANGE_PATTERN = re.compile(r"^[Xx]\s*(\d[\d,]*)\s*[~-]\s*(\d[\d,]*)\s*$")
_REWARD_SINGLE_PATTERN = re.compile(r"^[Xx]\s*(\d[\d,]*)\s*$")


@dataclass(frozen=True, slots=True)
class _PreviewLayoutPlan:
    """Measured title and reward-row bands for one qualified preview layout."""

    title_region: Bounds
    row_regions: tuple[Bounds, ...]
    name_min_x: int
    content_bottom: int
    owned_offset_y: int


# Arena rows keep Owned under the left artwork, so the row band spans both
# columns and the name column starts after the art. Common keeps every text in
# the right column, so its band starts at the name column directly.
_PREVIEW_LAYOUTS: dict[str, _PreviewLayoutPlan] = {
    "bag_arena_chest_preview": _PreviewLayoutPlan(
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
    "bag_common_victory_preview": _PreviewLayoutPlan(
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


@dataclass(frozen=True, slots=True)
class BagItemContentProducer:
    """Produce typed Bag item rows and qualified chest-preview content."""

    matcher: OpenCvTemplateMatcher = field(default_factory=OpenCvTemplateMatcher)

    def additions_for_screen(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        ocr_context: ObservationOcrContext,
        layout_id: str | None,
    ) -> ObservationAdditions | None:
        """Dispatch preview content under its qualified visual layout only."""

        if screen_type == ScreenType.PNC_BAG_CHEST_PREVIEW and layout_id in bag_chest_preview_layouts():
            return self.preview_additions(image=image, ocr_context=ocr_context, layout_id=layout_id)
        return None

    def tab_additions(
        self,
        *,
        image: Image.Image,
        tab: BagTab,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Publish one measured row per detected Speedup or Treasure card."""

        prepared = self.matcher.prepare_frame(image, reference_size=_REFERENCE_SIZE)
        if prepared is None:
            return ObservationAdditions()
        entries = tuple(
            self._card_entry(
                image=image,
                prepared=prepared,
                card_bounds=card.bounds,
                card_clipped=card.clipped,
                card_index=index,
                tab=tab,
                ocr_context=ocr_context,
            )
            for index, card in enumerate(detect_bag_card_geometry(image))
        )
        return ObservationAdditions(list_entries=_mark_duplicate_identities(entries))

    def preview_additions(
        self,
        *,
        image: Image.Image,
        ocr_context: ObservationOcrContext,
        layout_id: str,
    ) -> ObservationAdditions:
        """Publish the preview title, source identity and possible reward rows."""

        plan = _PREVIEW_LAYOUTS.get(layout_id)
        if plan is None:
            return ObservationAdditions()
        title_lines = ocr_context.read_lines(
            image,
            _scaled_region(plan.title_region, image, reference=_PREVIEW_REFERENCE_SIZE),
            purpose=OcrReadPurpose.CONTENT,
            detail="bag_preview_title",
            required_fact="bag_preview_title",
        )
        title_text = _join_lines(title_lines)
        title_bounds = _union_all(line.bounds for line in title_lines)
        entries = tuple(
            self._reward_entry(
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
                title_bounds=title_bounds,
            ),
        )

    def _card_entry(
        self,
        *,
        image: Image.Image,
        prepared: PreparedFrame,
        card_bounds: Bounds,
        card_clipped: bool,
        card_index: int,
        tab: BagTab,
        ocr_context: ObservationOcrContext,
    ) -> DetectedListEntry:
        """Measure one Bag card into a typed row with explicit unknowns."""

        if card_clipped:
            return DetectedListEntry(
                kind=ListEntryKind.BAG_ITEM,
                bounds=card_bounds,
                row_status=RowRecognitionStatus.CLIPPED,
            )
        lines = ocr_context.read_lines(
            image,
            _native_offset_region(_CARD_TEXT_REGION, card_bounds, image),
            purpose=OcrReadPurpose.CONTENT,
            detail=f"bag_card_{tab}_{card_index}",
            required_fact="bag_card_fields",
        )
        scale_x = _REFERENCE_SIZE[0] / image.width
        scale_y = _REFERENCE_SIZE[1] / image.height
        card_lines = [
            _CardLine(
                line=line,
                rel_x=round((line.bounds.x - card_bounds.x) * scale_x),
                rel_y=round((line.bounds.y - card_bounds.y) * scale_y),
            )
            for line in lines
        ]
        name_text = _join_lines(
            card_line.line for card_line in card_lines
            if card_line.rel_x >= _TEXT_COLUMN_MIN_X and card_line.rel_y <= _NAME_MAX_Y
        )
        description_text = _join_lines(
            card_line.line for card_line in card_lines
            if card_line.rel_x >= _TEXT_COLUMN_MIN_X and card_line.rel_y > _NAME_MAX_Y
        )
        owned_count = _owned_count(card_lines)
        identity = _identity_for_tab(tab, name_text, description_text)
        if identity is None and name_text is not None:
            retry_text = _join_lines(
                sorted(
                    ocr_context.read_lines(
                        image,
                        _native_offset_region(_CARD_NAME_REGION, card_bounds, image),
                        purpose=OcrReadPurpose.CONTENT,
                        detail=f"bag_card_name_{tab}_{card_index}",
                        required_fact="bag_card_fields",
                    ),
                    key=lambda line: line.bounds.x,
                )
            )
            if retry_text is not None:
                retry_identity = _identity_for_tab(tab, retry_text, description_text)
                if retry_identity is not None:
                    name_text = retry_text
                    identity = retry_identity
        magnifier = self._glyph_match(
            prepared, _MAGNIFIER_TEMPLATE, _reference_offset_region(_MAGNIFIER_SEARCH, card_bounds, image)
        )
        facts = BagItemFacts(
            selected_tab=tab,
            identity=identity,
            owned_count=owned_count,
            inspection_glyph_present=magnifier is not None,
        )
        if name_text is None and description_text is None:
            row_status = RowRecognitionStatus.UNREADABLE
        elif tab in {BagTab.MILITARY, BagTab.MISC}:
            # These tabs have no evidenced inspection control: a resolved
            # identity is observation-only and an unresolved one is unreadable.
            row_status = (
                RowRecognitionStatus.NO_ACTION if identity is not None
                else RowRecognitionStatus.UNREADABLE
            )
        elif (
            isinstance(identity, TreasureIdentity)
            and bag_item_inspection_supported(identity)
            and magnifier is not None
        ):
            row_status = RowRecognitionStatus.COMPLETE
        else:
            row_status = RowRecognitionStatus.NO_ACTION
        actionable = row_status == RowRecognitionStatus.COMPLETE
        action_bounds = _clamp_bounds(magnifier.bounds, card_bounds) if actionable else None
        return DetectedListEntry(
            kind=ListEntryKind.BAG_ITEM,
            bounds=card_bounds,
            title_text=name_text,
            subtitle_text=description_text,
            metadata=bag_item_facts_metadata(facts),
            row_status=row_status,
            action_bounds=action_bounds,
            action_point=action_bounds.center() if action_bounds is not None else None,
            bag_item_facts=facts,
        )

    def _reward_entry(
        self,
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
        row_bounds = _scaled_region(visible_region, image, reference=_PREVIEW_REFERENCE_SIZE)
        # Stop above the clipped Owned field rather than asking OCR to read
        # partial digits, which can otherwise be mistaken for a name fragment.
        text_region = (
            replace(visible_region, height=min(visible_region.height, owned_offset_y))
            if clipped else visible_region
        )
        lines = ocr_context.read_lines(
            image,
            _scaled_region(text_region, image, reference=_PREVIEW_REFERENCE_SIZE),
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
                # Owned is the bottom field in both qualified layouts. The
                # last row cuts it off; a recognizable prefix is not a count.
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
                RowRecognitionStatus.CLIPPED if clipped
                else RowRecognitionStatus.NO_ACTION if name_text is not None
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

    def _glyph_match(
        self,
        prepared: PreparedFrame,
        template: Path,
        search_region: Bounds,
    ) -> TemplateMatch | None:
        """Return the bounded template hit inside one reference-coordinate region."""

        return self.matcher.find_best_match(
            prepared,
            template,
            threshold=_MAGNIFIER_THRESHOLD,
            search_region=search_region,
        )


@dataclass(frozen=True, slots=True)
class _CardLine:
    """One OCR line positioned relative to its owning card in reference space."""

    line: OcrLine
    rel_x: int
    rel_y: int


def _native_offset_region(region: Bounds, card_bounds: Bounds, image: Image.Image) -> Bounds:
    """Translate one reference-space card-relative region to native pixels."""

    scale_x = image.width / _REFERENCE_SIZE[0]
    scale_y = image.height / _REFERENCE_SIZE[1]
    left = max(0, card_bounds.x + round(region.x * scale_x))
    top = max(0, card_bounds.y + round(region.y * scale_y))
    right = min(card_bounds.x + round((region.x + region.width) * scale_x), image.width)
    bottom = min(card_bounds.y + round((region.y + region.height) * scale_y), image.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _reference_offset_region(region: Bounds, card_bounds: Bounds, image: Image.Image) -> Bounds:
    """Translate a card-relative region into prepared-frame reference space."""

    scale_x = _REFERENCE_SIZE[0] / image.width
    scale_y = _REFERENCE_SIZE[1] / image.height
    card_x = round(card_bounds.x * scale_x)
    card_y = round(card_bounds.y * scale_y)
    left = max(0, card_x + region.x)
    top = max(0, card_y + region.y)
    right = min(left + region.width, _REFERENCE_SIZE[0])
    bottom = min(top + region.height, _REFERENCE_SIZE[1])
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _scaled_region(region: Bounds, image: Image.Image, *, reference: tuple[int, int]) -> Bounds:
    """Project reference-coordinate bounds into the current image space."""

    scale_x = image.width / reference[0]
    scale_y = image.height / reference[1]
    left = round(region.x * scale_x)
    top = round(region.y * scale_y)
    right = min(round((region.x + region.width) * scale_x), image.width)
    bottom = min(round((region.y + region.height) * scale_y), image.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _clamp_bounds(bounds: Bounds, container: Bounds) -> Bounds:
    """Clamp one measured rectangle inside its owning card bounds."""

    left = max(bounds.x, container.x)
    top = max(bounds.y, container.y)
    right = min(bounds.x + bounds.width, container.x + container.width)
    bottom = min(bounds.y + bounds.height, container.y + container.height)
    return Bounds(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _name_min_x_native(name_min_x: int, row_bounds: Bounds, region: Bounds) -> int:
    """Convert the plan's reference-space name column into native row-relative x."""

    if region.width <= 0:
        return 0
    return round(name_min_x * row_bounds.width / region.width)


def _join_lines(lines) -> str | None:
    """Join bounded line fragments into one literal, else None when empty."""

    parts = [line.text.strip() for line in lines if line.text.strip()]
    return " ".join(parts) if parts else None


def _union_all(bounds) -> Bounds | None:
    """Return the smallest rectangle covering all supplied bounds."""

    items = list(bounds)
    if not items:
        return None
    left = min(b.x for b in items)
    top = min(b.y for b in items)
    right = max(b.x + b.width for b in items)
    bottom = max(b.y + b.height for b in items)
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)


def _owned_count(card_lines: list[_CardLine]) -> int | None:
    """Read the displayed Owned count from any matching bounded line."""

    for card_line in card_lines:
        match = _OWNED_PATTERN.fullmatch(card_line.line.text.strip())
        if match is not None:
            return parse_grouped_integer(match.group(1))
    return None


def _identity_for_tab(
    tab: BagTab, name_text: str | None, description_text: str | None,
) -> BagItemIdentity | None:
    """Resolve both initial and retry reads under the selected item's family."""

    if tab == BagTab.TREASURE:
        return treasure_identity_for_label(name_text)
    if tab == BagTab.MILITARY:
        return _military_identity(name_text, description_text)
    if tab == BagTab.MISC:
        return _misc_identity(name_text, description_text)
    if tab == BagTab.SPEEDUP:
        return _speedup_identity(name_text, description_text)
    return None


def _speedup_identity(name_text: str | None, description_text: str | None) -> BagItemIdentity | None:
    """Resolve a Speedup identity from name and description tokens.

    Either field may supply the time information; when both parse they must
    agree, otherwise the identity stays unknown. Percentage bonuses keep their
    applicability, percent and active duration distinct from flat minutes.
    """

    name_normalized = normalize_ocr_text(name_text or "")
    desc_normalized = normalize_ocr_text(description_text or "")
    name_bonus = _SPEED_BONUS_NAME_PATTERN.fullmatch(name_normalized)
    name_time = _TIME_NAME_PATTERN.fullmatch(name_normalized)
    desc_bonus = _SPEED_BONUS_DESC_PATTERN.search(desc_normalized)
    desc_time = _TIME_DESC_PATTERN.search(desc_normalized)
    if (name_bonus or desc_bonus) and (name_time or desc_time):
        return None
    if name_bonus or desc_bonus:
        percent = int(name_bonus.group(1)) if name_bonus else int(desc_bonus.group(2))
        label = name_bonus.group(2) if name_bonus else desc_bonus.group(1)
        applicability = _APPLICABILITY_LABELS[label]
        if name_bonus and desc_bonus and (
            percent != int(desc_bonus.group(2)) or applicability != _APPLICABILITY_LABELS[desc_bonus.group(1)]
        ):
            return None
        active_minutes = int(desc_bonus.group(3)) * 60 if desc_bonus else None
        if active_minutes is None or active_minutes <= 0 or percent <= 0:
            return None
        return SpeedBonusIdentity(
            applicability=applicability,
            percent=percent,
            active_minutes=active_minutes,
        )
    name_minutes = _time_minutes(name_time.group(1), name_time.group(2)) if name_time else None
    desc_minutes = _time_minutes(desc_time.group(2), desc_time.group(3)) if desc_time else None
    name_applicability = (
        _APPLICABILITY_LABELS.get(name_time.group(3), BagItemApplicability.GENERAL)
        if name_time else None
    )
    desc_applicability = (
        _APPLICABILITY_LABELS.get(desc_time.group(1), BagItemApplicability.GENERAL)
        if desc_time else None
    )
    if name_time and desc_time and name_applicability != desc_applicability:
        return None
    if name_minutes is not None and desc_minutes is not None and name_minutes != desc_minutes:
        return None
    minutes = name_minutes if name_minutes is not None else desc_minutes
    if minutes is None or minutes <= 0:
        return None
    applicability = name_applicability if name_time else desc_applicability
    assert applicability is not None
    return TimeReductionIdentity(applicability=applicability, minutes=minutes)


def _time_minutes(value: str, unit: str) -> int:
    """Convert a displayed minute/hour magnitude into minutes."""

    minutes = int(value)
    return minutes if unit == "MIN" else minutes * 60


def _military_identity(
    name_text: str | None, description_text: str | None
) -> MilitaryItemIdentity | None:
    """Resolve a Military-tab identity from name and description tokens.

    Timed protection items carry `N-hr` in the name; boosts carry `N%`. The
    description supplies or confirms duration (`for N hrs`) and boost fields.
    When both fields parse the same fact they must agree, otherwise the
    identity stays unknown rather than guessing a variant.
    """

    name_normalized = normalize_ocr_text(name_text or "")
    desc_normalized = normalize_ocr_text(description_text or "")
    timed = _MILITARY_TIMED_NAME_PATTERN.fullmatch(name_normalized)
    boost = _MILITARY_BOOST_NAME_PATTERN.fullmatch(name_normalized)
    if timed is None and boost is None:
        return None
    desc_boost = _MILITARY_BOOST_DESC_PATTERN.search(desc_normalized)
    desc_duration = _MILITARY_DURATION_PATTERN.search(desc_normalized)
    if timed is not None:
        kind = _MILITARY_TIMED_KINDS[timed.group(2).replace("0", "O")]
        name_minutes = int(timed.group(1)) * 60 if timed.group(1) else None
        desc_minutes = int(desc_duration.group(1)) * 60 if desc_duration else None
        if name_minutes is not None and desc_minutes is not None and name_minutes != desc_minutes:
            return None
        minutes = name_minutes if name_minutes is not None else desc_minutes
        if minutes is None or minutes <= 0:
            return None
        return MilitaryItemIdentity(kind=kind, duration_minutes=minutes)
    assert boost is not None
    kind = _MILITARY_BOOST_KINDS[boost.group(2)]
    name_percent = int(boost.group(1)) if boost.group(1) else None
    if desc_boost is None or _MILITARY_BOOST_KINDS[desc_boost.group(1)] != kind:
        return None
    desc_percent = int(desc_boost.group(2))
    if name_percent is not None and name_percent != desc_percent:
        return None
    duration_minutes = int(desc_boost.group(3)) * 60
    if desc_percent <= 0 or duration_minutes <= 0:
        return None
    return MilitaryItemIdentity(
        kind=kind,
        duration_minutes=duration_minutes,
        percent=desc_percent,
    )


def _misc_identity(
    name_text: str | None, description_text: str | None
) -> MiscItemIdentity | None:
    """Resolve a Misc-tab identity from the displayed name.

    Only `N Lord EXP` carries an amount, which the description
    (`Adds N Lord EXP`) may independently confirm; material kinds carry none.
    """

    name_normalized = normalize_ocr_text(name_text or "")
    if not name_normalized:
        return None
    exp = _MISC_EXP_NAME_PATTERN.fullmatch(name_normalized)
    if exp is not None:
        amount = int(exp.group(1))
        if amount <= 0:
            return None
        desc_exp = _MISC_EXP_DESC_PATTERN.search(normalize_ocr_text(description_text or ""))
        if desc_exp is not None and int(desc_exp.group(1)) != amount:
            return None
        return MiscItemIdentity(kind=MiscKind.LORD_EXP, amount=amount)
    kind = _MISC_KIND_LABELS.get(name_normalized)
    if kind is None:
        return None
    return MiscItemIdentity(kind=kind)


def _mark_duplicate_identities(
    entries: tuple[DetectedListEntry, ...],
) -> tuple[DetectedListEntry, ...]:
    """Withhold taps when two complete rows resolve to the same identity."""

    duplicates = {
        key
        for entry in entries
        if entry.row_status == RowRecognitionStatus.COMPLETE
        and (key := _entry_identity_key(entry)) is not None
        and sum(
            other.row_status == RowRecognitionStatus.COMPLETE
            and _entry_identity_key(other) == key
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
        if _entry_identity_key(entry) in duplicates else entry
        for entry in entries
    )


def _entry_identity_key(entry: DetectedListEntry) -> str | None:
    """Return the canonical identity key for a complete Bag item row."""

    facts = entry.bag_item_facts
    if facts is None or facts.identity is None:
        return None
    return bag_item_identity_key(facts.identity)
