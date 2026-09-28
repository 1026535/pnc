"""Observed action popup recovery."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupDismissCandidate,
    PopupEvidenceKind,
    PopupOverlayObservation,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)
from tests.support.automation.engine.make_observed_action_executor import (
    _make_observed_action_executor,
)


def _join_landing_overlay() -> PopupOverlayObservation:
    """The typed overlay the reviewed alliance_join_landing profile publishes."""

    return PopupOverlayObservation(
        image_size=(540, 960),
        layout_id="alliance_join_landing",
        candidates=(
            PopupDismissCandidate(
                control_kind=PopupControlKind.BACKGROUND_DISMISS,
                bounds=Bounds(30, 830, 140, 70),
                action_point=(100, 865),
                confidence=1.0,
                evidence_kind=PopupEvidenceKind.GEOMETRY,
                reason="visual_anchor:alliance_join_landing",
            ),
        ),
        confidence=1.0,
        evidence_kind=PopupEvidenceKind.KNOWN_LAYOUT,
        reason="visual_anchor:alliance_join_landing",
    )


class ObservedActionPopupRecoveryTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves observed action popup recovery."""

    def test_chest_preview_remains_inspectable_until_explicit_close(self) -> None:
        """Normal runtime recovery must leave an intentionally opened preview alone."""
        preview = make_observation(
            ScreenType.PNC_BAG_CHEST_PREVIEW,
            visible_ids=(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE,),
        )
        fake_observer = FakeObservationService(observations=[])
        fake_session = FakeSession()
        executor = _make_observed_action_executor(fake_session)

        result = executor.recover_interruption_if_required(
            preview, label_prefix="inspect_chest_preview", observe=fake_observer.observe,
        )

        self.assertIsNone(result)
        self.assertEqual([], fake_session.taps)
        self.assertEqual([], fake_session.key_events)
        self.assertEqual([], fake_observer.requests)

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

    def test_expected_destination_is_preserved_while_unrelated_popup_recovers(self) -> None:
        """A follow-up screen the action expects is a destination, not an interruption."""

        registry = self._make_selector_registry(
            selector_id=UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
            target_screen=ScreenType.PNC_ALLIANCE_JOIN,
            verification_selectors=(),
        )
        # blocking_popup marks a destination screen that also carries
        # interruption evidence; expected-screen scoping must still preserve it.
        # The published mask element and typed overlay make this the production
        # landing shape — the expected gate, not dismissal absence, preserves it.
        landing = make_observation(
            ScreenType.PNC_ALLIANCE_JOIN,
            visible_ids=(UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK,),
            source_kinds={UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK: VisibleElementSourceKind.GEOMETRY},
            popup_overlay=_join_landing_overlay(),
            blocking_popup=True,
            frame_fingerprint="alliance-join-landing",
        )
        before = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_BOTTOM_NAV_ALLIANCE,),
        )
        execution, fake_observer, fake_session = self._execute_observed_tap(
            registry=registry,
            before=before,
            queued_observations=(landing,),
            selector_id=UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
        )

        self.assertEqual(execution.observation.screen_type, ScreenType.PNC_ALLIANCE_JOIN)
        self.assertEqual(fake_session.taps, [(5, 5)])
        self.assertEqual([], fake_session.key_events)

        unrelated = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
            blocking_popup=True,
            frame_fingerprint="unrelated-popup",
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        popup_observer = FakeObservationService(observations=[home])
        popup_session = FakeSession()
        executor = _make_observed_action_executor(popup_session)

        recovered = executor.recover_interruption_if_required(
            unrelated,
            label_prefix="unrelated_popup",
            observe=popup_observer.observe,
            expected_screens=frozenset({ScreenType.PNC_ALLIANCE_JOIN}),
        )

        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(ScreenType.PNC_HOME_CITY, recovered.screen_type)
        self.assertEqual([(5, 5)], popup_session.taps)

        # The same landing screen, when it is not an expected destination,
        # dismisses through its reviewed mask region: UnionGuide's embedded
        # CommonModelWin binds ScreenShotMask to OnBgClickHandler ->
        # BackToLastWindow -> CloseWin (isClickBgClose defaults true). The
        # stray landing stays CLEAR yet recovers because the mask selector is a
        # safe transient selector. Join/Create remain unowned and untouched.
        stray_session = FakeSession()
        stray_executor = _make_observed_action_executor(stray_session)
        stray = make_observation(
            ScreenType.PNC_ALLIANCE_JOIN,
            visible_ids=(UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK,),
            source_kinds={UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK: VisibleElementSourceKind.GEOMETRY},
            popup_overlay=_join_landing_overlay(),
            frame_fingerprint="stray-join-landing",
        )
        stray_home = make_observation(ScreenType.PNC_HOME_CITY)
        stray_observer = FakeObservationService(observations=[stray_home])

        stray_recovered = stray_executor.recover_interruption_if_required(
            stray,
            label_prefix="stray_join_landing",
            observe=stray_observer.observe,
            expected_screens=frozenset({ScreenType.PNC_HOME_CITY}),
        )

        self.assertIsNotNone(stray_recovered)
        assert stray_recovered is not None
        self.assertEqual(ScreenType.PNC_HOME_CITY, stray_recovered.screen_type)
        self.assertEqual([(100, 865)], stray_session.taps)
        self.assertEqual([], stray_session.key_events)

        # Without the published dismissal element the same landing fails closed:
        # a blocking observation errors, and a clear OCR-only landing (profile
        # anchors unmatched, so the reviewed mask geometry is not owned) is
        # preserved untouched rather than guessed at.
        no_element_session = FakeSession()
        no_element_executor = _make_observed_action_executor(no_element_session)
        no_element = make_observation(
            ScreenType.PNC_ALLIANCE_JOIN,
            blocking_popup=True,
            frame_fingerprint="stray-join-landing-no-element",
        )
        with self.assertRaises(SelectorResolutionError):
            no_element_executor.recover_interruption_if_required(
                no_element,
                label_prefix="stray_join_landing_no_element",
                observe=stray_observer.observe,
                expected_screens=frozenset({ScreenType.PNC_HOME_CITY}),
            )
        self.assertEqual([], no_element_session.taps)
        self.assertEqual([], no_element_session.key_events)

        unqualified = make_observation(
            ScreenType.PNC_ALLIANCE_JOIN,
            frame_fingerprint="stray-join-landing-unqualified",
        )
        self.assertIsNone(
            no_element_executor.recover_interruption_if_required(
                unqualified,
                label_prefix="stray_join_landing_unqualified",
                observe=stray_observer.observe,
                expected_screens=frozenset({ScreenType.PNC_HOME_CITY}),
            )
        )
        self.assertEqual([], no_element_session.taps)
        self.assertEqual([], no_element_session.key_events)
