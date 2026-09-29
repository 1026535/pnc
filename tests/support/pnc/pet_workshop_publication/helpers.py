"""Shared captured-frame helpers for Pet Workshop publication tests."""

from __future__ import annotations

import hashlib
import unittest
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopCellAccess,
    WorkshopItemStatus,
    WorkshopOccupancy,
    WorkshopOrderRewardCategory,
    WorkshopProductionMode,
    WorkshopSelectionKind,
    WorkshopSurfaceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pet_workshop import WorkshopContentProducer
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)
from tests.support.automation.session import FakeSession
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.publication import make_publication_pair
from tests.support.runtime.observation_service import FakeObservationService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"

_BOARD_LAYOUT_ID = "pet_workshop_board"
_ITEM_DETAIL_LAYOUT_ID = "pet_workshop_item_detail"
_ORDER_DETAIL_LAYOUT_ID = "pet_workshop_order_detail"
_HELP_LAYOUT_ID = "pet_workshop_help"
_STORAGE_LAYOUT_ID = "pet_workshop_storage"
_MANOR_LAYOUT_ID = "pet_workshop_manor"

# Reviewed board facts of the frozen at-rest LV8 capture pet_workshop.png.
_LV8_ITEMS: dict[int, int] = {
    1: 20105, 2: 20208, 4: 20204, 5: 20207, 7: 20004, 8: 20105, 12: 20205,
    15: 20105, 17: 20102, 20: 30002, 24: 20103, 36: 30105, 46: 10204,
}
_LV8_UNKNOWN_OCCUPIED = (3, 9, 21, 22, 23, 28, 29, 31, 37, 45, 52, 56)
# Greyed pieces on the LV8 board measured inactive; the rest keep unknown identity.
_LV8_INACTIVE = (3, 52, 56)
_LV8_LOCKED_EMPTY = (43, 44, 53, 54, 55, 62, 63)
_LV8_LOCKED_UNKNOWN = (50, 51, 57, 58, 59, 60, 61)
_LV8_ORDERS: tuple[dict[str, Any], ...] = (
    {
        "order_ref": 1,
        "requirements": {20105: 3},
        "rewards": (WorkshopOrderRewardCategory.CHEST,),
        "completeness": "complete",
        "ready": True,
        "submit": Bounds(198, 102, 72, 19),
    },
    {
        "order_ref": 2,
        "requirements": {10204: 1, 31109: 1},
        "rewards": (
            WorkshopOrderRewardCategory.FEED,
            WorkshopOrderRewardCategory.WORKSHOP_EXP,
        ),
        "completeness": "complete",
        "ready": False,
        "submit": None,
    },
    {
        "order_ref": 3,
        "requirements": {20210: 1},
        "rewards": (WorkshopOrderRewardCategory.BEAST_LASSO,),
        "completeness": "clipped",
        "ready": None,
        "submit": None,
    },
)

# Reviewed LV6 order facts of pet_workshop_lv6_20260917.png; the strip's third
# slot carries no card (plain strip background) so only two orders publish.
_LV6_REQUIREMENTS = ({20104: 1, 10106: 1}, {10107: 1, 20104: 1})

# Reviewed LV10 order facts of pet_workshop_lv10_20260927.png, the September 27
# manual run's final board: the first card is the chest/table order (green-inlay
# treasure variant and the Wood 9 table) with a ready Complete control rendered
# taller than the original authored template; the second is the
# food/pomegranate order (blue-inlay fruit variant), still not ready.
_LV10_ORDERS: tuple[dict[str, Any], ...] = (
    {
        "order_ref": 1,
        "requirements": {10106: 1, 20209: 1},
        "rewards": (WorkshopOrderRewardCategory.CHEST,),
        "completeness": "complete",
        "ready": True,
        # The preserved PW05 Complete_4 variant wins the integrated template
        # family and measures the upper button band; its center is on the
        # visible control. The larger variant's footprint is not the winner.
        "submit": Bounds(330, 170, 120, 32),
    },
    {
        "order_ref": 2,
        "requirements": {31109: 1, 20104: 1},
        "rewards": (
            WorkshopOrderRewardCategory.FEED,
            WorkshopOrderRewardCategory.WORKSHOP_EXP,
        ),
        "completeness": "complete",
        "ready": False,
        "submit": None,
    },
)


class _EmptyOcrService:
    """Deterministic OCR stub: every region reads empty, text stays unknown."""

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        return OcrResult(lines=(), words=())

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return ()

    def read_text(self, image: Image.Image, region: Bounds | None = None) -> str:
        return ""


def _capture(
    name: str, *, session_id: str, capture_sequence: int = 1, native_mode: bool = False
) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance and no payload shortcut."""

    with Image.open(FIXTURES / name) as source:
        image = source.copy() if native_mode else source.convert("RGB")
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=1,
            capture_sequence=capture_sequence,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _header_frame(name: str, *, session_id: str) -> CapturedScreenshot:
    """Compose a tracked native header band onto a blank native-size canvas.

    The header OCR regions only read the top ~70 image rows, so each 900x96
    RGBA crop is pasted at its native offset over a flat fill instead of
    duplicating a whole board capture per energy case.
    """

    with Image.open(FIXTURES / name) as band:
        image = Image.new("RGBA", (900, 1600), (20, 26, 38, 255))
        image.paste(band.copy(), (0, 0))
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=1,
            capture_sequence=1,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _wire(
    ocr_service: Any, *, workshop_matcher: OpenCvTemplateMatcher | None = None
) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publishers over the real packaged recognition stack."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(
        selector_registry=registry,
        workshop_producer=WorkshopContentProducer(matcher=workshop_matcher or matcher),
    )
    return make_publication_pair(
        selector_registry=registry,
        enricher=enricher,
        matcher=matcher,
        ocr_service=ocr_service,
    )


def _build_both(
    builder: ObservationBuilder,
    navigation: NavigationPerception,
    capture: CapturedScreenshot,
    screen_type: ScreenType,
) -> tuple[Observation, Observation]:
    """Publish one capture through both production paths with content enabled."""

    return (
        builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(screen_type),
            ocr_context=builder.create_ocr_context(capture),
        ),
        navigation.build(capture, include_content=True),
    )


def _elements(observation: Observation) -> set[UiElementId]:
    return set(observation.visible_elements)
