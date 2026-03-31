"""P&C-specific vision models."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds


@dataclass(frozen=True, slots=True)
class SelectorMatch:
    """Represents one selector detected by the P&C vision layer."""

    selector_id: UiElementId
    bounds: Bounds
    confidence: float
    source_kind: VisibleElementSourceKind = VisibleElementSourceKind.TEMPLATE
    extracted_text: str | None = None

