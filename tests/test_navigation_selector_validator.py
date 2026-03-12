"""Navigation-selector validator tests."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from pnc_automation.automation.action_executor import ActionExecutor
from pnc_automation.capture.artifact_store import ArtifactRecord
from pnc_automation.capture.screenshot_service import CapturedScreenshot
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.navigation_selector_validator import (
    NavigationSelectorValidator,
    NavigationValidationStatus,
    build_navigation_validation_cases,
    match_reviewed_navigation_outcome,
)
from pnc_automation.vision.observation_builder import CapturedObservation
from pnc_automation.vision.selector_interaction_kind import SelectorInteractionKind
from pnc_automation.vision.selectors import ClickDefinition, ClickOutcome, DetectionKind, SelectorDefinition, SelectorRegistry, SelectorStatus
from tests.test_support import FakeSession, build_logger, make_observation


class NavigationSelectorValidatorTests(unittest.TestCase):
    """Validates live navigation-selector report building and source preparation logic."""

    def test_build_navigation_validation_cases_emits_one_case_per_navigation_screen(self) -> None:
        """Builds one validation case per reviewed navigation host screen and skips non-navigation selectors."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    screens=(ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    click=ClickDefinition(),
                    click_outcomes=(ClickOutcome(target_screen=ScreenType.PNC_MORE_MENU),),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                    screens=(ScreenType.PNC_LOGIN,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.PLANNED,
                    interaction_kind=SelectorInteractionKind.ACTION,
                    click=None,
                ),
            )
        )

        cases = build_navigation_validation_cases(registry)

        self.assertEqual(
            [(case.selector_id, case.source_screen) for case in cases],
            [
                (UiElementId.PNC_BOTTOM_NAV_MORE, ScreenType.PNC_HOME_CITY),
                (UiElementId.PNC_BOTTOM_NAV_MORE, ScreenType.PNC_MORE_MENU),
            ],
        )

    def test_match_reviewed_navigation_outcome_reports_missing_verification_selectors(self) -> None:
        """Rejects destinations that hit the target screen but do not expose the reviewed verification selectors."""

        destination = make_observation(
            ScreenType.PNC_BAG,
            visible_ids=(UiElementId.PNC_BAG_MAIN_TAB_BAG,),
        )
        matched_outcome, missing = match_reviewed_navigation_outcome(
            destination,
            (
                ClickOutcome(
                    target_screen=ScreenType.PNC_BAG,
                    verification_selectors=(UiElementId.PNC_BAG_MAIN_TAB_BAG, UiElementId.PNC_BAG_USE_BUTTON),
                ),
            ),
        )

        self.assertIsNone(matched_outcome)
        self.assertEqual(missing, (UiElementId.PNC_BAG_USE_BUTTON,))

    def test_validator_prepares_more_menu_substate_before_clicking_manage_char(self) -> None:
        """Uses the reviewed More-menu preparation step before validating selectors hidden behind Settings."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_MORE_MANAGE_CHAR,
                    screens=(ScreenType.PNC_MORE_MENU,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    click=ClickDefinition(),
                    click_outcomes=(
                        ClickOutcome(
                            target_screen=ScreenType.PNC_CASTLE_SELECTION,
                            verification_selectors=(UiElementId.PNC_CASTLE_LIST_ENTRY,),
                        ),
                    ),
                ),
            )
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_HOME_CITY,
                        visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE,),
                        artifact_path=Path("home.png"),
                    ),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_MORE_MENU,
                        visible_ids=(UiElementId.PNC_BOTTOM_NAV_MORE, UiElementId.PNC_MORE_SETTINGS),
                        artifact_path=Path("more_root.png"),
                    ),
                    label="more_root",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_MORE_MENU,
                        visible_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,),
                        artifact_path=Path("more_settings.png"),
                    ),
                    label="more_settings",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_CASTLE_SELECTION,
                        visible_ids=(UiElementId.PNC_CASTLE_LIST_ENTRY,),
                        artifact_path=Path("castle_selection.png"),
                    ),
                    label="castle_selection",
                ),
            ]
        )
        session = FakeSession()
        validator = NavigationSelectorValidator(
            selector_registry=registry,
            observation_service=capture_service,
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            screen_flows=ScreenFlowPlanner(),
            logger=build_logger(),
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_MORE_MANAGE_CHAR,))

        self.assertEqual(report.passed_count, 1)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.results[0].status, NavigationValidationStatus.PASSED)
        self.assertEqual(
            session.taps,
            [
                (5, 5),
                (20, 20),
                (5, 5),
            ],
        )

    def test_validator_waits_for_a_delayed_destination_before_failing(self) -> None:
        """Allows one reviewed navigation to settle across follow-up observations after a transient loading frame."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    click=ClickDefinition(),
                    click_outcomes=(
                        ClickOutcome(
                            target_screen=ScreenType.PNC_WORLD_MAP,
                            verification_selectors=(UiElementId.PNC_WORLD_HOME_NAV,),
                        ),
                    ),
                ),
            )
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_HOME_CITY,
                        visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,),
                        artifact_path=Path("home.png"),
                    ),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.UNKNOWN,
                        artifact_path=Path("loading.png"),
                    ),
                    label="loading",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_WORLD_MAP,
                        visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
                        artifact_path=Path("world.png"),
                    ),
                    label="world",
                ),
            ]
        )
        session = FakeSession()
        validator = NavigationSelectorValidator(
            selector_registry=registry,
            observation_service=capture_service,
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            screen_flows=ScreenFlowPlanner(),
            logger=build_logger(),
            sleep=lambda _: None,
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        self.assertEqual(report.passed_count, 1)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.results[0].destination_screen, ScreenType.PNC_WORLD_MAP)
        self.assertEqual(session.taps, [(5, 5)])
        self.assertIn("navigation_validation_1_settle_1", capture_service.labels)

    def test_validator_closes_a_blocking_popup_before_matching_the_reviewed_destination(self) -> None:
        """Dismisses one blocking popup encountered after the click and then validates the destination contract."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    detection_kind=DetectionKind.PLANNED,
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    click=ClickDefinition(),
                    click_outcomes=(
                        ClickOutcome(
                            target_screen=ScreenType.PNC_WORLD_MAP,
                            verification_selectors=(UiElementId.PNC_WORLD_HOME_NAV,),
                        ),
                    ),
                ),
            )
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_HOME_CITY,
                        visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,),
                        artifact_path=Path("home.png"),
                    ),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_POPUP,
                        visible_ids=(UiElementId.PNC_POPUP_CLOSE_BUTTON,),
                        blocking_popup=True,
                        artifact_path=Path("popup.png"),
                    ),
                    label="popup",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_WORLD_MAP,
                        visible_ids=(UiElementId.PNC_WORLD_HOME_NAV,),
                        artifact_path=Path("world.png"),
                    ),
                    label="world",
                ),
            ]
        )
        session = FakeSession()
        validator = NavigationSelectorValidator(
            selector_registry=registry,
            observation_service=capture_service,
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            screen_flows=ScreenFlowPlanner(),
            logger=build_logger(),
            sleep=lambda _: None,
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        self.assertEqual(report.passed_count, 1)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(
            session.taps,
            [
                (5, 5),
                (5, 5),
            ],
        )
        self.assertEqual(report.results[0].destination_screen, ScreenType.PNC_WORLD_MAP)


@dataclass
class _FakeCapturedObservationService:
    """Returns a pre-seeded queue of captured observations for validator tests."""

    captures: list[CapturedObservation]
    labels: list[str] = field(default_factory=list)

    def capture_observation(self, label: str) -> CapturedObservation:
        """Returns the next queued captured observation."""

        self.labels.append(label)
        if not self.captures:
            raise AssertionError(f"No captured observation queued for label '{label}'.")
        return self.captures.pop(0)


def _make_captured_observation(observation: object, *, label: str) -> CapturedObservation:
    """Builds one artifact-backed captured observation for validator tests."""

    screenshot = CapturedScreenshot(
        artifact=ArtifactRecord(
            path=Path(f"{label}.png"),
            label=label,
            captured_at=datetime.now(tz=UTC),
            size_bytes=0,
            sha256="0" * 64,
        ),
        image=Image.new("RGB", (10, 10), (0, 0, 0)),
        image_format="PNG",
    )
    return CapturedObservation(screenshot=screenshot, observation=observation)


if __name__ == "__main__":
    unittest.main()
