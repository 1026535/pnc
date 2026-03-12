"""Typed observation requests that control OCR-backed enrichment cost."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.vision.pnc_ocr_capabilities import runtime_screen_family_ocr_types
from pnc_automation.vision.selectors import ClickOutcome


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """Describes which OCR-backed fact families are allowed for one observation."""

    ocr_screen_types: frozenset[ScreenType] = frozenset()
    include_popup_guard: bool = False
    include_loading_guard: bool = False

    @classmethod
    def base(cls) -> "ObservationRequest":
        """Returns the cheap selector-and-geometry-only observation request."""

        return cls()

    @classmethod
    def full_runtime_default(cls) -> "ObservationRequest":
        """Returns the broad full-frame OCR request used for unattended runtime observations."""

        return cls(
            ocr_screen_types=runtime_screen_family_ocr_types(),
            include_popup_guard=True,
            include_loading_guard=True,
        )

    @classmethod
    def runtime_default(cls) -> "ObservationRequest":
        """Returns the legacy alias for the canonical full-frame runtime request."""

        return cls.full_runtime_default()

    @classmethod
    def navigation_follow_up(cls, reviewed_outcomes: Sequence[ClickOutcome]) -> "ObservationRequest":
        """Returns the narrow OCR scope used after one reviewed navigation tap."""

        return cls(
            ocr_screen_types=frozenset(
                outcome.target_screen
                for outcome in reviewed_outcomes
                if outcome.target_screen not in {None, ScreenType.PNC_LOADING, ScreenType.PNC_POPUP}
            ),
            include_popup_guard=True,
            include_loading_guard=True,
        )

    @classmethod
    def source_screen_retry(cls, screen_type: ScreenType) -> "ObservationRequest":
        """Returns the OCR scope used to re-resolve one selector on its source screen."""

        return cls(ocr_screen_types=frozenset({screen_type}))

    def requires_ocr(self, screen_type: ScreenType) -> bool:
        """Returns whether the request needs OCR for the current coarse screen state."""

        if self.include_popup_guard:
            return True
        if self.include_loading_guard and screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            return True
        if screen_type == ScreenType.UNKNOWN:
            return bool(self.ocr_screen_types)
        return screen_type in self.ocr_screen_types

    def allows_screen(self, screen_type: ScreenType) -> bool:
        """Returns whether the request allows OCR builders for the requested screen family."""

        return screen_type in self.ocr_screen_types
