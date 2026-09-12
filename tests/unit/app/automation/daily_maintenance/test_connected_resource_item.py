"""Offline checks at the connected resource-item mutation boundary."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from pnc_automation.app.automation.daily_maintenance.connected_resource_item import (
    ConnectedResourceItemSession,
)
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.domain.resource_items import ResourceItem
from pnc_automation.app.pnc.domain.resource_items import ResourceInventoryStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds

from tests.support.pnc.observations import make_observation


class ConnectedResourceItemTests(unittest.TestCase):
    """Proves the live adapter sends only freshly resolved single-item actions."""

    def test_single_use_targets_the_fresh_visual_row(self) -> None:
        """Never dispatches the generic Bag Use or orange bulk selector."""

        observer = Mock()
        observer.observe.return_value = _observation("fresh")
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        session.use_one(ResourceItem("gold:50:normal", "gold", 50, 277, "fresh"))
        action, source = actions.execute_action.call_args.args
        self.assertIsInstance(action, TapListEntryAction)
        self.assertEqual(ListEntryKind.RESOURCE_ITEM, action.entry_kind)
        self.assertEqual("fresh", action.metadata_value)
        self.assertTrue(action.use_action_point)
        self.assertEqual("fresh", source.list_entries[0].metadata["observation_fingerprint"])

    def test_stale_fingerprint_never_dispatches(self) -> None:
        """Stops when inventory changed between selection and use."""

        observer = Mock()
        observer.observe.return_value = _observation("changed")
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            session.use_one(ResourceItem("gold:50:normal", "gold", 50, 277, "stale"))
        actions.execute_action.assert_not_called()

    def test_wrong_screen_never_dispatches(self) -> None:
        """Does not turn a popup or unknown screen into permission to tap."""

        observer = Mock()
        observer.observe.return_value = make_observation(ScreenType.UNKNOWN)
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        with self.assertRaisesRegex(ValueError, "Bag"):
            session.use_one(ResourceItem("gold:50:normal", "gold", 50, 277, "fresh"))
        actions.execute_action.assert_not_called()

    def test_ocr_geometry_is_rejected(self) -> None:
        """Requires a visually materialized row action point."""

        observer = Mock()
        observer.observe.return_value = _observation("fresh", provenance="ocr")
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        with self.assertRaisesRegex(ValueError, "visual"):
            session.use_one(ResourceItem("gold:50:normal", "gold", 50, 277, "fresh"))
        actions.execute_action.assert_not_called()

    def test_scroll_bounce_gets_one_bounded_stability_reread(self) -> None:
        """Accepts the final agreeing pair after a single overscroll animation frame."""

        settled = _observation("settled")
        moving = replace(
            settled,
            list_entries=(replace(settled.list_entries[0], bounds=Bounds(6, 302, 528, 120)),),
        )
        observer = Mock()
        observer.observe.side_effect = (moving, settled, settled)
        session = ConnectedResourceItemSession(observer, _actions(), Mock(), Mock())
        self.assertEqual(settled, session._stable("bounce"))
        self.assertEqual(3, observer.observe.call_count)

    def test_continuing_instability_stops_without_another_action(self) -> None:
        """Caps observation retries when the inventory never settles."""

        first = _observation("first")
        frames = tuple(
            replace(first, list_entries=(replace(
                first.list_entries[0], bounds=Bounds(6, y, 528, 120),
            ),)) for y in (302, 301, 300)
        )
        observer = Mock()
        observer.observe.side_effect = frames
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        with self.assertRaisesRegex(ValueError, "unstable"):
            session._stable("moving")
        self.assertEqual(3, observer.observe.call_count)
        actions.execute_action.assert_not_called()

    def test_bag_observation_reopens_inventory_after_required_update_recovery(self) -> None:
        """Resumes Bag reconciliation from Home after the shared updater finishes."""

        update = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        bag = _observation("after-update")
        observer = Mock()
        observer.observe.side_effect = (update, bag, bag)
        actions = _actions()
        actions.recover_interruption_if_required.side_effect = (home, None, None)
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())

        result = session._observe("resource_reconcile")

        self.assertEqual(result, bag)
        self.assertEqual(actions.recover_interruption_if_required.call_count, 3)
        self.assertEqual(3, observer.observe.call_count)

    def test_complete_view_uses_observed_rows_and_marks_unresolved_inventory_unknown(self) -> None:
        """Consumes parser-published unresolved rows without reopening the screenshot."""

        complete = _observation("fresh")
        self.assertEqual((), ConnectedResourceItemSession._require_complete_view(complete))
        unresolved = DetectedListEntry(
            ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED,
            Bounds(6, 430, 528, 120),
            row_status=RowRecognitionStatus.UNREADABLE,
            metadata={"unresolved_reason": "missing_title"},
        )
        unknown = replace(complete, list_entries=(complete.list_entries[0], unresolved))
        self.assertEqual(
            ("missing_title",),
            ConnectedResourceItemSession._require_complete_view(unknown),
        )

    def test_items_reject_duplicate_identity_rows_in_one_observation(self) -> None:
        """Never collapses duplicate semantic cards into one inventory count."""

        first = _observation("fresh").list_entries[0]
        duplicate = replace(
            first,
            bounds=Bounds(6, 440, 528, 120),
            action_bounds=Bounds(430, 460, 50, 36),
            action_point=(453, 478),
        )
        observation = replace(_observation("fresh"), list_entries=(first, duplicate))
        with self.assertRaisesRegex(ValueError, "duplicate item identities"):
            ConnectedResourceItemSession._items(observation)

    def test_scan_inventory_returns_typed_unknown_before_items_or_mutation(self) -> None:
        """Stops after a bad scrolled viewport without manufacturing an empty inventory."""

        complete = _observation("fresh")
        first = complete.list_entries[0]
        duplicate = replace(
            first,
            bounds=Bounds(6, 440, 528, 120),
            action_bounds=Bounds(430, 460, 50, 36),
            action_point=(453, 478),
        )
        incomplete = replace(first, row_status=RowRecognitionStatus.UNREADABLE, action_point=None, action_bounds=None)
        for invalid_entry in (duplicate, incomplete):
            with self.subTest(status=invalid_entry.row_status):
                invalid = replace(complete, list_entries=(first, invalid_entry))
                observer = Mock()
                actions = _actions()
                session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
                with (
                    patch.object(ConnectedResourceItemSession, "_open_inventory"),
                    patch.object(ConnectedResourceItemSession, "_stable", return_value=complete),
                    patch.object(ConnectedResourceItemSession, "_scroll", side_effect=(invalid, invalid, invalid)) as scroll,
                ):
                    result = session.scan_inventory()

                self.assertEqual(ResourceInventoryStatus.UNKNOWN, result.status)
                self.assertFalse(result.exhausted)
                self.assertEqual(1, len(result.items))
                self.assertTrue(result.unresolved_reasons)
                actions.execute_action.assert_not_called()
                self.assertEqual(1, scroll.call_count)

    def test_scan_inventory_rejects_new_unresolved_card_after_scroll(self) -> None:
        """Does not declare exhaustion when a later viewport adds an unreadable card."""

        complete = _observation("fresh")
        unresolved = DetectedListEntry(
            ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED,
            Bounds(6, 440, 528, 120),
            row_status=RowRecognitionStatus.UNREADABLE,
            metadata={"unresolved_reason": "missing_title"},
        )
        after = replace(complete, list_entries=(complete.list_entries[0], unresolved))
        observer = Mock()
        actions = _actions()
        session = ConnectedResourceItemSession(observer, actions, Mock(), Mock())
        with (
            patch.object(ConnectedResourceItemSession, "_open_inventory"),
            patch.object(ConnectedResourceItemSession, "_stable", return_value=complete),
            patch.object(ConnectedResourceItemSession, "_scroll", return_value=after) as scroll,
        ):
            result = session.scan_inventory()

        self.assertEqual(ResourceInventoryStatus.UNKNOWN, result.status)
        self.assertEqual(("missing_title",), result.unresolved_reasons)
        self.assertEqual(1, len(result.items))
        self.assertFalse(result.exhausted)
        actions.execute_action.assert_not_called()
        scroll.assert_called_once()


def _observation(fingerprint: str, *, provenance: str = "visual_geometry") -> Observation:
    """Creates a deterministic resource row with exact action-point provenance."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_BAG,
            effective_screen=ScreenType.PNC_BAG,
            guard=GuardVerdict.CLEAR,
            evidence=(ScreenEvidence(ScreenType.PNC_BAG, "test"),),
        ), visible_elements={}, artifact_path=Path("fake-resource.png"), image_size=(540, 960),
        list_entries=(DetectedListEntry(
            ListEntryKind.RESOURCE_ITEM, Bounds(6, 300, 528, 120),
            title_text="50 Gold", action_point=(453, 338), action_bounds=Bounds(430, 320, 50, 36),
            row_status=RowRecognitionStatus.COMPLETE,
            metadata={
                "item_id": "gold:50:normal", "resource": "gold", "amount": 50, "owned": 277,
                "observation_fingerprint": fingerprint, "coordinate_provenance": provenance,
            },
        ),),
    )


def _actions() -> Mock:
    """Creates an executor mock whose interruption probe defaults to no recovery."""

    actions = Mock()
    actions.recover_interruption_if_required.return_value = None
    return actions
