"""Navigation bag preview tests."""

from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import TreasureIdentity, TreasureKind
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
    list_entry_matches,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.navigation.core_bag import (
    bag_item_entry,
    bag_preview_frame,
    bag_treasure_frame,
)
from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_recording import RecordingNavigationCore


class BagChestPreviewNavigationCoreTests(RecordingNavigationCore, unittest.TestCase):
    """Prove the read-only chest inspection route through typed content proof."""


    def test_open_bag_chest_preview_taps_unique_row_once_for_matching_preview(self):
        """One qualified magnifier tap followed by two stable matching preview frames."""

        identity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)
        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            bag_treasure_frame((bag_item_entry(identity),), captured_at=now),
            bag_preview_frame(identity, captured_at=now + timedelta(seconds=1)),
            bag_preview_frame(identity, captured_at=now + timedelta(seconds=2)),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).open_bag_chest_preview(
            identity,
            observe_content=lambda _: next(frames),
        )

        self.assertIsNotNone(result.bag_preview)
        self.assertEqual(identity, result.bag_preview.source_identity)
        self.assertEqual(1, len(actuator.actions))
        action = actuator.actions[0]
        self.assertIsInstance(action, TapListEntryAction)
        self.assertEqual(ListEntryKind.BAG_ITEM, action.entry_kind)
        self.assertIsNone(action.title_text)
        self.assertEqual("identity", action.metadata_key)
        self.assertEqual("treasure:arena_surprise_chest", action.metadata_value)
        self.assertTrue(action.use_action_point)

    def test_open_bag_chest_preview_supports_common_identity(self):
        """The typed identity resolves despite OCR omitting display-title spaces."""

        identity = TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST)
        now = datetime(2026, 9, 16, tzinfo=UTC)
        row = bag_item_entry(identity, title="Common1stVictoryChest")
        frames = iter((
            bag_treasure_frame((row,), captured_at=now),
            bag_preview_frame(
                identity, layout_id="bag_common_victory_preview",
                captured_at=now + timedelta(seconds=1),
            ),
            bag_preview_frame(
                identity, layout_id="bag_common_victory_preview",
                captured_at=now + timedelta(seconds=2),
            ),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).open_bag_chest_preview(
            identity,
            observe_content=lambda _: next(frames),
        )

        self.assertEqual(identity, result.bag_preview.source_identity)
        action = actuator.actions[0]
        self.assertTrue(list_entry_matches(
            row, title_text=action.title_text, metadata_key=action.metadata_key,
            metadata_value=action.metadata_value, selected=action.selected,
        ))
        self.assertEqual(1, len(actuator.actions))

    def test_open_bag_chest_preview_rejects_unsupported_identities_without_any_tap(self):
        """Only Arena and Common are qualified; other magnifiers send no action."""

        for identity in (
            TreasureIdentity(TreasureKind.RARE_FIRST_VICTORY_CHEST),
            TreasureIdentity(TreasureKind.PINBALL),
            TreasureIdentity(TreasureKind.STARNA_DICE),
            TreasureIdentity(TreasureKind.DIAMOND_CHEST),
            TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 23),
            TreasureIdentity(TreasureKind.DEMON_CHEST, 21),
        ):
            with self.subTest(identity=identity):
                actuator = Actuator()
                with self.assertRaises(ValueError):
                    self.make_core(actuator).open_bag_chest_preview(
                        identity,
                        observe_content=lambda _: bag_treasure_frame((bag_item_entry(),)),
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_open_bag_chest_preview_rejects_unqualified_sources_without_any_tap(self):
        """Wrong tab/layout, missing, duplicated, or unreadable rows send no action."""

        identity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)
        cases = (
            ("unproved_layout", bag_treasure_frame((bag_item_entry(identity),), layout_id=None)),
            ("wrong_tab", bag_treasure_frame((bag_item_entry(identity),), tab=BagTab.SPEEDUP)),
            ("missing_row", bag_treasure_frame(())),
            (
                "unknown_identity_row",
                bag_treasure_frame((
                    bag_item_entry(TreasureIdentity(TreasureKind.PINBALL)),
                )),
            ),
            (
                "ambiguous",
                bag_treasure_frame((bag_item_entry(identity), bag_item_entry(identity))),
            ),
            (
                "unreadable",
                bag_treasure_frame((bag_item_entry(identity, status=RowRecognitionStatus.UNREADABLE),)),
            ),
            (
                "no_action",
                bag_treasure_frame((bag_item_entry(identity, status=RowRecognitionStatus.NO_ACTION),)),
            ),
            ("blocked", bag_treasure_frame((bag_item_entry(identity),), blocked=True)),
            ("wrong_screen", observation(ScreenType.PNC_HOME_CITY)),
        )
        for name, source in cases:
            with self.subTest(reason=name):
                actuator = Actuator()
                with self.assertRaises(RuntimeError):
                    self.make_core(actuator).open_bag_chest_preview(
                        identity,
                        observe_content=lambda _: source,
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_open_bag_chest_preview_rejects_wrong_preview_without_replaying_tap(self):
        """A preview whose title names another Treasure cannot prove completion."""

        identity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)
        wrong = TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST)
        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            bag_treasure_frame((bag_item_entry(identity),), captured_at=now),
            *(
                bag_preview_frame(
                    wrong, layout_id="bag_common_victory_preview",
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            self.make_core(actuator).open_bag_chest_preview(
                identity,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_bag_chest_preview_rejects_unreadable_preview_without_replaying_tap(self):
        """A preview with an unparsed title never confirms the route."""

        identity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)
        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            bag_treasure_frame((bag_item_entry(identity),), captured_at=now),
            *(
                bag_preview_frame(
                    None,
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            self.make_core(actuator).open_bag_chest_preview(
                identity,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_bag_chest_preview_rejects_stale_preview_without_replaying_tap(self):
        """A preview frame no newer than the source is a stale capture."""

        identity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST)
        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            bag_treasure_frame((bag_item_entry(identity),), captured_at=now),
            bag_preview_frame(identity, captured_at=now),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            self.make_core(actuator).open_bag_chest_preview(
                identity,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))
