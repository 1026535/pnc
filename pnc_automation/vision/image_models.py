"""Shared vision-layer match models."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.pnc.observation import Bounds, SelectorResolutionKind
from pnc_automation.pnc.ui_element_id import UiElementId


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    """Represents one template hit within a screenshot."""

    bounds: Bounds
    confidence: float


@dataclass(frozen=True, slots=True)
class SelectorMatch:
    """Represents one selector detected by the vision layer."""

    selector_id: UiElementId
    bounds: Bounds
    confidence: float
    resolution_kind: SelectorResolutionKind
    strategy_index: int
    extracted_text: str | None = None
