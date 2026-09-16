"""Canonical typed Trial Challenge card and Applicable Stats facts.

The category enum is the single identity owner for the six fixed Trial
Challenge cards. Vision producers resolve observed card titles through
:func:`trial_category_for_label` and measured Stats rows through the typed
records; automation consumers read the typed facts without re-deriving
availability, completion, or day schedules from display text.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.core.vision.image.models import Bounds


class TrialCategory(StrEnum):
    """Canonical identities of the six fixed Trial Challenge categories."""

    HERO = "hero"
    CURIO = "curio"
    TECH = "tech"
    GEAR = "gear"
    RUNE = "rune"
    SAUROI = "sauroi"


_TRIAL_CATEGORY_TITLES: dict[TrialCategory, str] = {
    TrialCategory.HERO: "Hero Trial",
    TrialCategory.CURIO: "Curio Trial",
    TrialCategory.TECH: "Tech Trial",
    TrialCategory.GEAR: "Gear Trial",
    TrialCategory.RUNE: "Rune Trial",
    TrialCategory.SAUROI: "Sauroi Trial",
}

_TRIAL_CATEGORY_BY_LABEL: dict[str, TrialCategory] = {
    normalize_ocr_text(title): category for category, title in _TRIAL_CATEGORY_TITLES.items()
}


def trial_category_title(category: TrialCategory) -> str:
    """Return the canonical display title for one Trial Challenge category."""

    if not isinstance(category, TrialCategory):
        raise TypeError("trial_category_title requires a TrialCategory.")
    return _TRIAL_CATEGORY_TITLES[category]


def trial_category_for_label(text: str) -> TrialCategory | None:
    """Resolve one normalized OCR card title to its canonical category."""

    return _TRIAL_CATEGORY_BY_LABEL.get(normalize_ocr_text(text))


def trial_category_metadata(facts: "TrialCardFacts | None") -> dict[str, str]:
    """Project typed category once for generic list-entry consumers.

    ``TapListEntryAction`` resolves rows through ``metadata``; the canonical
    semantic owner is :class:`TrialCardFacts`, so this is the only place a
    category value is copied into metadata.
    """

    if facts is None or facts.category is None:
        return {}
    return {"category": facts.category.value}


@dataclass(frozen=True, slots=True)
class TrialCardFacts:
    """Typed facts measured for one Trial Challenge category card.

    Every field comes from that card's own bounded region: ``category`` only
    from its bounded title, ``required_castle_level`` only from a lock
    requirement line, and the glyph facts only from measured template hits.
    States are independent observations — a card can show a countdown while
    castle-locked, and a chest presence never implies completion or
    claimability. Every field stays ``None`` when its evidence is absent.
    """

    category: TrialCategory | None = None
    progress_current: int | None = None
    progress_required: int | None = None
    required_castle_level: int | None = None
    countdown_text: str | None = None
    weekday_text: str | None = None
    locked: bool | None = None
    reward_chest_present: bool | None = None
    trial_button_present: bool | None = None
    stats_button_present: bool | None = None

    def __post_init__(self) -> None:
        """Reject malformed typed facts instead of publishing partial guesses."""

        if self.category is not None and not isinstance(self.category, TrialCategory):
            raise TypeError("TrialCardFacts.category must be a TrialCategory or None.")
        for field_name in ("progress_current", "progress_required", "required_castle_level"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise SelectorResolutionError(
                    f"TrialCardFacts.{field_name} must be a non-negative integer or None.",
                    value=value,
                )
        if (self.progress_current is None) != (self.progress_required is None):
            raise SelectorResolutionError(
                "TrialCardFacts progress values must be observed together or stay unknown."
            )
        for field_name in ("locked", "reward_chest_present", "trial_button_present", "stats_button_present"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"TrialCardFacts.{field_name} must be a bool or None.")


@dataclass(frozen=True, slots=True)
class TrialChallengeSummary:
    """Screen-level observed facts on the proved Trial Challenge layout.

    ``observed_counter`` is the integer shown beside the toolbar wing icon; it
    is an observed counter, not a named currency, and no consumer is invented
    for it.
    """

    observed_counter: int | None = None
    counter_bounds: Bounds | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keep the observed counter numeric and bounded."""

        if self.observed_counter is not None and (
            not isinstance(self.observed_counter, int)
            or isinstance(self.observed_counter, bool)
            or self.observed_counter < 0
        ):
            raise SelectorResolutionError(
                "TrialChallengeSummary.observed_counter must be a non-negative integer or None.",
                value=self.observed_counter,
            )
        if self.counter_bounds is not None and not isinstance(self.counter_bounds, Bounds):
            raise TypeError("TrialChallengeSummary.counter_bounds must be Bounds.")


@dataclass(frozen=True, slots=True)
class TrialApplicableStat:
    """One bounded label/value row measured inside the Applicable Stats table."""

    label_text: str
    percent_text: str
    percent_value: int | None
    bounds: Bounds

    def __post_init__(self) -> None:
        """Require literal observed text and measured row bounds."""

        if not isinstance(self.label_text, str) or not self.label_text.strip():
            raise ValueError("TrialApplicableStat.label_text must be non-empty.")
        if not isinstance(self.percent_text, str) or not self.percent_text.strip():
            raise ValueError("TrialApplicableStat.percent_text must be non-empty.")
        if self.percent_value is not None and (
            not isinstance(self.percent_value, int)
            or isinstance(self.percent_value, bool)
            or self.percent_value < 0
        ):
            raise SelectorResolutionError(
                "TrialApplicableStat.percent_value must be a non-negative integer or None.",
                value=self.percent_value,
            )
        if not isinstance(self.bounds, Bounds):
            raise TypeError("TrialApplicableStat.bounds must be Bounds.")


@dataclass(frozen=True, slots=True)
class TrialApplicableStatsDetail:
    """Typed facts measured on the Trial Applicable Stats detail.

    Identity stays owned by the visual detail profile; ``category`` comes only
    from the bounded explanatory footer (``In <Category> Trial, only ...``),
    and each stat row preserves its literal observed label and percent text.
    No value is a production constant and no action is authorized by this
    detail.
    """

    category: TrialCategory | None = None
    stats: tuple[TrialApplicableStat, ...] = ()
    footer_text: str | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keep the detail typed and bound to measured rows."""

        if self.category is not None and not isinstance(self.category, TrialCategory):
            raise TypeError("TrialApplicableStatsDetail.category must be a TrialCategory or None.")
        for stat in self.stats:
            if not isinstance(stat, TrialApplicableStat):
                raise TypeError("TrialApplicableStatsDetail.stats rows must be TrialApplicableStat.")
