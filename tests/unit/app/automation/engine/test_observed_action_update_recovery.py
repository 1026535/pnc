"""Observed action update recovery."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutionPolicy,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selector_interaction_kind import SelectorInteractionKind

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class ObservedActionUpdateRecoveryTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves observed action update recovery."""

    def test_observed_action_executor_recovers_initial_required_update_without_running_planned_action(self) -> None:
        """Confirms an initial update once, waits through loading, and skips the stale action plan."""

        before = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_HOME_BUILD_BUTTON,
                    reason="stale_pre_update_plan",
                ),
            ),
            before,
            observe=fake_observer.observe,
        )

        self.assertTrue(execution.update_recovered)
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(
            fake_observer.requests,
            [
                ObservationRequest.full_runtime_default(),
                ObservationRequest.full_runtime_default(),
            ],
        )

    def test_observed_action_executor_relaunches_once_when_update_returns_to_android_home(self) -> None:
        """Relaunches P&C once when the installer returns to Android Home before game loading."""

        before = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.ANDROID_HOME),
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        execution = executor.execute_actions((), before, observe=fake_observer.observe)

        self.assertTrue(execution.update_recovered)
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(fake_session.launches, 1)

    def test_observed_action_executor_closes_post_update_offer_before_home(self) -> None:
        """Dismisses a startup offer only through its typed close control while waiting for Home."""

        before = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_LOADING),
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                    frame_fingerprint="post-update-offer",
                ),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        execution = executor.execute_actions((), before, observe=fake_observer.observe)

        self.assertTrue(execution.update_recovered)
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])

    def test_observed_action_executor_never_closes_same_post_update_popup_twice(self) -> None:
        """Fails closed when a post-update popup survives its single safe close tap."""

        before = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        offer = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="same-post-update-offer",
        )
        fake_observer = FakeObservationService(observations=[offer, offer])
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        with self.assertRaisesRegex(SelectorResolutionError, "remained after"):
            executor.execute_actions((), before, observe=fake_observer.observe)

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])

    def test_observed_action_executor_recovers_update_before_follow_up_validation(self) -> None:
        """Runs update recovery before rejecting a normal action's interrupted follow-up."""

        registry = self._make_selector_registry(interaction_kind=SelectorInteractionKind.ACTION)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
                    blocking_popup=True,
                ),
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_HOME_CITY),
            ]
        )
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session, registry=registry)

        execution = executor.execute_actions(
            (
                TapAction(
                    selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    reason="interrupted_action",
                    observe_after=True,
                ),
            ),
            before,
            observe=fake_observer.observe,
        )

        self.assertTrue(execution.update_recovered)
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])

    def test_observed_action_executor_bounds_required_update_wait(self) -> None:
        """Fails with the freshest evidence when the update exceeds its configured wait budget."""

        before = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        fake_observer = FakeObservationService(
            observations=[
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_LOADING, artifact_path=Path("still_loading.png")),
            ]
        )
        fake_session = FakeSession()
        executor = _make_observed_action_executor(
            fake_session,
            policy=ObservedActionExecutionPolicy(
                update_poll_interval_seconds=1,
                update_max_wait_seconds=2,
            ),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "ten-minute recovery budget") as error_context:
            executor.execute_actions((), before, observe=fake_observer.observe)

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(error_context.exception.details["artifact_path"], "still_loading.png")
