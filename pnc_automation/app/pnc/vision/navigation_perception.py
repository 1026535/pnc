"""Independent screen identity and measured controls for the replacement navigator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import hashlib
from typing import Protocol

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, Observation
from pnc_automation.app.pnc.domain.screen_decision import ScreenEvidence, is_reviewed_viewport
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationAdditions, ObservationEnricher,
)
from pnc_automation.app.pnc.vision.observation_provenance import bind_list_entry, bind_visible_elements
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualScreenRecognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext


class NavigationGuard(ObservationEnricher, Protocol):
    """Reuse content parsing while exposing a separate global interruption gate."""

    def detect_interruption(
        self, image: Image.Image, *, ocr_context: ObservationOcrContext,
        owned_dismiss_bounds: tuple[Bounds, ...] = (),
    ) -> ObservationAdditions: ...


@dataclass(frozen=True, slots=True)
class NavigationPerception:
    """Recognize without candidate hints, inferred geometry, or content-driven identity.

    Global interruption parsing and content share the captured frame OCR context.
    Background controls are never exposed while an
    interruption owns the frame, but measured interruption controls remain
    available to the recovery authorization boundary. Unsupported screens
    remain UNKNOWN; there is no legacy fallback.
    """

    recognizer: VisualScreenRecognizer
    guard: NavigationGuard
    screen_classifier: ScreenClassifier
    create_ocr_context: Callable[[CapturedScreenshot], ObservationOcrContext]

    def build(self, screenshot: CapturedScreenshot, *, include_content: bool = False) -> Observation:
        """Return only controls actually matched on an independently identified frame."""
        image = screenshot.image
        visual = self.recognizer.recognize(image)
        ocr_context = self.create_ocr_context(screenshot)
        ocr_context.validate_capture(image, screenshot.frame_ref)
        interruption = self.guard.detect_interruption(
            image, ocr_context=ocr_context,
            owned_dismiss_bounds=tuple(control.bounds for control in visual.dismiss_controls),
        )
        evidence = tuple(visual.evidence) + tuple(interruption.screen_evidence)
        if not evidence and _is_near_black_frame(image):
            evidence = (ScreenEvidence(ScreenType.PNC_LOADING, "near_black_startup_frame"),)
        interrupted = bool(interruption.screen_evidence)
        decision = self.screen_classifier.decide(
            {}, evidence=interruption.screen_evidence if interrupted else evidence,
            background_evidence=visual.evidence if interrupted else (),
            guard=interruption.guard_verdict,
            viewport_reviewed=is_reviewed_viewport(image.size),
        )
        screen = decision.effective_screen
        if screen in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            controls = {}
        elif interrupted:
            controls = dict(interruption.visible_elements)
            if screen in {item.screen_type for item in visual.evidence}:
                # Keep interruption ownership even when a visual popup profile
                # has no controls. A matched template may refine only controls
                # already proved by the foreground guard (e.g. dialog Close).
                controls.update({
                    item.selector_id: item for item in visual.controls
                    if item.selector_id in controls
                    and controls[item.selector_id].bounds.contains_point(
                        item.action_point or item.bounds.center()
                    )
                })
        else:
            controls = {item.selector_id: item for item in visual.controls}
        controls = bind_visible_elements(
            controls, frame_ref=screenshot.frame_ref, source_screen=screen,
            source_layout_id=decision.layout_id,
        )
        observation = Observation(
            decision=decision,
            visible_elements=controls,
            popup_overlay=interruption.popup_overlay,
            image_size=image.size, artifact_path=screenshot.artifact_path,
            captured_at=screenshot.captured_at,
            frame_fingerprint=hashlib.sha256(image.tobytes()).hexdigest(),
            frame_ref=screenshot.frame_ref,
        )
        if not include_content or interrupted or not decision.action_eligible:
            return observation
        content_request = ObservationRequest(ocr_screen_types=frozenset({screen}))
        content = self.guard.enrich(
            image, screen, controls, content_request,
            ocr_context=ocr_context, ocr_regions={},
        )
        if any(item.screen_type != screen for item in content.screen_evidence):
            raise ValueError("Content parser contradicted independent screen identity.")
        # Parsed content cannot create controls, replace identity, or redirect a
        # transition. Keep the existing typed content parsers during migration.
        return replace(
            observation, list_entries=tuple(
                bind_list_entry(entry, frame_ref=screenshot.frame_ref, source_screen=screen,
                                     source_layout_id=decision.layout_id)
                for entry in content.list_entries
            ),
            spatial_surface=content.spatial_surface,
            current_castle=content.current_castle,
            current_castle_evidence=content.current_castle_evidence,
            text_field_states=content.text_field_states,
            available_march_slots=content.available_march_slots,
        )


def _is_near_black_frame(image: Image.Image) -> bool:
    """Recognize only an almost entirely black startup frame as passive loading."""

    grayscale = image.convert("L")
    _minimum, maximum = grayscale.getextrema()
    # Requiring every pixel to be very dark prevents sparse bright UI or a
    # partially rendered UNKNOWN screen from entering the loading settle path.
    return maximum <= 12
