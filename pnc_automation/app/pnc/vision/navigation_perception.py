"""Independent screen identity and measured controls for the replacement navigator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
import hashlib
from typing import Protocol, runtime_checkable

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, Observation, VisibleElement
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence, is_reviewed_viewport
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationAdditions, ObservationEnricher,
    SelectorEngine,
    _accepts_keyword,
    _matches_to_visible_elements,
    allows_guarded_field_enrichment,
    reconcile_visual_modal_guard,
)
from pnc_automation.app.pnc.vision.observation_diagnostics import ObservationDebugArtifactCollector
from pnc_automation.app.pnc.vision.building_details import filter_building_detail_controls
from pnc_automation.app.pnc.vision.observation_provenance import (
    bind_observation_content,
    bind_visible_elements,
    select_navigation_elements,
    select_template_action_elements,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier, partition_guard_evidence
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.app.pnc.vision.selectors import DetectionKind, SelectorRegistry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import (
    VisualRecognition,
    VisualScreenRecognizer,
    visual_controls_for_decision,
)
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.diagnostics.performance import performance_span
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext


class NavigationGuard(ObservationEnricher, Protocol):
    """Reuse content parsing while exposing a separate global interruption gate."""

    def detect_interruption(
        self, image: Image.Image, *, ocr_context: ObservationOcrContext,
        owned_dismiss_bounds: tuple[Bounds, ...] = (),
        owned_navigation_screen: ScreenType | None = None,
    ) -> ObservationAdditions: ...


@runtime_checkable
class _ContentLabelPublisher(Protocol):
    """Optional registry-backed publication for guards that also produce labels."""

    def content_labels(
        self,
        additions: ObservationAdditions,
    ) -> Mapping[UiElementId, VisibleElement]: ...


@runtime_checkable
class _SelectorRegistryProvider(Protocol):
    """Optional registry access for guards that own selector semantics."""

    selector_registry: SelectorRegistry | None


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
    selector_engine: SelectorEngine | None = None
    debug_artifact_collector: ObservationDebugArtifactCollector = field(
        default_factory=ObservationDebugArtifactCollector, kw_only=True,
    )

    def build(
        self,
        screenshot: CapturedScreenshot,
        *,
        include_content: bool = False,
        request: ObservationRequest | None = None,
    ) -> Observation:
        """Return only controls actually matched on an independently identified frame."""

        active_request = "default" if request is None else "targeted"
        with performance_span(
            "core.perception",
            attributes={"include_content": include_content, "request": active_request},
        ) as measured:
            ocr_context = self.create_ocr_context(screenshot)
            try:
                return self._build_with_ocr_context(
                    screenshot,
                    include_content=include_content,
                    request=request,
                    ocr_context=ocr_context,
                )
            finally:
                if measured is not None:
                    metrics = ocr_context.metrics
                    measured.set_attribute("ocr_requests", metrics.requests)
                    measured.set_attribute("ocr_engine_calls", metrics.engine_calls)
                    measured.set_attribute("ocr_processed_pixels", metrics.processed_pixel_area)
                    measured.set_attribute("ocr_cache_hits", metrics.cache_hits)
                    measured.set_attribute("ocr_fullframe_reuses", metrics.fullframe_reuses)
                    measured.set_attribute("ocr_engine_seconds", metrics.engine_seconds)
                    measured.set_attribute("ocr_diagnostics_count", len(metrics.diagnostics))

    def _build_with_ocr_context(
        self,
        screenshot: CapturedScreenshot,
        *,
        include_content: bool,
        request: ObservationRequest | None,
        ocr_context: ObservationOcrContext,
    ) -> Observation:
        """Performs visual and OCR perception with a caller-owned frame context."""

        if request is not None and not include_content:
            raise ValueError("Explicit navigation observation requests require include_content=True.")
        image = screenshot.image
        session_key = (
            None
            if screenshot.frame_ref is None
            else (
                screenshot.frame_ref.session_id,
                screenshot.frame_ref.session_epoch,
            )
        )
        visual_kwargs = (
            {
                "include_blocking_profiles": False,
                "session_key": session_key,
            }
            if _accepts_keyword(self.recognizer.recognize, "include_blocking_profiles")
            else {}
        )
        base_visual = self.recognizer.recognize(image, **visual_kwargs)
        if base_visual.evidence and all(
            item.screen_type in {
                ScreenType.PNC_POPUP,
                ScreenType.PNC_VIP_DAILY_RESET,
            }
            for item in base_visual.evidence
        ):
            base_visual = VisualRecognition()
        if base_visual.evidence:
            visual = base_visual
        else:
            popup_kwargs = (
                {
                    "blocking_profiles_only": True,
                    "session_key": session_key,
                }
                if _accepts_keyword(self.recognizer.recognize, "blocking_profiles_only")
                else {}
            )
            visual = self.recognizer.recognize(image, **popup_kwargs)
        ocr_context.validate_capture(image, screenshot.frame_ref)
        ocr_context.require_bounded_regions()
        matched_profiles = set(visual.profile_ids)
        matched_screens = {item.screen_type for item in visual.evidence}
        research_detail_owned = (
            matched_profiles == {"research_tree_node_detail"}
            and matched_screens == {ScreenType.PNC_RESEARCH_TREE}
            and any(
                control.selector_id == UiElementId.PNC_RESEARCH_START_BUTTON
                for control in visual.controls
            )
        )
        research_detail_active_owned = (
            "research_tree_node_detail_active" in matched_profiles
            and matched_profiles <= {
                "research_tree_node_detail",
                "research_tree_node_detail_active",
            }
            and matched_screens == {ScreenType.PNC_RESEARCH_TREE}
            and not any(
                control.selector_id == UiElementId.PNC_RESEARCH_START_BUTTON
                for control in visual.controls
            )
        )
        research_detail_max_owned = (
            matched_profiles == {"research_tree_node_detail_max"}
            and matched_screens == {ScreenType.PNC_RESEARCH_TREE}
            and not visual.controls
        )
        research_queue_owned = (
            matched_screens == {ScreenType.PNC_RESEARCH_QUEUE}
            and any(
                control.selector_id == UiElementId.PNC_RESEARCH_QUEUE_CLOSE
                for control in visual.dismiss_controls
            )
        )
        owned_dismiss_bounds = tuple(control.bounds for control in visual.dismiss_controls)
        owned_navigation_screen = (
            ScreenType.PNC_RESEARCH_TREE
            if research_detail_owned or research_detail_active_owned or research_detail_max_owned
            else ScreenType.PNC_RESEARCH_QUEUE if research_queue_owned
            else None
        )
        if isinstance(self.guard, PncObservationEnricher):
            interruption = self.guard.detect_interruption(
                image,
                ocr_context=ocr_context,
                owned_dismiss_bounds=owned_dismiss_bounds,
                owned_navigation_screen=owned_navigation_screen,
                include_generic_visual_fallback=visual.needs_generic_popup_close,
                require_bounded_modal_evidence=bool(base_visual.evidence),
            )
        else:
            interruption = self.guard.detect_interruption(
                image,
                ocr_context=ocr_context,
                owned_dismiss_bounds=owned_dismiss_bounds,
                owned_navigation_screen=owned_navigation_screen,
            )
        interruption = reconcile_visual_modal_guard(visual, interruption)
        evidence, background_evidence = partition_guard_evidence(
            visual.evidence, interruption.screen_evidence,
        )
        if not evidence and _is_near_black_frame(image):
            evidence = (ScreenEvidence(ScreenType.PNC_LOADING, "near_black_startup_frame"),)
        decision = self.screen_classifier.decide(
            {}, evidence=evidence,
            background_evidence=background_evidence,
            guard=interruption.guard_verdict,
            viewport_reviewed=is_reviewed_viewport(image.size),
        )
        interrupted = bool(interruption.screen_evidence)
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
            controls = visual_controls_for_decision(visual, decision)
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
        content_request = request or (
            ObservationRequest.chat_transcript_observation()
            if screen == ScreenType.PNC_CHAT
            else ObservationRequest.source_screen_retry(screen)
        )
        if (
            not include_content
            or not decision.action_eligible
            or (interrupted and not allows_guarded_field_enrichment(content_request, interruption))
        ):
            # Without content there is no building phase proof. Shared Upgrade
            # pixels cannot advertise either phase-owned generic action yet.
            observation = replace(
                observation,
                visible_elements=filter_building_detail_controls(observation.visible_elements, None),
            )
            return self._finish(screenshot, observation, ocr_context, visual.profile_ids)
        content = self.guard.enrich(
            image, screen, controls, content_request,
            ocr_context=ocr_context, ocr_regions={},
            layout_id=decision.layout_id,
        )
        if any(item.screen_type != screen for item in content.screen_evidence):
            raise ValueError("Content parser contradicted independent screen identity.")
        content_labels = bind_visible_elements(
            self.guard.content_labels(content)
            if isinstance(self.guard, _ContentLabelPublisher) else {},
            frame_ref=screenshot.frame_ref,
            source_screen=screen,
            source_layout_id=decision.layout_id,
        )
        selector_registry = (
            self.guard.selector_registry
            if isinstance(self.guard, _SelectorRegistryProvider)
            else None
        )
        navigation_elements = (
            bind_visible_elements(
                select_navigation_elements(
                    content.visible_elements,
                    selector_registry=selector_registry,
                    reserved_selector_ids=visual.control_selector_ids,
                ),
                frame_ref=screenshot.frame_ref,
                source_screen=screen,
                source_layout_id=decision.layout_id,
            )
            if not interrupted
            else {}
        )
        measured_action_elements = (
            bind_visible_elements(
                select_template_action_elements(
                    {
                        **self._detect_template_action_elements(
                            image,
                            screen,
                            selector_registry=selector_registry,
                            reserved_selector_ids=visual.control_selector_ids,
                            published_selector_ids=frozenset(observation.visible_elements),
                            ocr_context=ocr_context,
                        ),
                        **content.visible_elements,
                    },
                    selector_registry=selector_registry,
                    screen_type=screen,
                    reserved_selector_ids=visual.control_selector_ids,
                ),
                frame_ref=screenshot.frame_ref,
                source_screen=screen,
                source_layout_id=decision.layout_id,
            )
            if not interrupted
            else {}
        )
        # Parsed content cannot create controls, replace identity, or redirect a
        # transition. Keep the existing typed content parsers during migration.
        # Measured navigation controls the profile does not own ride alongside
        # the visual controls (e.g. the Alliance tab, which has no stable icon
        # template) since they are OCR-anchored on this frame and dispatch-gated
        # by reviewed safe outcomes. Screen-declared template action controls
        # the profile does not own publish through the same current-frame
        # provenance channel.
        observation = replace(
            observation,
            visible_elements=filter_building_detail_controls(
                {
                    **navigation_elements,
                    **measured_action_elements,
                    **observation.visible_elements,
                    **content_labels,
                },
                content.building_detail,
            ),
        )
        observation = bind_observation_content(
            observation, content,
            frame_ref=screenshot.frame_ref,
            source_screen=screen,
            source_layout_id=decision.layout_id,
        )
        return self._finish(screenshot, observation, ocr_context, visual.profile_ids)

    def _detect_template_action_elements(
        self,
        image: Image.Image,
        screen: ScreenType,
        *,
        selector_registry: SelectorRegistry | None,
        reserved_selector_ids: frozenset[UiElementId],
        published_selector_ids: frozenset[UiElementId],
        ocr_context: ObservationOcrContext,
    ) -> dict[UiElementId, VisibleElement]:
        """Measures screen-declared template action controls outside the profile.

        Detection runs only for ``action``/``template`` ids declared on this
        screen that the visual profile does not own and the observation has not
        already published, so the channel cannot duplicate or replace measured
        visual controls.
        """

        if selector_registry is None or self.selector_engine is None:
            return {}
        selector_ids = tuple(
            selector.id
            for selector in selector_registry.for_screen(screen)
            if selector.detection_kind == DetectionKind.TEMPLATE
            and selector.interaction_kind == SelectorInteractionKind.ACTION
            and selector.id not in reserved_selector_ids
            and selector.id not in published_selector_ids
        )
        if not selector_ids:
            return {}
        return _matches_to_visible_elements(
            self.selector_engine.detect(
                image,
                selector_registry,
                selector_ids=selector_ids,
                ocr_context=ocr_context,
            )
        )

    def _finish(
        self, screenshot: CapturedScreenshot, observation: Observation,
        ocr_context: ObservationOcrContext, profile_ids: tuple[str, ...],
    ) -> Observation:
        """Report remaining recognition gaps using this capture's existing evidence."""

        self.debug_artifact_collector.persist_recognition_gap(
            screenshot=screenshot, observation=observation, ocr_context=ocr_context,
            profile_ids=profile_ids,
        )
        return observation


def _is_near_black_frame(image: Image.Image) -> bool:
    """Recognize only an almost entirely black startup frame as passive loading."""

    grayscale = image.convert("L")
    _minimum, maximum = grayscale.getextrema()
    # Requiring every pixel to be very dark prevents sparse bright UI or a
    # partially rendered UNKNOWN screen from entering the loading settle path.
    return maximum <= 12
