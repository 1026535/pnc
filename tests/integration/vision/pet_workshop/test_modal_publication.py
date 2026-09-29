"""Captured Pet Workshop modal publication through both production observers."""

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
    FIXTURES,
    _EmptyOcrService,
    _HELP_LAYOUT_ID,
    _ITEM_DETAIL_LAYOUT_ID,
    _MANOR_LAYOUT_ID,
    _ORDER_DETAIL_LAYOUT_ID,
    _STORAGE_LAYOUT_ID,
    _build_both,
    _capture,
    _elements,
    _wire,
)

class PetWorkshopModalPublicationTests(unittest.TestCase):
    """Measured overlay surfaces publish their reviewed surface kind and controls."""

    def _assert_modal_identity(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        screen_type: ScreenType,
        layout_id: str,
    ) -> Any:
        self.assertEqual(screen_type, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(layout_id, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertTrue(
            any(
                evidence.screen_type == screen_type and evidence.layout_id == layout_id
                for evidence in observation.decision.evidence
            ),
            f"independent visual anchor evidence must own {layout_id}",
        )
        workshop = observation.workshop
        self.assertIsNotNone(workshop, f"{layout_id} must publish a workshop observation")
        assert workshop is not None
        self.assertEqual(capture.frame_ref, workshop.view.frame_ref)
        self.assertEqual(screen_type, workshop.view.source_screen)
        self.assertEqual(layout_id, workshop.view.source_layout_id)
        return workshop

    def _assert_both(
        self,
        fixture: str,
        screen_type: ScreenType,
        layout_id: str,
        session_id: str,
        *,
        native_mode: bool = False,
        ocr_service: Any | None = None,
    ) -> tuple[Observation, Observation, Any]:
        """Keep published Workshop dialogs inspectable by their owning workflow."""

        builder, navigation = _wire(
            _EmptyOcrService() if ocr_service is None else ocr_service
        )
        capture = _capture(
            fixture, session_id=session_id, native_mode=native_mode
        )
        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, screen_type
        )
        workshops = []
        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                workshops.append(
                    self._assert_modal_identity(
                        observation, capture, screen_type, layout_id
                    )
                )
                session = FakeSession()
                observer = FakeObservationService(observations=[])
                executor = _make_observed_action_executor(session)
                recovered = executor.recover_interruption_if_required(
                    observation,
                    label_prefix="inspect_workshop_dialog",
                    observe=observer.observe,
                )
                self.assertIsNone(recovered)
                self.assertEqual([], session.taps)
                self.assertEqual([], session.key_events)
                self.assertEqual([], observer.requests)
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)
        return builder_observation, navigation_observation, workshops[0]

    def test_item_detail_surface_publishes_close_control(self) -> None:
        """The item-detail dialog reports its surface and measured close X."""

        _, _, workshop = self._assert_both(
            "pet_workshop_item_detail.png",
            ScreenType.PNC_PET_WORKSHOP_ITEM_DETAIL,
            _ITEM_DETAIL_LAYOUT_ID,
            "pw02-item-detail",
        )
        self.assertEqual(WorkshopSurfaceKind.ITEM_DETAIL, workshop.state.surface)
        # The modal publishes no strip evidence; bounds stay unpublished.
        self.assertIsNone(workshop.view.order_strip_bounds)
        self.assertIsNotNone(workshop.view.close_control_bounds)
        assert workshop.view.close_control_bounds is not None
        self.assertTrue(
            Bounds(430, 185, 95, 90).contains_bounds(workshop.view.close_control_bounds)
        )

    def test_order_detail_surface_publishes_targets_and_rewards(self) -> None:
        """The order-detail dialog reads its requirement pair and reward icons."""

        observation, _, workshop = self._assert_both(
            "pet_workshop_order_detail.png",
            ScreenType.PNC_PET_WORKSHOP_ORDER_DETAIL,
            _ORDER_DETAIL_LAYOUT_ID,
            "pw02-order-detail",
        )
        self.assertEqual(WorkshopSurfaceKind.ORDER_DETAIL, workshop.state.surface)
        self.assertIsNone(workshop.view.order_strip_bounds)
        self.assertIsNotNone(workshop.view.close_control_bounds)
        orders = workshop.state.order_survey.orders
        self.assertEqual(1, len(orders))
        order = orders[0]
        self.assertEqual({20104: 1, 10106: 1}, order.requirements)
        self.assertEqual(
            (
                WorkshopOrderRewardCategory.FEED,
                WorkshopOrderRewardCategory.WORKSHOP_EXP,
            ),
            tuple(reward.category for reward in order.rewards),
        )
        self.assertEqual("order_detail", order.source)
        # No submit control exists on the detail surface; ready stays unknown.
        self.assertIsNone(order.ready)
        self.assertNotIn(
            UiElementId.PNC_PET_WORKSHOP_NEXT_BOARD_BUTTON,
            _elements(observation),
        )

    def test_order_detail_native_rgba_publishes_lasso_recipe(self) -> None:
        """The LV8 lasso order modal reads its Wood 10 + Fruit 5 recipe."""

        observation, _, workshop = self._assert_both(
            "pet_workshop_order_detail_lasso_native_rgba.png",
            ScreenType.PNC_PET_WORKSHOP_ORDER_DETAIL,
            _ORDER_DETAIL_LAYOUT_ID,
            "pw05-order-detail-lasso",
            native_mode=True,
        )
        state = workshop.state
        self.assertEqual(WorkshopSurfaceKind.ORDER_DETAIL, state.surface)
        self.assertIsNone(workshop.view.order_strip_bounds)
        self.assertIsNotNone(workshop.view.close_control_bounds)
        orders = state.order_survey.orders
        self.assertEqual(1, len(orders))
        order = orders[0]
        self.assertEqual({20210: 1, 20105: 1}, order.requirements)
        self.assertEqual(
            (
                WorkshopOrderRewardCategory.FEED,
                WorkshopOrderRewardCategory.BEAST_LASSO,
            ),
            tuple(reward.category for reward in order.rewards),
        )
        self.assertEqual("order_detail", order.source)
        self.assertIsNone(order.ready)
        self.assertNotIn(
            UiElementId.PNC_PET_WORKSHOP_NEXT_BOARD_BUTTON,
            _elements(observation),
        )

    def test_order_detail_native_rgba_publishes_chest_quantity(self) -> None:
        """The three-Fruit-5 detail modal proves its Item Chest badge quantity.

        The 2026-09-24 manual-board capture's raw count-zone OCR misread the
        chest's ``1`` badge as ``L``; the measured zone retries once on an
        upscaled crop and must publish quantity 1.
        """

        _, _, workshop = self._assert_both(
            "pet_workshop_order_detail_chest_20260924_native_rgba.png",
            ScreenType.PNC_PET_WORKSHOP_ORDER_DETAIL,
            _ORDER_DETAIL_LAYOUT_ID,
            "pw05-order-detail-chest",
            native_mode=True,
            ocr_service=_require_rapid_ocr_service(self),
        )
        state = workshop.state
        self.assertEqual(WorkshopSurfaceKind.ORDER_DETAIL, state.surface)
        orders = state.order_survey.orders
        self.assertEqual(1, len(orders))
        order = orders[0]
        self.assertEqual({20105: 3}, order.requirements)
        self.assertEqual(
            ((WorkshopOrderRewardCategory.CHEST, 1),),
            tuple((reward.category, reward.quantity) for reward in order.rewards),
        )
        self.assertEqual("order_detail", order.source)
        self.assertIsNone(order.ready)

    def test_help_surface_publishes_close_control(self) -> None:
        """The Tip rules dialog reports the help surface and its close X."""

        _, _, workshop = self._assert_both(
            "pet_workshop_help.png",
            ScreenType.PNC_PET_WORKSHOP_HELP,
            _HELP_LAYOUT_ID,
            "pw02-help",
        )
        self.assertEqual(WorkshopSurfaceKind.HELP, workshop.state.surface)
        self.assertIsNone(workshop.view.order_strip_bounds)
        self.assertIsNotNone(workshop.view.close_control_bounds)

    def test_storage_surface_is_excluded_modal_without_close(self) -> None:
        """The storage drawer is an excluded surface with no measured close."""

        _, _, workshop = self._assert_both(
            "pet_workshop_storage.png",
            ScreenType.PNC_PET_WORKSHOP_STORAGE,
            _STORAGE_LAYOUT_ID,
            "pw02-storage",
        )
        # The premium Get-Slots sheet is dismissed by an outside tap; no
        # dismiss control is measured or published.
        self.assertEqual(WorkshopSurfaceKind.EXCLUDED_MODAL, workshop.state.surface)
        self.assertIsNone(workshop.view.order_strip_bounds)
        self.assertIsNone(workshop.view.close_control_bounds)

    def test_storage_native_rgba_publishes_excluded_modal(self) -> None:
        """The six-slot LV7 sheet classifies as storage on its native frame.

        The reviewed LV7 capture carries six occupied slots with Get Slots in
        the second column; the fixed first-column bands missed it and the frame
        fell through to the board parser, crashing on its noise energy read.
        """

        with Image.open(FIXTURES / "pet_workshop_storage_lv7_native_rgba.png") as probe:
            self.assertEqual("RGBA", probe.mode)

        observation, _, workshop = self._assert_both(
            "pet_workshop_storage_lv7_native_rgba.png",
            ScreenType.PNC_PET_WORKSHOP_STORAGE,
            _STORAGE_LAYOUT_ID,
            "pw02-storage-lv7",
            native_mode=True,
            ocr_service=_require_rapid_ocr_service(self),
        )
        state = workshop.state
        self.assertEqual(WorkshopSurfaceKind.EXCLUDED_MODAL, state.surface)
        self.assertEqual((), state.cells)
        self.assertEqual((), state.order_survey.orders)
        self.assertIsNone(state.energy.current)
        self.assertIsNone(state.energy.capacity)
        self.assertIsNone(state.workshop_level)
        self.assertIsNone(state.workshop_exp)
        self.assertEqual(WorkshopSelectionKind.UNKNOWN, state.selection.kind)
        self.assertEqual(
            WorkshopProductionMode.UNKNOWN, state.production_mode
        )
        view = workshop.view
        self.assertEqual((900, 1600), view.image_size)
        self.assertIsNone(view.close_control_bounds)
        self.assertIsNone(view.order_strip_bounds)
        self.assertIsNone(view.detail_control_bounds)
        self.assertIsNone(view.recycle_control_bounds)
        self.assertFalse(
            {
                element
                for element in _elements(observation)
                if element.name.startswith("PNC_PET_WORKSHOP")
            },
            "an excluded storage modal publishes no Workshop action controls",
        )

    def test_manor_publishes_no_workshop_content(self) -> None:
        """The manor hub is a navigation screen, not a Workshop surface."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture("illusory_beast_manor.png", session_id="pw02-manor")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_ILLUSORY_BEAST_MANOR
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self.assertEqual(
                    ScreenType.PNC_ILLUSORY_BEAST_MANOR, observation.screen_type
                )
                self.assertEqual(_MANOR_LAYOUT_ID, observation.decision.layout_id)
                self.assertIsNone(observation.workshop)
                self.assertEqual(
                    {
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        UiElementId.PNC_ILLUSORY_BEAST_MANOR_PET_WORKSHOP_BUTTON,
                    },
                    _elements(observation),
                )
