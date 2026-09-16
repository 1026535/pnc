"""Canonical typed Bag item identities, per-card facts, and chest-preview content."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds


class BagItemApplicability(StrEnum):
    """Speedup applicability surfaced by a displayed card name or description."""

    GENERAL = "general"
    BUILD = "build"
    RESEARCH = "research"
    TRAINING = "training"
    HEAL = "heal"


@dataclass(frozen=True, slots=True)
class TimeReductionIdentity:
    """A flat speedup that removes a fixed number of minutes from remaining time."""

    applicability: BagItemApplicability
    minutes: int

    def __post_init__(self) -> None:
        if self.minutes <= 0:
            raise ValueError(f"minutes must be positive, got {self.minutes}")


@dataclass(frozen=True, slots=True)
class SpeedBonusIdentity:
    """A temporary percentage speed bonus that stays active for a displayed duration."""

    applicability: BagItemApplicability
    percent: int
    active_minutes: int

    def __post_init__(self) -> None:
        if self.percent <= 0:
            raise ValueError(f"percent must be positive, got {self.percent}")
        if self.active_minutes <= 0:
            raise ValueError(f"active_minutes must be positive, got {self.active_minutes}")


class TreasureKind(StrEnum):
    """Treasure-tab item families evidenced by current captures."""

    ARENA_SURPRISE_CHEST = "arena_surprise_chest"
    COMMON_FIRST_VICTORY_CHEST = "common_first_victory_chest"
    RARE_FIRST_VICTORY_CHEST = "rare_first_victory_chest"
    PINBALL = "pinball"
    STARNA_DICE = "starna_dice"
    OATH_RUNE_CHEST = "oath_rune_chest"
    DIAMOND_CHEST = "diamond_chest"
    DEMON_CHEST = "demon_chest"


_TREASURE_KIND_DISPLAY: dict[TreasureKind, str] = {
    TreasureKind.ARENA_SURPRISE_CHEST: "Arena Surprise Chest",
    TreasureKind.COMMON_FIRST_VICTORY_CHEST: "Common 1st Victory Chest",
    TreasureKind.RARE_FIRST_VICTORY_CHEST: "Rare 1st Victory Chest",
    TreasureKind.PINBALL: "Pinball",
    TreasureKind.STARNA_DICE: "Starna's Dice",
    TreasureKind.OATH_RUNE_CHEST: "Oath Rune Chest",
    TreasureKind.DIAMOND_CHEST: "Diamond Chest",
    TreasureKind.DEMON_CHEST: "Demon Chest",
}

# Treasure kinds that surface a "Lv.N" title prefix distinguishing same-art variants.
_LEVELLED_TREASURE_KINDS = frozenset({TreasureKind.OATH_RUNE_CHEST, TreasureKind.DEMON_CHEST})

_LEVELLED_LABEL_PATTERN = re.compile(r"^LV(\d+)(.+)$")


@dataclass(frozen=True, slots=True)
class TreasureIdentity:
    """A resolved Treasure-tab item; level is required exactly for levelled kinds."""

    kind: TreasureKind
    level: int | None = None

    def __post_init__(self) -> None:
        if self.kind in _LEVELLED_TREASURE_KINDS:
            if self.level is None or self.level <= 0:
                raise ValueError(f"{self.kind} requires a positive level, got {self.level}")
        elif self.level is not None:
            raise ValueError(f"{self.kind} does not carry a displayed level")


BagItemIdentity: TypeAlias = TimeReductionIdentity | SpeedBonusIdentity | TreasureIdentity


@dataclass(frozen=True, slots=True)
class BagItemFacts:
    """Typed facts resolved for one Speedup or Treasure card under a selected tab."""

    selected_tab: BagTab
    identity: BagItemIdentity | None = None
    owned_count: int | None = None
    inspection_glyph_present: bool | None = None


@dataclass(frozen=True, slots=True)
class BagPreviewRewardFacts:
    """One possible reward row inside a qualified chest preview.

    `quantity_min`/`quantity_max` parse the displayed `xA~B` possible-result range;
    `displayed_owned_count` is the preview's own current-inventory label. Neither is
    Bag inventory ownership and neither is ever a guarantee.
    """

    reward_name_text: str | None
    range_text: str | None = None
    quantity_min: int | None = None
    quantity_max: int | None = None
    displayed_owned_count: int | None = None


@dataclass(frozen=True, slots=True)
class BagChestPreviewFacts:
    """Screen-level facts for a qualified chest-preview popup.

    `source_identity` is parsed independently from the observed title text, never
    copied from a requested source.
    """

    title_text: str | None = None
    source_identity: TreasureIdentity | None = None
    title_bounds: Bounds | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None


def treasure_identity_for_label(label_text: str | None) -> TreasureIdentity | None:
    """Resolve a canonical TreasureIdentity from a displayed card or preview title."""

    if label_text is None:
        return None
    normalized = normalize_ocr_text(label_text)
    if not normalized:
        return None
    levelled = _LEVELLED_LABEL_PATTERN.fullmatch(normalized)
    if levelled:
        level = int(levelled.group(1))
        if level <= 0:
            return None
        suffix = levelled.group(2)
        for kind in _LEVELLED_TREASURE_KINDS:
            if normalize_ocr_text(_TREASURE_KIND_DISPLAY[kind]) == suffix:
                return TreasureIdentity(kind=kind, level=level)
        return _levelled_identity_with_letter_confusion(level, suffix)
    for kind in TreasureKind:
        if normalize_ocr_text(_TREASURE_KIND_DISPLAY[kind]) == normalized:
            if kind in _LEVELLED_TREASURE_KINDS:
                return None
            return TreasureIdentity(kind=kind)
    return None


def _levelled_identity_with_letter_confusion(level: int, suffix: str) -> TreasureIdentity | None:
    """Retry a levelled parse when OCR absorbed a leading letter as a digit.

    ``Lv.23 Oath Rune Chest`` can surface as ``LV230ATHRUNECHEST``: the longest
    digit run swallows the word's first letter. Shifting one trailing digit back
    as its letter confusion (0->O) recovers the displayed level and kind.
    """

    if level < 10 or not suffix.startswith("ATH"):
        return None
    shifted_level = level // 10
    if shifted_level <= 0 or level % 10 != 0:
        return None
    recovered = "O" + suffix
    for kind in _LEVELLED_TREASURE_KINDS:
        if normalize_ocr_text(_TREASURE_KIND_DISPLAY[kind]) == recovered:
            return TreasureIdentity(kind=kind, level=shifted_level)
    return None


def treasure_identity_title(identity: TreasureIdentity) -> str:
    """Return the canonical displayed title for tap matching and test metadata."""

    display = _TREASURE_KIND_DISPLAY[identity.kind]
    if identity.kind in _LEVELLED_TREASURE_KINDS:
        return f"Lv.{identity.level} {display}"
    return display


def bag_item_identity_key(identity: BagItemIdentity) -> str:
    """Return a stable canonical string identifying one resolved Bag item identity."""

    match identity:
        case TimeReductionIdentity(applicability=applicability, minutes=minutes):
            return f"time_reduction:{applicability}:{minutes}"
        case SpeedBonusIdentity(
            applicability=applicability, percent=percent, active_minutes=active_minutes
        ):
            return f"speed_bonus:{applicability}:{percent}:{active_minutes}"
        case TreasureIdentity(kind=kind, level=level):
            if level is not None:
                return f"treasure:{kind}:{level}"
            return f"treasure:{kind}"


def bag_item_facts_metadata(facts: BagItemFacts) -> dict[str, str]:
    """Return compact row metadata used by TapListEntryAction matching."""

    if facts.identity is None:
        return {}
    return {"identity": bag_item_identity_key(facts.identity)}


# Treasure identities whose inspection destination family is independently
# qualified. Other recognized magnifiers remain observation-only evidence.
_BAG_CHEST_PREVIEW_LAYOUTS: dict[TreasureKind, str] = {
    TreasureKind.ARENA_SURPRISE_CHEST: "bag_arena_chest_preview",
    TreasureKind.COMMON_FIRST_VICTORY_CHEST: "bag_common_victory_preview",
}


def bag_item_inspection_supported(identity: BagItemIdentity) -> bool:
    """Return True when the identity's preview destination family is qualified."""

    return isinstance(identity, TreasureIdentity) and identity.kind in _BAG_CHEST_PREVIEW_LAYOUTS


def bag_chest_preview_layout(identity: TreasureIdentity) -> str | None:
    """Return the qualified preview layout id for a supported Treasure identity."""

    return _BAG_CHEST_PREVIEW_LAYOUTS.get(identity.kind)


def bag_chest_preview_layouts() -> frozenset[str]:
    """Return all qualified chest-preview layout ids."""

    return frozenset(_BAG_CHEST_PREVIEW_LAYOUTS.values())
