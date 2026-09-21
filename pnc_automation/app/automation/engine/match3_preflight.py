"""Match-3 request checks for the current authored/direct task dispatcher."""

from __future__ import annotations

from typing import Any

from pnc_automation.app.automation.match3 import (
    Match3Component,
    Match3UnavailableError,
    require_match3_available,
)
from pnc_automation.app.pnc.domain.match3 import (
    Match3Availability,
    Match3AvailabilityStatus,
    Match3Context,
    Match3Request,
)
from pnc_automation.app.pnc.domain.policy_models import CampaignPolicy


def require_match3_task_available(
    component: Match3Component,
    parsed_params: object,
    **details: Any,
) -> None:
    """Reject battle requests until both the policy and task binding exist.

    Component availability does not qualify the legacy preparation task to
    execute a battle. Package 04 must replace this binding refusal when it
    composes the V14 adapter into the canonical Campaign dispatcher.
    """

    if not isinstance(parsed_params, CampaignPolicy) or parsed_params.battle_mode is None:
        return
    request = Match3Request(context=Match3Context.CAMPAIGN, mode=parsed_params.battle_mode)
    require_match3_available(component, request, **details)
    raise Match3UnavailableError(
        Match3Availability(
            context=request.context,
            mode=request.mode,
            status=Match3AvailabilityStatus.NOT_IMPLEMENTED,
            reason="The Campaign task has no match-3 execution adapter; preparation cannot satisfy a battle request.",
        ),
        **details,
    )
