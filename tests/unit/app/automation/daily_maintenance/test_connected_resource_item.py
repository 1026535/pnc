"""Offline checks at the connected resource-item mutation boundary."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.connected_resource_item import (
    ConnectedResourceItemSession,
)
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.domain.resource_items import ResourceItem
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
        observer.observe.return_value = Observation(ScreenType.UNKNOWN, {})
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


def _observation(fingerprint: str, *, provenance: str = "visual_geometry") -> Observation:
    """Creates a deterministic resource row with exact action-point provenance."""

    return Observation(
        ScreenType.PNC_BAG, {}, artifact_path=Path("fake-resource.png"), image_size=(540, 960),
        list_entries=(DetectedListEntry(
            ListEntryKind.RESOURCE_ITEM, Bounds(6, 300, 528, 120),
            title_text="50 Gold", action_point=(453, 338),
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
