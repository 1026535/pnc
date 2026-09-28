"""Navigation trial tests."""

from datetime import UTC, datetime, timedelta
import unittest

from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.observation import (
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.trial_challenge import TrialCategory
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.navigation.core_frames import Actuator, observation
from tests.support.pnc.navigation.core_recording import RecordingNavigationCore
from tests.support.pnc.navigation.core_trial import (
    trial_card_entry,
    trial_list_frame,
    trial_stats_detail_frame,
)


class TrialNavigationCoreTests(RecordingNavigationCore, unittest.TestCase):
    """Prove the read-only Gear Stats inspection route through typed content proof."""


    def test_open_trial_stats_taps_unique_gear_row_once_for_matching_detail(self):
        """One qualified Gear row tap followed by two stable matching detail frames."""

        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            trial_list_frame((trial_card_entry(),), captured_at=now),
            trial_stats_detail_frame(captured_at=now + timedelta(seconds=1)),
            trial_stats_detail_frame(captured_at=now + timedelta(seconds=2)),
        ))
        actuator = Actuator()
        result = self.make_core(actuator).open_trial_stats(
            TrialCategory.GEAR,
            observe_content=lambda _: next(frames),
        )

        self.assertIsNotNone(result.trial_stats_detail)
        self.assertEqual(TrialCategory.GEAR, result.trial_stats_detail.category)
        self.assertEqual(1, len(actuator.actions))
        action = actuator.actions[0]
        self.assertIsInstance(action, TapListEntryAction)
        self.assertEqual(ListEntryKind.TRIAL_CATEGORY, action.entry_kind)
        self.assertEqual("Gear Trial", action.title_text)
        self.assertEqual("category", action.metadata_key)
        self.assertEqual(TrialCategory.GEAR.value, action.metadata_value)
        self.assertTrue(action.use_action_point)

    def test_open_trial_stats_rejects_unsupported_categories_without_any_tap(self):
        """Only Gear's Stats entry is qualified; other categories are unsupported."""

        for category in (
            TrialCategory.HERO, TrialCategory.CURIO, TrialCategory.TECH,
            TrialCategory.RUNE, TrialCategory.SAUROI,
        ):
            with self.subTest(category=category):
                actuator = Actuator()
                with self.assertRaises(ValueError):
                    self.make_core(actuator).open_trial_stats(
                        category, observe_content=lambda _: trial_list_frame((trial_card_entry(),))
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_open_trial_stats_rejects_unqualified_sources_without_any_tap(self):
        """Unproved, missing, duplicated, or unreadable Gear rows send no action."""

        cases = (
            ("unproved_list", trial_list_frame((trial_card_entry(),), proved=False)),
            ("missing", trial_list_frame((trial_card_entry(TrialCategory.TECH, status=RowRecognitionStatus.NO_ACTION),))),
            (
                "ambiguous",
                trial_list_frame((trial_card_entry(), trial_card_entry())),
            ),
            (
                "unreadable",
                trial_list_frame((trial_card_entry(status=RowRecognitionStatus.UNREADABLE),)),
            ),
            (
                "no_action",
                trial_list_frame((trial_card_entry(status=RowRecognitionStatus.NO_ACTION),)),
            ),
            ("wrong_screen", observation(ScreenType.PNC_HOME_CITY)),
        )
        for name, source in cases:
            with self.subTest(reason=name):
                actuator = Actuator()
                with self.assertRaises(RuntimeError):
                    self.make_core(actuator).open_trial_stats(
                        TrialCategory.GEAR,
                        observe_content=lambda _: source,
                    )
                self.assertEqual(0, len(actuator.actions))

    def test_open_trial_stats_rejects_wrong_category_detail_without_replaying_tap(self):
        """A detail whose footer names another category cannot prove completion."""

        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            trial_list_frame((trial_card_entry(),), captured_at=now),
            *(
                trial_stats_detail_frame(
                    TrialCategory.RUNE,
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            self.make_core(actuator).open_trial_stats(
                TrialCategory.GEAR,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_trial_stats_rejects_unreadable_detail_without_replaying_tap(self):
        """A detail with an unreadable footer category never confirms the route."""

        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            trial_list_frame((trial_card_entry(),), captured_at=now),
            *(
                trial_stats_detail_frame(
                    None,
                    captured_at=now + timedelta(seconds=index),
                )
                for index in range(1, 5)
            ),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "unexpected screen"):
            self.make_core(actuator).open_trial_stats(
                TrialCategory.GEAR,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))

    def test_open_trial_stats_rejects_stale_detail_without_replaying_tap(self):
        """A detail frame no newer than the source is a stale capture."""

        now = datetime(2026, 9, 16, tzinfo=UTC)
        frames = iter((
            trial_list_frame((trial_card_entry(),), captured_at=now),
            trial_stats_detail_frame(captured_at=now),
        ))
        actuator = Actuator()
        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            self.make_core(actuator).open_trial_stats(
                TrialCategory.GEAR,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual(1, len(actuator.actions))
