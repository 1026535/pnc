"""Synthetic SequencedObservationBuilder fixture."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, UnavailableOcrService



@dataclass(slots=True)
class _SequencedObservationBuilder:
    """Returns a pre-seeded sequence of built observations."""

    observations: list

    def create_ocr_context(self, screenshot: object) -> ObservationOcrContext:
        return ObservationOcrContext(
            screenshot.image,
            UnavailableOcrService(),
            screenshot.frame_ref,
            "test",
        )

    def build(
        self,
        screenshot: object,
        *,
        request: ObservationRequest | None = None,
        ocr_context: ObservationOcrContext | None = None,
    ) -> object:
        """Returns the next queued observation for one capture request."""

        del screenshot, request, ocr_context
        if not self.observations:
            raise AssertionError("No observation queued for ObservationService.")
        return self.observations.pop(0)
