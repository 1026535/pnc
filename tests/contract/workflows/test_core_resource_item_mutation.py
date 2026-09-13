"""Exercise the core Resource Item mutation boundary and durable receipt."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.coordinator import DailyReadOnlySurvey
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.engine.core_resource_item_session import CoreResourceItemSession
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowRunner
from pnc_automation.app.automation.daily_maintenance.core_resource_item import CoreResourceItemWorkflow
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyCapabilityPolicy,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.pnc.domain.action_requests import TapListEntryAction
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CoordinateProvenance,
    DailyQuestId,
    DailyQuestRow,
    DailyQuestRowState,
    DailyTargetOutcomeStatus,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationIntentState,
    NormalizedBounds,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.resource_items import ResourceItem
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.vision.image.models import Bounds
from tests.contract.workflows.test_core_daily_mutation import daily as daily_observation
from tests.support.pnc.observations import make_observation


def _resource_frame(
    item: ResourceItem,
    *,
    selected: bool = True,
    generic_use: bool = False,
    artifact: str | None = None,
):
    """Build one complete Resource row with an explicitly selected tab."""

    visible = ()
    if selected:
        visible += (UiElementId.PNC_BAG_SUBTAB_RESOURCE,)
    if generic_use:
        visible += (UiElementId.PNC_BAG_USE_BUTTON,)
    entry = DetectedListEntry(
        kind=ListEntryKind.RESOURCE_ITEM,
        bounds=Bounds(20, 120, 500, 80),
        title_text=item.item_id,
        action_point=(450, 160),
        action_bounds=Bounds(420, 135, 80, 45),
        row_status=RowRecognitionStatus.COMPLETE,
        metadata={
            "item_id": item.item_id,
            "resource": item.resource,
            "amount": item.amount,
            "owned": item.owned,
            "observation_fingerprint": item.fingerprint,
            "coordinate_provenance": "visual_geometry",
        },
    )
    return make_observation(
        ScreenType.PNC_BAG,
        visible_ids=visible,
        source_kinds={UiElementId.PNC_BAG_SUBTAB_RESOURCE: VisibleElementSourceKind.TEMPLATE},
        list_entries=(entry,),
        artifact_path=None if artifact is None else Path(artifact),
    )


def _daily_survey(*, completed: bool, artifact: str = "daily.png") -> DailyReadOnlySurvey:
    """Build the same typed full-survey receipt used by the coordinator."""

    state = DailyQuestRowState.COMPLETED if completed else DailyQuestRowState.REQUIREMENT
    return DailyReadOnlySurvey(
        rows=(DailyQuestRow(
            quest_id=DailyQuestId.USE_RESOURCE_ITEM,
            normalized_title="Use Resource Item",
            state=state,
            bounds=NormalizedBounds(0.1, 0.4, 0.8, 0.1),
            observation_fingerprint="daily-row",
            coordinate_provenance=CoordinateProvenance.DYNAMIC_ENTRY_GEOMETRY,
        ),),
        unknown_titles=(),
        scanned_viewports=2,
        artifact_paths=(artifact,),
    )


def _daily_resource_observation(*, completed: bool):
    """Build a coordinator-readable full Daily viewport for the resource row."""

    frame = daily_observation("completed" if completed else "requirement")
    row = frame.list_entries[0]
    return replace(
        frame,
        artifact_path=Path("daily.png"),
        list_entries=(replace(
            row,
            title_text="Use Resource Item",
            metadata={
                **row.metadata,
                "quest_id": "use_resource_item",
                "row_state": "completed" if completed else "requirement",
            },
        ),),
    )


class _Navigation:
    """Provide only the reviewed navigation calls exercised by this contract."""

    def __init__(self, runtime: "_Runtime") -> None:
        self.runtime = runtime

    def navigate(self, target: ScreenType):
        self.runtime.targets.append(target)
        self.runtime.current_screen = target
        if target == ScreenType.PNC_HOME_CITY:
            return self.runtime.fresh(make_observation(ScreenType.PNC_HOME_CITY))
        if target == ScreenType.PNC_BAG:
            return self.runtime.fresh(self.runtime.resource_frame())
        if target == ScreenType.PNC_QUEST_DAILY:
            return self.runtime.fresh(
                _daily_resource_observation(completed=self.runtime.daily_completed),
            )
        raise AssertionError(f"unexpected target {target}")

    def scroll_resource_inventory(
        self, *, upward: bool, adjusted: bool, fine: bool,
        observe_content, confirm_scroll,
    ):
        """Return a fresh stable frame without bypassing the session's observer."""

        observe_content("resource_scroll_source")
        return confirm_scroll()

    def scroll_daily_quest(self, *, adjusted: bool, observe_content):
        """Return one fresh Daily frame; the fixture already has a bottom marker."""

        del adjusted
        observe_content("daily_scroll_source")
        return self.runtime.fresh(
            _daily_resource_observation(completed=self.runtime.daily_completed),
        )


class _Runtime:
    """Deterministic runtime double; all mutation input is recorded by ``actuator``."""

    def __init__(
        self,
        castle: CastleIdentity,
        *,
        item: ResourceItem,
        selected: bool = True,
        generic_use: bool = False,
        consumed: bool = True,
        daily_completed: bool = True,
        store: DailyRunJournalStore | None = None,
    ) -> None:
        self.castle = castle
        self.item = item
        self.selected = selected
        self.generic_use = generic_use
        self.consumed = consumed
        self.daily_completed = daily_completed
        self.store = store
        self.used = False
        self.observation_count = 0
        self.last_observation = None
        self.current_screen = ScreenType.PNC_HOME_CITY
        self.targets: list[ScreenType] = []
        self.ready_labels: list[str] = []
        self.record = Mock()
        self.trace_path = Path("trace.jsonl")
        self.preflight_active_castle_identity = Mock(return_value=castle)
        self.actuator = Mock()
        self.actuator.execute_action.side_effect = self._execute_action
        self.runtime = SimpleNamespace(require_observed_action_executor=lambda reason: self.actuator)
        self.navigation = _Navigation(self)

    def fresh(self, observation):
        self.observation_count += 1
        captured_at = datetime(2026, 9, 13, tzinfo=UTC) + timedelta(seconds=self.observation_count)
        self.last_observation = replace(observation, captured_at=captured_at)
        return self.last_observation

    def observe(self, label: str, *, include_content: bool = False):
        if self.current_screen == ScreenType.PNC_QUEST_DAILY:
            return self.fresh(
                _daily_resource_observation(completed=self.daily_completed),
            )
        return self.fresh(self.resource_frame())

    def observe_ready(self, label: str, *, include_content: bool = False):
        """Mirror the runtime's ready boundary for Resource Item contract coverage."""

        self.ready_labels.append(label)
        return self.observe(label, include_content=include_content)

    def resource_frame(self):
        item = self.item
        if self.used and self.consumed:
            item = replace(item, owned=item.owned - 1, fingerprint="after")
        return _resource_frame(
            item,
            selected=self.selected,
            generic_use=self.generic_use,
            artifact="resource.png",
        )

    def _execute_action(self, action, observation) -> bool:
        if self.store is not None:
            checkpoint = self.store.load(
                game_reset_id="reset", account_id="account", castle=self.castle,
            )
            if checkpoint is None or checkpoint.mutation_intents[0].state != MutationIntentState.DISPATCHED:
                raise AssertionError("resource input was sent before durable DISPATCHED")
        self.used = True
        return True


class CoreResourceItemMutationTests(unittest.TestCase):
    """Keep core authority and Resource Item exactly-once behavior under contract."""

    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = DailyRunJournalStore(Path(temporary.name))
        self.castle = CastleIdentity("K1", "Castle", 20)
        self.checkpoint = DailyTaskCheckpoint("2026-09-13", "reset", "account", self.castle)
        policy = DailyCapabilityPolicy(DailyQuestId.USE_RESOURCE_ITEM, TaskId.USE_RESOURCE_ITEM, 1)
        self.scope = CoreMutationBoundary(
            target=DailyMaintenanceTargetConfig("account", "castle", self.castle, (policy,)),
            boundary=DailyRunBoundary(date(2026, 9, 13), "reset"),
            authorizer=DailyMutationAuthorizer((MutationAcknowledgement(
                "account", "castle", DailyQuestId.USE_RESOURCE_ITEM, date(2026, 9, 13), 1, 0,
            ),)),
            journal_store=self.store,
        )
        self.item = ResourceItem("food-small", "food", 100, 3, "before")

    def _load(self):
        return self.store.load(game_reset_id="reset", account_id="account", castle=self.castle)

    def test_authority_is_denied_before_any_device_access(self) -> None:
        runtime = _Runtime(self.castle, item=self.item, store=self.store)
        denied = replace(self.scope, authorizer=DailyMutationAuthorizer())
        with self.assertRaises(PermissionError):
            CoreWorkflowRunner(runtime, denied).run(CoreResourceItemWorkflow(self.checkpoint))
        runtime.preflight_active_castle_identity.assert_not_called()
        runtime.actuator.execute_action.assert_not_called()
        self.assertEqual([], runtime.targets)
        self.assertIsNone(self._load())

    def test_unselected_or_generic_bag_cannot_dispatch_resource_use(self) -> None:
        for selected, generic in ((False, False), (False, True)):
            with self.subTest(selected=selected, generic=generic):
                runtime = _Runtime(
                    self.castle, item=self.item, selected=selected,
                    generic_use=generic, store=self.store,
                )
                with self.assertRaisesRegex(RuntimeError, "selected Resource tab"):
                    CoreWorkflowRunner(runtime, self.scope).run(CoreResourceItemWorkflow(self.checkpoint))
                runtime.actuator.execute_action.assert_not_called()
                self.assertIsNone(self._load())

    def test_selected_resource_tab_dispatches_exact_action_after_durable_intent(self) -> None:
        runtime = _Runtime(self.castle, item=self.item, store=self.store)
        result = CoreWorkflowRunner(runtime, self.scope).run(CoreResourceItemWorkflow(self.checkpoint))
        checkpoint, outcome = result.value
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, outcome.status)
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        self.assertEqual(ScreenType.PNC_HOME_CITY, result.exit_screen)
        runtime.actuator.execute_action.assert_called_once()
        action, observation = runtime.actuator.execute_action.call_args.args
        self.assertIsInstance(action, TapListEntryAction)
        self.assertEqual(ListEntryKind.RESOURCE_ITEM, action.entry_kind)
        self.assertEqual("observation_fingerprint", action.metadata_key)
        self.assertEqual("before", action.metadata_value)
        self.assertTrue(action.use_action_point)
        self.assertEqual(("resource.png", "daily.png"), outcome.artifact_paths)
        self.assertIn("resource_inventory_entry", runtime.ready_labels)

    def test_ambiguous_result_reconciles_without_replaying_input(self) -> None:
        runtime = _Runtime(
            self.castle, item=self.item, consumed=False,
            daily_completed=False, store=self.store,
        )
        checkpoint, outcome = CoreWorkflowRunner(runtime, self.scope).run(
            CoreResourceItemWorkflow(self.checkpoint),
        ).value
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(MutationIntentState.RECONCILED, checkpoint.mutation_intents[0].state)
        _, again = CoreWorkflowRunner(runtime, self.scope).run(
            CoreResourceItemWorkflow(checkpoint),
        ).value
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, again.status)
        runtime.actuator.execute_action.assert_called_once()

    def test_stock_decrement_without_daily_receipt_reconciles_later_without_reuse(self) -> None:
        runtime = _Runtime(
            self.castle, item=self.item, consumed=True,
            daily_completed=False, store=self.store,
        )
        checkpoint, outcome = CoreWorkflowRunner(runtime, self.scope).run(
            CoreResourceItemWorkflow(self.checkpoint),
        ).value
        self.assertEqual(DailyTargetOutcomeStatus.PENDING_CLARIFICATION, outcome.status)
        self.assertEqual(MutationIntentState.RECONCILED, checkpoint.mutation_intents[0].state)
        self.assertTrue(runtime.used)

        runtime.daily_completed = True
        checkpoint, outcome = CoreWorkflowRunner(runtime, self.scope).run(
            CoreResourceItemWorkflow(checkpoint),
        ).value
        self.assertEqual(DailyTargetOutcomeStatus.SUCCESS, outcome.status)
        self.assertEqual(MutationIntentState.COMMITTED, checkpoint.mutation_intents[0].state)
        runtime.actuator.execute_action.assert_called_once()

    def test_changed_fingerprint_is_rejected_without_use(self) -> None:
        runtime = _Runtime(self.castle, item=replace(self.item, fingerprint="changed"), store=self.store)
        session = CoreResourceItemSession(
            runtime=runtime,
            observe=runtime.observe,
            open_inventory=lambda: None,
            daily_survey=lambda: _daily_survey(completed=False),
        )
        with self.assertRaisesRegex(ValueError, "changed"):
            session.use_one(self.item)
        runtime.actuator.execute_action.assert_not_called()


if __name__ == "__main__":
    unittest.main()
