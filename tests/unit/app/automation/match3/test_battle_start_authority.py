"""Offline tests for the durable Campaign battle-start authority boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app.automation.daily_maintenance.application_service import DailyRunBoundary
from pnc_automation.app.automation.daily_maintenance.authorization import DailyMutationAuthorizer
from pnc_automation.app.automation.daily_maintenance.invocation_factory import (
    generate_match3_invocation_id,
)
from pnc_automation.app.automation.daily_maintenance.mutation_dispatcher import (
    MutationReconciliation,
)
from pnc_automation.app.automation.engine.core_daily_mutation import CoreMutationBoundary
from pnc_automation.app.automation.match3 import (
    FORMATION_PREPARATION_LAYOUT_ID,
    CampaignBattleStartAuthority,
    FormationPreparationProof,
    Match3ContinuationObservation,
    Match3ContinuationState,
    Match3StartBudget,
    Match3StartPreflight,
    UnavailableMatch3Component,
    require_campaign_battle_start_authority,
    require_formation_preparation_proof,
    require_match3_start_preflight,
)
from pnc_automation.app.authoring.config.daily_maintenance import DailyMaintenanceTargetConfig
from pnc_automation.app.pnc.domain.campaign import (
    CampaignMode,
    CampaignNodeFacts,
    CampaignStageDetail,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.daily_maintenance import (
    ActionPointReservation,
    DailyQuestId,
    DailyTaskCheckpoint,
    MutationAcknowledgement,
    MutationBudgetKind,
    MutationIntent,
    MutationIntentState,
)
from pnc_automation.app.pnc.domain.match3 import (
    Match3Context,
    Match3Mode,
    Match3MutationKind,
    Match3Request,
    Match3Target,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    Observation,
    VisibleElement,
)
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopIntentKind,
    WorkshopMutationKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.persistence.daily_run_journal_store import DailyRunJournalStore
from pnc_automation.core.errors import ConfigurationError
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

_SESSION = "session-1"
_EPOCH = 1
_STAGE_LAYOUT = "campaign_stage_chapter_6"
_LEFT_CHALLENGE_BOUNDS = Bounds(28, 714, 190, 68)
_FORMATION_BACK_BOUNDS = Bounds(23, 7, 57, 63)
_ACCOUNT_ID = "acct-1"
_CASTLE = CastleIdentity(kingdom="287", castle_name="Castle-A", castle_level=10)
_CASTLE_REF = "castle_a"
_MAINTENANCE_DATE = date(2026, 9, 4)
_RESET_ID = "pnc-reset-2026-09-04-00"
_LATER_RESET_ID = "pnc-reset-2026-09-05-00"


def _frame(*, capture: int, input_sequence: int) -> FrameRef:
    """One session frame reference."""

    return FrameRef(
        session_id=_SESSION,
        session_epoch=_EPOCH,
        capture_sequence=capture,
        input_sequence=input_sequence,
        captured_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
    )


def _stage_detail(frame: FrameRef, *, chapter: int = 6, stage: int = 4) -> CampaignStageDetail:
    """Source-frame Campaign stage facts with the observed 12-point Challenge cost."""

    return CampaignStageDetail(
        chapter_number=chapter,
        stage_number=stage,
        mode=CampaignMode.STANDARD,
        action_points=60,
        max_action_points=120,
        challenge_cost=12,
        frame_ref=frame,
        source_screen=ScreenType.PNC_CAMPAIGN_STAGE,
        source_layout_id=_STAGE_LAYOUT,
    )


def _stage_observation(detail: CampaignStageDetail, frame: FrameRef) -> Observation:
    """A clear, unblocked Campaign stage-detail observation with its Challenge control."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_CAMPAIGN_STAGE,
            effective_screen=ScreenType.PNC_CAMPAIGN_STAGE,
            layout_id=_STAGE_LAYOUT,
            guard=GuardVerdict.CLEAR,
        ),
        visible_elements={
            UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON: VisibleElement(
                selector_id=UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON,
                bounds=_LEFT_CHALLENGE_BOUNDS,
                confidence=0.98,
                frame_ref=frame,
                source_screen=ScreenType.PNC_CAMPAIGN_STAGE,
                source_layout_id=_STAGE_LAYOUT,
            )
        },
        campaign_stage=detail,
        frame_ref=frame,
    )


def _formation_observation(frame: FrameRef) -> Observation:
    """A clear formation-preparation frame carrying verified identity."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_HERO_FORMATION,
            effective_screen=ScreenType.PNC_HERO_FORMATION,
            layout_id=FORMATION_PREPARATION_LAYOUT_ID,
            guard=GuardVerdict.CLEAR,
        ),
        visible_elements={
            UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON: VisibleElement(
                selector_id=UiElementId.PNC_CAMPAIGN_FORMATION_BACK_BUTTON,
                bounds=_FORMATION_BACK_BOUNDS,
                confidence=0.99,
                frame_ref=frame,
                source_screen=ScreenType.PNC_HERO_FORMATION,
                source_layout_id=FORMATION_PREPARATION_LAYOUT_ID,
            )
        },
        current_castle=_CASTLE,
        current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        verified_pnc_account_id=_ACCOUNT_ID,
        frame_ref=frame,
    )


def _request(*, stage: int = 4, chapter: int = 6) -> Match3Request:
    """A Campaign solver request selecting the given observed node ordinals."""

    return Match3Request(
        context=Match3Context.CAMPAIGN,
        mode=Match3Mode.SOLVER,
        target=Match3Target(
            context=Match3Context.CAMPAIGN,
            campaign_node=CampaignNodeFacts(
                chapter_number=chapter, stage_number=stage, mode=CampaignMode.STANDARD
            ),
        ),
    )


def _preflight(
    *, stage: int = 4, chapter: int = 6, cost: int = 12, max_attempts: int = 1
) -> Match3StartPreflight:
    """One qualified Campaign start proposal bound to synthetic formation evidence."""

    source_frame = _frame(capture=10, input_sequence=4)
    detail = _stage_detail(source_frame, chapter=chapter, stage=stage)
    if cost != 12:
        detail = replace(detail, challenge_cost=cost)
    proof = require_formation_preparation_proof(
        request=_request(stage=stage, chapter=chapter),
        source=_stage_observation(detail, source_frame),
        dispatch=InputDispatchRecord(
            source_frame=source_frame,
            dispatch=TapDispatch(point=(40, 730), input_sequence=source_frame.input_sequence + 1),
        ),
        destination=_formation_observation(_frame(capture=11, input_sequence=5)),
    )
    assert proof.destination_frame is not None
    return require_match3_start_preflight(
        transition=proof,
        formation=_formation_observation(proof.destination_frame),
        continuation=Match3ContinuationObservation(
            state=Match3ContinuationState.OFF,
            frame_ref=proof.destination_frame,
            source_screen=ScreenType.PNC_HERO_FORMATION,
            source_layout_id=FORMATION_PREPARATION_LAYOUT_ID,
        ),
        budget=Match3StartBudget(
            max_action_points=max(cost, 12), max_attempts=max_attempts
        ),
        account_id=_ACCOUNT_ID,
        castle=_CASTLE,
    )


def _target(*, account_id: str = _ACCOUNT_ID, castle: CastleIdentity = _CASTLE) -> DailyMaintenanceTargetConfig:
    """One resolved mutation target bound to the preflight identity."""

    return DailyMaintenanceTargetConfig(
        account_id=account_id,
        castle_ref=_CASTLE_REF,
        castle=castle,
        capabilities=(),
    )


def _acknowledgement(*, max_action_points: int = 120) -> MutationAcknowledgement:
    """The actual one-attempt Campaign battle-start acknowledgement."""

    return MutationAcknowledgement(
        account_id=_ACCOUNT_ID,
        castle_ref=_CASTLE_REF,
        quest_id=None,
        maintenance_date=_MAINTENANCE_DATE,
        max_mutations=1,
        max_diamond_spend=0,
        action_kind=Match3MutationKind.CAMPAIGN_BATTLE_START.value,
        max_action_points=max_action_points,
    )


def _checkpoint(game_reset_id: str = _RESET_ID) -> DailyTaskCheckpoint:
    """One empty checkpoint for the shared account/castle/reset boundary."""

    return DailyTaskCheckpoint(
        maintenance_date=_MAINTENANCE_DATE.isoformat(),
        game_reset_id=game_reset_id,
        account_id=_ACCOUNT_ID,
        castle=_CASTLE,
    )


def _authority(
    store: DailyRunJournalStore,
    *,
    game_reset_id: str = _RESET_ID,
    preflight: Match3StartPreflight | None = None,
    invocation_id: str | None = None,
) -> CampaignBattleStartAuthority:
    """The bound authority for one invocation over the given journal root."""

    return require_campaign_battle_start_authority(
        target=_target(),
        boundary=DailyRunBoundary(
            maintenance_date=_MAINTENANCE_DATE, game_reset_id=game_reset_id
        ),
        authorizer=DailyMutationAuthorizer((_acknowledgement(),)),
        journal_store=store,
        preflight=_preflight() if preflight is None else preflight,
        invocation_id=generate_match3_invocation_id(
            account_id=_ACCOUNT_ID, castle=_CASTLE, game_reset_id=game_reset_id
        )
        if invocation_id is None
        else invocation_id,
    )


def _campaign_intent(
    authority: CampaignBattleStartAuthority, state: MutationIntentState
) -> MutationIntent:
    """The durable record the authority's operation would journal."""

    operation = authority.operation()
    return MutationIntent(
        operation_id=operation.operation_id,
        quest_id=None,
        state=state,
        expected_precondition=operation.expected_precondition,
        expected_postcondition=operation.expected_postcondition,
        action_kind=operation.action_kind.value,
        target=dict(operation.target),
        invocation_id=operation.invocation_id,
        action_point_reservation=operation.action_point_reservation,
    )


class CampaignBattleStartAuthorityTests(unittest.TestCase):
    """The exact-identity factory and bound operation shape."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.authority = _authority(self.store)

    def test_operation_binds_exact_target_mode_cost_and_identity(self) -> None:
        """The one journaled operation carries the bound attempt identity exactly."""

        operation = self.authority.operation()
        detail = self.authority.preflight.stage_detail

        self.assertIs(Match3MutationKind.CAMPAIGN_BATTLE_START, operation.action_kind)
        self.assertEqual(
            {
                "context": Match3Context.CAMPAIGN.value,
                "chapter_number": 6,
                "stage_number": 4,
                "match3_mode": Match3Mode.SOLVER.value,
                "campaign_mode": CampaignMode.STANDARD.value,
            },
            operation.target,
        )
        self.assertIsNone(operation.quest_id)
        self.assertEqual(0, operation.diamond_budget)
        self.assertEqual(self.authority.invocation_id, operation.invocation_id)
        self.assertEqual(f"{self.authority.invocation_id}-start", operation.operation_id)
        self.assertEqual(
            detail.challenge_cost, operation.action_point_reservation.reserved_action_points
        )
        self.assertFalse(operation.action_point_reservation.released)

    def test_authority_carries_the_actual_acknowledgement(self) -> None:
        """The retained acknowledgement is the exact resolved feature slice."""

        acknowledgement = self.authority.acknowledgement
        self.assertIsNone(acknowledgement.quest_id)
        self.assertEqual(
            Match3MutationKind.CAMPAIGN_BATTLE_START.value, acknowledgement.action_kind
        )
        self.assertEqual(_ACCOUNT_ID, acknowledgement.account_id)
        self.assertEqual(_CASTLE_REF, acknowledgement.castle_ref)
        self.assertEqual(_MAINTENANCE_DATE, acknowledgement.maintenance_date)
        self.assertEqual(1, acknowledgement.max_mutations)
        self.assertEqual(0, acknowledgement.max_diamond_spend)
        self.assertEqual(120, acknowledgement.max_action_points)

    def test_factory_requires_acknowledged_ap_ceiling_and_one_attempt(self) -> None:
        """A caller proposal cannot raise the actual AP or attempt allowance."""

        boundary = DailyRunBoundary(
            maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
        )
        with self.assertRaisesRegex(ValueError, "positive AP ceiling"):
            replace(_acknowledgement(), max_action_points=None)
        with self.assertRaisesRegex(PermissionError, "acknowledged AP allowance"):
            require_campaign_battle_start_authority(
                target=_target(),
                boundary=boundary,
                authorizer=DailyMutationAuthorizer((_acknowledgement(max_action_points=11),)),
                journal_store=self.store,
                preflight=_preflight(),
                invocation_id="match3-campaign-test",
            )
        with self.assertRaisesRegex(PermissionError, "exactly one attempt"):
            require_campaign_battle_start_authority(
                target=_target(),
                boundary=boundary,
                authorizer=DailyMutationAuthorizer((_acknowledgement(),)),
                journal_store=self.store,
                preflight=_preflight(max_attempts=2),
                invocation_id="match3-campaign-test",
            )

    def test_factory_rejects_mismatched_identity(self) -> None:
        """Preflight account/castle must match the resolved mutation target."""

        for target in (
            _target(account_id="acct-2"),
            _target(castle=CastleIdentity(kingdom="287", castle_name="Castle-B", castle_level=10)),
        ):
            with self.subTest(target=target):
                with self.assertRaises(PermissionError):
                    require_campaign_battle_start_authority(
                        target=target,
                        boundary=DailyRunBoundary(
                            maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
                        ),
                        authorizer=DailyMutationAuthorizer((_acknowledgement(),)),
                        journal_store=self.store,
                        preflight=_preflight(),
                        invocation_id="match3-campaign-test",
                    )

    def test_factory_requires_the_actual_acknowledgement(self) -> None:
        """No authorization exists without exactly one matching feature acknowledgement."""

        with self.assertRaises(PermissionError):
            require_campaign_battle_start_authority(
                target=_target(),
                boundary=DailyRunBoundary(
                    maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
                ),
                authorizer=DailyMutationAuthorizer(()),
                journal_store=self.store,
                preflight=_preflight(),
                invocation_id="match3-campaign-test",
            )

    def test_factory_rejects_forged_or_wrongly_scoped_inputs(self) -> None:
        """Untyped proposals cannot compose authority through the factory."""

        boundary = DailyRunBoundary(
            maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
        )
        authorizer = DailyMutationAuthorizer((_acknowledgement(),))
        with self.assertRaises(TypeError):
            require_campaign_battle_start_authority(
                target=_target(),
                boundary=boundary,
                authorizer=authorizer,
                journal_store=self.store,
                preflight="forged",
                invocation_id="match3-campaign-test",
            )

    def test_direct_construction_is_refused(self) -> None:
        """The authority cannot be constructed or relabelled outside its factory."""

        workshop_scope = CoreMutationBoundary(
            target=_target(),
            boundary=DailyRunBoundary(
                maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
            ),
            authorizer=DailyMutationAuthorizer((_acknowledgement(),)),
            journal_store=self.store,
            feature_action_kind=WorkshopMutationKind.RUN,
            feature_max_mutations=1,
            feature_max_diamond_spend=0,
        )
        for boundary in (workshop_scope, self.authority.mutation_boundary):
            with self.subTest(boundary=boundary.feature_action_kind):
                with self.assertRaises(ValueError):
                    CampaignBattleStartAuthority(
                        preflight=_preflight(),
                        acknowledgement=_acknowledgement(),
                        invocation_id="match3-campaign-test",
                        mutation_boundary=boundary,
                    )
        with self.assertRaises(ValueError):
            replace(self.authority, invocation_id="forged-invocation")

    def test_insufficient_observed_ap_is_rejected_before_journaling(self) -> None:
        """Observed AP below the Challenge cost refuses authority before any record."""

        preflight = _preflight()
        for action_points in (5, 0, None):
            with self.subTest(action_points=action_points):
                forged = replace(preflight.stage_detail, action_points=action_points)
                with patch.object(FormationPreparationProof, "stage_detail", forged):
                    with self.assertRaises(PermissionError):
                        require_campaign_battle_start_authority(
                            target=_target(),
                            boundary=DailyRunBoundary(
                                maintenance_date=_MAINTENANCE_DATE, game_reset_id=_RESET_ID
                            ),
                            authorizer=DailyMutationAuthorizer((_acknowledgement(),)),
                            journal_store=self.store,
                            preflight=preflight,
                            invocation_id="match3-campaign-test",
                        )
        self.assertIsNone(
            self.store.load(
                game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
            )
        )

    def test_production_battle_starts_remain_unavailable(self) -> None:
        """The authority adds no production availability for any context/mode pair."""

        component = UnavailableMatch3Component()
        for context in Match3Context:
            for mode in Match3Mode:
                with self.subTest(context=context, mode=mode):
                    self.assertFalse(component.availability(context, mode).available)


class CampaignBattleStartDispatchTests(unittest.TestCase):
    """Exactly-once dispatch, durable ambiguity, and consumed-attempt semantics."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.authority = _authority(self.store)
        self.checkpoint = _checkpoint()

    def _reload(self, game_reset_id: str = _RESET_ID) -> DailyTaskCheckpoint:
        """Reload the durable checkpoint the way a restarted caller would."""

        loaded = self.store.load(
            game_reset_id=game_reset_id, account_id=_ACCOUNT_ID, castle=_CASTLE
        )
        assert loaded is not None
        return loaded

    def _dispatch(self, authority: CampaignBattleStartAuthority, checkpoint: DailyTaskCheckpoint, dispatch):
        return authority.dispatch_battle_start(
            checkpoint=checkpoint,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(False, False),
        )

    def test_dispatch_journals_consumed_attempt_before_the_callback(self) -> None:
        """The durable DISPATCHED record exists before any input callback runs."""

        observed_states: list[MutationIntentState] = []

        def dispatch() -> None:
            loaded = self._reload()
            observed_states.append(loaded.mutation_intents[0].state)

        result = self.authority.dispatch_battle_start(
            checkpoint=self.checkpoint,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )

        self.assertEqual([MutationIntentState.DISPATCHED], observed_states)
        self.assertTrue(result.committed)
        intent = result.checkpoint.mutation_intents[0]
        self.assertEqual(MutationIntentState.COMMITTED, intent.state)
        self.assertEqual(
            Match3MutationKind.CAMPAIGN_BATTLE_START.value, intent.action_kind
        )
        self.assertEqual(self.authority.invocation_id, intent.invocation_id)
        self.assertEqual(12, intent.action_point_reservation.reserved_action_points)

    def test_pre_dispatch_persist_failure_blocks_the_callback(self) -> None:
        """A journal write failure before dispatch never reaches the input callback."""

        dispatched: list[bool] = []
        with patch.object(
            DailyRunJournalStore, "prepare_intent", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                self.authority.dispatch_battle_start(
                    checkpoint=self.checkpoint,
                    dispatch=lambda: dispatched.append(True),
                    reconcile=lambda: MutationReconciliation(False, False),
                )
        self.assertEqual([], dispatched)
        self.assertIsNone(
            self.store.load(
                game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
            )
        )

    def test_dispatch_exception_consumes_attempt_and_refuses_replay(self) -> None:
        """Timeout mid-dispatch leaves a durable consumed attempt; no second send."""

        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1
            raise TimeoutError("battle start dispatch timed out")

        with self.assertRaises(TimeoutError):
            self.authority.dispatch_battle_start(
                checkpoint=self.checkpoint,
                dispatch=dispatch,
                reconcile=lambda: MutationReconciliation(False, False),
            )
        reloaded = self._reload()
        self.assertEqual(MutationIntentState.DISPATCHED, reloaded.mutation_intents[0].state)

        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, reloaded, dispatch)
        forged_low_cost = replace(
            self.authority.operation(),
            operation_id="forged-start-2",
            target={
                "context": Match3Context.CAMPAIGN.value,
                "chapter_number": 1,
                "stage_number": 1,
                "match3_mode": Match3Mode.SOLVER.value,
                "campaign_mode": CampaignMode.STANDARD.value,
            },
            action_point_reservation=ActionPointReservation(reserved_action_points=1),
        )
        foreign_scope = _authority(self.store)
        for caller_supplied in (forged_low_cost, foreign_scope, "forged"):
            with self.subTest(caller_supplied=type(caller_supplied).__name__):
                with self.assertRaises((TypeError, PermissionError)):
                    self.authority.mutation_boundary.dispatch_campaign_battle_start(
                        checkpoint=reloaded,
                        authority=caller_supplied,
                        dispatch=dispatch,
                        reconcile=lambda: MutationReconciliation(False, False),
                    )
        self.assertEqual(1, dispatch_count)

    def test_unproven_reconciliation_stays_pending_and_refuses_replay(self) -> None:
        """A missing receipt marks the attempt pending; replay stays refused."""

        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        result = self._dispatch(self.authority, self.checkpoint, dispatch)

        self.assertTrue(result.pending_clarification)
        self.assertFalse(result.retry_permitted)
        self.assertEqual(
            MutationIntentState.RECONCILED, result.checkpoint.mutation_intents[0].state
        )
        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, self._reload(), dispatch)
        self.assertEqual(1, dispatch_count)

    def test_committed_attempt_is_consumed_and_never_replays(self) -> None:
        """A proven attempt stays terminal; replay is refused without dispatching."""

        dispatch_count = 0

        def dispatch() -> None:
            nonlocal dispatch_count
            dispatch_count += 1

        result = self.authority.dispatch_battle_start(
            checkpoint=self.checkpoint,
            dispatch=dispatch,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )
        self.assertTrue(result.committed)
        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, self._reload(), dispatch)
        self.assertEqual(1, dispatch_count)

    def test_reconciliation_reobserves_but_never_resends(self) -> None:
        """The reconciliation path commits proven outcomes without another dispatch."""

        self._dispatch(self.authority, self.checkpoint, lambda: None)

        result = self.authority.reconcile_battle_start(
            checkpoint=self._reload(),
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )

        self.assertTrue(result.committed)
        self.assertFalse(result.retry_permitted)
        self.assertEqual(
            MutationIntentState.COMMITTED, result.checkpoint.mutation_intents[0].state
        )

    def test_no_spend_releases_reservation_but_attempt_stays_consumed(self) -> None:
        """Authoritative no-spend frees only the AP reservation, never the attempt."""

        result = self.authority.dispatch_battle_start(
            checkpoint=self.checkpoint,
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=False,
                original_precondition_proven=False,
                authoritative_no_spend=True,
            ),
        )

        self.assertTrue(result.pending_clarification)
        self.assertFalse(result.retry_permitted)
        intent = result.checkpoint.mutation_intents[0]
        self.assertEqual(MutationIntentState.RECONCILED, intent.state)
        self.assertTrue(intent.action_point_reservation.released)
        persisted = self._reload().mutation_intents[0]
        self.assertTrue(persisted.action_point_reservation.released)
        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, self._reload(), lambda: None)

    def test_prepared_attempt_is_consumed_and_retry_never_replays(self) -> None:
        """A crash between prepare and dispatch leaves a consumed attempt.

        The Campaign-facing result clamps the generic ``retry_permitted`` flag:
        a journaled attempt never reports a further dispatch permission.
        """

        checkpoint = self.store.prepare_intent(
            self.checkpoint, _campaign_intent(self.authority, MutationIntentState.PREPARED)
        )

        result = self.authority.reconcile_battle_start(
            checkpoint=checkpoint,
            reconcile=lambda: MutationReconciliation(False, False),
        )

        self.assertFalse(result.retry_permitted)
        dispatched: list[bool] = []
        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, checkpoint, lambda: dispatched.append(True))
        self.assertEqual([], dispatched)

    def test_reobserved_precondition_after_dispatch_grants_no_retry(self) -> None:
        """A DISPATCHED attempt whose precondition is reobserved cannot send again.

        The generic dispatcher reports ``retry_permitted`` when the original
        precondition is reobserved; the Campaign-facing result never exposes a
        new dispatch permission, the callback count stays at one, and neither
        a restart nor a new invocation can replay the consumed attempt.
        """

        dispatch_calls: list[bool] = []

        def dispatch() -> None:
            dispatch_calls.append(True)
            raise TimeoutError("battle start dispatch timed out")

        with self.assertRaises(TimeoutError):
            self.authority.dispatch_battle_start(
                checkpoint=self.checkpoint,
                dispatch=dispatch,
                reconcile=lambda: MutationReconciliation(False, False),
            )
        reloaded = self._reload()
        self.assertEqual(MutationIntentState.DISPATCHED, reloaded.mutation_intents[0].state)

        result = self.authority.reconcile_battle_start(
            checkpoint=reloaded,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=False, original_precondition_proven=True
            ),
        )

        self.assertTrue(result.pending_clarification)
        self.assertFalse(result.retry_permitted)
        self.assertEqual(1, len(dispatch_calls))
        with self.assertRaises(PermissionError):
            self._dispatch(self.authority, self._reload(), dispatch)
        restarted = _authority(self.store, invocation_id=self.authority.invocation_id)
        with self.assertRaises(PermissionError):
            self._dispatch(restarted, self._reload(), dispatch)
        with self.assertRaises(RuntimeError):
            self._dispatch(_authority(self.store), self._reload(), dispatch)
        self.assertEqual(1, len(dispatch_calls))

    def test_consumed_attempt_survives_restart_and_new_reset(self) -> None:
        """A fresh store and a later reset cannot evade the journaled attempt."""

        self._dispatch(self.authority, self.checkpoint, lambda: None)

        restarted_store = DailyRunJournalStore(Path(self.temporary_directory.name))
        restarted = _authority(
            restarted_store,
            game_reset_id=_LATER_RESET_ID,
            invocation_id=self.authority.invocation_id,
        )
        with self.assertRaises(PermissionError):
            self._dispatch(restarted, _checkpoint(_LATER_RESET_ID), lambda: None)

    def test_unresolved_prior_attempt_blocks_a_new_invocation(self) -> None:
        """A new invocation cannot start while another attempt is unresolved."""

        self._dispatch(self.authority, self.checkpoint, lambda: None)

        with self.assertRaises(RuntimeError):
            self._dispatch(_authority(self.store), self._reload(), lambda: None)

    def test_committed_attempt_allows_a_new_invocation(self) -> None:
        """A committed prior attempt does not block a separately authorized invocation."""

        result = self.authority.dispatch_battle_start(
            checkpoint=self.checkpoint,
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )
        self.assertTrue(result.committed)

        follow_up = _authority(self.store)
        result = follow_up.dispatch_battle_start(
            checkpoint=result.checkpoint,
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )

        self.assertTrue(result.committed)
        self.assertEqual(2, len(result.checkpoint.mutation_intents))

    def test_unresolved_same_checkpoint_mutation_blocks_dispatch(self) -> None:
        """Any unresolved journaled mutation in the checkpoint blocks the start."""

        checkpoint = self.store.prepare_intent(
            self.checkpoint,
            MutationIntent(
                operation_id="arena-1",
                quest_id=DailyQuestId.HERO_ARENA,
                state=MutationIntentState.PREPARED,
                expected_precondition="free attempt visible",
                expected_postcondition="Daily progress increased",
            ),
        )

        with self.assertRaises(RuntimeError):
            self._dispatch(self.authority, checkpoint, lambda: None)

    def test_unresolved_prior_workshop_operation_blocks_dispatch(self) -> None:
        """An unresolved Workshop operation from an earlier reset blocks the start."""

        older = self.store.prepare_intent(
            _checkpoint("pnc-reset-2026-09-03-00"),
            MutationIntent(
                operation_id="workshop-op-1",
                quest_id=None,
                state=MutationIntentState.PREPARED,
                expected_precondition="workshop control visible",
                expected_postcondition="workshop receipt observed",
                action_kind=WorkshopIntentKind.PRODUCE.value,
                target={"step": "produce"},
                invocation_id="pet-workshop-run-1",
            ),
        )
        older = self.store.transition_intent(
            older, "workshop-op-1", MutationIntentState.DISPATCHED
        )
        self.assertIsNotNone(older)

        with self.assertRaises(RuntimeError):
            self._dispatch(self.authority, self.checkpoint, lambda: None)


class CampaignBattleStartJournalTests(unittest.TestCase):
    """Durable serialization, decode, and fail-closed store semantics."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.store = DailyRunJournalStore(Path(self.temporary_directory.name))
        self.authority = _authority(self.store)

    def _journal_payload(self, mutation_intents: list[dict[str, object]], **overrides):
        """One version-two journal payload for direct on-disk fixtures."""

        payload: dict[str, object] = {
            "schema_version": 2,
            "maintenance_date": _MAINTENANCE_DATE.isoformat(),
            "game_reset_id": _RESET_ID,
            "account_id": _ACCOUNT_ID,
            "castle": {
                "kingdom": _CASTLE.kingdom,
                "castle_name": _CASTLE.castle_name,
                "castle_level": _CASTLE.castle_level,
            },
            "current_quest_id": None,
            "completed_quest_ids": [],
            "mutation_intents": mutation_intents,
            "consumed_recovery_stages": [],
            "last_typed_screen": None,
            "workshop_invocations": [],
        }
        payload.update(overrides)
        return payload

    def _write_journal(self, payload: dict, game_reset_id: str = _RESET_ID) -> Path:
        path = self.store.checkpoint_path(
            game_reset_id=game_reset_id, account_id=_ACCOUNT_ID, castle=_CASTLE
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_reservation_round_trips_through_the_journal(self) -> None:
        """The AP reservation persists and decodes exactly."""

        authority = self.authority
        authority.dispatch_battle_start(
            checkpoint=_checkpoint(),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )

        loaded = self.store.load(
            game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
        )
        reservation = loaded.mutation_intents[0].action_point_reservation
        self.assertEqual(12, reservation.reserved_action_points)
        self.assertFalse(reservation.released)
        raw = json.loads(
            self.store.checkpoint_path(
                game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"reserved_action_points": 12, "released": False},
            raw["mutation_intents"][0]["action_point_reservation"],
        )

    def test_non_campaign_serialization_is_unchanged(self) -> None:
        """Daily, building, and Workshop intents keep their exact prior shape."""

        checkpoint = self.store.prepare_intent(
            _checkpoint(),
            MutationIntent(
                operation_id="arena-1",
                quest_id=DailyQuestId.HERO_ARENA,
                state=MutationIntentState.PREPARED,
                expected_precondition="free attempt visible",
                expected_postcondition="Daily progress increased",
            ),
        )
        checkpoint = self.store.prepare_intent(
            checkpoint,
            MutationIntent(
                operation_id="workshop-op-1",
                quest_id=None,
                state=MutationIntentState.PREPARED,
                expected_precondition="workshop control visible",
                expected_postcondition="workshop receipt observed",
                action_kind=WorkshopIntentKind.PRODUCE.value,
                target={"step": "produce"},
                invocation_id="pet-workshop-run-1",
            ),
        )
        checkpoint = self.store.transition_intent(
            checkpoint, "workshop-op-1", MutationIntentState.DISPATCHED
        )
        self.assertIsNotNone(checkpoint)

        raw = json.loads(
            self.store.checkpoint_path(
                game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
            ).read_text(encoding="utf-8")
        )
        for intent in raw["mutation_intents"]:
            self.assertNotIn("action_point_reservation", intent)

    def test_legacy_journal_without_new_fields_still_decodes(self) -> None:
        """A pre-M1 record lacking reservation and invocation keys loads cleanly."""

        legacy_intent = {
            "operation_id": "arena-1",
            "quest_id": DailyQuestId.HERO_ARENA.value,
            "state": "committed",
            "expected_precondition": "free attempt visible",
            "expected_postcondition": "Daily progress increased",
            "diamond_budget": 0,
            "diamonds_spent": 0,
            "metadata": {},
            "action_kind": None,
            "target": None,
        }
        self._write_journal(
            self._journal_payload([legacy_intent], schema_version=1)
        )

        loaded = self.store.load(
            game_reset_id=_RESET_ID, account_id=_ACCOUNT_ID, castle=_CASTLE
        )
        self.assertEqual(1, len(loaded.mutation_intents))
        self.assertIsNone(loaded.mutation_intents[0].invocation_id)
        self.assertIsNone(loaded.mutation_intents[0].action_point_reservation)
        self.assertEqual(
            (),
            self.store.find_campaign_battle_start_attempts(
                account_id=_ACCOUNT_ID, castle=_CASTLE, invocation_id="inv-1"
            ),
        )

    def test_malformed_campaign_record_fails_closed(self) -> None:
        """A campaign intent missing its reservation is never silently skipped."""

        self._write_journal(
            self._journal_payload(
                [
                    {
                        "operation_id": "op-1",
                        "quest_id": None,
                        "state": "dispatched",
                        "expected_precondition": "pre",
                        "expected_postcondition": "post",
                        "diamond_budget": 0,
                        "diamonds_spent": 0,
                        "metadata": {},
                        "action_kind": Match3MutationKind.CAMPAIGN_BATTLE_START.value,
                        "target": {"chapter_number": 6, "stage_number": 4},
                        "invocation_id": "inv-1",
                    }
                ]
            )
        )

        with self.assertRaises(ConfigurationError):
            self.store.find_campaign_battle_start_attempts(
                account_id=_ACCOUNT_ID, castle=_CASTLE, invocation_id="inv-1"
            )

    def test_campaign_attempt_query_scopes_to_exact_identity(self) -> None:
        """Attempts only match the exact account, castle, and invocation."""

        self.authority.dispatch_battle_start(
            checkpoint=_checkpoint(),
            dispatch=lambda: None,
            reconcile=lambda: MutationReconciliation(
                postcondition_proven=True, original_precondition_proven=False
            ),
        )
        invocation_id = self.authority.invocation_id

        self.assertEqual(
            1,
            len(
                self.store.find_campaign_battle_start_attempts(
                    account_id=_ACCOUNT_ID, castle=_CASTLE, invocation_id=invocation_id
                )
            ),
        )
        self.assertEqual(
            (),
            self.store.find_campaign_battle_start_attempts(
                account_id=_ACCOUNT_ID, castle=_CASTLE, invocation_id="other-invocation"
            ),
        )
        self.assertEqual(
            (),
            self.store.find_campaign_battle_start_attempts(
                account_id="acct-2", castle=_CASTLE, invocation_id=invocation_id
            ),
        )
        self.assertEqual(
            (),
            self.store.find_campaign_battle_start_attempts(
                account_id=_ACCOUNT_ID,
                castle=CastleIdentity(kingdom="287", castle_name="Castle-B", castle_level=10),
                invocation_id=invocation_id,
            ),
        )
        attempt = self.store.find_campaign_battle_start_attempts(
            account_id=_ACCOUNT_ID, castle=_CASTLE, invocation_id=invocation_id
        )[0]
        self.assertEqual(_RESET_ID, attempt.game_reset_id)
        self.assertEqual(f"{invocation_id}-start", attempt.operation_id)


if __name__ == "__main__":
    unittest.main()
