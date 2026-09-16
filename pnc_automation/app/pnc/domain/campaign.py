"""Typed Campaign facts observed from the map and chapter-path screens.

Only facts proved by the current frame may be populated. An unobserved value
stays ``None``; there is no chapter-name catalog, implicit mode, or ordinal
derived from artwork color alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef


class CampaignMode(StrEnum):
    """Supported campaign execution modes."""

    STANDARD = "standard"
    ELITE = "elite"


@dataclass(frozen=True, slots=True)
class CampaignChapterIdentity:
    """The chapter named by the accepted chapter-path title for one frame."""

    chapter_number: int
    name: str | None = None
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Require a real observed chapter number and truthful provenance."""

        if isinstance(self.chapter_number, bool) or not isinstance(self.chapter_number, int):
            raise TypeError("Campaign chapter identity requires an integer chapter number.")
        if self.chapter_number <= 0:
            raise ValueError("Campaign chapter identity requires a positive chapter number.")
        if self.name is not None and not isinstance(self.name, str):
            raise TypeError("Campaign chapter name must be observed text or None.")
        if self.source_screen is not None and self.source_screen != ScreenType.PNC_CAMPAIGN_CHAPTER:
            raise SelectorResolutionError(
                "Campaign chapter identity must come from a chapter-path frame.",
                source_screen=self.source_screen,
            )


@dataclass(frozen=True, slots=True)
class CampaignNodeFacts:
    """Observed facts for one Campaign map chapter node or chapter-path stage node."""

    chapter_number: int | None = None
    stage_number: int | None = None
    name: str | None = None
    locked: bool | None = None
    selected: bool | None = None
    completed: bool | None = None
    mode: CampaignMode | None = None

    def __post_init__(self) -> None:
        """Reject invented ordinals and non-tri-state flags."""

        for field_name, value in (
            ("chapter_number", self.chapter_number),
            ("stage_number", self.stage_number),
        ):
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"Campaign node {field_name} must be an integer or None.")
            if value <= 0:
                raise ValueError(f"Campaign node {field_name} must be positive.")
        for field_name, value in (
            ("locked", self.locked),
            ("selected", self.selected),
            ("completed", self.completed),
        ):
            if value is not None and not isinstance(value, bool):
                raise TypeError(f"Campaign node {field_name} must be a bool or None.")
        if self.name is not None and not isinstance(self.name, str):
            raise TypeError("Campaign node name must be observed text or None.")
        if self.mode is not None and not isinstance(self.mode, CampaignMode):
            raise TypeError("Campaign node mode must be an observed CampaignMode or None.")
