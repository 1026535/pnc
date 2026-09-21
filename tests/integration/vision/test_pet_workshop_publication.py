"""Captured Pet Workshop publication through both production observers.

Qualifies the PW02 measured surfaces on the reviewed fixtures: real selector
registry, packaged visual recognizer, production enricher, and the shared
template matcher. ``ObservationBuilder`` and ``NavigationPerception`` must
agree on identity, the typed ``WorkshopObservation`` (logical state plus
measured view), and the measured controls, with frame/layout provenance on
the published view. Structural assertions run on a deterministic empty OCR
backend so unknown text fields stay unknown; the RapidOCR-gated case checks
the header counters when the real backend is available.

Fixture provenance (``tests/data/screen_recognition/manifest.json``):
``pet_workshop.png`` / ``pet_workshop_lv8_native_rgba.png`` are the at-rest
LV8 board; ``pet_workshop_lv6_20260917.png`` is the LV6 board;
``pet_workshop_selected_{treasure,bowl}_20260917.png`` carry reviewed
selection states; the item/order detail, help and storage fixtures cover the
measured overlay surfaces.
"""

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
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


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
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return builder, navigation


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


class PetWorkshopBoardPublicationTests(unittest.TestCase):
    """Replayed board captures qualify the typed Workshop contract on both paths."""

    def _assert_board_identity(
        self, observation: Observation, capture: CapturedScreenshot
    ) -> None:
        """Require independent board identity, a clear decision, and provenance."""

        self.assertEqual(ScreenType.PNC_PET_WORKSHOP, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(_BOARD_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertEqual(
            hashlib.sha256(capture.image.tobytes()).hexdigest(),
            observation.frame_fingerprint,
        )
        self.assertTrue(
            any(
                evidence.screen_type == ScreenType.PNC_PET_WORKSHOP
                and evidence.layout_id == _BOARD_LAYOUT_ID
                for evidence in observation.decision.evidence
            ),
            "independent visual anchor evidence must own the board layout",
        )

    def _assert_board_observation(
        self, observation: Observation, capture: CapturedScreenshot
    ) -> Any:
        """Return the published WorkshopObservation after shared board checks."""

        workshop = observation.workshop
        self.assertIsNotNone(workshop, "board capture must publish a workshop observation")
        assert workshop is not None
        state = workshop.state
        view = workshop.view
        self.assertEqual(WorkshopSurfaceKind.BOARD, state.surface)
        self.assertEqual(capture.frame_ref, view.frame_ref)
        self.assertEqual(ScreenType.PNC_PET_WORKSHOP, view.source_screen)
        self.assertEqual(_BOARD_LAYOUT_ID, view.source_layout_id)
        self.assertEqual(capture.image.size, view.image_size)
        return workshop

    def test_lv8_board_publishes_state_on_both_paths(self) -> None:
        """The at-rest LV8 board yields the same reviewed state on both publishers."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture("pet_workshop.png", session_id="pw02-lv8")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_board_identity(observation, capture)
                workshop = self._assert_board_observation(observation, capture)
                state = workshop.state
                self.assertEqual(63, len(state.cells))
                self.assertEqual(63, len(workshop.view.cell_bounds))
                self.assertEqual(
                    {
                        (WorkshopCellAccess.USABLE, WorkshopOccupancy.OCCUPIED): 25,
                        (WorkshopCellAccess.USABLE, WorkshopOccupancy.EMPTY): 24,
                        (WorkshopCellAccess.LOCKED, WorkshopOccupancy.EMPTY): 7,
                        (WorkshopCellAccess.LOCKED, WorkshopOccupancy.UNKNOWN): 7,
                    },
                    Counter(
                        (cell.access, cell.occupancy) for cell in state.cells
                    ),
                )
                items = {
                    cell.cell_id: cell.item_id
                    for cell in state.cells
                    if cell.item_id is not None
                }
                self.assertEqual(_LV8_ITEMS, items)
                self.assertEqual(
                    set(_LV8_UNKNOWN_OCCUPIED),
                    {
                        cell.cell_id
                        for cell in state.cells
                        if cell.occupancy == WorkshopOccupancy.OCCUPIED
                        and cell.item_id is None
                    },
                )
                # Grey overlays measure inactive independently of identity.
                self.assertEqual(
                    set(_LV8_INACTIVE),
                    {
                        cell.cell_id
                        for cell in state.cells
                        if cell.item_status == WorkshopItemStatus.INACTIVE
                    },
                )
                self.assertEqual(
                    set(_LV8_LOCKED_EMPTY),
                    {
                        cell.cell_id
                        for cell in state.cells
                        if cell.access == WorkshopCellAccess.LOCKED
                        and cell.occupancy == WorkshopOccupancy.EMPTY
                    },
                )
                self.assertEqual(
                    set(_LV8_LOCKED_UNKNOWN),
                    {
                        cell.cell_id
                        for cell in state.cells
                        if cell.access == WorkshopCellAccess.LOCKED
                        and cell.occupancy == WorkshopOccupancy.UNKNOWN
                    },
                )
                # Header counters stay unknown without an OCR backend.
                self.assertIsNone(state.workshop_level)
                self.assertIsNone(state.workshop_exp)
                self.assertIsNone(state.energy.current)
                self.assertIsNone(state.energy.capacity)
                self.assertEqual(WorkshopSelectionKind.NONE, state.selection.kind)
                # Bolt overlays measured on this board qualify ordinary mode.
                self.assertEqual("ordinary", state.production_mode.value)
                strip = workshop.view.order_strip_bounds
                self.assertIsNotNone(strip)
                assert strip is not None
                self.assertTrue(
                    Bounds(10, 60, 530, 185).contains_bounds(strip),
                    f"measured strip bounds {strip} outside the strip surface",
                )
                orders = state.order_survey.orders
                self.assertEqual(3, len(orders))
                self.assertEqual(3, len(workshop.view.order_views))
                views_by_ref = {
                    view.order_ref: view for view in workshop.view.order_views
                }
                for order, expected in zip(orders, _LV8_ORDERS, strict=True):
                    self.assertEqual(expected["order_ref"], order.order_ref)
                    self.assertEqual(expected["requirements"], order.requirements)
                    self.assertEqual(
                        expected["rewards"],
                        tuple(reward.category for reward in order.rewards),
                    )
                    self.assertEqual(
                        expected["completeness"], order.completeness.value
                    )
                    self.assertEqual(expected["ready"], order.ready)
                    self.assertEqual("order_strip", order.source)
                    view = views_by_ref[order.order_ref]
                    self.assertEqual(expected["submit"], view.submit_bounds)
                    self.assertIsNotNone(view.portrait_bounds)
                # Measured controls: persistent bar controls only; the
                # selection-dependent inspect/recycle pair stays unpublished.
                self.assertEqual(
                    {
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        UiElementId.PNC_PET_WORKSHOP_HELP_BUTTON,
                        UiElementId.PNC_PET_WORKSHOP_STORAGE_BUTTON,
                        UiElementId.PNC_PET_WORKSHOP_NEXT_BOARD_BUTTON,
                    },
                    _elements(observation),
                )
                self.assertIsNone(workshop.view.detail_control_bounds)
                self.assertIsNone(workshop.view.recycle_control_bounds)
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)

    def test_lv6_board_publishes_reviewed_orders(self) -> None:
        """The LV6 board decodes its two present cards; the empty slot stays absent."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture("pet_workshop_lv6_20260917.png", session_id="pw02-lv6")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_board_identity(observation, capture)
                workshop = self._assert_board_observation(observation, capture)
                state = workshop.state
                self.assertEqual(63, len(state.cells))
                orders = state.order_survey.orders
                self.assertEqual(2, len(orders))
                self.assertEqual(2, len(workshop.view.order_views))
                for order, requirements in zip(orders, _LV6_REQUIREMENTS, strict=True):
                    self.assertEqual(requirements, order.requirements)
                self.assertEqual("complete", orders[0].completeness.value)
                self.assertFalse(orders[0].ready)
                self.assertEqual(
                    (
                        WorkshopOrderRewardCategory.FEED,
                        WorkshopOrderRewardCategory.WORKSHOP_EXP,
                    ),
                    tuple(reward.category for reward in orders[0].rewards),
                )
                self.assertEqual("complete", orders[1].completeness.value)
                self.assertEqual(
                    (WorkshopOrderRewardCategory.FEED,),
                    tuple(reward.category for reward in orders[1].rewards),
                )
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)

    def test_missed_requirement_hit_marks_card_unreadable(self) -> None:
        """A missed icon hit degrades the card instead of shrinking its recipe."""

        class _DropThirdFruitHit(OpenCvTemplateMatcher):
            """Drop one coconut tile match to replay the review's missed hit."""

            def find_matches(
                self,
                image: Any,
                template_path: Any,
                *,
                threshold: float,
                search_region: Bounds | None = None,
                reference_size: tuple[int, int] | None = None,
                max_matches: int = 8,
            ) -> Any:
                matches = super().find_matches(
                    image,
                    template_path,
                    threshold=threshold,
                    search_region=search_region,
                    reference_size=reference_size,
                    max_matches=max_matches,
                )
                if (
                    Path(template_path).name == "pet_workshop_req_fruit_5.png"
                    and len(matches) >= 3
                ):
                    return matches[:-1]
                return matches

        registry = build_default_selector_registry()
        matcher = OpenCvTemplateMatcher()
        enricher = PncObservationEnricher(
            selector_registry=registry,
            workshop_producer=WorkshopContentProducer(matcher=_DropThirdFruitHit()),
        )
        builder = ObservationBuilder(
            selector_registry=registry,
            selector_engine=ImageSelectorEngine(matcher),
            screen_classifier=ScreenClassifier(),
            enricher=enricher,
            ocr_service=_EmptyOcrService(),
            visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        )
        capture = _capture("pet_workshop.png", session_id="pw02-missed-hit")
        observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_PET_WORKSHOP),
            ocr_context=builder.create_ocr_context(capture),
        )
        workshop = observation.workshop
        self.assertIsNotNone(workshop)
        assert workshop is not None
        orders = workshop.state.order_survey.orders
        self.assertEqual(3, len(orders))
        # Two of the three fruit hits matched, but the third measured tile run
        # has no icon: the card must not publish a complete two-piece recipe.
        self.assertEqual({20105: 2}, orders[0].requirements)
        self.assertEqual("unreadable", orders[0].completeness.value)
        self.assertEqual("complete", orders[1].completeness.value)

    def test_native_rgba_board_publishes_on_both_paths(self) -> None:
        """Native RGBA reaches real OCR and both publishers without test conversion."""

        builder, navigation = _wire(_require_rapid_ocr_service(self))
        capture = _capture(
            "pet_workshop_lv8_native_rgba.png",
            session_id="pw02-lv8-rgba",
            native_mode=True,
        )
        self.assertEqual("RGBA", capture.image.mode)

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_board_identity(observation, capture)
                workshop = self._assert_board_observation(observation, capture)
                state = workshop.state
                self.assertEqual((8, 8, 166, 200), (
                    state.workshop_level, state.workshop_exp,
                    state.energy.current, state.energy.capacity,
                ))
                self.assertEqual(
                    ((1,), (9922, 6), (2,)),
                    tuple(tuple(r.quantity for r in o.rewards) for o in state.order_survey.orders),
                )
                self.assertEqual(63, len(state.cells))
                items = {
                    cell.cell_id: cell.item_id
                    for cell in state.cells
                    if cell.item_id is not None
                }
                self.assertEqual(_LV8_ITEMS, items)
                self.assertEqual(
                    WorkshopSelectionKind.NONE, state.selection.kind
                )
                orders = state.order_survey.orders
                self.assertEqual(3, len(orders))
                for order, expected in zip(orders, _LV8_ORDERS, strict=True):
                    self.assertEqual(expected["order_ref"], order.order_ref)
                    self.assertEqual(expected["requirements"], order.requirements)
                    self.assertEqual(
                        expected["rewards"],
                        tuple(reward.category for reward in order.rewards),
                    )
                    self.assertEqual(
                        expected["completeness"], order.completeness.value
                    )
                self.assertIsNotNone(workshop.view.order_strip_bounds)
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)

    def test_missed_reward_icon_keeps_unknown_group(self) -> None:
        """Missing EXP art cannot disappear inside the preceding feed count zone."""

        class DropExp(OpenCvTemplateMatcher):
            """Replay one missed reward match without changing its real pixels."""

            def find_matches(self, image: Any, template_path: Any, **kwargs: Any) -> Any:
                if Path(template_path).name == "pet_workshop_rew_exp.png":
                    return ()
                return super().find_matches(image, template_path, **kwargs)

        capture = _capture("pet_workshop.png", session_id="pw02-reward-miss")
        for ocr in (_EmptyOcrService(), _require_rapid_ocr_service(self)):
            builder, navigation = _wire(ocr, workshop_matcher=DropExp())
            first, second = _build_both(builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP)
            self.assertEqual(first.workshop, second.workshop)
            assert first.workshop is not None
            order = first.workshop.state.order_survey.orders[1]
            self.assertEqual("unreadable", order.completeness.value)
            self.assertEqual(
                (WorkshopOrderRewardCategory.FEED, WorkshopOrderRewardCategory.UNKNOWN),
                tuple(reward.category for reward in order.rewards),
            )
            self.assertIsNone(order.rewards[1].quantity)
            if not isinstance(ocr, _EmptyOcrService):
                self.assertEqual(9922, order.rewards[0].quantity)

    def test_scrolled_three_piece_card_keeps_clipped_coverage(self) -> None:
        """A synthetic strip scroll hides one coconut behind the timer viewport."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture("pet_workshop.png", session_id="pw02-scrolled-strip")
        # Transform an authored reference, not a live capture: the order
        # viewport moves left by one tile while the timer continues to occlude it.
        capture.image.paste(capture.image.crop((158, 45, 540, 230)), (106, 45))
        capture.image.paste(Image.new("RGB", (52, 185), (56, 91, 90)), (488, 45))
        for observation in _build_both(builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP):
            assert observation.workshop is not None
            orders = observation.workshop.state.order_survey.orders
            self.assertEqual({20105: 2}, orders[0].requirements)
            self.assertEqual("clipped", orders[0].completeness.value)
            self.assertEqual({10204: 1, 31109: 1}, orders[1].requirements)
            self.assertEqual("complete", orders[1].completeness.value)
            self.assertEqual(230, observation.workshop.view.order_views[1].portrait_bounds.x)
            self.assertEqual("clipped", orders[2].completeness.value)

    def test_ambiguous_selection_abstains_even_with_empty_bar(self) -> None:
        """Competing brackets cannot be overridden by an apparently empty bar."""

        class SplitCorners(OpenCvTemplateMatcher):
            """Supply contradictory votes at two actual board cells."""

            def find_matches(self, image: Any, template_path: Any, **kwargs: Any) -> Any:
                name = Path(template_path).name
                if name == "pet_workshop_sel_corner.png":
                    return tuple(TemplateMatch(bounds=Bounds(x, 246, 6, 6), confidence=0.99)
                                 for x in (27, 77, 98, 148))
                if "sel_corner" in name:
                    return ()
                return super().find_matches(image, template_path, **kwargs)

        builder, navigation = _wire(_EmptyOcrService(), workshop_matcher=SplitCorners())
        capture = _capture("pet_workshop.png", session_id="pw02-split-corners")
        for observation in _build_both(builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP):
            assert observation.workshop is not None
            self.assertEqual(WorkshopSelectionKind.UNKNOWN, observation.workshop.state.selection.kind)

    def test_item_identity_without_state_evidence_abstains(self) -> None:
        """Readable identity cannot make an unqualified action state normal."""

        class DropState(OpenCvTemplateMatcher):
            """Retain sprite hits while withholding the independent state evidence."""

            def find_best_match(self, image: Any, template_path: Any, **kwargs: Any) -> Any:
                if Path(template_path).name.startswith("pet_workshop_state_"):
                    return None
                return super().find_best_match(image, template_path, **kwargs)

        builder, navigation = _wire(_EmptyOcrService(), workshop_matcher=DropState())
        capture = _capture("pet_workshop.png", session_id="pw02-state-miss")
        for observation in _build_both(builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP):
            assert observation.workshop is not None
            known = [c for c in observation.workshop.state.cells if c.item_id is not None]
            self.assertEqual(_LV8_ITEMS, {c.cell_id: c.item_id for c in known})
            self.assertTrue(all(c.item_status == WorkshopItemStatus.UNKNOWN for c in known))

    def test_selected_treasure_publishes_selection_and_recycle(self) -> None:
        """The selected treasure cell carries inspect and recycle controls."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture(
            "pet_workshop_selected_treasure_20260917.png", session_id="pw02-sel-treasure"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_board_identity(observation, capture)
                workshop = self._assert_board_observation(observation, capture)
                self.assertEqual(
                    WorkshopSelectionKind.SELECTED, workshop.state.selection.kind
                )
                self.assertEqual(33, workshop.state.selection.cell_id)
                self.assertIsNotNone(workshop.view.detail_control_bounds)
                self.assertIsNotNone(workshop.view.recycle_control_bounds)
                self.assertTrue(
                    {
                        UiElementId.PNC_PET_WORKSHOP_INSPECT_BUTTON,
                        UiElementId.PNC_PET_WORKSHOP_RECYCLE_BUTTON,
                    }.issubset(_elements(observation))
                )
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)

    def test_selected_bowl_publishes_inspect_without_recycle(self) -> None:
        """The selected bowl cell keeps the item-dependent recycle unpublished."""

        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture(
            "pet_workshop_selected_bowl_20260917.png", session_id="pw02-sel-bowl"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, capture, ScreenType.PNC_PET_WORKSHOP
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_board_identity(observation, capture)
                workshop = self._assert_board_observation(observation, capture)
                self.assertEqual(
                    WorkshopSelectionKind.SELECTED, workshop.state.selection.kind
                )
                self.assertEqual(1, workshop.state.selection.cell_id)
                self.assertIsNotNone(workshop.view.detail_control_bounds)
                # The inactive bowl offers no recycle control; absence is
                # measured, not inferred.
                self.assertIsNone(workshop.view.recycle_control_bounds)
                self.assertIn(
                    UiElementId.PNC_PET_WORKSHOP_INSPECT_BUTTON,
                    _elements(observation),
                )
                self.assertNotIn(
                    UiElementId.PNC_PET_WORKSHOP_RECYCLE_BUTTON,
                    _elements(observation),
                )
        self.assertEqual(builder_observation.workshop, navigation_observation.workshop)


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
    ) -> tuple[Observation, Observation, Any]:
        builder, navigation = _wire(_EmptyOcrService())
        capture = _capture(fixture, session_id=session_id)
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


class PetWorkshopHeaderOcrTests(unittest.TestCase):
    """RapidOCR-backed reads of the measured header counters."""

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
        }
        for fixture, facts in expected.items():
            capture = _capture(fixture, session_id="pw02-header")
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


if __name__ == "__main__":
    unittest.main()
