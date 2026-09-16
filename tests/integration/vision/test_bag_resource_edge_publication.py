"""V09 captured Resource edge publication through both production observers.

Replays the September 13 scrolled Resource frames that exposed the card-edge
publication defect plus the September 15 Speedup/Treasure tab captures, through
the real selector registry, packaged recognizer, production enricher/planner
and the real RapidOCR backend. Retained viewport-clipped fragments must publish
unresolved CLIPPED rows with no action or invented item facts, while the
existing selected-tab gate keeps Resource rows and actions off the neighbouring
tabs.
"""

from __future__ import annotations

import hashlib
import unittest
from typing import Any

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrReadStatus
from tests.integration.vision.test_bag_foundation_publication import (
    _BoundedRapidOcrService,
    _capture,
    _manual_rows,
    _new_context,
    _wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


_EDGE_RESOURCE_FRAMES = (
    "bag_variants/bag_resource_scroll_first.png",
    "bag_variants/bag_resource_scroll_settled.png",
)
_NON_RESOURCE_TAB_FRAMES = {
    "bag_variants/bag_speedup_tab.png": BagTab.SPEEDUP,
    "bag_variants/bag_treasure_tab.png": BagTab.TREASURE,
}
_EDGE_CONTROLS = {
    UiElementId.PNC_BACK_BUTTON_TOP_LEFT: Bounds(42, 18, 86, 54),
    UiElementId.PNC_BAG_SUBTAB_RESOURCE: Bounds(2, 207, 146, 60),
    UiElementId.PNC_BAG_SUBTAB_SPEEDUP: Bounds(182, 207, 146, 60),
    UiElementId.PNC_BAG_SUBTAB_TREASURE: Bounds(542, 207, 146, 60),
}
_BAG_LAYOUT_ID = "bag"


class BagResourceEdgePublicationTests(unittest.TestCase):
    """Real-capture proof for the Resource viewport-edge publication repair."""

    def _assert_bag_identity(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
    ) -> None:
        """Require independent Bag identity, a clear decision, and measured controls."""

        self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
        self.assertEqual(BagTab.RESOURCE, observation.active_bag_tab)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertTrue(observation.decision.action_eligible)
        self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertEqual(
            hashlib.sha256(capture.image.tobytes()).hexdigest(),
            observation.frame_fingerprint,
        )
        self.assertEqual(set(_EDGE_CONTROLS), set(observation.visible_elements))
        for selector_id, bounds in _EDGE_CONTROLS.items():
            element = observation.require(selector_id)
            self.assertEqual(bounds, element.bounds)
            self.assertEqual(capture.frame_ref, element.frame_ref)
            self.assertEqual(ScreenType.PNC_BAG, element.source_screen)
            self.assertEqual(_BAG_LAYOUT_ID, element.source_layout_id)

    def _assert_annotated_rows(
        self,
        observation: Observation,
        annotated_rows: tuple[dict[str, Any], ...],
        capture: CapturedScreenshot,
    ) -> None:
        """Compare published rows with the reviewed card annotations."""

        rows = observation.list_entries
        self.assertEqual(len(annotated_rows), len(rows))
        for row, annotated in zip(rows, annotated_rows, strict=True):
            self.assertEqual(capture.frame_ref, row.frame_ref)
            self.assertEqual(ScreenType.PNC_BAG, row.source_screen)
            self.assertEqual(_BAG_LAYOUT_ID, row.source_layout_id)
            self.assertEqual(annotated["expected_kind"], row.kind.value)
            card = Bounds(*annotated["card"])
            self.assertLessEqual(abs(row.bounds.x - card.x), 2)
            self.assertLessEqual(abs(row.bounds.y - card.y), 2)
            self.assertLessEqual(abs(row.bounds.width - card.width), 2)
            self.assertLessEqual(abs(row.bounds.height - card.height), 2)
            if annotated["expected_status"] == "clipped":
                self._assert_clipped_row(row)
                continue
            self._assert_complete_row(row, annotated)

    def _assert_clipped_row(self, row: DetectedListEntry) -> None:
        """A retained edge fragment stays unresolved and never invents facts."""

        self.assertEqual(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED, row.kind)
        self.assertEqual(RowRecognitionStatus.CLIPPED, row.row_status)
        self.assertIsNone(row.title_text)
        self.assertIsNone(row.action_point)
        self.assertIsNone(row.action_bounds)
        self.assertEqual("clipped_card", row.metadata["unresolved_reason"])
        for fact in ("item_id", "resource", "amount", "owned"):
            self.assertNotIn(fact, row.metadata)

    def _assert_complete_row(self, row: DetectedListEntry, annotated: dict[str, Any]) -> None:
        """Interior rows keep identity, counts and measured single-Use geometry."""

        self.assertEqual(ListEntryKind.RESOURCE_ITEM, row.kind)
        self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
        self.assertIsNotNone(row.action_point)
        self.assertIsNotNone(row.action_bounds)
        assert row.action_bounds is not None and row.action_point is not None
        self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
        self.assertTrue(row.action_bounds.contains_point(row.action_point))
        metadata = annotated["expected_metadata"]
        self.assertEqual(metadata["item_id"], row.metadata["item_id"])
        self.assertEqual(metadata["resource"], row.metadata["resource"])
        self.assertEqual(metadata["amount"], row.metadata["amount"])
        self.assertEqual(metadata["owned"], row.metadata["owned"])
        self.assertTrue(Bounds(*annotated["Use"]).contains_point(row.action_point))

    def test_scrolled_resource_frames_publish_clipped_edge_rows_on_both_paths(self) -> None:
        """Both scroll frames emit clipped edge rows plus complete interior rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        for sequence, name in enumerate(_EDGE_RESOURCE_FRAMES, start=1):
            with self.subTest(frame=name):
                capture = _capture(name, session_id="v09-bag-edge", capture_sequence=sequence)
                annotated_rows = _manual_rows(name)
                builder_context = _new_context(builder, contexts, capture)
                backend.bind(capture.image.size)
                observations = (
                    builder.build(
                        capture,
                        request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                        ocr_context=builder_context,
                    ),
                    navigation.build(capture, include_content=True),
                )
                navigation_context = contexts[-1]
                for publisher, observation, context in (
                    ("observation_builder", observations[0], builder_context),
                    ("navigation_perception", observations[1], navigation_context),
                ):
                    with self.subTest(publisher=publisher):
                        self._assert_bag_identity(observation, capture)
                        self._assert_annotated_rows(observation, annotated_rows, capture)
                        self.assertTrue(context.bounded_regions_required)
                        self.assertTrue(
                            any(
                                diagnostic.required_fact == "resource_inventory_rows"
                                and diagnostic.status == OcrReadStatus.ENGINE
                                for diagnostic in context.read_diagnostics
                            ),
                            "the Bag body read must run through the bounded planner",
                        )
                self.assertEqual(
                    observations[0].list_entries,
                    observations[1].list_entries,
                )

    def test_resource_to_other_tabs_publish_no_stale_resource_actions(self) -> None:
        """Speedup and Treasure frames after Resource work carry no Resource facts."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation, contexts = _wire(backend)
        session = "v09-bag-edge-tabs"
        resource_capture = _capture(
            "bag_variants/bag_resource_scroll_settled.png",
            session_id=session,
            capture_sequence=1,
        )
        backend.bind(resource_capture.image.size)
        builder.build(
            resource_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            ocr_context=_new_context(builder, contexts, resource_capture),
        )
        navigation.build(resource_capture, include_content=True)

        for sequence, (name, expected_tab) in enumerate(
            _NON_RESOURCE_TAB_FRAMES.items(), start=2,
        ):
            with self.subTest(frame=name):
                tab_capture = _capture(name, session_id=session, capture_sequence=sequence)
                backend.bind(tab_capture.image.size)
                builder_context = _new_context(builder, contexts, tab_capture)
                observations = (
                    builder.build(
                        tab_capture,
                        request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                        ocr_context=builder_context,
                    ),
                    navigation.build(tab_capture, include_content=True),
                )
                navigation_context = contexts[-1]
                for publisher, observation, context in (
                    ("observation_builder", observations[0], builder_context),
                    ("navigation_perception", observations[1], navigation_context),
                ):
                    with self.subTest(publisher=publisher):
                        self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
                        self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
                        self.assertEqual(expected_tab, observation.active_bag_tab)
                        self.assertEqual(tab_capture.frame_ref, observation.frame_ref)
                        self.assertNotEqual(
                            hashlib.sha256(resource_capture.image.tobytes()).hexdigest(),
                            observation.frame_fingerprint,
                        )
                        self.assertEqual((), observation.list_entries)
                        # Measured Bag navigation controls, including the
                        # unselected Resource button, stay available on the
                        # neighbouring tabs; Resource rows/actions/body reads
                        # remain gated to the typed Resource selection.
                        self.assertEqual(set(_EDGE_CONTROLS), set(observation.visible_elements))
                        for selector_id, bounds in _EDGE_CONTROLS.items():
                            element = observation.require(selector_id)
                            self.assertEqual(bounds, element.bounds)
                            self.assertEqual(tab_capture.frame_ref, element.frame_ref)
                            self.assertEqual(ScreenType.PNC_BAG, element.source_screen)
                            self.assertEqual(_BAG_LAYOUT_ID, element.source_layout_id)
                        self.assertFalse(
                            any(
                                diagnostic.required_fact == "resource_inventory_rows"
                                for diagnostic in context.read_diagnostics
                            ),
                            "the Resource body read must not run on another tab",
                        )


if __name__ == "__main__":
    unittest.main()
