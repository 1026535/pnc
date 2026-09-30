"""Shared match-3 battle component contract and its M0 unavailable implementation."""

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
    "FormationPreparationError",
    "FormationPreparationProof",
    "Match3Component",
    "Match3Session",
    "Match3UnavailableError",
    "UnavailableMatch3Component",
    "require_formation_preparation_proof",
    "require_match3_available",
]
