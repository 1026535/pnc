"""Campaign."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId, TaskStatus
from pnc_automation.app.automation.tasks.campaign_task import CampaignTask
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.campaign import CampaignMode, CampaignNodeFacts
from pnc_automation.app.pnc.domain.match3 import Match3Mode
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
    SpatialObjectKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import ScriptValidationError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures


def _stage_entry(
    stage_number: int | None,
    *,
    mode: CampaignMode | None = None,
    locked: bool | None = False,
    row_status: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
    chapter_number: int | None = 10,
) -> DetectedListEntry:
    """Build one typed chapter-path stage row carrying observed node facts."""

    return DetectedListEntry(
        kind=ListEntryKind.CAMPAIGN_STAGE,
        bounds=Bounds(90, 560, 50, 50),
        title_text=None if stage_number is None else str(stage_number),
        campaign_node=CampaignNodeFacts(
            chapter_number=chapter_number,
            stage_number=stage_number,
            locked=locked,
            mode=mode,
        ),
        metadata={} if stage_number is None else {"stage_number": stage_number},
        row_status=row_status,
        action_bounds=(
            None if row_status != RowRecognitionStatus.COMPLETE else Bounds(95, 565, 40, 40)
        ),
        action_point=None if row_status != RowRecognitionStatus.COMPLETE else (115, 585),
    )


class CampaignTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves campaign."""

    def test_campaign_task_can_open_campaign_from_spatial_home_city_target_without_private_search_logic(self) -> None:
        """Falls through to the shared home-city spatial opener when no Campaign shortcut selector is visible."""

        task = CampaignTask()
        context = self._make_context(params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Campaign",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CAMPAIGN),
                    ),
                ),
            ),
        )

        actions = task.plan(context, observation)

        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], TapSpatialObjectAction)
        self.assertEqual(actions[0].query.metadata_key, "home_city_object_id")
        self.assertEqual(actions[0].query.metadata_value, "campaign")
        self.assertEqual(actions[0].follow_up_request, ObservationRequest.campaign_map_follow_up())

    def test_campaign_task_selects_typed_stage_mode_and_skips_unobserved_modes(self) -> None:
        """Typed campaign_node facts drive eligibility; unobserved modes never act."""

        task = CampaignTask()
        context = self._make_context(
            params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN
        )

        eligible = make_observation(
            ScreenType.PNC_CAMPAIGN_CHAPTER,
            list_entries=(
                _stage_entry(None, locked=True, row_status=RowRecognitionStatus.NO_ACTION),
                _stage_entry(3, mode=CampaignMode.STANDARD),
            ),
        )
        actions = task.plan(context, eligible)
        self.assertEqual(len(actions), 2)
        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertEqual(actions[0].entry_kind, ListEntryKind.CAMPAIGN_STAGE)
        self.assertEqual(actions[0].title_text, "3")
        self.assertTrue(actions[0].use_action_point)

        for entries in (
            (_stage_entry(3, mode=None),),
            (_stage_entry(3, mode=CampaignMode.ELITE),),
            (_stage_entry(3, mode=CampaignMode.STANDARD, row_status=RowRecognitionStatus.UNREADABLE),),
            (_stage_entry(None, locked=True, row_status=RowRecognitionStatus.NO_ACTION),),
        ):
            with self.subTest(entries=entries):
                observation = make_observation(
                    ScreenType.PNC_CAMPAIGN_CHAPTER, list_entries=entries
                )
                self.assertEqual(task.plan(context, observation), [])

    def test_campaign_task_honors_enabled_mode_priority_order(self) -> None:
        """Configured mode order picks the higher-priority observed stage."""

        task = CampaignTask()
        context = self._make_context(
            params=task.parse_params({"enabled_modes": ["elite", "standard"]}),
            task_id=TaskId.CAMPAIGN,
        )
        observation = make_observation(
            ScreenType.PNC_CAMPAIGN_CHAPTER,
            list_entries=(
                _stage_entry(3, mode=CampaignMode.STANDARD),
                _stage_entry(5, mode=CampaignMode.ELITE),
            ),
        )

        actions = task.plan(context, observation)

        self.assertIsInstance(actions[0], TapListEntryAction)
        self.assertEqual(actions[0].title_text, "5")

    def test_campaign_task_verify_skips_ineligible_stage_evidence_on_both_surfaces(self) -> None:
        """Unsupported stage evidence is a skip on map and chapter, never a retry."""

        task = CampaignTask()
        context = self._make_context(
            params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN
        )
        ineligible_sets = (
            (),
            (_stage_entry(3, mode=None),),
            (_stage_entry(3, mode=CampaignMode.ELITE),),
            (_stage_entry(3, locked=True, mode=CampaignMode.STANDARD),),
            (_stage_entry(3, locked=None, mode=CampaignMode.STANDARD),),
            (_stage_entry(None, locked=True, row_status=RowRecognitionStatus.NO_ACTION),),
            (_stage_entry(3, mode=CampaignMode.STANDARD, row_status=RowRecognitionStatus.UNREADABLE),),
        )
        for screen in (ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER):
            for entries in ineligible_sets:
                with self.subTest(screen=screen, entries=entries):
                    before = make_observation(screen, list_entries=entries)
                    result = task.verify(
                        context,
                        before,
                        make_observation(screen, list_entries=entries),
                    )
                    self.assertEqual(result.status, TaskStatus.SKIPPED)

    def test_campaign_task_verify_still_acts_on_eligible_stage_evidence(self) -> None:
        """An eligible stage row keeps success and retry semantics intact."""

        task = CampaignTask()
        context = self._make_context(
            params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN
        )
        before = make_observation(
            ScreenType.PNC_CAMPAIGN_CHAPTER,
            list_entries=(_stage_entry(3, mode=CampaignMode.STANDARD),),
        )

        success = task.verify(context, before, make_observation(ScreenType.PNC_BATTLE_PREP))
        unchanged = task.verify(
            context,
            before,
            make_observation(
                ScreenType.PNC_CAMPAIGN_CHAPTER,
                list_entries=(_stage_entry(3, mode=CampaignMode.STANDARD),),
            ),
        )

        self.assertEqual(success.status, TaskStatus.SUCCESS)
        self.assertEqual(unchanged.status, TaskStatus.FAILED)
        self.assertTrue(unchanged.retryable)

    def test_campaign_task_accepts_battle_prep_as_campaign_entry_outcome(self) -> None:
        """Keeps Campaign entry proof consistent with the task's owned battle-prep state."""

        task = CampaignTask()
        context = self._make_context(params=task.parse_params({"enabled_modes": ["standard"]}), task_id=TaskId.CAMPAIGN)

        result = task.verify(
            context,
            make_observation(ScreenType.PNC_HOME_CITY),
            make_observation(ScreenType.PNC_BATTLE_PREP),
        )

        self.assertEqual(result.status, TaskStatus.SUCCESS)

    def test_campaign_policy_parses_battle_mode_independently_of_difficulty(self) -> None:
        """battle_mode selects one shared match-3 mode without changing enabled_modes."""

        policy = CampaignTask().parse_params(
            {"enabled_modes": ["elite"], "battle_mode": "game_auto"}
        )

        self.assertEqual(policy.enabled_modes, (CampaignMode.ELITE,))
        self.assertEqual(policy.battle_mode, Match3Mode.GAME_AUTO)

    def test_campaign_policy_keeps_battle_mode_unset_by_default(self) -> None:
        """Omission preserves the existing preparation-only campaign behavior."""

        policy = CampaignTask().parse_params({"enabled_modes": ["standard"]})

        self.assertIsNone(policy.battle_mode)

    def test_campaign_policy_rejects_invalid_battle_mode_values(self) -> None:
        """Misspelled, non-string or container battle modes fail validation."""

        for invalid in ("auto", "solve", "", 3, ["solver"], True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ScriptValidationError):
                    CampaignTask().parse_params({"battle_mode": invalid})

    def test_campaign_policy_rejects_unknown_parameters(self) -> None:
        """Unknown campaign keys fail instead of silently dropping battle-mode typos."""

        with self.assertRaisesRegex(ScriptValidationError, "battle_modes"):
            CampaignTask().parse_params({"battle_modes": ["solver"]})
