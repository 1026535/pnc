"""Observed action settling."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.observed_action_executor import (
    ObservedActionExecutionPolicy,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import TapAction
from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
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


class ObservedActionSettlingTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves observed action settling."""

    def test_observed_action_executor_escalates_unknown_navigation_destination_to_full_runtime_observation(self) -> None:
        """Promotes settled unknown navigation results to one broad runtime observation before returning."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.UNKNOWN),
                make_observation(ScreenType.PNC_MORE_MENU, visible_ids=(UiElementId.PNC_MORE_SETTINGS,)),
            ),
            policy=ObservedActionExecutionPolicy(max_settle_observations=0),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(
            fake_observer.requests,
            [
                ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes),
                ObservationRequest.full_runtime_default(),
            ],
        )
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_preserves_same_screen_status_banner_without_settle_retry(self) -> None:
        """Keeps a same-screen status-banner frame as the final result so tasks can surface the live rejection reason."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_STATUS_BANNER),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertTrue(execution.observation.has(UiElementId.PNC_STATUS_BANNER))
        self.assertEqual(fake_observer.labels, ["post_action_1"])
        self.assertEqual(fake_observer.requests, [ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes)])
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_preserves_unknown_status_banner_without_runtime_retry(self) -> None:
        """Keeps transient status-banner observations even when the coarse follow-up screen is still unknown."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_STATUS_BANNER,)),),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.UNKNOWN)
        self.assertTrue(execution.observation.has(UiElementId.PNC_STATUS_BANNER))
        self.assertEqual(fake_observer.labels, ["post_action_1"])
        self.assertEqual(fake_observer.requests, [ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes)])
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_skips_ocr_retry_for_non_navigation_selectors(self) -> None:
        """Keeps non-navigation taps on the low-level path even when they were geometry-backed."""

        registry = self._make_selector_registry(interaction_kind=SelectorInteractionKind.ACTION)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, _, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(make_observation(ScreenType.PNC_HOME_CITY),),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertFalse(execution.selector_interactions)

    def test_observed_action_executor_rejects_geometry_navigation_without_safe_outcomes(self) -> None:
        """Fails fast when a geometry-backed navigation selector has no reviewed safe outcome contract."""

        registry = self._make_selector_registry(safe_to_click=False)
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        fake_observer = FakeObservationService(observations=[])
        executor = _make_observed_action_executor(FakeSession(), registry=registry)

        with self.assertRaises(SelectorResolutionError):
            executor.execute_actions(
                (
                    TapAction(
                        selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
                        reason="unsafe_navigation_tap",
                        observe_after=True,
                    ),
                ),
                before,
                observe=fake_observer.observe,
            )

    def test_observed_action_executor_stops_when_settle_budget_is_exhausted(self) -> None:
        """Returns the latest transitional state without any OCR retry when settling never stabilizes."""

        registry = self._make_selector_registry()
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
            source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(
                make_observation(ScreenType.PNC_LOADING),
                make_observation(ScreenType.PNC_LOADING),
            ),
            policy=ObservedActionExecutionPolicy(max_settle_observations=1),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_LOADING)
        self.assertEqual(len(fake_observer.requests), 2)
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)
