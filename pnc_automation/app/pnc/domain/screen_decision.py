"""Immutable screen identity and guard decisions shared by perception and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType


REVIEWED_VIEWPORTS = frozenset({(540, 960), (900, 1600)})


def is_reviewed_viewport(image_size: tuple[int, int]) -> bool:
    """Returns whether geometry has a reviewed 9:16 viewport calibration."""

    return image_size in REVIEWED_VIEWPORTS


class GuardVerdict(StrEnum):
    """Outcome of the global popup/loading/update guard stage."""

    CLEAR = "clear"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"
    NOT_EVALUATED = "not_evaluated"


# These screens own an overlay surface.  Their controls may be dispatched only
# after the overlay itself is proved; background controls remain unavailable.
BLOCKING_SCREEN_TYPES = frozenset(
    {
        ScreenType.PNC_POPUP,
        ScreenType.PNC_VIP_DAILY_RESET,
        ScreenType.PNC_BUILDING_UPGRADE_WARNING,
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
        ScreenType.PNC_BUILD_SPEEDUP_CONFIRM,
        ScreenType.PNC_MAIL_COMPOSE_POPUP,
        ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
        ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
    }
)


@dataclass(frozen=True, slots=True)
class ScreenEvidence:
    """One independent, typed conclusion about the current screen."""

    screen_type: ScreenType
    reason: str
    layout_id: str | None = None
    layout_revision: int | None = None


@dataclass(frozen=True, slots=True)
class ScreenDecision:
    """The sole immutable authority for screen identity and action guards."""

    base_screen: ScreenType
    effective_screen: ScreenType
    layout_id: str | None = None
    guard: GuardVerdict = GuardVerdict.NOT_EVALUATED
    evidence: tuple[ScreenEvidence, ...] = ()
    coordinate_only: bool = False

    @property
    def action_eligible(self) -> bool:
        """Returns whether ordinary UI actions may use this decision."""

        return (
            not self.coordinate_only
            and self.guard in {GuardVerdict.CLEAR, GuardVerdict.BLOCKED}
            and self.effective_screen not in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}
        )
