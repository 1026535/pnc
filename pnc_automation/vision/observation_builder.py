"""Builds typed observations from screenshots and selector detections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from PIL import Image

from pnc_automation.config.models import CastleIdentity, CastleRosterOrdering, PncAccountCastleRosterConfig
from pnc_automation.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.mail import MailboxType
from pnc_automation.pnc.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    VisibleElement,
    VisibleElementSourceKind,
    castle_identity_from_entry,
    castle_entry_identity_matches,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.image_models import SelectorMatch
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.ocr_service import OcrService
from pnc_automation.vision.screen_classifier import ScreenClassifier, ScreenEvidence
from pnc_automation.vision.selectors import DetectionKind, SelectorRegistry
from pnc_automation.vision.template_matcher import PillowTemplateMatcher


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
                region = selector.relative_bounds.materialize_region(image_size=image.size)
                text = self.ocr_service.read_text(image, region).strip()
                if text == "":
                    continue
                matches.append(
                    SelectorMatch(
                        selector_id=selector.id,
                        bounds=selector_to_bounds(region),
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

    def build(self, screenshot: CapturedScreenshot, *, request: ObservationRequest | None = None) -> Observation:
        """Builds one observation from a captured screenshot."""

        active_request = request or ObservationRequest.full_runtime_default()
        probe_matches = self.selector_engine.detect(
            screenshot.image,
            self.selector_registry,
            selector_ids=self.screen_classifier.probe_selector_ids(),
        )
        visible_elements = _matches_to_visible_elements(probe_matches)
        screen_type = self.screen_classifier.classify(visible_elements)
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
        ):
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
            artifact_path=screenshot.artifact.path,
            image_size=screenshot.image.size,
            captured_at=screenshot.artifact.captured_at,
            blocking_popup=screen_type == ScreenType.PNC_POPUP or UiElementId.PNC_POPUP_CLOSE_BUTTON in visible_elements,
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
    pnc_account_id: str | None = None
    castle_roster_store: CastleRosterStore | None = None
    verified_pnc_account_id: str | None = None
    validated_current_castle: CastleIdentity | None = None
    validated_current_castle_evidence: CurrentCastleEvidenceKind | None = None

    def capture_observation(
        self,
        label: str,
        request: ObservationRequest | None = None,
    ) -> CapturedObservation:
        """Captures a fresh screenshot artifact and returns both the screenshot and typed observation."""

        screenshot = self.screenshot_service.capture(self.session, artifact_directory=self.artifact_directory, label=label)
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
        return CapturedObservation(screenshot=screenshot, observation=observation)

    def observe(self, label: str, request: ObservationRequest | None = None) -> Observation:
        """Captures a fresh screenshot artifact and returns the built observation."""

        return self.capture_observation(label, request=request).observation

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
        """Keeps Lord Info validation only while the session remains on home-adjacent screens."""

        if observation.screen_type == ScreenType.PNC_LORD_INFO and observation.current_castle is not None:
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


def selector_to_bounds(region: object) -> object:
    """Converts a selector region into bounds while avoiding an import cycle."""

    from pnc_automation.pnc.observation import Bounds

    return Bounds(x=region.x, y=region.y, width=region.width, height=region.height)


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


def _trusted_observed_account_id(observation: Observation) -> str | None:
    """Returns account evidence only for screens that expose an explicit login identity."""

    if observation.screen_type not in {ScreenType.PNC_LOGIN, ScreenType.PNC_ACCOUNT_SWITCH}:
        return None
    return observation.current_pnc_account_id


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
