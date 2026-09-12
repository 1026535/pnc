"""Observed action popup recovery."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


class ObservedActionPopupRecoveryTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves observed action popup recovery."""

    def test_observed_action_executor_retries_geometry_navigation_taps_once_through_ocr(self) -> None:
        """Promotes one settled geometry miss to an OCR-backed retry using the narrow follow-up requests."""

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
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.GEOMETRY},
                ),
                make_observation(
                    ScreenType.PNC_HOME_CITY,
                    visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                    source_kinds={UiElementId.PNC_BOTTOM_NAV_MORE: VisibleElementSourceKind.OCR},
                ),
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(fake_observer.requests[0], ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes))
        self.assertEqual(fake_observer.requests[1], ObservationRequest.source_screen_retry(ScreenType.PNC_HOME_CITY))
        self.assertEqual(fake_observer.requests[2], ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes))
        self.assertTrue(execution.selector_interactions[0].fallback_attempted)
        self.assertTrue(execution.selector_interactions[0].fallback_used)
        self.assertEqual(execution.selector_interactions[0].fallback_source_kind, VisibleElementSourceKind.OCR)

    def test_observed_action_executor_settles_transitions_to_success_without_ocr_retry(self) -> None:
        """Waits through loading transitions before deciding whether the primary tap actually missed."""

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
                make_observation(
                    ScreenType.PNC_MORE_MENU,
                    visible_ids=(UiElementId.PNC_MORE_SETTINGS,),
                ),
            ),
        )

        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertEqual(len(fake_observer.requests), 2)
        self.assertTrue(all(request == ObservationRequest.navigation_follow_up(registry.selectors[0].click_outcomes) for request in fake_observer.requests))
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_stops_on_popup_without_ocr_retry(self) -> None:
        """Returns popup states to the shared popup path instead of double-tapping during recovery."""

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
                make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    blocking_popup=True,
                    frame_fingerprint="navigation-popup",
                ),
                make_observation(ScreenType.PNC_MORE_MENU, visible_ids=(UiElementId.PNC_MORE_SETTINGS,)),
            ),
        )

        # One navigation tap plus one safe popup-close tap; the original
        # navigation action is not retried after interruption recovery.
        self.assertEqual(fake_session.taps, [(5, 5), (5, 5)])
        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_MORE_MENU)
        self.assertFalse(execution.selector_interactions[0].fallback_attempted)

    def test_observed_action_executor_recovers_known_disconnect_and_valiant_popups_once(self) -> None:
        """Known OCR-backed popups use one explicit close tap and never Android Back."""

        for popup_name in ("disconnect", "valiant_conquest"):
            with self.subTest(popup=popup_name):
                popup = make_observation(
                    ScreenType.PNC_POPUP,
                    visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                    visible_texts={UiElementId.PNC_POPUP_CLOSE_BUTTON: "Confirm" if popup_name == "disconnect" else None},
                    blocking_popup=True,
                    frame_fingerprint=f"{popup_name}-popup",
                )
                home = make_observation(ScreenType.PNC_HOME_CITY)
                fake_observer = FakeObservationService(observations=[home])
                fake_session = FakeSession()
                executor = _make_observed_action_executor(fake_session)

                recovered = executor.recover_interruption_if_required(
                    popup,
                    label_prefix=f"known_{popup_name}",
                    observe=fake_observer.observe,
                )

                self.assertIsNotNone(recovered)
                assert recovered is not None
                self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
                self.assertEqual([(5, 5)], fake_session.taps)
                self.assertEqual([], fake_session.key_events)
                self.assertEqual(0, fake_session.launches)
                self.assertEqual([ObservationRequest.full_runtime_default()], fake_observer.requests)
