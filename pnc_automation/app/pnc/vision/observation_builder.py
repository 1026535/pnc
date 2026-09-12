"""Builds typed observations from screenshots and selector detections."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from PIL import Image

from pnc_automation.core.errors import ScreenClassificationError, SelectorResolutionError
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactKind,
    ObservationArtifactOwner,
    ObservationArtifactSelection,
    ResolvedObservationArtifactPolicy,
    resolve_observation_artifact_policy,
)
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.app.authoring.config.models import CastleIdentity, CastleRosterOrdering, PncAccountCastleRosterConfig
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.mail import MailboxType, compose_text_field_selector_ids
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    PopupOverlayObservation,
    SpatialSurfaceObservation,
    VisibleElement,
    VisibleElementSourceKind,
    castle_identity_from_entry,
    castle_entry_identity_matches,
)
from pnc_automation.app.pnc.domain.screen_decision import (
    GuardVerdict,
    ScreenDecision,
    ScreenEvidence,
    is_reviewed_viewport,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.observation_provenance import bind_list_entry, bind_visible_elements
from pnc_automation.app.pnc.vision.observation_request import (
    ObservationRequest,
    world_map_coordinate_dialog_text_field_selector_ids,
)
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    OcrRegionRead,
    OcrRegionPlan,
    compile_ocr_region_plans,
    execute_ocr_region_plans,
)
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrReadPurpose,
    OcrService,
    UnavailableOcrService,
)
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import DetectionKind, SelectorRegistry
from pnc_automation.app.pnc.vision.world_map_coordinates import read_world_coordinate_bar_text, world_coordinate_text_matches
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition, VisualScreenRecognizer
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame

class ObservationEnricher(Protocol):
    """Adds higher-level facts after basic selector detection."""

    def recognize_guards(
        self,
        image: Image.Image,
        request: ObservationRequest,
        *,
        ocr_context: ObservationOcrContext,
    ) -> "ObservationAdditions":
        """Recognizes global blocking/loading guards independently of request scope."""

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
        request: ObservationRequest,
        *,
        ocr_context: ObservationOcrContext,
        ocr_regions: Mapping[UiElementId, OcrRegionRead],
    ) -> "ObservationAdditions":
        """Returns derived observation additions."""


@dataclass(frozen=True, slots=True)
class ObservationAdditions:
    """Derived observation facts produced after primary screen classification."""

    visible_elements: Mapping[UiElementId, VisibleElement] = field(default_factory=dict)
    suppress_geometry_selector_ids: frozenset[UiElementId] = frozenset()
    list_entries: tuple[DetectedListEntry, ...] = ()
    spatial_surface: SpatialSurfaceObservation | None = None
    screen_evidence: tuple[ScreenEvidence, ...] = ()
    popup_overlay: PopupOverlayObservation | None = None
    guard_verdict: GuardVerdict = GuardVerdict.NOT_EVALUATED
    current_castle: CastleIdentity | None = None
    current_castle_evidence: CurrentCastleEvidenceKind | None = None
    current_pnc_account_id: str | None = None
    available_march_slots: int | None = None
    active_chat_channel: ChatChannel | None = None
    profile_player_name: str | None = None
    mailbox_type: MailboxType | None = None
    mailbox_empty: bool | None = None
    empty_mailboxes: frozenset[MailboxType] = frozenset()
    text_field_states: Mapping[UiElementId, ObservedTextFieldState] = field(default_factory=dict)
    chat_draft_empty: bool | None = None
    chat_draft_text: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationSelectorDetectionPlan:
    """Defines the initial selector scope for one observation build request."""

    selector_ids: tuple[UiElementId, ...]
    source: str


@dataclass(frozen=True, slots=True)
class CapturedObservation:
    """Pairs one persisted screenshot capture with the built typed observation."""

    screenshot: CapturedScreenshot
    observation: Observation
    ocr_context: ObservationOcrContext | None = None


@dataclass(slots=True)
class DefaultObservationEnricher:
    """Default no-op enricher used until screenshot-specific extraction is added."""

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
        request: ObservationRequest,
        *,
        ocr_context: ObservationOcrContext,
        ocr_regions: Mapping[UiElementId, OcrRegionRead],
    ) -> ObservationAdditions:
        """Returns an empty enrichment result."""

        del image, screen_type, visible_elements, request, ocr_context, ocr_regions
        return ObservationAdditions()

    def recognize_guards(
        self,
        image: Image.Image,
        request: ObservationRequest,
        *,
        ocr_context: ObservationOcrContext,
    ) -> ObservationAdditions:
        """Leaves guard recognition explicitly unevaluated for test doubles."""

        del image, request, ocr_context
        return ObservationAdditions()


class SelectorEngine(Protocol):
    """Detects selectors from a screenshot using the registry metadata."""

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: Sequence[UiElementId] | None = None,
        ocr_context: ObservationOcrContext | None = None,
    ) -> Sequence[SelectorMatch]:
        """Returns all selectors detected in the image."""


@dataclass(slots=True)
class ObservationDebugArtifactCollector:
    """Persists debug-only OCR sidecars that capture lines the runtime could not yet classify."""

    def persist_unidentified_ocr_sidecar(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
    ) -> None:
        """Writes one sidecar containing unmatched OCR lines next to the persisted screenshot artifact."""

        artifact_path = screenshot.artifact_path
        if artifact_path is None:
            return
        recognized_texts = _recognized_ocr_text_hints(observation)
        unidentified_lines = _unidentified_ocr_lines(
            lines=ocr_context.read_lines(
                screenshot.image,
                purpose=OcrReadPurpose.DEBUG,
                detail="debug_unidentified_ocr",
            ),
            recognized_texts=recognized_texts,
        )
        if not unidentified_lines:
            return
        sidecar_path = artifact_path.with_name(f"{artifact_path.stem}_unidentified_ocr.json")
        sidecar_path.write_text(
            json.dumps(
                {
                    "artifact_path": str(artifact_path),
                    "screen_type": observation.screen_type.value,
                    "captured_at": observation.captured_at.isoformat(),
                    "recognized_text_hints": sorted(recognized_texts),
                    "unidentified_ocr_lines": [
                        {
                            "text": line.text,
                            "normalized_text": normalize_ocr_text(line.text),
                            "bounds": {
                                "x": line.bounds.x,
                                "y": line.bounds.y,
                                "width": line.bounds.width,
                                "height": line.bounds.height,
                            },
                            "confidence": line.confidence,
                        }
                        for line in unidentified_lines
                    ],
                },
                indent=2,
                ensure_ascii=True,
            ),
            encoding="utf-8",
        )


@dataclass(slots=True)
class ImageSelectorEngine:
    """Detects selectors using template matching and optional OCR."""

    template_matcher: OpenCvTemplateMatcher
    # Kept as a compatibility injection point for older fixture builders; OCR
    # ownership remains with ObservationBuilder's frame-scoped context.
    ocr_service: OcrService | None = None

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: Sequence[UiElementId] | None = None,
        ocr_context: ObservationOcrContext,
    ) -> Sequence[SelectorMatch]:
        """Detects selectors supported by the configured engines."""

        requested_selector_ids = None if selector_ids is None else frozenset(selector_ids)
        matches: list[SelectorMatch] = []
        prepared_frames: dict[tuple[int, int] | None, PreparedFrame | None] = {}
        for selector in registry.all():
            if requested_selector_ids is not None and selector.id not in requested_selector_ids:
                continue
            if selector.detection_kind in {DetectionKind.SEMANTIC, DetectionKind.GUARDED_GEOMETRY, DetectionKind.UNSUPPORTED}:
                continue
            if selector.detection_kind == DetectionKind.TEMPLATE:
                if selector.template_path is None:
                    raise SelectorResolutionError(
                        "Enabled template selector is missing its template path.",
                        selector_id=selector.id,
                    )
                if not selector.template_path.is_file():
                    raise SelectorResolutionError(
                        "Enabled template selector asset is missing.",
                        selector_id=selector.id,
                        template_path=str(selector.template_path),
                    )
                if selector.template_mask not in {None, "embedded_alpha"}:
                    raise SelectorResolutionError(
                        "Template selector declares an unsupported mask strategy.",
                        selector_id=selector.id,
                        template_mask=selector.template_mask,
                    )
                reference_size = selector.template_reference_size
                if reference_size not in prepared_frames:
                    prepared_frames[reference_size] = self.template_matcher.prepare_frame(
                        image,
                        reference_size=reference_size,
                    )
                prepared_frame = prepared_frames[reference_size]
                match = self.template_matcher.find_best_match(
                    prepared_frame,
                    selector.template_path,
                    threshold=selector.threshold,
                    search_region=selector.template_search_region,
                ) if prepared_frame is not None else None
                if match is None:
                    continue
                matches.append(
                    SelectorMatch(
                        selector_id=selector.id,
                        bounds=match.bounds,
                        confidence=match.confidence,
                        source_kind=VisibleElementSourceKind.TEMPLATE,
                    )
                )
                continue
            if selector.detection_kind == DetectionKind.OCR_REGION:
                if selector.relative_bounds is None:
                    continue
                bounds = selector.relative_bounds.materialize_region(image_size=image.size)
                try:
                    text = _read_ocr_region_text(
                        image=image,
                        bounds=bounds,
                        selector_id=selector.id,
                        ocr_context=ocr_context,
                    ).strip()
                except ScreenClassificationError:
                    continue
                if not _ocr_region_text_matches_selector(selector_id=selector.id, text=text):
                    continue
                matches.append(
                    SelectorMatch(
                        selector_id=selector.id,
                        bounds=bounds,
                        confidence=1.0,
                        source_kind=VisibleElementSourceKind.OCR,
                        extracted_text=text,
                    )
                )
        return matches


@dataclass(slots=True)
class ObservationBuilder:
    """Converts one captured screenshot into an authoritative observation."""

    selector_registry: SelectorRegistry
    selector_engine: SelectorEngine
    screen_classifier: ScreenClassifier
    enricher: ObservationEnricher = field(default_factory=DefaultObservationEnricher)
    debug_artifact_collector: ObservationDebugArtifactCollector | None = None
    visual_recognizer: VisualScreenRecognizer | None = None
    ocr_service: OcrService | None = None
    ocr_backend_revision: str = "runtime"

    def create_ocr_context(self, screenshot: CapturedScreenshot) -> ObservationOcrContext:
        """Create the single OCR context owned by one captured screenshot."""

        backend = self.ocr_service
        if backend is None:
            backend = getattr(self.enricher, "ocr_service", None)
        if backend is None:
            backend = UnavailableOcrService()
        return ObservationOcrContext(
            screenshot.image,
            backend,
            getattr(screenshot, "frame_ref", None),
            self.ocr_backend_revision,
        )

    def compile_ocr_region_plans(
        self,
        *,
        resolved_screen: ScreenType,
        request: ObservationRequest,
        image_size: tuple[int, int],
    ) -> tuple[OcrRegionPlan, ...]:
        """Compile fixed OCR fields and coordinate regions for one resolved frame."""

        return compile_ocr_region_plans(
            registry=self.selector_registry,
            resolved_screen=resolved_screen,
            request=request,
            image_size=image_size,
        )

    def build(
        self,
        screenshot: CapturedScreenshot,
        *,
        request: ObservationRequest | None = None,
        ocr_context: ObservationOcrContext | None = None,
    ) -> Observation:
        """Builds one observation from a screenshot through the decision pipeline."""

        if ocr_context is None:
            ocr_context = self.create_ocr_context(screenshot)
        else:
            ocr_context.validate_capture(screenshot.image, getattr(screenshot, "frame_ref", None))
        active_request = request or ObservationRequest.full_runtime_default()
        viewport_reviewed = is_reviewed_viewport(screenshot.image.size)
        if active_request.world_map_coordinate_only:
            detection_plan = self._selector_detection_plan(active_request)
            visible_elements = _matches_to_visible_elements(
                self.selector_engine.detect(
                    screenshot.image,
                    self.selector_registry,
                    selector_ids=detection_plan.selector_ids,
                    ocr_context=ocr_context,
                )
            )
            additions = self.enricher.enrich(
                screenshot.image,
                ScreenType.PNC_WORLD_MAP,
                visible_elements,
                active_request,
                ocr_context=ocr_context,
                ocr_regions={},
            )
            decision = self.screen_classifier.decide(
                visible_elements,
                additions.screen_evidence,
                guard=GuardVerdict.NOT_EVALUATED,
                coordinate_only=True,
                viewport_reviewed=True,
            )
            return self._publish(
                screenshot=screenshot,
                decision=decision,
                visible_elements=additions.visible_elements,
                additions=additions,
            )

        visual = (
            VisualRecognition()
            if self.visual_recognizer is None
            else self.visual_recognizer.recognize(screenshot.image)
        )
        # Strong visual identity cannot suppress the global popup/loading guard.
        if visual.evidence:
            active_request = replace(active_request, include_popup_guard=True, include_loading_guard=True)
        detection_plan = self._selector_detection_plan(active_request)
        # The mandatory full-frame guard stage owns the first OCR read.  Any
        # later selector/content crop can then reuse contained lines from this
        # pinned context without issuing an independent backend call.
        guard_additions = self.enricher.recognize_guards(
            screenshot.image,
            active_request,
            ocr_context=ocr_context,
        )
        guard_verdict = guard_additions.guard_verdict
        global_evidence = (*visual.evidence, *guard_additions.screen_evidence)
        if guard_verdict == GuardVerdict.BLOCKED and not _blocked_screen_has_requested_fields(
            active_request,
            guard_additions,
        ):
            preliminary = self.screen_classifier.decide(
                {},
                global_evidence,
                guard=guard_verdict,
                viewport_reviewed=viewport_reviewed,
            )
            return self._publish(
                screenshot=screenshot,
                decision=preliminary,
                visible_elements=guard_additions.visible_elements,
                additions=guard_additions,
            )
        if guard_verdict == GuardVerdict.BLOCKED:
            # A known modal may expose requested fields of its own, but its
            # background selectors must never participate in this decision.
            visible_elements = dict(guard_additions.visible_elements)
        else:
            probe_matches = self.selector_engine.detect(
                screenshot.image,
                self.selector_registry,
                selector_ids=detection_plan.selector_ids,
                ocr_context=ocr_context,
            )
            visible_elements = _matches_to_visible_elements(probe_matches)
        classification_elements = dict(visible_elements)
        preliminary = self.screen_classifier.decide(
            classification_elements,
            global_evidence,
            guard=guard_verdict,
            viewport_reviewed=viewport_reviewed,
        )
        if preliminary.guard == GuardVerdict.BLOCKED and not _blocked_screen_has_requested_fields(
            active_request,
            guard_additions,
        ):
            return self._publish(
                screenshot=screenshot,
                decision=preliminary,
                visible_elements=guard_additions.visible_elements,
                additions=guard_additions,
            )

        semantic_request = replace(
            active_request,
            include_popup_guard=False,
            include_loading_guard=False,
        )
        # Compile and execute only the fixed fields owned by the accepted screen.
        # The mandatory guard has already pinned the full-frame result, so these
        # reads reuse that context without creating a second OCR owner.
        ocr_region_plans = self.compile_ocr_region_plans(
            resolved_screen=preliminary.effective_screen,
            request=semantic_request,
            image_size=screenshot.image.size,
        )
        planned_reads = execute_ocr_region_plans(
            image=screenshot.image,
            plans=ocr_region_plans,
            ocr_context=ocr_context,
        )
        ocr_regions = {
            read.plan.selector_id: read
            for read in planned_reads
            if read.plan.selector_id is not None
        }
        additions = self.enricher.enrich(
            screenshot.image,
            preliminary.effective_screen,
            visible_elements,
            semantic_request,
            ocr_context=ocr_context,
            ocr_regions=ocr_regions,
        )
        if guard_verdict == GuardVerdict.BLOCKED:
            # Preserve the modal's own guarded fields and controls while
            # allowing explicitly requested content enrichment to add facts.
            additions = _merge_observation_additions(guard_additions, additions)
        overlay_screens = {
            ScreenType.PNC_POPUP,
            ScreenType.PNC_VIP_DAILY_RESET,
            ScreenType.PNC_BUILDING_UPGRADE_WARNING,
        }
        overlay_evidence = tuple(
            item for item in additions.screen_evidence if item.screen_type in overlay_screens
        )
        if additions.popup_overlay is not None or overlay_evidence:
            # Only the topmost blocking surface owns actionable controls.
            visible_elements = dict(additions.visible_elements)
            if overlay_evidence:
                global_evidence = overlay_evidence
        elif any(item.screen_type in overlay_screens for item in visual.evidence):
            visible_elements = {}
            additions = ObservationAdditions(guard_verdict=guard_verdict)
            global_evidence = tuple(item for item in visual.evidence if item.screen_type in overlay_screens)
        if (
            preliminary.effective_screen == ScreenType.UNKNOWN
            and not additions.screen_evidence
            and guard_verdict == GuardVerdict.CLEAR
            and _request_has_narrow_semantic_scope(active_request)
        ):
            # A narrow source request cannot hide an unexpected screen.  Give
            # the canonical semantic enricher one broad retry on this same
            # frame, then let the final classifier reconcile its evidence.
            fallback_additions = self.enricher.enrich(
                screenshot.image,
                ScreenType.UNKNOWN,
                visible_elements,
                replace(
                    ObservationRequest.full_runtime_default(),
                    include_popup_guard=False,
                    include_loading_guard=False,
                    expected_mailbox=active_request.expected_mailbox,
                    expected_world_coordinate=active_request.expected_world_coordinate,
                ),
                ocr_context=ocr_context,
                ocr_regions=ocr_regions,
            )
            additions = _merge_observation_additions(additions, fallback_additions)
        combined_evidence = (*global_evidence, *additions.screen_evidence)
        guard_verdict = _merge_guard_verdicts(guard_verdict, additions.guard_verdict)
        visible_elements = _merge_visible_element_maps(
            visible_elements,
            additions.visible_elements,
        )
        decision = self.screen_classifier.decide(
            visible_elements,
            combined_evidence,
            guard=guard_verdict,
            viewport_reviewed=viewport_reviewed,
        )

        # Complete selector detection before geometry publication, while keeping
        # geometry out of every classification decision.
        if decision.effective_screen != ScreenType.UNKNOWN and decision.guard != GuardVerdict.UNRESOLVED:
            visible_elements, _ = self._complete_screen_scope(
                screenshot=screenshot,
                visible_elements=visible_elements,
                screen_type=decision.effective_screen,
                evidence=combined_evidence,
                suppress_geometry_selector_ids=additions.suppress_geometry_selector_ids,
                materialize_geometry=False,
                ocr_context=ocr_context,
            )
            decision = self.screen_classifier.decide(
                visible_elements,
                combined_evidence,
                guard=guard_verdict,
                viewport_reviewed=viewport_reviewed,
            )
        if decision.effective_screen != ScreenType.UNKNOWN and decision.guard != GuardVerdict.UNRESOLVED:
            visible_elements, _ = self._complete_screen_scope(
                screenshot=screenshot,
                visible_elements=visible_elements,
                screen_type=decision.effective_screen,
                evidence=combined_evidence,
                suppress_geometry_selector_ids=additions.suppress_geometry_selector_ids,
                materialize_geometry=True,
                detect_selectors=False,
                ocr_context=ocr_context,
            )
            decision = self.screen_classifier.decide(
                visible_elements,
                combined_evidence,
                guard=guard_verdict,
                viewport_reviewed=viewport_reviewed,
            )
        return self._publish(
            screenshot=screenshot,
            decision=decision,
            visible_elements=visible_elements,
            additions=additions,
        )

    def _publish(
        self,
        *,
        screenshot: CapturedScreenshot,
        decision: ScreenDecision,
        visible_elements: Mapping[UiElementId, VisibleElement],
        additions: ObservationAdditions,
    ) -> Observation:
        """Publishes only facts tied to an accepted screen decision and frame."""

        if (
            not decision.coordinate_only
            and (
                decision.guard in {GuardVerdict.UNRESOLVED, GuardVerdict.NOT_EVALUATED}
                or decision.effective_screen == ScreenType.UNKNOWN
            )
        ):
            visible_elements = {}
            additions = ObservationAdditions(guard_verdict=decision.guard)
        visible_elements = self._filter_visible_elements_for_decision(
            visible_elements,
            decision=decision,
            additions=additions,
        )
        visible_elements = bind_visible_elements(
            visible_elements,
            frame_ref=getattr(screenshot, "frame_ref", None),
            source_screen=decision.effective_screen,
            source_layout_id=decision.layout_id,
        )
        bound_list_entries = tuple(
            bind_list_entry(
                entry,
                frame_ref=getattr(screenshot, "frame_ref", None),
                source_screen=decision.effective_screen,
                source_layout_id=decision.layout_id,
            )
            for entry in additions.list_entries
        )
        return Observation(
            decision=decision,
            visible_elements=visible_elements,
            list_entries=bound_list_entries,
            spatial_surface=additions.spatial_surface,
            artifact_path=_screenshot_artifact_path(screenshot),
            image_size=screenshot.image.size,
            frame_fingerprint=hashlib.sha256(
                payload
                if (payload := getattr(screenshot, "payload", None)) is not None
                else screenshot.image.tobytes()
            ).hexdigest(),
            captured_at=_screenshot_captured_at(screenshot),
            popup_overlay=additions.popup_overlay,
            current_castle=additions.current_castle,
            current_castle_evidence=additions.current_castle_evidence,
            current_pnc_account_id=additions.current_pnc_account_id,
            available_march_slots=additions.available_march_slots,
            active_chat_channel=additions.active_chat_channel,
            profile_player_name=additions.profile_player_name,
            mailbox_type=additions.mailbox_type,
            mailbox_empty=additions.mailbox_empty,
            empty_mailboxes=additions.empty_mailboxes,
            text_field_states=additions.text_field_states,
            chat_draft_empty=additions.chat_draft_empty,
            chat_draft_text=additions.chat_draft_text,
            frame_ref=getattr(screenshot, "frame_ref", None),
        )

    def _filter_visible_elements_for_decision(
        self,
        visible_elements: Mapping[UiElementId, VisibleElement],
        *,
        decision: ScreenDecision,
        additions: ObservationAdditions,
    ) -> dict[UiElementId, VisibleElement]:
        """Drops raw selector matches owned by another source while retaining proved semantic controls."""

        if decision.coordinate_only:
            return dict(visible_elements)
        definitions = {selector.id: selector for selector in self.selector_registry.all()}
        semantic_evidence = {e.screen_type for e in additions.screen_evidence}
        result: dict[UiElementId, VisibleElement] = {}
        for selector_id, element in visible_elements.items():
            definition = definitions.get(selector_id)
            if element.identity_evidence:
                if definition is None or decision.effective_screen not in definition.screens:
                    continue
                result[selector_id] = element
                continue
            if not semantic_evidence or decision.effective_screen in semantic_evidence:
                result[selector_id] = element
        return result

    def _selector_detection_plan(self, request: ObservationRequest) -> ObservationSelectorDetectionPlan:
        """Returns the minimal initial selector scope implied by the observation request."""

        if request.world_map_coordinate_only:
            return ObservationSelectorDetectionPlan(selector_ids=(), source="world_map_coordinate_only")
        selector_ids: set[UiElementId] = set(self.screen_classifier.probe_selector_ids())
        source = "classifier_probe"
        for screen_type in request.candidate_screen_types:
            if screen_type == ScreenType.UNKNOWN:
                continue
            selector_ids.update(selector.id for selector in self.selector_registry.for_screen(screen_type))
            source = "classifier_plus_request_scope"
        if request.include_popup_guard:
            selector_ids.add(UiElementId.PNC_POPUP_CLOSE_BUTTON)
        if request.include_loading_guard:
            selector_ids.update(selector.id for selector in self.selector_registry.for_screen(ScreenType.PNC_LOADING))
        if not selector_ids:
            return ObservationSelectorDetectionPlan(
                selector_ids=self.screen_classifier.probe_selector_ids(),
                source=source,
            )
        return ObservationSelectorDetectionPlan(
            selector_ids=tuple(sorted(selector_ids, key=lambda selector_id: selector_id.value)),
            source=source,
        )

    def persist_debug_artifacts(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
    ) -> None:
        """Persists any configured debug-only sidecars for one completed observation capture."""

        if self.debug_artifact_collector is None:
            return
        self.debug_artifact_collector.persist_unidentified_ocr_sidecar(
            screenshot=screenshot,
            observation=observation,
            ocr_context=ocr_context,
        )

    def _complete_screen_scope(
        self,
        *,
        screenshot: CapturedScreenshot,
        visible_elements: Mapping[UiElementId, VisibleElement],
        screen_type: ScreenType,
        evidence: Sequence[ScreenEvidence] = (),
        suppress_geometry_selector_ids: frozenset[UiElementId] = frozenset(),
        materialize_geometry: bool = True,
        detect_selectors: bool = True,
        ocr_context: ObservationOcrContext,
    ) -> tuple[dict[UiElementId, VisibleElement], ScreenType]:
        """Completes screen-scoped selector detection and geometry for one classified screen."""

        if screen_type == ScreenType.UNKNOWN:
            return dict(visible_elements), screen_type
        screen_selector_ids = tuple(
            selector.id
            for selector in self.selector_registry.for_screen(screen_type)
            if selector.id not in visible_elements
        )
        completed_visible_elements = dict(visible_elements)
        if screen_selector_ids and detect_selectors:
            completed_visible_elements = _merge_visible_element_maps(
                completed_visible_elements,
                _matches_to_visible_elements(
                    self.selector_engine.detect(
                        screenshot.image,
                        self.selector_registry,
                        selector_ids=screen_selector_ids,
                        ocr_context=ocr_context,
                    )
                ),
            )
        if materialize_geometry and is_reviewed_viewport(screenshot.image.size):
            geometry_elements = {
                element.selector_id: element
                for element in self.selector_registry.materialize_for_screen(
                    screen_type,
                    image_size=screenshot.image.size,
                    exclude_selector_ids=frozenset(completed_visible_elements) | suppress_geometry_selector_ids,
                )
            }
            completed_visible_elements = _merge_visible_element_maps(completed_visible_elements, geometry_elements)
        # Detection completion must not become a second identity authority.
        del evidence
        return completed_visible_elements, screen_type


@dataclass(slots=True)
class ObservationService:
    """Captures screenshots and immediately builds typed observations."""

    screenshot_service: ScreenshotService
    observation_builder: ObservationBuilder
    session: BlueStacksSession
    artifact_directory: str
    mode: ObservationMode = ObservationMode.DEBUG
    pnc_account_id: str | None = None
    castle_roster_store: CastleRosterStore | None = None
    verified_pnc_account_id: str | None = None
    validated_current_castle: CastleIdentity | None = None
    validated_current_castle_evidence: CurrentCastleEvidenceKind | None = None
    read_only_probe_mode: bool = False

    def configure_read_only_probe_mode(self, enabled: bool = True) -> None:
        """Configures this shared observer to suppress roster writes during probes."""

        self.read_only_probe_mode = enabled

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> CapturedObservation:
        """Captures a fresh screenshot artifact and returns both the screenshot and typed observation."""

        artifact_policy = self._resolve_artifact_policy(
            request=request,
            artifact_selection=artifact_selection,
        )
        screenshot = self.screenshot_service.capture(
            self.session,
            artifact_directory=self.artifact_directory,
            label=label,
            persist=ObservationArtifactKind.SCREENSHOT in artifact_policy.for_owner(
                ObservationArtifactOwner.OBSERVATION_SERVICE
            ),
        )
        ocr_context = self.observation_builder.create_ocr_context(screenshot)
        roster_snapshot = self._get_castle_roster_snapshot()
        observation = self.observation_builder.build(
            screenshot,
            request=request,
            ocr_context=ocr_context,
        )
        current_castle, current_castle_evidence = self._resolve_current_castle(observation)
        verified_pnc_account_id = self._resolve_verified_pnc_account_id(observation, roster_snapshot)
        observation = replace(
            observation,
            current_castle=current_castle,
            current_castle_evidence=current_castle_evidence,
            verified_pnc_account_id=verified_pnc_account_id,
            castle_roster_snapshot=roster_snapshot,
        )
        self.verified_pnc_account_id = verified_pnc_account_id
        self._update_validated_current_castle(observation)
        self._sync_castle_roster(observation)
        self._persist_debug_artifacts(
            screenshot=screenshot,
            observation=observation,
            ocr_context=ocr_context,
        )
        return CapturedObservation(
            screenshot=screenshot,
            observation=observation,
            ocr_context=ocr_context,
        )

    def observe(
        self,
        label: str,
        request: ObservationRequest | None = None,
        *,
        artifact_selection: ObservationArtifactSelection | None = None,
    ) -> Observation:
        """Captures a fresh screenshot artifact and returns the built observation."""

        return self.capture_observation(
            label,
            request=request,
            artifact_selection=artifact_selection,
        ).observation

    def _resolve_artifact_policy(
        self,
        *,
        request: ObservationRequest | None,
        artifact_selection: ObservationArtifactSelection | None,
    ) -> ResolvedObservationArtifactPolicy:
        """Returns the requested routine artifact selection and rejects kinds this service cannot own."""

        artifact_policy = resolve_observation_artifact_policy(
            mode=self.mode,
            request_selection=None if request is None else request.artifact_selection,
            override_selection=artifact_selection,
        )
        unsupported_artifact_kinds = artifact_policy.unsupported_for_owner(ObservationArtifactOwner.OBSERVATION_SERVICE)
        if unsupported_artifact_kinds:
            unsupported = ", ".join(sorted(kind.value for kind in unsupported_artifact_kinds))
            raise ValueError(
                "ObservationService cannot satisfy non-screenshot artifact requests outside their owning flow "
                f"boundary: {unsupported}."
            )
        return artifact_policy

    def _persist_debug_artifacts(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
        ocr_context: ObservationOcrContext,
    ) -> None:
        """Persists debug-only OCR sidecars without affecting the light-mode runtime path."""

        if self.mode != ObservationMode.DEBUG or screenshot.artifact_path is None:
            return
        persist_debug_artifacts = getattr(self.observation_builder, "persist_debug_artifacts", None)
        if callable(persist_debug_artifacts):
            persist_debug_artifacts(
                screenshot=screenshot,
                observation=observation,
                ocr_context=ocr_context,
            )

    def _sync_castle_roster(self, observation: Observation) -> None:
        """Persists discovered castle rosters whenever the castle-selection screen is observed."""

        if self.read_only_probe_mode:
            return
        if self.castle_roster_store is None or self.pnc_account_id is None:
            return
        if observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            return
        if observation.verified_pnc_account_id != self.pnc_account_id:
            return
        castles = tuple(castle_identity_from_entry(entry) for entry in observation.entries(ListEntryKind.CASTLE))
        if not castles:
            return
        self.castle_roster_store.sync(
            self.pnc_account_id,
            castles,
            ordering=CastleRosterOrdering.UNKNOWN,
        )

    def _get_castle_roster_snapshot(self) -> PncAccountCastleRosterConfig | None:
        """Returns the immutable pre-observation roster snapshot for the configured account."""

        if self.castle_roster_store is None or self.pnc_account_id is None:
            return None
        return self.castle_roster_store.get(self.pnc_account_id)

    def _resolve_current_castle(
        self,
        observation: Observation,
    ) -> tuple[CastleIdentity | None, CurrentCastleEvidenceKind | None]:
        """Carries current-castle evidence back across home-adjacent screens with its strength intact."""

        if observation.current_castle is not None:
            return observation.current_castle, observation.resolved_current_castle_evidence
        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
            return self.validated_current_castle, self.validated_current_castle_evidence
        return None, None

    def _update_validated_current_castle(self, observation: Observation) -> None:
        """Keeps validated current-castle evidence alive while the session stays home-adjacent."""

        if observation.screen_type in {ScreenType.PNC_LORD_INFO, ScreenType.PNC_CASTLE_SELECTION} and observation.current_castle is not None:
            self.validated_current_castle = observation.current_castle
            self.validated_current_castle_evidence = observation.resolved_current_castle_evidence
            return
        if observation.screen_type not in {
            ScreenType.PNC_HOME_CITY,
            ScreenType.PNC_MORE_MENU,
            ScreenType.PNC_LOADING,
            ScreenType.PNC_POPUP,
            ScreenType.UNKNOWN,
        }:
            self.validated_current_castle = None
            self.validated_current_castle_evidence = None

    def _resolve_verified_pnc_account_id(
        self,
        observation: Observation,
        roster_snapshot: PncAccountCastleRosterConfig | None,
    ) -> str | None:
        """Carries forward trusted account ownership evidence across observations."""

        observed_account_id = _trusted_observed_account_id(observation)
        if observed_account_id is not None:
            return observed_account_id
        if self.verified_pnc_account_id is not None:
            if (
                self.pnc_account_id is not None
                and self.verified_pnc_account_id != self.pnc_account_id
                and observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}
            ):
                return None
            return self.verified_pnc_account_id
        if (
            self.pnc_account_id is not None
            and roster_snapshot is not None
            and observation.screen_type == ScreenType.PNC_CASTLE_SELECTION
            and _castle_selection_matches_snapshot(observation, roster_snapshot)
        ):
            return self.pnc_account_id
        return None


def _merge_guard_verdicts(*verdicts: GuardVerdict) -> GuardVerdict:
    """Combines guard stages without allowing an unevaluated stage to erase a rejection."""

    if GuardVerdict.UNRESOLVED in verdicts:
        return GuardVerdict.UNRESOLVED
    if GuardVerdict.BLOCKED in verdicts:
        return GuardVerdict.BLOCKED
    if GuardVerdict.CLEAR in verdicts:
        return GuardVerdict.CLEAR
    return GuardVerdict.NOT_EVALUATED


def _matches_to_visible_elements(matches: Sequence[SelectorMatch]) -> dict[UiElementId, VisibleElement]:
    """Converts selector-engine output into the observation's visible-element map."""

    return {
        match.selector_id: VisibleElement(
            selector_id=match.selector_id,
            bounds=match.bounds,
            confidence=match.confidence,
            source_kind=match.source_kind,
            extracted_text=match.extracted_text,
        )
        for match in matches
    }


def _merge_visible_element_maps(
    *maps: Mapping[UiElementId, VisibleElement],
) -> dict[UiElementId, VisibleElement]:
    """Merges visible-element maps while keeping the strongest selector source."""

    merged: dict[UiElementId, VisibleElement] = {}
    for mapping in maps:
        for selector_id, element in mapping.items():
            current = merged.get(selector_id)
            if current is None or _should_replace_visible_element(current=current, candidate=element):
                merged[selector_id] = element
    return merged


def _merge_observation_additions(
    primary: ObservationAdditions,
    fallback: ObservationAdditions,
) -> ObservationAdditions:
    """Appends broad fallback evidence without discarding facts from the scoped pass.

    A narrow request may already have extracted rows, spatial state, or text
    fields before its screen identity was unresolved.  The broad same-frame
    retry supplies identity evidence; it must not replace those facts or make
    the observation lose its original semantic context.
    """

    list_entries = list(primary.list_entries)
    for entry in fallback.list_entries:
        if entry not in list_entries:
            list_entries.append(entry)
    text_field_states = dict(primary.text_field_states)
    for selector_id, state in fallback.text_field_states.items():
        text_field_states.setdefault(selector_id, state)
    return replace(
        primary,
        visible_elements=_merge_visible_element_maps(
            primary.visible_elements,
            fallback.visible_elements,
        ),
        suppress_geometry_selector_ids=(
            primary.suppress_geometry_selector_ids | fallback.suppress_geometry_selector_ids
        ),
        list_entries=tuple(list_entries),
        spatial_surface=primary.spatial_surface or fallback.spatial_surface,
        screen_evidence=primary.screen_evidence + fallback.screen_evidence,
        guard_verdict=_merge_guard_verdicts(primary.guard_verdict, fallback.guard_verdict),
        current_castle=primary.current_castle or fallback.current_castle,
        current_castle_evidence=primary.current_castle_evidence or fallback.current_castle_evidence,
        current_pnc_account_id=primary.current_pnc_account_id or fallback.current_pnc_account_id,
        available_march_slots=(
            primary.available_march_slots
            if primary.available_march_slots is not None
            else fallback.available_march_slots
        ),
        active_chat_channel=primary.active_chat_channel or fallback.active_chat_channel,
        profile_player_name=primary.profile_player_name or fallback.profile_player_name,
        mailbox_type=primary.mailbox_type or fallback.mailbox_type,
        empty_mailboxes=primary.empty_mailboxes | fallback.empty_mailboxes,
        mailbox_empty=(
            primary.mailbox_empty
            if primary.mailbox_empty is not None
            else fallback.mailbox_empty
        ),
        text_field_states=text_field_states,
        chat_draft_empty=(
            primary.chat_draft_empty
            if primary.chat_draft_empty is not None
            else fallback.chat_draft_empty
        ),
        chat_draft_text=primary.chat_draft_text or fallback.chat_draft_text,
    )


def _blocked_screen_has_requested_fields(
    request: ObservationRequest,
    guard_additions: ObservationAdditions,
) -> bool:
    """Returns whether a proven modal owns fields explicitly requested by this build."""

    requested = request.text_field_selectors
    if not requested:
        return False
    guarded_screens = {evidence.screen_type for evidence in guard_additions.screen_evidence}
    if ScreenType.PNC_MAIL_COMPOSE_POPUP in guarded_screens:
        if requested.intersection(compose_text_field_selector_ids()):
            return True
    if ScreenType.PNC_WORLD_COORDINATE_DIALOG in guarded_screens:
        if requested.intersection(world_map_coordinate_dialog_text_field_selector_ids()):
            return True
    return False


def _single_screen_evidence(evidence: Sequence[ScreenEvidence]) -> ScreenType | None:
    """Return one newly proved non-loading screen, otherwise defer to reconciliation."""

    screens = {
        item.screen_type
        for item in evidence
        if item.screen_type not in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}
    }
    return next(iter(screens)) if len(screens) == 1 else None


def _request_has_narrow_semantic_scope(request: ObservationRequest) -> bool:
    """Returns whether a request actually narrows semantic family/content work.

    Guard flags are intentionally excluded: normal observations run the guard
    stage independently, so a caller may disable those flags on an otherwise
    full semantic request without accidentally triggering a second broad pass.
    """

    full_runtime = ObservationRequest.full_runtime_default()
    return any(
        (
            request.candidate_screen_types != full_runtime.candidate_screen_types,
            request.ocr_screen_types != full_runtime.ocr_screen_types,
            request.include_chat_state != full_runtime.include_chat_state,
            request.include_chat_entries != full_runtime.include_chat_entries,
            request.text_field_selectors != full_runtime.text_field_selectors,
            request.expected_mailbox is not None,
            request.expected_world_coordinate is not None,
        )
    )


def _should_replace_visible_element(*, current: VisibleElement, candidate: VisibleElement) -> bool:
    """Returns whether one visible element should replace the current canonical entry."""

    current_priority = _visible_element_priority(current)
    candidate_priority = _visible_element_priority(candidate)
    if candidate_priority != current_priority:
        return candidate_priority > current_priority
    return candidate.confidence >= current.confidence


def _visible_element_priority(element: VisibleElement) -> int:
    """Returns the canonical source precedence for one visible selector."""

    if element.source_kind == VisibleElementSourceKind.GEOMETRY:
        return 0
    if element.source_kind == VisibleElementSourceKind.TEMPLATE:
        return 1
    if element.source_kind == VisibleElementSourceKind.OCR:
        return 2
    raise ValueError(f"Unsupported visible-element source kind '{element.source_kind}'.")


def _ocr_region_text_matches_selector(*, selector_id: UiElementId, text: str) -> bool:
    """Returns whether one OCR-region crop proves the requested selector semantically."""

    if text.strip() == "":
        return False
    if selector_id == UiElementId.PNC_WORLD_HOME_NAV:
        return normalize_ocr_text(text) == "HOME"
    if selector_id == UiElementId.PNC_WORLD_COORDINATE_BAR:
        return world_coordinate_text_matches(text)
    return True


def _read_ocr_region_text(
    *,
    image: Image.Image,
    bounds: object,
    selector_id: UiElementId,
    ocr_context: ObservationOcrContext,
) -> str:
    """Returns OCR text for one selector region, preferring selector-specific preprocessing when it improves recognition."""

    if selector_id == UiElementId.PNC_WORLD_COORDINATE_BAR:
        filtered_text = read_world_coordinate_bar_text(image=image, bounds=bounds, ocr_context=ocr_context)
        if _ocr_region_text_matches_selector(selector_id=selector_id, text=filtered_text):
            return filtered_text
    return ocr_context.read_text(
        image,
        bounds,
        purpose=OcrReadPurpose.CONTENT,
        detail=f"selector_region:{selector_id.value}",
    )


def _trusted_observed_account_id(observation: Observation) -> str | None:
    """Returns account evidence only for screens that expose an explicit login identity."""

    if observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}:
        return None
    return observation.current_pnc_account_id


def _recognized_ocr_text_hints(observation: Observation) -> frozenset[str]:
    """Returns normalized OCR phrases already explained by the typed observation."""

    recognized_texts: set[str] = set()
    _add_recognized_text(recognized_texts, observation.current_pnc_account_id)
    _add_recognized_text(recognized_texts, observation.verified_pnc_account_id)
    _add_recognized_text(recognized_texts, observation.profile_player_name)
    _add_recognized_text(recognized_texts, observation.chat_draft_text)
    if observation.current_castle is not None:
        _add_recognized_text(recognized_texts, observation.current_castle.castle_name)
        _add_recognized_text(recognized_texts, observation.current_castle.kingdom)
    for element in observation.visible_elements.values():
        _add_recognized_text(recognized_texts, element.extracted_text)
    for entry in observation.list_entries:
        _add_recognized_text(recognized_texts, entry.title_text)
        _add_recognized_text(recognized_texts, entry.subtitle_text)
        for value in entry.metadata.values():
            if isinstance(value, str):
                _add_recognized_text(recognized_texts, value)
    if observation.spatial_surface is not None:
        coordinate_text = observation.spatial_surface.metadata.get("coordinate_text")
        if isinstance(coordinate_text, str):
            _add_recognized_text(recognized_texts, coordinate_text)
        for object_ in observation.spatial_surface.objects:
            _add_recognized_text(recognized_texts, object_.name_text)
            _add_recognized_text(recognized_texts, object_.alliance_tag)
            _add_recognized_text(recognized_texts, object_.kingdom)
            if object_.alliance_tag is not None and object_.name_text is not None:
                _add_recognized_text(recognized_texts, f"{object_.alliance_tag}{object_.name_text}")
    return frozenset(recognized_texts)


def _add_recognized_text(recognized_texts: set[str], text: str | None) -> None:
    """Adds one non-blank normalized text hint to the recognized OCR set."""

    if text is None:
        return
    normalized_text = normalize_ocr_text(text)
    if normalized_text == "":
        return
    recognized_texts.add(normalized_text)


def _unidentified_ocr_lines(
    *,
    lines: Sequence[OcrLine],
    recognized_texts: frozenset[str],
) -> tuple[OcrLine, ...]:
    """Returns only OCR lines whose normalized text is not already explained by the observation."""

    unidentified_lines: list[OcrLine] = []
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text == "" or _recognized_text_matches_line(normalized_text, recognized_texts):
            continue
        unidentified_lines.append(line)
    return tuple(unidentified_lines)


def _recognized_text_matches_line(normalized_text: str, recognized_texts: frozenset[str]) -> bool:
    """Returns whether one normalized OCR line is already represented by the typed observation."""

    for recognized_text in recognized_texts:
        if normalized_text == recognized_text:
            return True
        if len(normalized_text) >= 4 and len(recognized_text) >= 4:
            if normalized_text in recognized_text or recognized_text in normalized_text:
                return True
    return False


def _screenshot_artifact_path(screenshot: object) -> object:
    """Returns the persisted screenshot path from both real and synthetic captured screenshots."""

    artifact_path = getattr(screenshot, "artifact_path", None)
    if artifact_path is not None:
        return artifact_path
    artifact = getattr(screenshot, "artifact", None)
    if artifact is None:
        return None
    return getattr(artifact, "path", None)


def _screenshot_captured_at(screenshot: object) -> object:
    """Returns the capture timestamp from both real and synthetic captured screenshots."""

    captured_at = getattr(screenshot, "captured_at", None)
    if captured_at is not None:
        return captured_at
    artifact = getattr(screenshot, "artifact", None)
    if artifact is not None and getattr(artifact, "captured_at", None) is not None:
        return artifact.captured_at
    fallback_captured_at = screenshot.image.info.get("captured_at")
    if fallback_captured_at is not None:
        return fallback_captured_at
    from datetime import UTC, datetime

    return datetime.now(tz=UTC)


def _castle_selection_matches_snapshot(
    observation: Observation,
    roster_snapshot: PncAccountCastleRosterConfig,
) -> bool:
    """Returns whether the visible roster window fully matches the trusted cached roster snapshot."""

    visible_castles = observation.entries(ListEntryKind.CASTLE)
    if not visible_castles:
        return False
    matched_castles = 0
    for entry in visible_castles:
        if any(castle_entry_identity_matches(entry, castle) for castle in roster_snapshot.castles):
            matched_castles += 1
            continue
        return False
    return matched_castles > 0
