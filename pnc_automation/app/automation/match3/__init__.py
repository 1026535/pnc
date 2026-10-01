"""Shared match-3 battle component contract and its M0 unavailable implementation."""

from pnc_automation.app.automation.match3.battle_start_authority import (
    CampaignBattleStartAuthority,
    require_campaign_battle_start_authority,
)
from pnc_automation.app.automation.match3.battle_start_preflight import (
    Match3ContinuationObservation,
    Match3ContinuationState,
    Match3StartBudget,
    Match3StartPreflight,
    Match3StartPreflightError,
    require_match3_start_preflight,
)
from pnc_automation.app.automation.match3.component import (
    Match3Component,
    Match3Session,
    Match3UnavailableError,
    UnavailableMatch3Component,
    require_match3_available,
)
from pnc_automation.app.automation.match3.formation_preparation import (
    FORMATION_PREPARATION_LAYOUT_ID,
    FormationPreparationError,
    FormationPreparationProof,
    require_formation_preparation_proof,
)

__all__ = [
    "FORMATION_PREPARATION_LAYOUT_ID",
    "CampaignBattleStartAuthority",
    "FormationPreparationError",
    "FormationPreparationProof",
    "Match3Component",
    "Match3ContinuationObservation",
    "Match3ContinuationState",
    "Match3StartBudget",
    "Match3StartPreflight",
    "Match3StartPreflightError",
    "Match3Session",
    "Match3UnavailableError",
    "UnavailableMatch3Component",
    "require_campaign_battle_start_authority",
    "require_formation_preparation_proof",
    "require_match3_available",
    "require_match3_start_preflight",
]
