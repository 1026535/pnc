"""Case-bound measured controls stay separate from ordinary UI admission."""

from __future__ import annotations

import logging
import time
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.core_runtime import CoreRuntime
from pnc_automation.app.automation.engine.developmental_control import (
    BodyEntryWitness,
    ConsumedCaseAttempt,
    DevelopmentalCasePurpose,
    DevelopmentalControlScope,
    MeasuredControlProof,
)
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.automation.engine.workflow_effect import WorkflowEffect
from pnc_automation.app.automation.engine.core_workflow import WorkflowEffect as WorkflowEffectAlias
from pnc_automation.app.pnc.domain.action_requests import TapPointAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectSourceKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchFailure,
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface


class DevelopmentalControlTests(unittest.TestCase):
    def test_workflow_effect_facade_is_the_neutral_enum_object(self) -> None:
        self.assertIs(WorkflowEffect, WorkflowEffectAlias)

    def setUp(self) -> None:
        source_ref = self._frame(1, 0)
        body = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING, action_point=(500, 800)),
            bounds=Bounds(450, 750, 100, 100),
            action_bounds=Bounds(495, 795, 10, 10),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": HomeCityObjectId.BANK.value},
            frame_ref=source_ref,
            source_screen=ScreenType.PNC_HOME_CITY,
        )
        source = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE, objects=(body,)),
            artifact_path=Path("body.png"), image_size=(900, 1600), frame_ref=source_ref,
        )
        body_action = TapSpatialObjectAction(
            target_point=body.action_point, expected_object=body, exact_geometry=True,
        )
        body_receipt = InputDispatchRecord(
            source_frame=source_ref,
            dispatch=TapDispatch(point=(500, 800), input_sequence=1),
            artifact_path=source.artifact_path,
            home_city=True,
        )
        self.current = make_observation(
            ScreenType.UNKNOWN,
            artifact_path=Path("menu.png"), image_size=(900, 1600),
            frame_ref=self._frame(2, 1),
        )
        self.scope = DevelopmentalControlScope(
            assignment_id="assignment", case_id="bank_menu", case_spec_ref="frozen-case",
            purpose=DevelopmentalCasePurpose.CONTROL_DISCOVERY,
            operation_id="bank_menu_discovery", released_action_id="open_bank_menu",
            control_name="task_owned_menu_button", target=HomeCityObjectId.BANK,
            home_city_slot=None,
            allowed_source_screens=frozenset({ScreenType.UNKNOWN, ScreenType.PNC_POPUP}),
            effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
            read_only=False, resource_allowance_ref=None,
            attempt=ConsumedCaseAttempt("bank_menu", "task_owned_menu_button", 1, 1, "journal:1"),
            body_entry=BodyEntryWitness("bank_menu", "bank_menu_discovery", source, body_action, body_receipt),
            input_chain=(body_receipt,), latest_input_follow_up=self.current,
        )
        self.proof = MeasuredControlProof(
            frame_ref=self.current.frame_ref, artifact_path=self.current.artifact_path,
            frame_fingerprint=self.current.frame_fingerprint, image_size=(900, 1600),
            decision=self.current.decision, screen_type=ScreenType.UNKNOWN,
            control_name="task_owned_menu_button", foreground_target=HomeCityObjectId.BANK,
            task_owned_foreground=True, visual_reason="fresh Bank menu control observed",
            intended_effect=WorkflowEffect.NONSPENDING_STATE_CHANGE,
            bounds=Bounds(300, 400, 50, 30), action_point=(325, 415),
        )
        self.session = FakeSession()
        self.session._input_sequence = 1
        self.events: list[object] = []
        self.executor = ActionExecutor(
            session=self.session, selector_registry=build_default_selector_registry(),
            stable_click_delay_ms=0, post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0, chat_post_action_observe_delay_ms=0,
            logger=logging.LoggerAdapter(logging.getLogger(__name__), {}),
            sleep=lambda _: None, input_dispatch_recorder=self.events.append,
            max_input_attempts=3, input_attempt_deadline=time.monotonic() + 60,
        )

    @staticmethod
    def _frame(capture: int, inputs: int) -> FrameRef:
        return FrameRef("session", 1, capture, inputs, datetime.now(tz=UTC))

    def test_current_task_owned_unknown_control_has_one_exact_receipt(self) -> None:
        receipt = self.executor.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertEqual([(325, 415)], self.session.taps)
        self.assertEqual([True], self.session.tap_exact_geometry)
        self.assertEqual([self.proof.bounds], self.session.tap_safe_bounds)
        self.assertEqual(2, receipt.dispatch.input_sequence)
        self.assertEqual([receipt], self.events)
        self.assertEqual(1, self.executor.input_attempts)
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertEqual(1, len(self.session.taps))

    def test_wrong_case_body_or_visual_proof_refuses_without_input(self) -> None:
        cases = (
            (replace(self.scope, case_id="other"), self.proof, self.current),
            (replace(self.scope, home_city_slot=object()), self.proof, self.current),
            (replace(self.scope, read_only=True), self.proof, self.current),
            (replace(self.scope, purpose=DevelopmentalCasePurpose.CAPTURE_ONLY), self.proof, self.current),
            (self.scope, replace(self.proof, artifact_path=Path("older.png")), self.current),
            (self.scope, replace(self.proof, action_point=(1, 1)), self.current),
            (self.scope, replace(self.proof, intended_effect=WorkflowEffect.READ_ONLY), self.current),
            (self.scope, replace(self.proof, task_owned_foreground=False), self.current),
        )
        for scope, proof, observation in cases:
            with self.subTest(scope=scope.case_id, proof=proof), self.assertRaises(SelectorResolutionError):
                self.executor.execute_developmental_control(scope, proof, observation)
        self.assertEqual([], self.session.taps)

    def test_passive_recapture_requires_new_matching_annotation_and_no_input(self) -> None:
        recapture = make_observation(
            ScreenType.UNKNOWN, artifact_path=Path("recapture.png"), image_size=(900, 1600),
            frame_ref=self._frame(3, 1),
        )
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(self.scope, self.proof, recapture)
        fresh_proof = replace(
            self.proof, frame_ref=recapture.frame_ref, artifact_path=recapture.artifact_path,
            frame_fingerprint=recapture.frame_fingerprint, decision=recapture.decision,
        )
        self.executor.execute_developmental_control(self.scope, fresh_proof, recapture)
        self.assertEqual([(325, 415)], self.session.taps)

    def test_second_control_requires_complete_input_chain_and_new_follow_up(self) -> None:
        first_control_receipt = InputDispatchRecord(
            source_frame=self.current.frame_ref,
            dispatch=TapDispatch(point=(325, 415), input_sequence=2),
            artifact_path=self.current.artifact_path,
        )
        later = make_observation(
            ScreenType.UNKNOWN, artifact_path=Path("return.png"), image_size=(900, 1600),
            frame_ref=self._frame(3, 2),
        )
        scope = replace(
            self.scope, control_name="task_owned_back", released_action_id="bank_back",
            attempt=ConsumedCaseAttempt("bank_menu", "task_owned_back", 2, 2, "journal:2"),
            input_chain=(self.scope.body_entry.receipt, first_control_receipt),
            latest_input_follow_up=later,
        )
        proof = replace(
            self.proof, frame_ref=later.frame_ref, artifact_path=later.artifact_path,
            frame_fingerprint=later.frame_fingerprint, decision=later.decision,
            control_name="task_owned_back",
        )
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(replace(scope, input_chain=scope.input_chain[:1]), proof, later)
        self.session._input_sequence = 2
        receipt = self.executor.execute_developmental_control(scope, proof, later)
        self.assertEqual(3, receipt.dispatch.input_sequence)
        self.assertEqual([(325, 415)], self.session.taps)

    def test_refused_logical_attempt_does_not_require_a_physical_receipt(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(
                self.scope, replace(self.proof, artifact_path=Path("older.png")), self.current,
            )
        self.assertEqual([], self.events)
        scope = replace(
            self.scope,
            attempt=ConsumedCaseAttempt(
                "bank_menu", "task_owned_menu_button", 2, 2, "journal:2",
            ),
        )
        receipt = self.executor.execute_developmental_control(scope, self.proof, self.current)
        self.assertEqual(2, receipt.dispatch.input_sequence)
        self.assertEqual([receipt], self.events)

    def test_unreleased_resource_effect_and_global_budget_refuse(self) -> None:
        resource_scope = replace(self.scope, effect=WorkflowEffect.RESOURCE_CHANGING)
        resource_proof = replace(self.proof, intended_effect=WorkflowEffect.RESOURCE_CHANGING)
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(resource_scope, resource_proof, self.current)
        self.executor.max_input_attempts = None
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertEqual([], self.session.taps)

    def test_uncertain_send_consumes_attempt_and_cannot_replay_frame(self) -> None:
        self.session.tap_error = RuntimeError("synthetic send uncertainty")
        with self.assertRaisesRegex(RuntimeError, "synthetic send uncertainty"):
            self.executor.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertEqual([(325, 415)], self.session.taps)
        self.assertEqual(1, self.executor.input_attempts)
        self.assertEqual(1, len(self.events))
        self.assertIsInstance(self.events[0], InputDispatchFailure)
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertEqual(1, len(self.session.taps))

    def test_ordinary_raw_point_remains_denied_on_unknown(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            self.executor.execute_action(TapPointAction(x=325, y=415), self.current)
        self.assertEqual([], self.session.taps)

    def test_runtime_wrapper_captures_one_immediate_unrecovered_follow_up(self) -> None:
        after = make_observation(
            ScreenType.PNC_POPUP, blocking_popup=True, artifact_path=Path("after.png"),
            image_size=(900, 1600), frame_ref=self._frame(3, 2),
        )
        runtime = CoreRuntime(
            runtime=None, navigation=None, artifact_directory="task", trace_path=Path("trace.jsonl"),
            _perception=None, _run_id="synthetic",
            _observed_action_executor=SimpleNamespace(action_executor=self.executor),
        )
        with patch.object(CoreRuntime, "capture_once", return_value=after) as capture:
            result = runtime.execute_developmental_control(self.scope, self.proof, self.current)
        self.assertIs(after, result.follow_up)
        self.assertEqual(2, result.receipt.dispatch.input_sequence)
        capture.assert_called_once_with("developmental_control_after_input", include_content=True)
