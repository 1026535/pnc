"""Builds typed observations from screenshots and selector detections."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from PIL import Image

from pnc_automation.config.models import CastleRosterOrdering, PncAccountCastleRosterConfig, SelectedCastleConfig
from pnc_automation.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.pnc.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    VisibleElement,
    castle_entry_identity_matches,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.image_models import SelectorMatch
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
    ) -> "ObservationAdditions":
        """Returns derived observation additions."""


@dataclass(frozen=True, slots=True)
class ObservationAdditions:
    """Derived observation facts produced after primary screen classification."""

    visible_elements: Mapping[UiElementId, VisibleElement] = field(default_factory=dict)
    list_entries: tuple[DetectedListEntry, ...] = ()
    screen_evidence: tuple[ScreenEvidence, ...] = ()
    current_castle: SelectedCastleConfig | None = None
    current_pnc_account_id: str | None = None
    available_march_slots: int | None = None


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
    ) -> ObservationAdditions:
        """Returns an empty enrichment result."""

        del image, screen_type, visible_elements
        return ObservationAdditions()


class SelectorEngine(Protocol):
    """Detects selectors from a screenshot using the registry metadata."""

    def detect(self, image: Image.Image, registry: SelectorRegistry) -> Sequence[SelectorMatch]:
        """Returns all selectors detected in the image."""


@dataclass(slots=True)
class PillowSelectorEngine:
    """Detects selectors using template matching and optional OCR."""

    template_matcher: PillowTemplateMatcher
    ocr_service: OcrService

    def detect(self, image: Image.Image, registry: SelectorRegistry) -> Sequence[SelectorMatch]:
        """Detects selectors supported by the configured engines."""

        matches: list[SelectorMatch] = []
        for selector in registry.all():
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
                    )
                )
                continue
            if selector.detection_kind == DetectionKind.OCR_REGION:
                if selector.ocr_region is None:
                    continue
                text = self.ocr_service.read_text(image, selector.ocr_region).strip()
                if text == "":
                    continue
                matches.append(
                    SelectorMatch(
                        selector_id=selector.id,
                        bounds=selector_to_bounds(selector.ocr_region),
                        confidence=1.0,
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

    def build(self, screenshot: CapturedScreenshot) -> Observation:
        """Builds one observation from a captured screenshot."""

        matches = self.selector_engine.detect(screenshot.image, self.selector_registry)
        visible_elements = {
            match.selector_id: VisibleElement(
                selector_id=match.selector_id,
                bounds=match.bounds,
                confidence=match.confidence,
                extracted_text=match.extracted_text,
            )
            for match in matches
        }
        screen_type = self.screen_classifier.classify(visible_elements)
        additions = self.enricher.enrich(screenshot.image, screen_type, visible_elements)
        visible_elements = dict(additions.visible_elements) | visible_elements
        screen_type = self.screen_classifier.classify(visible_elements, additions.screen_evidence)
        return Observation(
            screen_type=screen_type,
            visible_elements=visible_elements,
            list_entries=additions.list_entries,
            artifact_path=screenshot.artifact.path,
            image_size=screenshot.image.size,
            captured_at=screenshot.artifact.captured_at,
            blocking_popup=screen_type == ScreenType.PNC_POPUP or UiElementId.PNC_POPUP_CLOSE_BUTTON in visible_elements,
            current_castle=additions.current_castle,
            current_pnc_account_id=additions.current_pnc_account_id,
            available_march_slots=additions.available_march_slots,
        )


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
    validated_current_castle: SelectedCastleConfig | None = None

    def capture_observation(self, label: str) -> CapturedObservation:
        """Captures a fresh screenshot artifact and returns both the screenshot and typed observation."""

        screenshot = self.screenshot_service.capture(self.session, artifact_directory=self.artifact_directory, label=label)
        roster_snapshot = self._get_castle_roster_snapshot()
        observation = self.observation_builder.build(screenshot)
        current_castle = self._resolve_current_castle(observation)
        verified_pnc_account_id = self._resolve_verified_pnc_account_id(observation, roster_snapshot)
        observation = replace(
            observation,
            current_castle=current_castle,
            verified_pnc_account_id=verified_pnc_account_id,
            castle_roster_snapshot=roster_snapshot,
        )
        self.verified_pnc_account_id = verified_pnc_account_id
        self._update_validated_current_castle(observation)
        self._sync_castle_roster(observation)
        return CapturedObservation(screenshot=screenshot, observation=observation)

    def observe(self, label: str) -> Observation:
        """Captures a fresh screenshot artifact and returns the built observation."""

        return self.capture_observation(label).observation

    def _sync_castle_roster(self, observation: Observation) -> None:
        """Persists discovered castle rosters whenever the castle-selection screen is observed."""

        if self.castle_roster_store is None or self.pnc_account_id is None:
            return
        if observation.screen_type != ScreenType.PNC_CASTLE_SELECTION:
            return
        if observation.verified_pnc_account_id != self.pnc_account_id:
            return
        castles = tuple(_entry_to_selected_castle(entry) for entry in observation.entries(ListEntryKind.CASTLE))
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

    def _resolve_current_castle(self, observation: Observation) -> SelectedCastleConfig | None:
        """Carries one Lord Info castle-name validation back across home-adjacent screens."""

        if observation.current_castle is not None:
            return observation.current_castle
        if observation.screen_type in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
            return self.validated_current_castle
        return None

    def _update_validated_current_castle(self, observation: Observation) -> None:
        """Keeps Lord Info validation only while the session remains on home-adjacent screens."""

        if observation.screen_type == ScreenType.PNC_LORD_INFO and observation.current_castle is not None:
            self.validated_current_castle = observation.current_castle
            return
        if observation.screen_type not in {ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU}:
            self.validated_current_castle = None

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


def _entry_to_selected_castle(entry: DetectedListEntry) -> "SelectedCastleConfig":
    """Converts one observed castle row into the shared typed castle identity model."""

    from pnc_automation.config.models import SelectedCastleConfig
    from pnc_automation.errors import SelectorResolutionError

    if entry.title_text is None or entry.title_text.strip() == "":
        raise SelectorResolutionError("Observed castle entry is missing its castle name.", entry_kind=entry.kind)
    kingdom = entry.require_metadata("kingdom")
    castle_level = entry.metadata.get("castle_level")
    if not isinstance(kingdom, str) or kingdom.strip() == "":
        raise SelectorResolutionError("Observed castle entry is missing a valid kingdom.", entry_kind=entry.kind)
    if castle_level is not None and not isinstance(castle_level, int):
        raise SelectorResolutionError(
            "Observed castle entry contains a non-integer castle level.",
            entry_kind=entry.kind,
            castle_level=castle_level,
        )
    return SelectedCastleConfig(
        kingdom=kingdom,
        castle_name=entry.title_text,
        castle_level=castle_level,
    )


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
