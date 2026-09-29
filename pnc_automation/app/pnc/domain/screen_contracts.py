"""Shared screen-family contracts used across P&C task, flow, and vision layers."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.screen_type import ScreenType

_CAMPAIGN_FLOW_SCREEN_TYPES = frozenset(
    {
        ScreenType.PNC_CAMPAIGN_MAP,
        ScreenType.PNC_CAMPAIGN_CHAPTER,
        ScreenType.PNC_CAMPAIGN_STAGE,
    }
)


def campaign_flow_screen_types() -> frozenset[ScreenType]:
    """Returns the canonical screens that prove the runtime is inside Campaign.

    Battle-preparation and Hero Formation surfaces are shared across game
    modes, so they cannot prove Campaign context on their own.
    """

    return _CAMPAIGN_FLOW_SCREEN_TYPES
