"""Pure OCR text parsing and duplicate-row decisions for Bag content."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagItemApplicability,
    BagItemIdentity,
    MilitaryItemIdentity,
    MilitaryKind,
    MiscItemIdentity,
    MiscKind,
    SpeedBonusIdentity,
    TimeReductionIdentity,
    bag_item_identity_key,
    treasure_identity_for_label,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, RowRecognitionStatus
from pnc_automation.app.pnc.vision.numeric_parsing import parse_grouped_integer
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine

_OWNED_PATTERN = re.compile(r"^[O0D]?wned\s*:\s*(.+)$", re.IGNORECASE)
_SPEED_BONUS_NAME_PATTERN = re.compile(r"^(\d+)(BUILD|RESEARCH|TRAINING|HEAL)SPEEDUP$")
_SPEED_BONUS_DESC_PATTERN = re.compile(r"(BUILD|RESEARCH|TRAINING|HEAL)SPEEDBY(\d+)FOR(\d+)HRS?")
_TIME_NAME_PATTERN = re.compile(r"^(\d+)(MIN|HRS?)(BUILD|RESEARCH|TRAINING|HEAL)?SPEEDUP$")
_TIME_DESC_PATTERN = re.compile(r"(BUILD|RESEARCH|TRAINING|HEAL)?(?:REMAINING)?TIMEBY(\d+)(MIN|HRS?)")
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


@dataclass(frozen=True, slots=True)
class CardLine:
    """One OCR line positioned relative to its owning card in reference space."""

    line: OcrLine
    rel_x: int
    rel_y: int


def join_lines(lines) -> str | None:
    """Join bounded line fragments into one literal, else ``None``."""

    parts = [line.text.strip() for line in lines if line.text.strip()]
    return " ".join(parts) if parts else None


def union_all(bounds) -> Bounds | None:
    """Return the smallest rectangle covering all supplied bounds."""

    items = list(bounds)
    if not items:
        return None
    left = min(bound.x for bound in items)
    top = min(bound.y for bound in items)
    right = max(bound.x + bound.width for bound in items)
    bottom = max(bound.y + bound.height for bound in items)
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)


def owned_count(card_lines: list[CardLine]) -> int | None:
    """Read the displayed Owned count from a bounded card line."""

    for card_line in card_lines:
        match = _OWNED_PATTERN.fullmatch(card_line.line.text.strip())
        if match is not None:
            return parse_grouped_integer(match.group(1))
    return None


def identity_for_tab(
    tab: BagTab,
    name_text: str | None,
    description_text: str | None,
) -> BagItemIdentity | None:
    """Resolve one identity using only the selected tab's canonical parser."""

    if tab == BagTab.TREASURE:
        return treasure_identity_for_label(name_text)
    if tab == BagTab.MILITARY:
        return military_identity(name_text, description_text)
    if tab == BagTab.MISC:
        return misc_identity(name_text, description_text)
    if tab == BagTab.SPEEDUP:
        return speedup_identity(name_text, description_text)
    return None


def speedup_identity(name_text: str | None, description_text: str | None) -> BagItemIdentity | None:
    """Resolve a Speedup identity while rejecting conflicting OCR fields."""

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
            percent != int(desc_bonus.group(2))
            or applicability != _APPLICABILITY_LABELS[desc_bonus.group(1)]
        ):
            return None
        active_minutes = int(desc_bonus.group(3)) * 60 if desc_bonus else None
        if active_minutes is None or active_minutes <= 0 or percent <= 0:
            return None
        return SpeedBonusIdentity(applicability=applicability, percent=percent, active_minutes=active_minutes)
    name_minutes = _time_minutes(name_time.group(1), name_time.group(2)) if name_time else None
    desc_minutes = _time_minutes(desc_time.group(2), desc_time.group(3)) if desc_time else None
    name_applicability = (
        _APPLICABILITY_LABELS.get(name_time.group(3), BagItemApplicability.GENERAL)
        if name_time
        else None
    )
    desc_applicability = (
        _APPLICABILITY_LABELS.get(desc_time.group(1), BagItemApplicability.GENERAL)
        if desc_time
        else None
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
    minutes = int(value)
    return minutes if unit == "MIN" else minutes * 60


def military_identity(name_text: str | None, description_text: str | None) -> MilitaryItemIdentity | None:
    """Resolve a Military identity and preserve duration/boost conflicts."""

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
    return MilitaryItemIdentity(kind=kind, duration_minutes=duration_minutes, percent=desc_percent)


def misc_identity(name_text: str | None, description_text: str | None) -> MiscItemIdentity | None:
    """Resolve a Misc identity, treating Lord EXP as a denomination."""

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
    return MiscItemIdentity(kind=kind) if kind is not None else None


def mark_duplicate_identities(entries: tuple[DetectedListEntry, ...]) -> tuple[DetectedListEntry, ...]:
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
        )
        > 1
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
        if _entry_identity_key(entry) in duplicates
        else entry
        for entry in entries
    )


def _entry_identity_key(entry: DetectedListEntry) -> str | None:
    facts = entry.bag_item_facts
    if facts is None or facts.identity is None:
        return None
    return bag_item_identity_key(facts.identity)
