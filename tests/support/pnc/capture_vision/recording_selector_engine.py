"""Synthetic RecordingSelectorEngine fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry



@dataclass(slots=True)
class _RecordingSelectorEngine:
    """Records selector-engine requests so observation scans stay scoped."""

    responses: list[tuple[SelectorMatch, ...]]
    requested_selector_ids: list[tuple[UiElementId, ...]] = field(default_factory=list)

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: tuple[UiElementId, ...] | None = None,
    ) -> tuple[SelectorMatch, ...]:
        """Records one selector request and returns the queued response."""

        del image, registry
        self.requested_selector_ids.append(()) if selector_ids is None else self.requested_selector_ids.append(tuple(selector_ids))
        if not self.responses:
            raise AssertionError("No selector-engine response queued.")
        return self.responses.pop(0)
