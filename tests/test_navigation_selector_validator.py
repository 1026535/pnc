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
from pnc_automation.pnc.observation import ResolvedSelectorSource, SelectorResolutionKind
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
from pnc_automation.vision.selectors import (
    ClickDefinition,
    ClickOutcome,
    RelativeBounds,
    SelectorDefinition,
    SelectorRegistry,
    SelectorResolutionPolicy,
    SelectorResolutionStep,
    SelectorStatus,
)
from tests.test_support import FakeSession, build_logger, make_observation, make_visible


class NavigationSelectorValidatorTests(unittest.TestCase):
    """Validates live navigation-selector report building and source preparation logic."""

    def test_build_navigation_validation_cases_emits_one_case_per_navigation_screen(self) -> None:
        """Builds one validation case per reviewed navigation host screen and skips non-navigation selectors."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_BOTTOM_NAV_MORE,
                    screens=(ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU),
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(SelectorResolutionKind.PARSER_CANDIDATE),
                    click=ClickDefinition(),
                    click_outcomes=(ClickOutcome(target_screen=ScreenType.PNC_MORE_MENU),),
                ),
                SelectorDefinition(
                    id=UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                    screens=(ScreenType.PNC_LOGIN,),
                    status=SelectorStatus.PLANNED,
                    interaction_kind=SelectorInteractionKind.ACTION,
                    resolution=_resolution(SelectorResolutionKind.PARSER_CANDIDATE),
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
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(SelectorResolutionKind.PARSER_CANDIDATE),
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
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(SelectorResolutionKind.RELATIVE_BOUNDS, relative_bounds=_bounds()),
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
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(SelectorResolutionKind.RELATIVE_BOUNDS, relative_bounds=_bounds()),
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

    def test_validator_retries_once_when_geometry_source_can_re_resolve_with_stronger_step(self) -> None:
        """Retries one reviewed navigation when the first tap used geometry and a fresh observation exposes a stronger step."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(
                        SelectorResolutionKind.TEMPLATE,
                        SelectorResolutionKind.RELATIVE_BOUNDS,
                        relative_bounds=_bounds(),
                    ),
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
        fallback_source = ResolvedSelectorSource(
            resolution_kind=SelectorResolutionKind.RELATIVE_BOUNDS,
            strategy_index=1,
            strategy_label="relative_bounds",
            is_fallback=True,
        )
        stronger_source = ResolvedSelectorSource(
            resolution_kind=SelectorResolutionKind.TEMPLATE,
            strategy_index=0,
            strategy_label="template",
            is_fallback=False,
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    _observation_with_source(
                        source=fallback_source,
                        artifact_path=Path("home.png"),
                    ),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.ANDROID_HOME,
                        artifact_path=Path("geometry_miss.png"),
                    ),
                    label="geometry_miss",
                ),
                _make_captured_observation(
                    _observation_with_source(
                        source=stronger_source,
                        artifact_path=Path("stronger_source.png"),
                    ),
                    label="stronger_source",
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
            max_destination_settle_observations=1,
            sleep=lambda _: None,
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        self.assertEqual(report.passed_count, 1)
        self.assertTrue(report.results[0].retry_attempted)
        self.assertEqual(report.results[0].retry_source_artifact_path, Path("stronger_source.png"))
        self.assertEqual(report.results[0].retry_destination_artifact_path, Path("world.png"))
        self.assertEqual(session.taps, [(5, 5), (5, 5)])

    def test_validator_does_not_retry_when_first_source_was_not_geometry(self) -> None:
        """Does not perform the guarded retry for template- or parser-resolved taps."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(SelectorResolutionKind.TEMPLATE, SelectorResolutionKind.RELATIVE_BOUNDS, relative_bounds=_bounds()),
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
        template_source = ResolvedSelectorSource(
            resolution_kind=SelectorResolutionKind.TEMPLATE,
            strategy_index=0,
            strategy_label="template",
            is_fallback=False,
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    _observation_with_source(source=template_source),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(ScreenType.PNC_HOME_CITY),
                    label="miss",
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
            max_destination_settle_observations=1,
            sleep=lambda _: None,
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        self.assertEqual(report.failed_count, 1)
        self.assertFalse(report.results[0].retry_attempted)
        self.assertEqual(session.taps, [(5, 5)])

    def test_validator_stops_after_one_stronger_retry_failure(self) -> None:
        """Attempts at most one stronger retry when geometry misses and the stronger tap still fails."""

        registry = SelectorRegistry(
            selectors=(
                SelectorDefinition(
                    id=UiElementId.PNC_HOME_WORLD_SWITCH,
                    screens=(ScreenType.PNC_HOME_CITY,),
                    status=SelectorStatus.CLICK_MAPPED,
                    interaction_kind=SelectorInteractionKind.NAVIGATION,
                    resolution=_resolution(
                        SelectorResolutionKind.TEMPLATE,
                        SelectorResolutionKind.RELATIVE_BOUNDS,
                        relative_bounds=_bounds(),
                    ),
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
        fallback_source = ResolvedSelectorSource(
            resolution_kind=SelectorResolutionKind.RELATIVE_BOUNDS,
            strategy_index=1,
            strategy_label="relative_bounds",
            is_fallback=True,
        )
        stronger_source = ResolvedSelectorSource(
            resolution_kind=SelectorResolutionKind.TEMPLATE,
            strategy_index=0,
            strategy_label="template",
            is_fallback=False,
        )
        capture_service = _FakeCapturedObservationService(
            captures=[
                _make_captured_observation(
                    _observation_with_source(
                        source=fallback_source,
                        artifact_path=Path("home.png"),
                    ),
                    label="home",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.ANDROID_HOME,
                        artifact_path=Path("geometry_miss.png"),
                    ),
                    label="geometry_miss",
                ),
                _make_captured_observation(
                    _observation_with_source(
                        source=stronger_source,
                        artifact_path=Path("stronger_source.png"),
                    ),
                    label="stronger_source",
                ),
                _make_captured_observation(
                    make_observation(
                        ScreenType.PNC_HOME_CITY,
                        visible_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,),
                        artifact_path=Path("still_home.png"),
                    ),
                    label="still_home",
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
            max_destination_settle_observations=1,
            sleep=lambda _: None,
        )

        report = validator.validate(selector_ids=(UiElementId.PNC_HOME_WORLD_SWITCH,))

        self.assertEqual(report.failed_count, 1)
        self.assertTrue(report.results[0].retry_attempted)
        self.assertEqual(report.results[0].retry_source_artifact_path, Path("stronger_source.png"))
        self.assertEqual(report.results[0].retry_destination_artifact_path, Path("still_home.png"))
        self.assertEqual(session.taps, [(5, 5), (5, 5)])


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


def _resolution(
    *kinds: SelectorResolutionKind,
    relative_bounds: RelativeBounds | None = None,
) -> SelectorResolutionPolicy:
    """Builds one typed selector-resolution policy for validator fixtures."""

    steps: list[SelectorResolutionStep] = []
    for kind in kinds:
        if kind == SelectorResolutionKind.RELATIVE_BOUNDS:
            steps.append(
                SelectorResolutionStep(
                    kind=kind,
                    relative_bounds=relative_bounds if relative_bounds is not None else _bounds(),
                )
            )
            continue
        steps.append(
            SelectorResolutionStep(
                kind=kind,
                template_path=Path("synthetic.png") if kind == SelectorResolutionKind.TEMPLATE else None,
            )
        )
    return SelectorResolutionPolicy(steps=tuple(steps))


def _bounds() -> RelativeBounds:
    """Builds one deterministic geometry fallback for validator fixtures."""

    return RelativeBounds(
        x_ratio=0.1,
        y_ratio=0.1,
        width_ratio=0.2,
        height_ratio=0.2,
    )


def _observation_with_source(
    *,
    source: ResolvedSelectorSource,
    artifact_path: Path | None = None,
) -> object:
    """Builds one observation whose selector carries explicit resolution provenance."""

    observation = make_observation(
        ScreenType.PNC_HOME_CITY,
        artifact_path=artifact_path,
    )
    visible_elements = dict(observation.visible_elements)
    visible_elements[UiElementId.PNC_HOME_WORLD_SWITCH] = make_visible(
        UiElementId.PNC_HOME_WORLD_SWITCH,
        source=source,
    )
    return observation.__class__(
        screen_type=observation.screen_type,
        visible_elements=visible_elements,
        list_entries=observation.list_entries,
        artifact_path=observation.artifact_path,
        image_size=observation.image_size,
        captured_at=observation.captured_at,
        blocking_popup=observation.blocking_popup,
        current_castle=observation.current_castle,
        current_pnc_account_id=observation.current_pnc_account_id,
        verified_pnc_account_id=observation.verified_pnc_account_id,
        castle_roster_snapshot=observation.castle_roster_snapshot,
        available_march_slots=observation.available_march_slots,
    )


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
