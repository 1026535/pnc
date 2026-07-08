"""Builds typed observations from screenshots and selector detections."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from PIL import Image

from pnc_automation.core.errors import ScreenClassificationError
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
from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    SpatialSurfaceObservation,
    VisibleElement,
    VisibleElementSourceKind,
    castle_identity_from_entry,
    castle_entry_identity_matches,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.app.pnc.vision.image_models import SelectorMatch
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrService
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier, ScreenEvidence
from pnc_automation.app.pnc.vision.selectors import DetectionKind, SelectorRegistry
from pnc_automation.app.pnc.vision.world_map_coordinates import read_world_coordinate_bar_text, world_coordinate_text_matches
from pnc_automation.core.vision.template.template_matcher import PillowTemplateMatcher

class ObservationEnricher(Protocol):
    """Adds higher-level facts after basic selector detection."""

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
        request: ObservationRequest,
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
    current_castle: CastleIdentity | None = None
    current_castle_evidence: CurrentCastleEvidenceKind | None = None
    current_pnc_account_id: str | None = None
    available_march_slots: int | None = None
    active_chat_channel: ChatChannel | None = None
    profile_player_name: str | None = None
    mailbox_type: MailboxType | None = None
    mailbox_empty: bool | None = None
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


@dataclass(slots=True)
class DefaultObservationEnricher:
    """Default no-op enricher used until screenshot-specific extraction is added."""

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
        request: ObservationRequest,
    ) -> ObservationAdditions:
        """Returns an empty enrichment result."""

        del image, screen_type, visible_elements, request
        return ObservationAdditions()


class SelectorEngine(Protocol):
    """Detects selectors from a screenshot using the registry metadata."""

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: Sequence[UiElementId] | None = None,
    ) -> Sequence[SelectorMatch]:
        """Returns all selectors detected in the image."""


@dataclass(slots=True)
class ObservationDebugArtifactCollector:
    """Persists debug-only OCR sidecars that capture lines the runtime could not yet classify."""

    ocr_service: OcrService

    def persist_unidentified_ocr_sidecar(
        self,
        *,
        screenshot: CapturedScreenshot,
        observation: Observation,
    ) -> None:
        """Writes one sidecar containing unmatched OCR lines next to the persisted screenshot artifact."""

        artifact_path = screenshot.artifact_path
        if artifact_path is None:
            return
        recognized_texts = _recognized_ocr_text_hints(observation)
        unidentified_lines = _unidentified_ocr_lines(
            lines=self.ocr_service.read_lines(screenshot.image),
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
class PillowSelectorEngine:
    """Detects selectors using template matching and optional OCR."""

    template_matcher: PillowTemplateMatcher
    ocr_service: OcrService

    def detect(
        self,
        image: Image.Image,
        registry: SelectorRegistry,
        *,
        selector_ids: Sequence[UiElementId] | None = None,
    ) -> Sequence[SelectorMatch]:
        """Detects selectors supported by the configured engines."""

        requested_selector_ids = None if selector_ids is None else frozenset(selector_ids)
        matches: list[SelectorMatch] = []
        for selector in registry.all():
            if requested_selector_ids is not None and selector.id not in requested_selector_ids:
                continue
            if selector.detection_kind == DetectionKind.PLANNED:
                continue
            if selector.detection_kind in {DetectionKind.TEMPLATE, DetectionKind.COLLECTION}:
                if selector.template_path is None or not selector.template_path.is_file():
                    continue
                match = self.template_matcher.find_best_match(image, selector.template_path, threshold=selector.threshold)
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
                        ocr_service=self.ocr_service,
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

    def build(self, screenshot: CapturedScreenshot, *, request: ObservationRequest | None = None) -> Observation:
        """Builds one observation from a captured screenshot."""

        active_request = request or ObservationRequest.full_runtime_default()
        detection_plan = self._selector_detection_plan(active_request)
        probe_matches = self.selector_engine.detect(
            screenshot.image,
            self.selector_registry,
            selector_ids=detection_plan.selector_ids,
        )
        visible_elements = _matches_to_visible_elements(probe_matches)
        screen_type = self.screen_classifier.classify(visible_elements)
        if not active_request.world_map_coordinate_only:
            visible_elements, screen_type = self._complete_screen_scope(
                screenshot=screenshot,
                visible_elements=visible_elements,
                screen_type=screen_type,
            )
        base_screen_type = screen_type
        additions = self.enricher.enrich(
            screenshot.image,
            screen_type,
            visible_elements,
            active_request,
        )
        visible_elements = _merge_visible_element_maps(visible_elements, additions.visible_elements)
        screen_type = self.screen_classifier.classify(visible_elements, additions.screen_evidence)
        if (
            additions.visible_elements
            or additions.screen_evidence
            or additions.suppress_geometry_selector_ids
            or screen_type != base_screen_type
        ) and not active_request.world_map_coordinate_only:
            visible_elements, screen_type = self._complete_screen_scope(
                screenshot=screenshot,
                visible_elements=visible_elements,
                screen_type=screen_type,
                evidence=additions.screen_evidence,
                suppress_geometry_selector_ids=additions.suppress_geometry_selector_ids,
            )
        return Observation(
            screen_type=screen_type,
            visible_elements=visible_elements,
            list_entries=additions.list_entries,
            spatial_surface=additions.spatial_surface,
            artifact_path=_screenshot_artifact_path(screenshot),
            image_size=screenshot.image.size,
            captured_at=_screenshot_captured_at(screenshot),
            blocking_popup=screen_type in {ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET}
            or UiElementId.PNC_POPUP_CLOSE_BUTTON in visible_elements
            or UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON in visible_elements,
            current_castle=additions.current_castle,
            current_castle_evidence=additions.current_castle_evidence,
            current_pnc_account_id=additions.current_pnc_account_id,
            available_march_slots=additions.available_march_slots,
            active_chat_channel=additions.active_chat_channel,
            profile_player_name=additions.profile_player_name,
            mailbox_type=additions.mailbox_type,
            mailbox_empty=additions.mailbox_empty,
            text_field_states=additions.text_field_states,
            chat_draft_empty=additions.chat_draft_empty,
            chat_draft_text=additions.chat_draft_text,
        )

    def _selector_detection_plan(self, request: ObservationRequest) -> ObservationSelectorDetectionPlan:
        """Returns the minimal initial selector scope implied by the observation request."""

        if request.world_map_coordinate_only:
            return ObservationSelectorDetectionPlan(selector_ids=(), source="world_map_coordinate_only")
        if not request.candidate_screen_types:
            return ObservationSelectorDetectionPlan(
                selector_ids=self.screen_classifier.probe_selector_ids(),
                source="classifier_probe",
            )
        selector_ids: set[UiElementId] = set()
        for screen_type in request.candidate_screen_types:
            if screen_type == ScreenType.UNKNOWN:
                continue
            selector_ids.update(selector.id for selector in self.selector_registry.for_screen(screen_type))
        if request.include_popup_guard:
            selector_ids.add(UiElementId.PNC_POPUP_CLOSE_BUTTON)
        if request.include_loading_guard:
            selector_ids.update(selector.id for selector in self.selector_registry.for_screen(ScreenType.PNC_LOADING))
        if not selector_ids:
            return ObservationSelectorDetectionPlan(
                selector_ids=self.screen_classifier.probe_selector_ids(),
                source="classifier_probe",
            )
        return ObservationSelectorDetectionPlan(
            selector_ids=tuple(sorted(selector_ids, key=lambda selector_id: selector_id.value)),
            source="request_candidate_scope",
        )

    def persist_debug_artifacts(self, *, screenshot: CapturedScreenshot, observation: Observation) -> None:
        """Persists any configured debug-only sidecars for one completed observation capture."""

        if self.debug_artifact_collector is None:
            return
        self.debug_artifact_collector.persist_unidentified_ocr_sidecar(
            screenshot=screenshot,
            observation=observation,
        )

    def _complete_screen_scope(
        self,
        *,
        screenshot: CapturedScreenshot,
        visible_elements: Mapping[UiElementId, VisibleElement],
        screen_type: ScreenType,
        evidence: Sequence[ScreenEvidence] = (),
        suppress_geometry_selector_ids: frozenset[UiElementId] = frozenset(),
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
        if screen_selector_ids:
            completed_visible_elements = _merge_visible_element_maps(
                completed_visible_elements,
                _matches_to_visible_elements(
                    self.selector_engine.detect(
                        screenshot.image,
                        self.selector_registry,
                        selector_ids=screen_selector_ids,
                    )
                ),
            )
        geometry_elements = {
            element.selector_id: element
            for element in self.selector_registry.materialize_for_screen(
                screen_type,
                image_size=screenshot.image.size,
                exclude_selector_ids=frozenset(completed_visible_elements) | suppress_geometry_selector_ids,
            )
        }
        completed_visible_elements = _merge_visible_element_maps(completed_visible_elements, geometry_elements)
        return completed_visible_elements, self.screen_classifier.classify(completed_visible_elements, evidence)


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
        roster_snapshot = self._get_castle_roster_snapshot()
        observation = self.observation_builder.build(screenshot, request=request)
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
        self._persist_debug_artifacts(screenshot=screenshot, observation=observation)
        return CapturedObservation(screenshot=screenshot, observation=observation)

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

    def _persist_debug_artifacts(self, *, screenshot: CapturedScreenshot, observation: Observation) -> None:
        """Persists debug-only OCR sidecars without affecting the light-mode runtime path."""

        if self.mode != ObservationMode.DEBUG or screenshot.artifact_path is None:
            return
        persist_debug_artifacts = getattr(self.observation_builder, "persist_debug_artifacts", None)
        if callable(persist_debug_artifacts):
            persist_debug_artifacts(screenshot=screenshot, observation=observation)

    def _sync_castle_roster(self, observation: Observation) -> None:
        """Persists discovered castle rosters whenever the castle-selection screen is observed."""

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
        if observation.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
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
    ocr_service: OcrService,
) -> str:
    """Returns OCR text for one selector region, preferring selector-specific preprocessing when it improves recognition."""

    if selector_id == UiElementId.PNC_WORLD_COORDINATE_BAR:
        filtered_text = read_world_coordinate_bar_text(image=image, bounds=bounds, ocr_service=ocr_service)
        if _ocr_region_text_matches_selector(selector_id=selector_id, text=filtered_text):
            return filtered_text
    return ocr_service.read_text(image, bounds)


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
