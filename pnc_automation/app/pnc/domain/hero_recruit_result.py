"""Observed Hero Hall result facts, independent of recruitment authorization."""

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.emulator.provenance import FrameRef


class HeroRecruitResultPhase(StrEnum):
    """Stable result phases qualified from the saved recruitment sequence."""

    HERO_PRESENTATION = "hero_presentation"
    FRAGMENT_RESULT = "fragment_result"


HERO_RECRUIT_RESULT_LAYOUTS = {
    "hero_recruit_presentation": HeroRecruitResultPhase.HERO_PRESENTATION,
    "hero_recruit_fragments": HeroRecruitResultPhase.FRAGMENT_RESULT,
}


@dataclass(frozen=True, slots=True)
class HeroRecruitResult:
    """Current displayed result; no field establishes a new committed recruit.

    Titles are literal OCR rather than a hero catalog. The lower Items left and
    Recruit cost are displayed counters with no inferred currency identity.
    Unknown values remain absent, including star counts on fragment artwork.
    """

    phase: HeroRecruitResultPhase
    title_text: str | None = None
    quantity: int | None = None
    star_count: int | None = None
    items_left: int | None = None
    recruit_cost: int | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Reject malformed observations without inventing missing content."""

        if not isinstance(self.phase, HeroRecruitResultPhase):
            raise TypeError("Hero recruit result phase must be a HeroRecruitResultPhase.")
        for name in ("quantity", "star_count", "items_left", "recruit_cost"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"Hero recruit result {name} must be a non-negative integer or None.")
