"""Clear-guard observation enricher for selector-only builder fixtures."""

from __future__ import annotations

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.vision.observation_builder import DefaultObservationEnricher, ObservationAdditions
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest


class _ClearObservationEnricher(DefaultObservationEnricher):
    """Explicitly proves a clear guard for selector-only builder fixtures."""

    def recognize_guards(
        self,
        image: Image.Image,
        request: ObservationRequest,
        *,
        ocr_context,
        owned_dismiss_bounds=(),
    ) -> ObservationAdditions:
        del image, request, ocr_context, owned_dismiss_bounds
        return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)
