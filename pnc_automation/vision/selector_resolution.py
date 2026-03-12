"""Canonical selector-resolution context and resolver."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from PIL import Image

from pnc_automation.config.models import SelectedCastleConfig
from pnc_automation.pnc.observation import (
    DetectedListEntry,
    ResolvedSelectorSource,
    SelectorResolutionKind,
    VisibleElement,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.image_models import SelectorMatch
from pnc_automation.vision.ocr_service import OcrResult
from pnc_automation.vision.screen_classifier import ScreenEvidence
from pnc_automation.vision.text_anchors import DetectedTextAnchor


@dataclass(frozen=True, slots=True)
class ScreenInterpretation:
    """Captures one trusted parser pass over a screenshot before selector resolution."""

    ocr_result: OcrResult | None = None
    text_anchors: tuple[DetectedTextAnchor, ...] = ()
    visible_elements: Mapping[UiElementId, VisibleElement] = field(default_factory=dict)
    suppress_geometry_selector_ids: frozenset[UiElementId] = frozenset()
    list_entries: tuple[DetectedListEntry, ...] = ()
    screen_evidence: tuple[ScreenEvidence, ...] = ()
    current_castle: SelectedCastleConfig | None = None
    current_pnc_account_id: str | None = None
    available_march_slots: int | None = None

    @property
    def parser_candidates(self) -> Mapping[UiElementId, VisibleElement]:
        """Returns the trusted parser-produced selector candidates."""

        return self.visible_elements

    @property
    def blocked_relative_bounds_selector_ids(self) -> frozenset[UiElementId]:
        """Returns the selector ids whose geometry fallback is blocked on this observation."""

        return self.suppress_geometry_selector_ids


@dataclass(frozen=True, slots=True)
class SelectorResolutionContext:
    """Carries one screenshot's shared resolution inputs across all selector policies."""

    image: Image.Image
    screen_type: ScreenType
    exact_matches: Mapping[UiElementId, SelectorMatch]
    interpretation: ScreenInterpretation

    @property
    def image_size(self) -> tuple[int, int]:
        """Returns the current screenshot size."""

        return self.image.size

    @property
    def parser_candidates(self) -> Mapping[UiElementId, VisibleElement]:
        """Returns the trusted parser candidates keyed by canonical selector id."""

        return self.interpretation.parser_candidates


@dataclass(slots=True)
class SelectorResolver:
    """Resolves one screen's selectors through their ordered canonical policies."""

    def resolve_for_screen(
        self,
        *,
        selectors: tuple[object, ...],
        context: SelectorResolutionContext,
    ) -> dict[UiElementId, VisibleElement]:
        """Returns the resolved visible-element map for one classified screen."""

        resolved: dict[UiElementId, VisibleElement] = {}
        for selector in selectors:
            element = self._resolve_selector(selector=selector, context=context)
            if element is None:
                continue
            resolved[element.selector_id] = element
        return resolved

    def _resolve_selector(
        self,
        *,
        selector: object,
        context: SelectorResolutionContext,
    ) -> VisibleElement | None:
        """Returns the first successful resolution step for one selector on the current screen."""

        steps = getattr(selector, "resolution").steps
        if not steps:
            return None
        exact_match = context.exact_matches.get(getattr(selector, "id"))
        parser_candidate = context.parser_candidates.get(getattr(selector, "id"))
        for index, step in enumerate(steps):
            if step.kind in {SelectorResolutionKind.TEMPLATE, SelectorResolutionKind.OCR_REGION}:
                if exact_match is None or exact_match.strategy_index != index:
                    continue
                return self._resolved_from_exact_match(
                    selector_id=exact_match.selector_id,
                    match=exact_match,
                    strategy_label=step.strategy_label,
                )
            if step.kind == SelectorResolutionKind.PARSER_CANDIDATE:
                if parser_candidate is None:
                    continue
                return self._resolved_from_parser_candidate(
                    selector_id=getattr(selector, "id"),
                    candidate=parser_candidate,
                    strategy_index=index,
                    strategy_label=step.strategy_label,
                )
            if step.kind == SelectorResolutionKind.RELATIVE_BOUNDS:
                if getattr(selector, "id") in context.interpretation.blocked_relative_bounds_selector_ids:
                    continue
                materialized = step.materialize(selector_id=getattr(selector, "id"), image_size=context.image_size)
                return self._resolved_with_source(
                    selector_id=getattr(selector, "id"),
                    element=materialized,
                    resolution_kind=SelectorResolutionKind.RELATIVE_BOUNDS,
                    strategy_index=index,
                    strategy_label=step.strategy_label,
                )
        return None

    def _resolved_from_exact_match(
        self,
        *,
        selector_id: UiElementId,
        match: SelectorMatch,
        strategy_label: str,
    ) -> VisibleElement:
        """Builds one resolved visible element from an exact match."""

        return self._resolved_with_source(
            selector_id=selector_id,
            element=VisibleElement(
                selector_id=selector_id,
                bounds=match.bounds,
                confidence=match.confidence,
                extracted_text=match.extracted_text,
            ),
            resolution_kind=match.resolution_kind,
            strategy_index=match.strategy_index,
            strategy_label=strategy_label,
        )

    def _resolved_from_parser_candidate(
        self,
        *,
        selector_id: UiElementId,
        candidate: VisibleElement,
        strategy_index: int,
        strategy_label: str,
    ) -> VisibleElement:
        """Decorates one trusted parser candidate with final selector provenance."""

        return self._resolved_with_source(
            selector_id=selector_id,
            element=candidate,
            resolution_kind=SelectorResolutionKind.PARSER_CANDIDATE,
            strategy_index=strategy_index,
            strategy_label=strategy_label,
        )

    def _resolved_with_source(
        self,
        *,
        selector_id: UiElementId,
        element: VisibleElement,
        resolution_kind: SelectorResolutionKind,
        strategy_index: int,
        strategy_label: str,
    ) -> VisibleElement:
        """Returns one visible element annotated with canonical resolution provenance."""

        return replace(
            element,
            selector_id=selector_id,
            source=ResolvedSelectorSource(
                resolution_kind=resolution_kind,
                strategy_index=strategy_index,
                strategy_label=strategy_label,
                is_fallback=strategy_index > 0,
            ),
        )
