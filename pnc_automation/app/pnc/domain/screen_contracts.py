"""Shared screen-family contracts used across P&C task, flow, and vision layers."""

from __future__ import annotations

from pnc_automation.app.pnc.enums.screen_type import ScreenType

_CAMPAIGN_FLOW_SCREEN_TYPES = frozenset(
    {
        ScreenType.PNC_CAMPAIGN_MAP,
        ScreenType.PNC_CAMPAIGN_STAGE,
        ScreenType.PNC_BATTLE_PREP,
    }
)


def campaign_flow_screen_types() -> frozenset[ScreenType]:
    """Returns the canonical screens that prove the runtime is inside Campaign."""

    return _CAMPAIGN_FLOW_SCREEN_TYPES
