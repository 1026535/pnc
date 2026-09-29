"""Captured Pet Workshop header publication through real OCR."""

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
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.pet_workshop_publication.helpers import (
    _BOARD_LAYOUT_ID,
    _capture,
    _header_frame,
    _wire,
)

class PetWorkshopHeaderOcrTests(unittest.TestCase):
    """Scripted and RapidOCR reads of the measured header counters."""



    def test_header_counters_read_on_real_ocr(self) -> None:
        """Level, EXP, energy and reward counts parse from measured regions."""

        service = _require_rapid_ocr_service(self)
        builder, navigation = _wire(service)
        del navigation  # Builder path suffices for the OCR-dependent fields.
        # Reviewed header and order-card reward facts per fixture.
        expected: dict[str, dict[str, Any]] = {
            "pet_workshop.png": {
                "header": (8, 8, 166, 200),
                "rewards": (
                    ((WorkshopOrderRewardCategory.CHEST, 1),),
                    (
                        (WorkshopOrderRewardCategory.FEED, 9922),
                        (WorkshopOrderRewardCategory.WORKSHOP_EXP, 6),
                    ),
                    ((WorkshopOrderRewardCategory.BEAST_LASSO, 2),),
                ),
            },
            "pet_workshop_lv6_20260917.png": {
                "header": (6, 79, 200, 200),
                "rewards": (
                    (
                        (WorkshopOrderRewardCategory.FEED, 968),
                        (WorkshopOrderRewardCategory.WORKSHOP_EXP, 1),
                    ),
                    ((WorkshopOrderRewardCategory.FEED, 1634),),
                ),
            },
            "pet_workshop_board_20260924_native_rgba.png": {
                "header": (8, 21, 139, 200),
                "native": True,
                "rewards": (
                    (
                        (WorkshopOrderRewardCategory.UNKNOWN, None),
                        (WorkshopOrderRewardCategory.WORKSHOP_EXP, 2),
                    ),
                    ((WorkshopOrderRewardCategory.CHEST, 1),),
                ),
            },
            "pet_workshop_lv10_20260927.png": {
                "header": (10, 64, 141, 200),
                "native": True,
                "rewards": (
                    ((WorkshopOrderRewardCategory.CHEST, 1),),
                    (
                        (WorkshopOrderRewardCategory.FEED, 7722),
                        (WorkshopOrderRewardCategory.WORKSHOP_EXP, 3),
                    ),
                ),
            },
        }
        for fixture, facts in expected.items():
            capture = _capture(
                fixture,
                session_id="pw02-header",
                native_mode=facts.get("native", False),
            )
            observation = builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(
                    ScreenType.PNC_PET_WORKSHOP
                ),
                ocr_context=builder.create_ocr_context(capture),
            )
            workshop = observation.workshop
            self.assertIsNotNone(workshop)
            assert workshop is not None
            level, exp, energy_current, energy_capacity = facts["header"]
            with self.subTest(fixture=fixture):
                self.assertEqual(level, workshop.state.workshop_level)
                self.assertEqual(exp, workshop.state.workshop_exp)
                self.assertEqual(energy_current, workshop.state.energy.current)
                self.assertEqual(energy_capacity, workshop.state.energy.capacity)
                orders = workshop.state.order_survey.orders
                self.assertEqual(len(facts["rewards"]), len(orders))
                for order, reward_facts in zip(
                    orders, facts["rewards"], strict=True
                ):
                    self.assertEqual(
                        reward_facts,
                        tuple(
                            (reward.category, reward.quantity)
                            for reward in order.rewards
                        ),
                    )

    def test_native_energy_gauge_keeps_overlapped_leading_digit(self) -> None:
        """The native energy pill reads 162/200 and 163/200 despite a ghost '1'.

        September 27 manual-run regression: RapidOCR reports a stray ``1``
        line overlapping the leading digit of the real ``162/200``/``163/200``
        token. The canonical header path must keep the overlapped digit; an
        inserting a separator after overlap dedup corrupts the gauge into
        ``62/200``/``63/200``.
        """

        service = _require_rapid_ocr_service(self)
        builder, _navigation = _wire(service)
        del _navigation
        producer = WorkshopContentProducer(matcher=OpenCvTemplateMatcher())
        cases = {
            "pet_workshop_energy_162_20260927.png": (10, 64, 162, 200),
            "pet_workshop_energy_163_20260927.png": (10, 64, 163, 200),
        }
        for fixture, header in cases.items():
            capture = _header_frame(fixture, session_id="pw-f1-energy")
            additions = producer.additions_for_screen(
                image=capture.image,
                screen_type=ScreenType.PNC_PET_WORKSHOP,
                ocr_context=builder.create_ocr_context(capture),
                layout_id=_BOARD_LAYOUT_ID,
            )
            self.assertIsNotNone(additions)
            assert additions is not None and additions.workshop is not None
            state = additions.workshop.state
            with self.subTest(fixture=fixture):
                self.assertEqual(
                    header,
                    (
                        state.workshop_level,
                        state.workshop_exp,
                        state.energy.current,
                        state.energy.capacity,
                    ),
                )
