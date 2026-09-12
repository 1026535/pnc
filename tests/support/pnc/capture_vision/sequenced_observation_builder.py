"""Synthetic SequencedObservationBuilder fixture."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.vision.observation_request import ObservationRequest



@dataclass(slots=True)
class _SequencedObservationBuilder:
    """Returns a pre-seeded sequence of built observations."""

    observations: list

    def build(self, screenshot: object, *, request: ObservationRequest | None = None) -> object:
        """Returns the next queued observation for one capture request."""

        del screenshot, request
        if not self.observations:
            raise AssertionError("No observation queued for ObservationService.")
        return self.observations.pop(0)
