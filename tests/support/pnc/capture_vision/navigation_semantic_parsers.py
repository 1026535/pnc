"""Canonical semantic parsers for explicit-screen synthetic navigation tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    PncObservationEnricher,
    _build_home_city_additions,
    _build_castle_roster_additions,
    _build_lord_info_additions,
    _build_matching_text_screen_additions,
    _build_more_settings_menu_additions,
    _build_status_banner_additions,
    _build_world_map_additions,
    _build_world_map_root_additions,
)
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.text_anchors import TextAnchorDetector
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService


def _anchors(lines: tuple[OcrLine, ...]):
    """Detect shared text anchors from caller-supplied semantic OCR lines."""

    return TextAnchorDetector().detect(OcrResult(lines=lines, words=()))


def _build_home_city_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Project supplied OCR geometry through the canonical home-city parser."""

    additions = _build_home_city_additions(
        image=image,
        lines=lines,
        anchors=_anchors(lines),
        visible_elements={},
        selector_registry=build_default_selector_registry(),
    )
    return additions or ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "explicit_test_input"),)
    )


def _build_world_map_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Project supplied OCR geometry through the canonical world-map parser."""

    registry = build_default_selector_registry()
    context = ObservationOcrContext(image, _FakeOcrService(lines=lines), None, "synthetic-navigation")
    context.require_bounded_regions()
    additions = _build_world_map_additions(
        image=image,
        lines=lines,
        anchors=_anchors(lines),
        selector_registry=registry,
        ocr_context=context,
    )
    return additions or ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP, "explicit_test_input"),)
    )


def _build_world_map_status_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...], request: ObservationRequest
) -> ObservationAdditions:
    """Project world-map OCR and its status banner through canonical parsers."""

    additions = _build_world_map_semantic_additions(image=image, lines=lines)
    status = _build_status_banner_additions(image=image, lines=lines, request=request)
    if status is None:
        return additions
    return replace(
        additions,
        visible_elements={**additions.visible_elements, **status.visible_elements},
    )


def _build_world_map_root_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Project coarse world-map-root OCR through its canonical parser."""

    additions = _build_world_map_root_additions(image=image, lines=lines, anchors=_anchors(lines))
    return additions or ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_ROOT, "explicit_test_input"),)
    )


def _build_world_overview_semantic_parser(
    *, request: ObservationRequest
) -> Callable[..., ObservationAdditions]:
    """Return the canonical overview parser with its explicit request bound."""

    def parse(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
        enricher = PncObservationEnricher(selector_registry=build_default_selector_registry())
        additions = enricher._build_world_map_overview_additions(
            image=image,
            lines=lines,
            request=request,
        )
        return additions or ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_OVERVIEW, "explicit_test_input"),)
        )

    return parse


def _build_text_screen_semantic_parser(
    *, request: ObservationRequest, screen_type: ScreenType
) -> Callable[..., ObservationAdditions]:
    """Return the canonical exact text-screen parser with its request bound."""

    def parse(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> ObservationAdditions:
        additions = _build_matching_text_screen_additions(
            image=image,
            lines=lines,
            request=request,
            observed_screen=screen_type,
            selector_registry=None,
        )
        return additions or ObservationAdditions(
            screen_evidence=(ScreenEvidence(screen_type, "explicit_test_input"),)
        )

    return parse


def _build_lord_info_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Project supplied OCR through the canonical Lord Info parser."""

    additions = _build_lord_info_additions(image=image, lines=lines)
    return additions or ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_LORD_INFO, "explicit_test_input"),)
    )


def _build_settings_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Project supplied OCR through the canonical full-screen Settings parser."""

    additions = _build_more_settings_menu_additions(image=image, lines=lines)
    return additions or ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_SETTINGS, "explicit_test_input"),)
    )


def _build_castle_selection_semantic_additions(
    *, image: Image.Image, lines: tuple[OcrLine, ...]
) -> ObservationAdditions:
    """Exercise the runtime roster producer after an explicit screen decision."""

    context = ObservationOcrContext(image, _FakeOcrService(lines=lines), None, "synthetic-navigation")
    context.require_bounded_regions()
    return _build_castle_roster_additions(
        image=image, lines=lines, anchors=_anchors(lines), ocr_context=context,
    ) or ObservationAdditions()
