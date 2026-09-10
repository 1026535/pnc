"""Independent screen identity and measured controls for the replacement navigator."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Protocol

from pnc_automation.app.pnc.domain.observation import Bounds, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions, ObservationEnricher
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualScreenRecognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot


class NavigationGuard(ObservationEnricher, Protocol):
    """Reuse content parsing while exposing a separate global interruption gate."""

    def detect_interruption(self, image, *, owned_dismiss_bounds: tuple[Bounds, ...] = ()) -> ObservationAdditions: ...


@dataclass(frozen=True, slots=True)
class NavigationPerception:
    """Recognize without candidate hints, inferred geometry, or content-driven identity.

    Global interruption parsing reuses the existing detector on the normalized
    reference frame. Its controls are never exposed to this non-spending core.
    Unsupported screens remain UNKNOWN; there is no legacy fallback.
    """

    recognizer: VisualScreenRecognizer
    guard: NavigationGuard

    def build(self, screenshot: CapturedScreenshot, *, include_content: bool = False) -> Observation:
        """Return only controls actually matched on an independently identified frame."""
        image = screenshot.image
        visual = self.recognizer.recognize(image)
        normalized = image.resize(self.recognizer.reference_size)
        scale_x, scale_y = normalized.width / image.width, normalized.height / image.height
        owned_dismiss_bounds = tuple(
            Bounds(round(control.bounds.x * scale_x), round(control.bounds.y * scale_y),
                   round(control.bounds.width * scale_x), round(control.bounds.height * scale_y))
            for control in visual.dismiss_controls
        )
        interruption = self.guard.detect_interruption(normalized, owned_dismiss_bounds=owned_dismiss_bounds)
        interrupted = bool(interruption.screen_evidence)
        screens = {item.screen_type for item in visual.evidence}
        screen = next(iter(screens)) if len(screens) == 1 else ScreenType.UNKNOWN
        if interrupted:
            screen = interruption.screen_evidence[0].screen_type
        blocked = screen in {
            ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET,
            ScreenType.PNC_BUILDING_UPGRADE_WARNING,
        }
        controls = {} if interrupted or blocked or screen == ScreenType.UNKNOWN else {
            item.selector_id: item for item in visual.controls
        }
        observation = Observation(
            screen_type=screen, visible_elements=controls, blocking_popup=blocked,
            image_size=image.size, artifact_path=screenshot.artifact_path,
            captured_at=screenshot.captured_at,
            frame_fingerprint=hashlib.sha256(image.tobytes()).hexdigest(),
        )
        if not include_content or interrupted or blocked or screen == ScreenType.UNKNOWN:
            return observation
        content = self.guard.enrich(
            image, screen, controls,
            ObservationRequest(ocr_screen_types=frozenset({screen})),
        )
        if any(item.screen_type != screen for item in content.screen_evidence):
            raise ValueError("Content parser contradicted independent screen identity.")
        # Parsed content cannot create controls, replace identity, or redirect a
        # transition. Keep the existing typed content parsers during migration.
        return replace(
            observation, list_entries=content.list_entries,
            spatial_surface=content.spatial_surface,
            text_field_states=content.text_field_states,
            available_march_slots=content.available_march_slots,
        )
