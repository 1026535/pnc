"""Offline contract coverage for Workshop authority, identity, and journal lifecycle."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path

from pnc_automation.app.authoring.config.daily_maintenance import (
    DailyMaintenanceConfig,
    DailyMaintenanceTargetConfig,
)
from pnc_automation.app.authoring.config.mutation_acknowledgement import (
    parse_mutation_acknowledgement,
)
from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import (
    DailyMutationAuthorizer,
)
from pnc_automation.app.automation.daily_maintenance.invocation_factory import (
    build_daily_run_boundary,
    generate_workshop_invocation_id,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    JournaledMutationResult,
    MutationOperation,
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.pet_workshop.authority import (
    WorkshopRunAuthority,
    build_workshop_run_authority,
)
from pnc_automation.app.pnc.domain.building_operations import BuildingMutationKind
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationBudgetKind,
    MutationIntent,
    MutationIntentState,
    WorkshopInvocationRecord,
)
from pnc_automation.app.pnc.domain.feature_actions import (
    is_workshop_journaled_action,
    normalize_feature_action_kind,
    normalize_journaled_action_kind,
)
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopIntentKind,
    WorkshopMutationKind,
    WorkshopOrderRewardCategory,
    WorkshopPolicy,
    WorkshopStopReason,
)
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.errors import ConfigurationError

_CASTLE = CastleIdentity("K1", "Main", 10)
_OTHER_CASTLE = CastleIdentity("K1", "Other", 9)
_MAINTENANCE_DATE = date(2026, 9, 14)


def _workshop_acknowledgement(
    *,
    budget_kind: MutationBudgetKind = MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
    max_mutations: int | None = None,
    castle_ref: str = "K1:Main",
) -> MutationAcknowledgement:
    """Builds one exact Workshop run acknowledgement for the fixture castle."""

    return MutationAcknowledgement(
        account_id="account",
        castle_ref=castle_ref,
        quest_id=None,
        maintenance_date=_MAINTENANCE_DATE,
        max_mutations=max_mutations,
        max_diamond_spend=0,
        action_kind=WorkshopMutationKind.RUN.value,
        budget_kind=budget_kind,
    )


def _workshop_scope(
    store: DailyRunJournalStore,
    *,
    castle: CastleIdentity = _CASTLE,
    castle_ref: str = "K1:Main",
    game_reset_id: str = "reset-1",
    budget_kind: MutationBudgetKind = MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
    max_mutations: int = 1,
) -> CoreMutationBoundary:
    """Builds one Workshop-scoped mutation boundary backed by an exact acknowledgement."""

    return CoreMutationBoundary(
        target=DailyMaintenanceTargetConfig("account", castle_ref, castle, ()),
        boundary=DailyRunBoundary(_MAINTENANCE_DATE, game_reset_id),
        authorizer=DailyMutationAuthorizer((_workshop_acknowledgement(
            budget_kind=budget_kind,
            max_mutations=max_mutations if budget_kind is MutationBudgetKind.COUNTED else None,
            castle_ref=castle_ref,
        ),)),
        journal_store=store,
        feature_action_kind=WorkshopMutationKind.RUN,
        feature_budget_kind=budget_kind,
        feature_max_mutations=(
            max_mutations if budget_kind is MutationBudgetKind.COUNTED else None
        ),
    )


def _checkpoint(
    *,
    game_reset_id: str = "reset-1",
    castle: CastleIdentity = _CASTLE,
) -> DailyTaskCheckpoint:
    """Builds one durable checkpoint shell for the fixture scope."""

    return DailyTaskCheckpoint(
        maintenance_date=_MAINTENANCE_DATE.isoformat(),
        game_reset_id=game_reset_id,
        account_id="account",
        castle=castle,
    )


def _workshop_operation(operation_id: str, *, invocation_id: str = "inv-1") -> MutationOperation:
    """Builds one typed, zero-diamond Workshop mutation operation."""

    return MutationOperation(
        operation_id=operation_id,
        quest_id=None,
        expected_precondition="eligible merge pair is visible",
        expected_postcondition="merged piece occupies one cell",
        diamond_budget=0,
        action_kind=WorkshopIntentKind.MERGE,
        target={"cells": ["a1", "a2"]},
        invocation_id=invocation_id,
    )


class WorkshopActionIdentityTests(unittest.TestCase):
    """Prove exact typed action normalization for the Workshop scope."""

    def test_normalize_feature_action_kind_accepts_only_typed_feature_kinds(self) -> None:
        self.assertIs(WorkshopMutationKind.RUN, normalize_feature_action_kind("pet_workshop.run"))
        self.assertIs(BuildingMutationKind.UPGRADE, normalize_feature_action_kind("building_upgrade"))
        self.assertIs(
            BuildingMutationKind.CONSTRUCT,
            normalize_feature_action_kind("building_construct"),
        )
        for unknown in ("pet_workshop.solve", "workshop", "pet_workshop.run.run", ""):
            with self.subTest(unknown=unknown):
                with self.assertRaises(ValueError):
                    normalize_feature_action_kind(unknown)

    def test_normalize_journaled_action_kind_accepts_typed_sub_actions(self) -> None:
        self.assertIs(WorkshopIntentKind.MERGE, normalize_journaled_action_kind("merge"))
        self.assertIs(BuildingMutationKind.UPGRADE, normalize_journaled_action_kind("building_upgrade"))
        self.assertTrue(is_workshop_journaled_action("recycle"))
        self.assertFalse(is_workshop_journaled_action("building_upgrade"))
        self.assertFalse(is_workshop_journaled_action(None))
        with self.assertRaises(ValueError):
            normalize_journaled_action_kind("pet_workshop.run")


class WorkshopAcknowledgementTests(unittest.TestCase):
    """Prove observed-bar parsing, zero-diamond enforcement, and counted compatibility."""

    def test_observed_workshop_bar_budget_parses_exact_nested_form(self) -> None:
        acknowledgement = parse_mutation_acknowledgement(
            '{"account_id":"account","castle_ref":"K1:Main",'
            '"action_kind":"pet_workshop.run","maintenance_date":"2026-09-14",'
            '"budget":{"kind":"observed_workshop_bar","max_diamond_spend":0}}'
        )

        self.assertIsNone(acknowledgement.quest_id)
        self.assertEqual("pet_workshop.run", acknowledgement.action_kind)
        self.assertIs(MutationBudgetKind.OBSERVED_WORKSHOP_BAR, acknowledgement.budget_kind)
        self.assertIsNone(acknowledgement.max_mutations)
        acknowledgement.authorize(
            account_id="account",
            castle_ref="K1:Main",
            quest_id=None,
            max_mutations=None,
            max_diamond_spend=0,
            maintenance_date=_MAINTENANCE_DATE,
            action_kind="pet_workshop.run",
            budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
        )

    def test_nested_budget_rejects_flat_fields_and_daily_capability(self) -> None:
        with self.assertRaises(ConfigurationError):
            parse_mutation_acknowledgement(
                '{"account_id":"account","castle_ref":"K1:Main",'
                '"capability":"hero_arena","maintenance_date":"2026-09-14",'
                '"budget":{"kind":"observed_workshop_bar","max_diamond_spend":0}}'
            )
        with self.assertRaises(ConfigurationError):
            parse_mutation_acknowledgement(
                '{"account_id":"account","castle_ref":"K1:Main",'
                '"action_kind":"pet_workshop.run","maintenance_date":"2026-09-14",'
                '"budget":{"kind":"observed_workshop_bar","max_diamond_spend":0},'
                '"max_mutations":1,"max_diamond_spend":0}'
            )
        with self.assertRaises(ConfigurationError):
            parse_mutation_acknowledgement(
                '{"account_id":"account","castle_ref":"K1:Main",'
                '"action_kind":"pet_workshop.run","maintenance_date":"2026-09-14",'
                '"budget":{"kind":"counted","max_diamond_spend":0}}'
            )

    def test_flat_counted_feature_form_still_parses(self) -> None:
        acknowledgement = parse_mutation_acknowledgement(
            '{"account_id":"account","castle_ref":"K1:Main",'
            '"action_kind":"pet_workshop.run","maintenance_date":"2026-09-14",'
            '"max_mutations":4,"max_diamond_spend":0}'
        )

        self.assertIs(MutationBudgetKind.COUNTED, acknowledgement.budget_kind)
        self.assertEqual(4, acknowledgement.max_mutations)

    def test_workshop_scope_enforces_zero_diamond_spend(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot spend diamonds"):
            MutationAcknowledgement(
                account_id="account",
                castle_ref="K1:Main",
                quest_id=None,
                maintenance_date=_MAINTENANCE_DATE,
                max_mutations=None,
                max_diamond_spend=1,
                action_kind=WorkshopMutationKind.RUN.value,
                budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
            )
        acknowledgement = _workshop_acknowledgement()
        with self.assertRaisesRegex(ValueError, "diamond limit exactly"):
            acknowledgement.authorize(
                account_id="account",
                castle_ref="K1:Main",
                quest_id=None,
                action_kind=WorkshopMutationKind.RUN.value,
                budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
                max_mutations=None,
                max_diamond_spend=1,
                maintenance_date=_MAINTENANCE_DATE,
            )
        with self.assertRaisesRegex(ValueError, "exact budget form"):
            acknowledgement.authorize(
                account_id="account",
                castle_ref="K1:Main",
                quest_id=None,
                action_kind=WorkshopMutationKind.RUN.value,
                max_mutations=1,
                max_diamond_spend=0,
                maintenance_date=_MAINTENANCE_DATE,
            )

    def test_observed_bar_budget_requires_the_workshop_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "pet_workshop.run scope"):
                CoreMutationBoundary(
                    target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=DailyRunJournalStore(Path(temporary)),
                    feature_action_kind=BuildingMutationKind.UPGRADE,
                    feature_budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
                )
            with self.assertRaisesRegex(ValueError, "cannot spend diamonds"):
                CoreMutationBoundary(
                    target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=DailyRunJournalStore(Path(temporary)),
                    feature_action_kind=WorkshopMutationKind.RUN,
                    feature_max_diamond_spend=5,
                )
            with self.assertRaisesRegex(ValueError, "must be positive"):
                CoreMutationBoundary(
                    target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=DailyRunJournalStore(Path(temporary)),
                    feature_action_kind=WorkshopMutationKind.RUN,
                    feature_max_mutations=0,
                )
            with self.assertRaisesRegex(ValueError, "must be positive"):
                CoreMutationBoundary(
                    target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=DailyRunJournalStore(Path(temporary)),
                    feature_action_kind=WorkshopMutationKind.RUN,
                    feature_max_mutations=None,
                )
            with self.assertRaisesRegex(ValueError, "cannot carry a counted mutation cap"):
                CoreMutationBoundary(
                    target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=DailyRunJournalStore(Path(temporary)),
                    feature_action_kind=WorkshopMutationKind.RUN,
                    feature_budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
                    feature_max_mutations=1,
                )


class WorkshopInvocationLifecycleTests(unittest.TestCase):
    """Prove invocation registration, sequencing, pending lookup, and no replay."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.scope = _workshop_scope(self.store)
        self.checkpoint = self.store.save(_checkpoint()) and self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )

    def _dispatched_pending(
        self,
        *,
        game_reset_id: str = "reset-1",
        castle: CastleIdentity = _CASTLE,
        invocation_id: str = "prior-inv",
        operation_id: str = "prior-inv-op-1",
    ) -> DailyTaskCheckpoint:
        """Journals one DISPATCHED Workshop operation inside a registered invocation."""

        checkpoint = self.store.register_workshop_invocation(
            _checkpoint(game_reset_id=game_reset_id, castle=castle),
            WorkshopInvocationRecord(
                invocation_id=invocation_id,
                action_kind=WorkshopMutationKind.RUN.value,
                budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
                operation_sequence=1,
            ),
        )
        checkpoint = self.store.prepare_intent(
            checkpoint,
            MutationIntent(
                operation_id=operation_id,
                quest_id=None,
                state=MutationIntentState.PREPARED,
                expected_precondition="eligible merge pair is visible",
                expected_postcondition="merged piece occupies one cell",
                action_kind=WorkshopIntentKind.MERGE.value,
                target={"cells": ["a1", "a2"]},
                invocation_id=invocation_id,
            ),
        )
        return self.store.transition_intent(
            checkpoint,
            operation_id,
            MutationIntentState.DISPATCHED,
        )

    def test_prepare_invocation_registers_identity_and_allocates_operations(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(
            checkpoint=self.checkpoint,
            metadata={"source": "daily"},
        )

        self.assertIn("reset-1", record.invocation_id)
        self.assertEqual(WorkshopMutationKind.RUN.value, record.action_kind)
        self.assertIs(MutationBudgetKind.OBSERVED_WORKSHOP_BAR, record.budget_kind)
        self.assertIsNone(record.max_mutations)
        self.assertEqual((record,), checkpoint.workshop_invocations)

        checkpoint, first_id = self.scope.allocate_workshop_operation_id(
            checkpoint,
            record.invocation_id,
        )
        checkpoint, second_id = self.scope.allocate_workshop_operation_id(
            checkpoint,
            record.invocation_id,
        )
        self.assertEqual(f"{record.invocation_id}-op-1", first_id)
        self.assertEqual(f"{record.invocation_id}-op-2", second_id)

        persisted = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        self.assertEqual(2, persisted.workshop_invocations[0].operation_sequence)
        with self.assertRaises(KeyError):
            self.scope.allocate_workshop_operation_id(checkpoint, "unknown-invocation")

    def test_update_invocation_persists_pending_and_stop_reason(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint = self.scope.update_workshop_invocation(
            checkpoint,
            replace(
                record,
                pending_operation_id=f"{record.invocation_id}-op-1",
                stop_reason=WorkshopStopReason.UNRESOLVED_STATE.value,
            ),
        )

        persisted = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        updated = persisted.workshop_invocations[0]
        self.assertEqual(f"{record.invocation_id}-op-1", updated.pending_operation_id)
        self.assertEqual(WorkshopStopReason.UNRESOLVED_STATE.value, updated.stop_reason)

    def test_new_invocation_is_refused_while_cross_reset_pending_exists(self) -> None:
        self._dispatched_pending(game_reset_id="reset-0")

        self.assertEqual(1, len(self.scope.find_pending_workshop_operations()))
        with self.assertRaisesRegex(RuntimeError, "unresolved Workshop operation"):
            self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)

    def test_pending_lookup_is_castle_scoped_and_alias_invariant(self) -> None:
        self._dispatched_pending(game_reset_id="reset-0")

        other_castle_scope = _workshop_scope(
            self.store,
            castle=_OTHER_CASTLE,
            castle_ref="K1:Other",
        )
        self.assertEqual((), other_castle_scope.find_pending_workshop_operations())

        alias_scope = _workshop_scope(
            self.store,
            castle=_CASTLE,
            castle_ref="K1:Main-alias",
        )
        self.assertEqual(1, len(alias_scope.find_pending_workshop_operations()))

        other_account_scope = CoreMutationBoundary(
            target=DailyMaintenanceTargetConfig("other-account", "K1:Main", _CASTLE, ()),
            boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
            authorizer=DailyMutationAuthorizer(()),
            journal_store=self.store,
            feature_action_kind=WorkshopMutationKind.RUN,
            feature_budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
            feature_max_mutations=None,
        )
        self.assertEqual((), other_account_scope.find_pending_workshop_operations())

    def test_dispatched_pending_resumes_by_reconciliation_only(self) -> None:
        self._dispatched_pending(game_reset_id="reset-0")
        pending = self.scope.find_pending_workshop_operations()[0]
        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        result = self.scope.resume_pending_workshop_operation(
            pending=pending,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(True, False),
        )

        self.assertEqual(0, dispatch_count)
        self.assertTrue(result.committed)
        self.assertEqual((), self.scope.find_pending_workshop_operations())

        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        self.assertNotEqual(pending.intent.invocation_id, record.invocation_id)
        self.assertEqual((record,), checkpoint.workshop_invocations)

    def test_pending_resume_rejects_foreign_castle(self) -> None:
        self._dispatched_pending(game_reset_id="reset-0")
        pending = self.scope.find_pending_workshop_operations()[0]
        other_scope = _workshop_scope(
            self.store,
            castle=_OTHER_CASTLE,
            castle_ref="K1:Other",
        )

        with self.assertRaisesRegex(PermissionError, "different scope"):
            other_scope.resume_pending_workshop_operation(
                pending=pending,
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )

    def test_dispatch_journals_typed_workshop_identity(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = self.scope.allocate_workshop_operation_id(
            checkpoint,
            record.invocation_id,
        )
        operation = _workshop_operation(operation_id, invocation_id=record.invocation_id)

        result = self.scope.dispatch_workshop_operation(
            checkpoint=checkpoint,
            operation=operation,
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(True, False),
        )

        self.assertTrue(result.committed)
        persisted = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        intent = persisted.mutation_intents[0]
        self.assertEqual(WorkshopIntentKind.MERGE.value, intent.action_kind)
        self.assertEqual(record.invocation_id, intent.invocation_id)
        self.assertEqual({"cells": ["a1", "a2"]}, intent.target)
        self.assertIsNone(intent.quest_id)

    def test_dispatch_rejects_unregistered_or_invalid_operations(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = self.scope.allocate_workshop_operation_id(
            checkpoint,
            record.invocation_id,
        )

        with self.assertRaisesRegex(PermissionError, "registered durable invocation"):
            self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=_workshop_operation("op-x", invocation_id="unregistered"),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        with self.assertRaisesRegex(PermissionError, "does not authorize a Workshop run"):
            building_scope = CoreMutationBoundary(
                target=DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),
                boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                authorizer=DailyMutationAuthorizer(()),
                journal_store=self.store,
                feature_action_kind=BuildingMutationKind.UPGRADE,
            )
            building_scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )

    def test_dispatch_rejects_diamond_quest_and_non_mutating_operations(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = self.scope.allocate_workshop_operation_id(
            checkpoint,
            record.invocation_id,
        )
        base = _workshop_operation(operation_id, invocation_id=record.invocation_id)

        with self.assertRaisesRegex(PermissionError, "Daily quest identity"):
            self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=replace(base, quest_id=DailyQuestId.HERO_ARENA),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        with self.assertRaisesRegex(PermissionError, "cannot spend diamonds"):
            self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=replace(base, diamond_budget=1),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        with self.assertRaisesRegex(PermissionError, "sub-action kind"):
            self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=replace(base, action_kind=WorkshopIntentKind.SELECT),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        with self.assertRaisesRegex(ValueError, "invocation id"):
            self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=replace(base, invocation_id=None),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )

    def _dispatched_uncommitted(
        self,
        scope: CoreMutationBoundary,
    ) -> tuple[DailyTaskCheckpoint, WorkshopInvocationRecord, JournaledMutationResult]:
        """Journal one operation whose reconciliation stays unresolved."""

        checkpoint, record = scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = scope.allocate_workshop_operation_id(
            checkpoint, record.invocation_id,
        )
        result = scope.dispatch_workshop_operation(
            checkpoint=checkpoint,
            operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(False, False),
        )
        return checkpoint, record, result

    def test_stale_progress_writes_cannot_erase_pending_operations(self) -> None:
        stale, record, result = self._dispatched_uncommitted(self.scope)
        persisted_record = result.checkpoint.workshop_invocations[0]

        self.assertFalse(result.committed)
        self.assertEqual(1, len(self.scope.find_pending_workshop_operations()))
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.scope.update_workshop_invocation(
                stale,
                replace(
                    persisted_record,
                    stop_reason=WorkshopStopReason.UNRESOLVED_STATE.value,
                ),
            )
        self.assertEqual(1, len(self.scope.find_pending_workshop_operations()))
        with self.assertRaisesRegex(RuntimeError, "stale"):
            self.scope.allocate_workshop_operation_id(stale, record.invocation_id)
        self.assertEqual(1, len(self.scope.find_pending_workshop_operations()))

        updated = self.scope.update_workshop_invocation(
            result.checkpoint,
            replace(
                persisted_record,
                pending_operation_id=f"{persisted_record.invocation_id}-op-1",
                stop_reason=WorkshopStopReason.UNRESOLVED_STATE.value,
            ),
        )
        self.assertEqual(
            WorkshopStopReason.UNRESOLVED_STATE.value,
            updated.workshop_invocations[0].stop_reason,
        )
        self.assertEqual(1, len(self.scope.find_pending_workshop_operations()))

    def test_invocation_update_preserves_identity_budget_and_sequence(self) -> None:
        _, _, result = self._dispatched_uncommitted(self.scope)
        persisted_record = result.checkpoint.workshop_invocations[0]

        with self.assertRaisesRegex(PermissionError, "cannot regress"):
            self.scope.update_workshop_invocation(
                result.checkpoint,
                replace(persisted_record, operation_sequence=0),
            )
        with self.assertRaisesRegex(PermissionError, "immutable"):
            self.scope.update_workshop_invocation(
                result.checkpoint,
                replace(
                    persisted_record,
                    budget_kind=MutationBudgetKind.COUNTED,
                    max_mutations=5,
                ),
            )
        persisted = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        self.assertEqual(persisted_record, persisted.workshop_invocations[0])

    def test_unjournaled_invocations_fail_persisted_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scope = _workshop_scope(DailyRunJournalStore(Path(temporary)))
            ghost = replace(
                _checkpoint(),
                workshop_invocations=(
                    WorkshopInvocationRecord(
                        invocation_id="ghost-inv",
                        action_kind=WorkshopMutationKind.RUN.value,
                        budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
                    ),
                ),
            )

            with self.assertRaisesRegex(RuntimeError, "missing from the durable journal"):
                scope.prepare_workshop_invocation(checkpoint=ghost)
            with self.assertRaisesRegex(RuntimeError, "missing from the durable journal"):
                scope.update_workshop_invocation(ghost, ghost.workshop_invocations[0])

    def test_counted_budget_is_bound_per_invocation(self) -> None:
        scope = _workshop_scope(
            self.store,
            budget_kind=MutationBudgetKind.COUNTED,
            max_mutations=1,
        )
        checkpoint = self.checkpoint
        for _ in range(2):
            checkpoint, record = scope.prepare_workshop_invocation(checkpoint=checkpoint)
            checkpoint, operation_id = scope.allocate_workshop_operation_id(
                checkpoint, record.invocation_id,
            )
            result = scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
            self.assertTrue(result.committed)
            checkpoint = result.checkpoint

    def test_counted_cap_exhausts_within_one_invocation(self) -> None:
        scope = _workshop_scope(
            self.store,
            budget_kind=MutationBudgetKind.COUNTED,
            max_mutations=1,
        )
        checkpoint, record = scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = scope.allocate_workshop_operation_id(
            checkpoint, record.invocation_id,
        )
        result = scope.dispatch_workshop_operation(
            checkpoint=checkpoint,
            operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(True, False),
        )
        self.assertTrue(result.committed)

        checkpoint, second_id = scope.allocate_workshop_operation_id(
            result.checkpoint, record.invocation_id,
        )
        with self.assertRaisesRegex(PermissionError, "cap has been exhausted"):
            scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=_workshop_operation(second_id, invocation_id=record.invocation_id),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )

    def test_invocation_budget_must_match_authorized_scope(self) -> None:
        scope = _workshop_scope(
            self.store,
            budget_kind=MutationBudgetKind.COUNTED,
            max_mutations=1,
        )
        widened = self.store.register_workshop_invocation(
            self.checkpoint,
            WorkshopInvocationRecord(
                invocation_id="wider-inv",
                action_kind=WorkshopMutationKind.RUN.value,
                budget_kind=MutationBudgetKind.COUNTED,
                max_mutations=5,
                operation_sequence=1,
            ),
        )
        with self.assertRaisesRegex(PermissionError, "authorized budget"):
            scope.dispatch_workshop_operation(
                checkpoint=widened,
                operation=_workshop_operation("wider-inv-op-1", invocation_id="wider-inv"),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        mixed = self.store.register_workshop_invocation(
            widened,
            WorkshopInvocationRecord(
                invocation_id="observed-inv",
                action_kind=WorkshopMutationKind.RUN.value,
                budget_kind=MutationBudgetKind.OBSERVED_WORKSHOP_BAR,
            ),
        )
        with self.assertRaisesRegex(PermissionError, "authorized budget"):
            scope.dispatch_workshop_operation(
                checkpoint=mixed,
                operation=_workshop_operation("observed-inv-op-1", invocation_id="observed-inv"),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
        with self.assertRaisesRegex(PermissionError, "immutable"):
            scope.update_workshop_invocation(
                mixed,
                replace(mixed.workshop_invocations[0], max_mutations=9),
            )

    def test_observed_bar_invocation_has_no_counted_cap(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        for _ in range(3):
            checkpoint, operation_id = self.scope.allocate_workshop_operation_id(
                checkpoint, record.invocation_id,
            )
            result = self.scope.dispatch_workshop_operation(
                checkpoint=checkpoint,
                operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
                dispatch=lambda: None,
                reconcile=lambda: MutationReconciliation(True, False),
            )
            self.assertTrue(result.committed)
            checkpoint = result.checkpoint

    def test_castle_level_change_preserves_journal_and_pending_identity(self) -> None:
        checkpoint, record = self.scope.prepare_workshop_invocation(checkpoint=self.checkpoint)
        checkpoint, operation_id = self.scope.allocate_workshop_operation_id(
            checkpoint, record.invocation_id,
        )
        result = self.scope.dispatch_workshop_operation(
            checkpoint=checkpoint,
            operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(True, False),
        )
        self.assertTrue(result.committed)

        leveled = CastleIdentity("K1", "Main", 11)
        loaded = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=leveled,
        )
        self.assertEqual(10, loaded.castle.castle_level)
        leveled_scope = _workshop_scope(self.store, castle=leveled)
        self.assertEqual((), leveled_scope.find_pending_workshop_operations())

    def test_pending_resume_survives_castle_level_change(self) -> None:
        self._dispatched_pending(game_reset_id="reset-0")
        leveled_scope = _workshop_scope(
            self.store,
            castle=CastleIdentity("K1", "Main", 11),
        )
        pending = leveled_scope.find_pending_workshop_operations()

        self.assertEqual(1, len(pending))
        self.assertEqual(10, pending[0].castle.castle_level)
        result = leveled_scope.resume_pending_workshop_operation(
            pending=pending[0],
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(True, False),
        )
        self.assertTrue(result.committed)
        self.assertEqual((), leveled_scope.find_pending_workshop_operations())

    def test_same_day_run_tolerates_persisted_lower_castle_level(self) -> None:
        leveled_scope = _workshop_scope(
            self.store,
            castle=CastleIdentity("K1", "Main", 11),
        )
        checkpoint, record = leveled_scope.prepare_workshop_invocation(
            checkpoint=self.checkpoint,
        )
        self.assertEqual(10, checkpoint.castle.castle_level)

        checkpoint, operation_id = leveled_scope.allocate_workshop_operation_id(
            checkpoint, record.invocation_id,
        )
        result = leveled_scope.dispatch_workshop_operation(
            checkpoint=checkpoint,
            operation=_workshop_operation(operation_id, invocation_id=record.invocation_id),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(True, False),
        )
        self.assertTrue(result.committed)


class WorkshopJournalMigrationTests(unittest.TestCase):
    """Prove v1 journals migrate forward without losing receipts."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))

    def _v1_payload(self) -> dict[str, object]:
        """Builds one complete version-one journal payload with existing receipts."""

        return {
            "schema_version": 1,
            "maintenance_date": "2026-09-14",
            "game_reset_id": "reset-1",
            "account_id": "account",
            "castle": {"kingdom": "K1", "castle_name": "Main", "castle_level": 10},
            "current_quest_id": None,
            "completed_quest_ids": ["claim_completed"],
            "mutation_intents": [
                {
                    "operation_id": "arena-1",
                    "quest_id": "hero_arena",
                    "state": "committed",
                    "expected_precondition": "free attempt visible",
                    "expected_postcondition": "Daily progress increased",
                    "diamond_budget": 0,
                    "diamonds_spent": 0,
                    "metadata": {"receipt": "post.png"},
                    "action_kind": None,
                    "target": None,
                }
            ],
            "consumed_recovery_stages": ["hero_arena:reread"],
            "last_typed_screen": None,
        }

    def test_v1_journal_loads_with_empty_invocations_and_preserves_receipts(self) -> None:
        path = self.store.checkpoint_path(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._v1_payload()), encoding="utf-8")

        checkpoint = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )

        self.assertEqual((), checkpoint.workshop_invocations)
        self.assertEqual(1, len(checkpoint.mutation_intents))
        intent = checkpoint.mutation_intents[0]
        self.assertIsNone(intent.invocation_id)
        self.assertEqual(MutationIntentState.COMMITTED, intent.state)
        self.assertEqual("post.png", intent.metadata["receipt"])

    def test_v1_journal_migrates_to_v2_on_save(self) -> None:
        path = self.store.checkpoint_path(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._v1_payload()), encoding="utf-8")
        checkpoint = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )

        self.store.save(checkpoint)
        migrated = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(2, migrated["schema_version"])
        self.assertEqual([], migrated["workshop_invocations"])
        self.assertEqual("arena-1", migrated["mutation_intents"][0]["operation_id"])
        self.assertIsNone(migrated["mutation_intents"][0]["invocation_id"])

    def test_invocation_records_round_trip_through_v2(self) -> None:
        checkpoint = _checkpoint()
        record = WorkshopInvocationRecord(
            invocation_id="inv-a",
            action_kind=WorkshopMutationKind.RUN.value,
            budget_kind=MutationBudgetKind.COUNTED,
            max_mutations=3,
            operation_sequence=2,
            pending_operation_id="inv-a-op-2",
            stop_reason=WorkshopStopReason.ZERO_ENERGY.value,
            metadata={"origin": "daily"},
        )
        checkpoint = self.store.register_workshop_invocation(checkpoint, record)

        loaded = self.store.load(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )

        self.assertEqual(record, loaded.workshop_invocations[0])
        self.assertEqual(record, checkpoint.workshop_invocations[0])

    def test_malformed_journal_raises_configuration_error(self) -> None:
        path = self.store.checkpoint_path(
            game_reset_id="reset-1",
            account_id="account",
            castle=_CASTLE,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema_version": 99}', encoding="utf-8")

        with self.assertRaises(ConfigurationError):
            self.store.load(
                game_reset_id="reset-1",
                account_id="account",
                castle=_CASTLE,
            )


class InvocationFactoryTests(unittest.TestCase):
    """Prove the shared run-boundary and invocation-id factory contracts."""

    def test_build_daily_run_boundary_uses_game_reset_hour(self) -> None:
        config = DailyMaintenanceConfig(
            maintenance_timezone="America/Toronto",
            maintenance_hour_local=3,
            game_reset_hour_utc=0,
            targets=(DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ()),),
        )

        boundary = build_daily_run_boundary(config)

        self.assertRegex(boundary.game_reset_id, r"^pnc-reset-\d{4}-\d{2}-\d{2}-00$")
        self.assertIsInstance(boundary.maintenance_date, date)
        self.assertEqual(boundary, build_daily_run_boundary(config))

    def test_generate_workshop_invocation_id_is_unique_and_scoped(self) -> None:
        first = generate_workshop_invocation_id(
            account_id="account",
            castle=_CASTLE,
            game_reset_id="reset-1",
        )
        second = generate_workshop_invocation_id(
            account_id="account",
            castle=_CASTLE,
            game_reset_id="reset-1",
        )

        self.assertNotEqual(first, second)
        self.assertIn("reset-1", first)
        self.assertIn("K1_Main", first)


class WorkshopRunAuthorityTests(unittest.TestCase):
    """Prove the shared policy/scope composition for direct and Daily adapters."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.target = DailyMaintenanceTargetConfig("account", "K1:Main", _CASTLE, ())
        self.policy = WorkshopPolicy(
            order_piece_total=2,
            reward_priority=(WorkshopOrderRewardCategory.BEAST_LASSO,),
            recyclable_item_ids=frozenset(),
            max_cooldown_wait_ms=60_000,
        )

    def test_build_authority_composes_policy_with_authorized_scope(self) -> None:
        for budget_kind, max_mutations in (
            (MutationBudgetKind.OBSERVED_WORKSHOP_BAR, None),
            (MutationBudgetKind.COUNTED, 3),
        ):
            with self.subTest(budget_kind=budget_kind):
                authority = build_workshop_run_authority(
                    target=self.target,
                    policy=self.policy,
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer((_workshop_acknowledgement(
                        budget_kind=budget_kind,
                        max_mutations=max_mutations,
                    ),)),
                    journal_store=self.store,
                    budget_kind=budget_kind,
                    max_mutations=max_mutations,
                )

                self.assertIs(self.policy, authority.policy)
                self.assertIs(
                    WorkshopMutationKind.RUN,
                    authority.mutation_boundary.feature_action_kind,
                )
                authority.mutation_boundary.authorize(action_kind=WorkshopMutationKind.RUN)
                self.assertFalse(
                    authority.mutation_boundary.supports_mutation(
                        capability=DailyQuestId.HERO_HALL,
                    )
                )
                self.assertIsNone(
                    self.store.load(
                        game_reset_id="reset-1",
                        account_id="account",
                        castle=_CASTLE,
                    )
                )

    def test_build_authority_requires_exact_acknowledgement(self) -> None:
        with self.assertRaisesRegex(PermissionError, "exactly one matching acknowledgement"):
            build_workshop_run_authority(
                target=self.target,
                policy=self.policy,
                boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                authorizer=DailyMutationAuthorizer(()),
                journal_store=self.store,
            )
        with self.assertRaisesRegex(PermissionError, "exactly one matching acknowledgement"):
            build_workshop_run_authority(
                target=self.target,
                policy=self.policy,
                boundary=DailyRunBoundary(date(2026, 9, 15), "reset-2"),
                authorizer=DailyMutationAuthorizer((_workshop_acknowledgement(),)),
                journal_store=self.store,
            )

    def test_authority_rejects_untyped_or_miscoped_members(self) -> None:
        with self.assertRaisesRegex(TypeError, "WorkshopPolicy"):
            WorkshopRunAuthority(
                policy=object(),
                mutation_boundary=_workshop_scope(self.store),
            )
        with self.assertRaisesRegex(ValueError, "pet_workshop.run"):
            WorkshopRunAuthority(
                policy=self.policy,
                mutation_boundary=CoreMutationBoundary(
                    target=self.target,
                    boundary=DailyRunBoundary(_MAINTENANCE_DATE, "reset-1"),
                    authorizer=DailyMutationAuthorizer(()),
                    journal_store=self.store,
                    feature_action_kind=BuildingMutationKind.UPGRADE,
                ),
            )


if __name__ == "__main__":
    unittest.main()
