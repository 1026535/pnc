"""Independent screen identity and measured controls for the replacement navigator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
from typing import Protocol

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, Observation, VisibleElement
from pnc_automation.app.pnc.domain.popup import PopupDismissCandidate, PopupOverlayObservation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
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
    reference frame. Background controls are never exposed while an
    interruption owns the frame, but measured interruption controls remain
    available to the recovery authorization boundary. Unsupported screens
    remain UNKNOWN; there is no legacy fallback.
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
        popup_overlay = _rescale_popup_overlay(interruption.popup_overlay, target_size=image.size)
        interrupted = bool(interruption.screen_evidence)
        screens = {item.screen_type for item in visual.evidence}
        screen = next(iter(screens)) if len(screens) == 1 else ScreenType.UNKNOWN
        if interrupted:
            screen = interruption.screen_evidence[0].screen_type
        elif not visual.evidence and _is_near_black_frame(image):
            screen = ScreenType.PNC_LOADING
        blocked = popup_overlay is not None or screen in {
            ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET,
            ScreenType.PNC_BUILDING_UPGRADE_WARNING,
        }
        if interrupted or blocked or screen == ScreenType.UNKNOWN:
            # A blocking frame owns the observation. Preserve only controls
            # measured by the interruption detector; background visual
            # controls must never leak into popup recovery.
            controls = _rescale_visible_elements(
                interruption.visible_elements,
                source_size=self.recognizer.reference_size,
                target_size=image.size,
            ) if interrupted or blocked else {}
        else:
            controls = {item.selector_id: item for item in visual.controls}
        observation = Observation(
            screen_type=screen, visible_elements=controls, blocking_popup=blocked,
            popup_overlay=popup_overlay,
            image_size=image.size, artifact_path=screenshot.artifact_path,
            captured_at=screenshot.captured_at,
            frame_fingerprint=hashlib.sha256(image.tobytes()).hexdigest(),
        )
        if not include_content or interrupted or blocked or screen == ScreenType.UNKNOWN:
            return observation
        content_request = (
            ObservationRequest.chat_transcript_observation()
            if screen == ScreenType.PNC_CHAT
            else ObservationRequest(ocr_screen_types=frozenset({screen}))
        )
        content = self.guard.enrich(image, screen, controls, content_request)
        if any(item.screen_type != screen for item in content.screen_evidence):
            raise ValueError("Content parser contradicted independent screen identity.")
        # Parsed content cannot create controls, replace identity, or redirect a
        # transition. Keep the existing typed content parsers during migration.
        return replace(
            observation, list_entries=content.list_entries,
            spatial_surface=content.spatial_surface,
            current_castle=content.current_castle,
            current_castle_evidence=content.current_castle_evidence,
            mailbox_type=content.mailbox_type,
            mailbox_empty=content.mailbox_empty,
            text_field_states=content.text_field_states,
            available_march_slots=content.available_march_slots,
            active_chat_channel=content.active_chat_channel,
            chat_draft_empty=content.chat_draft_empty,
            chat_draft_text=content.chat_draft_text,
        )


def _rescale_visible_elements(
    elements: Mapping[UiElementId, VisibleElement],
    *,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> dict[UiElementId, VisibleElement]:
    """Project interruption controls from recognizer reference pixels to the capture."""

    if source_size == target_size:
        return dict(elements)

    return {
        selector_id: replace(
            element,
            bounds=_rescale_bounds(element.bounds, source_size=source_size, target_size=target_size),
            action_point=_rescale_point(element.action_point, source_size=source_size, target_size=target_size),
        )
        for selector_id, element in elements.items()
    }


def _is_near_black_frame(image: Image.Image) -> bool:
    """Recognize only an almost entirely black startup frame as passive loading."""

    grayscale = image.convert("L")
    _minimum, maximum = grayscale.getextrema()
    # Requiring every pixel to be very dark prevents sparse bright UI or a
    # partially rendered UNKNOWN screen from entering the loading settle path.
    return maximum <= 12


def _rescale_bounds(
    bounds: Bounds,
    *,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> Bounds:
    """Project one rectangle between the normalized and captured image spaces."""

    source_width, source_height = source_size
    target_width, target_height = target_size
    left = round(bounds.x * target_width / source_width)
    top = round(bounds.y * target_height / source_height)
    right = round((bounds.x + bounds.width) * target_width / source_width)
    bottom = round((bounds.y + bounds.height) * target_height / source_height)
    return Bounds(left, top, max(1, right - left), max(1, bottom - top))


def _rescale_point(
    point: tuple[int, int] | None,
    *,
    source_size: tuple[int, int],
    target_size: tuple[int, int],
) -> tuple[int, int] | None:
    """Project one measured action point between image coordinate spaces."""

    if point is None:
        return None
    source_width, source_height = source_size
    target_width, target_height = target_size
    return (
        round(point[0] * target_width / source_width),
        round(point[1] * target_height / source_height),
    )


def _rescale_popup_overlay(
    overlay: PopupOverlayObservation | None,
    *,
    target_size: tuple[int, int],
) -> PopupOverlayObservation | None:
    """Translate normalized guard evidence back into the captured screenshot's coordinates."""

    if overlay is None or overlay.image_size == target_size:
        return overlay
    candidates = tuple(
        PopupDismissCandidate(
            control_kind=candidate.control_kind,
            bounds=_rescale_bounds(
                candidate.bounds,
                source_size=overlay.image_size,
                target_size=target_size,
            ),
            action_point=_rescale_point(
                candidate.action_point,
                source_size=overlay.image_size,
                target_size=target_size,
            ),
            confidence=candidate.confidence,
            evidence_kind=candidate.evidence_kind,
            extracted_text=candidate.extracted_text,
            reason=candidate.reason,
        )
        for candidate in overlay.candidates
    )
    return PopupOverlayObservation(
        image_size=target_size,
        modal_bounds=None if overlay.modal_bounds is None else _rescale_bounds(
            overlay.modal_bounds,
            source_size=overlay.image_size,
            target_size=target_size,
        ),
        layout_id=overlay.layout_id,
        candidates=candidates,
        confidence=overlay.confidence,
        evidence_kind=overlay.evidence_kind,
        reason=overlay.reason,
    )
