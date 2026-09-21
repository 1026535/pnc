"""Typed shared match-3 battle contract.

One shared component serves Campaign, Arena and Lost Land. Feature callers
select a context and an explicit battle mode; the shared API reports honest
availability and returns typed results. M0 implements no battle policy, so
every valid context/mode pair reports ``not_implemented``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.domain.campaign import CampaignChapterIdentity, CampaignNodeFacts
from pnc_automation.app.pnc.domain.observation import DetectedListEntry
from pnc_automation.app.pnc.domain.screen_decision import ScreenDecision
from pnc_automation.core.infra.emulator.provenance import FrameRef


class Match3Context(StrEnum):
    """Feature contexts that can host a shared match-3 battle."""

    CAMPAIGN = "campaign"
    ARENA = "arena"
    LOST_LAND = "lost_land"


class Match3Mode(StrEnum):
    """The explicit battle policy a feature caller must select."""

    SOLVER = "solver"
    DAILY_EXIT = "daily_exit"
    GAME_AUTO = "game_auto"


class Match3AvailabilityStatus(StrEnum):
    """Reports whether one context/mode pair can execute in this build."""

    AVAILABLE = "available"
    NOT_IMPLEMENTED = "not_implemented"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Match3Availability:
    """The pure availability answer for one context/mode pair."""

    context: Match3Context
    mode: Match3Mode
    status: Match3AvailabilityStatus
    reason: str = ""

    def __post_init__(self) -> None:
        """Require typed members and an actionable reason for unavailable pairs."""

        if not isinstance(self.context, Match3Context):
            raise TypeError("Match3Availability.context must be a Match3Context.")
        if not isinstance(self.mode, Match3Mode):
            raise TypeError("Match3Availability.mode must be a Match3Mode.")
        if not isinstance(self.status, Match3AvailabilityStatus):
            raise TypeError("Match3Availability.status must be a Match3AvailabilityStatus.")
        if not isinstance(self.reason, str):
            raise TypeError("Match3Availability.reason must be a string.")
        if self.status is not Match3AvailabilityStatus.AVAILABLE and not self.reason.strip():
            raise ValueError("An unavailable match-3 pair requires an actionable reason.")

    @property
    def available(self) -> bool:
        """Reports whether this pair can execute in this build."""

        return self.status is Match3AvailabilityStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class Match3Target:
    """References the feature-observed target behind one battle request.

    The reference carries observed facts only; it is not a readiness or
    authorization certificate. Campaign requests reuse the existing observed
    node/chapter fact models. Menu and row references retain their original
    source frame; they do not describe the caller's later preparation screen.
    """

    context: Match3Context
    campaign_node: CampaignNodeFacts | None = None
    campaign_chapter: CampaignChapterIdentity | None = None
    frame_ref: FrameRef | None = None
    source_decision: ScreenDecision | None = None
    selected_entry: DetectedListEntry | None = None

    def __post_init__(self) -> None:
        """Require a typed context and observed-fact reference fields."""

        if not isinstance(self.context, Match3Context):
            raise TypeError("Match3Target.context must be a Match3Context.")
        if self.campaign_node is not None and not isinstance(self.campaign_node, CampaignNodeFacts):
            raise TypeError("Match3Target.campaign_node must be a CampaignNodeFacts or None.")
        if self.campaign_chapter is not None and not isinstance(
            self.campaign_chapter, CampaignChapterIdentity
        ):
            raise TypeError("Match3Target.campaign_chapter must be a CampaignChapterIdentity or None.")
        if self.frame_ref is not None and not isinstance(self.frame_ref, FrameRef):
            raise TypeError("Match3Target.frame_ref must be a FrameRef or None.")
        if self.context is not Match3Context.CAMPAIGN and (
            self.campaign_node is not None or self.campaign_chapter is not None
        ):
            raise ValueError("Campaign target facts require the campaign context.")
        if self.source_decision is not None:
            if not isinstance(self.source_decision, ScreenDecision):
                raise TypeError("Match3Target.source_decision must be a ScreenDecision or None.")
            if self.frame_ref is None:
                raise ValueError("A match-3 source decision requires its observed FrameRef.")
        if self.campaign_chapter is not None and self.campaign_chapter.frame_ref is not None:
            if self.campaign_chapter.frame_ref != self.frame_ref:
                raise ValueError("Campaign chapter provenance must match the target source frame.")
        if self.campaign_chapter is not None and self.source_decision is not None:
            for source, decision in (
                (self.campaign_chapter.source_screen, self.source_decision.effective_screen),
                (self.campaign_chapter.source_layout_id, self.source_decision.layout_id),
            ):
                if source is not None and source != decision:
                    raise ValueError("Campaign chapter provenance must match the target source decision.")
        if self.selected_entry is not None:
            if not isinstance(self.selected_entry, DetectedListEntry):
                raise TypeError("Match3Target.selected_entry must be a DetectedListEntry or None.")
            if self.source_decision is None or self.frame_ref is None:
                raise ValueError("A selected match-3 entry requires its source decision and frame.")
            if (
                self.selected_entry.frame_ref != self.frame_ref
                or self.selected_entry.source_screen != self.source_decision.effective_screen
                or self.selected_entry.source_layout_id != self.source_decision.layout_id
            ):
                raise ValueError("Selected entry provenance must match the target source frame, screen and layout.")
            if self.selected_entry.campaign_node is not None:
                if self.context is not Match3Context.CAMPAIGN:
                    raise ValueError("Campaign row facts require the campaign context.")
                if self.campaign_node is not None and self.campaign_node != self.selected_entry.campaign_node:
                    raise ValueError("Campaign target facts must match the selected entry.")


@dataclass(frozen=True, slots=True)
class Match3Request:
    """One explicit shared match-3 battle request from a feature caller.

    The caller must select exactly one mode; there is no default battle mode.
    """

    context: Match3Context
    mode: Match3Mode
    target: Match3Target | None = None

    def __post_init__(self) -> None:
        """Require typed context/mode values and a consistent target reference."""

        if not isinstance(self.context, Match3Context):
            raise TypeError("Match3Request.context must be a Match3Context.")
        if not isinstance(self.mode, Match3Mode):
            raise TypeError("Match3Request.mode must be a Match3Mode.")
        if self.target is not None:
            if not isinstance(self.target, Match3Target):
                raise TypeError("Match3Request.target must be a Match3Target or None.")
            if self.target.context is not self.context:
                raise ValueError("Match3Request.target must reference the request's context.")


@dataclass(frozen=True, slots=True)
class Match3Result:
    """The honest terminal result of one shared match-3 execution.

    An unavailable request returns its typed availability; it never carries a
    fabricated battle outcome, victory or feature receipt.
    """

    request: Match3Request
    availability: Match3Availability

    def __post_init__(self) -> None:
        """Require the availability answer to describe the requested pair."""

        if not isinstance(self.request, Match3Request):
            raise TypeError("Match3Result.request must be a Match3Request.")
        if not isinstance(self.availability, Match3Availability):
            raise TypeError("Match3Result.availability must be a Match3Availability.")
        if (
            self.availability.context is not self.request.context
            or self.availability.mode is not self.request.mode
        ):
            raise ValueError("Match3Result.availability must describe the request's context/mode pair.")
