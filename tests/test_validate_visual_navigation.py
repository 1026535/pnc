"""The live proof must reject resource spending and target changes before execution."""

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import tools.validate_navigation_selectors as validate_navigation_selectors

from pnc_automation.app.pnc.domain.action_requests import (
    InputTextAction, KeyEventAction, TapAction, TapListEntryAction,
    TapPointAction, WaitAction,
)
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    ListEntryKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_selector_validator import (
    NavigationSelectorValidationReport,
    NavigationSelectorValidationResult,
    NavigationValidationStatus,
)
from pnc_automation.core.errors import SelectorResolutionError
from tests.test_support import make_entry, make_observation, make_spatial_surface
from tools.validate_visual_navigation import (
    ALLOWED_TAPS,
    PROBE_BACK_SCREENS,
    PROBE_SELECTOR_SCREENS,
    ROUTE_DECLARATIONS,
    ProbeRoute,
    _verify_manage_identity,
    _coordinate_proof,
    _fields_identity_summary,
    _visual_profile_ids,
    run_probe,
    require_probe_route,
    summarize,
    validate_navigation_selector_ids,
    validate_probe_action,
)


class VisualNavigationSafetyTests(unittest.TestCase):
    def test_navigation_and_bounded_wait_are_allowed(self) -> None:
        for action in (
            TapAction(selector_id=UiElementId.PNC_MORE_SETTINGS),
            KeyEventAction(key_code="KEYCODE_BACK"),
            WaitAction(milliseconds=1000),
        ):
            validate_probe_action(action)

    def test_spending_target_selection_and_unbounded_input_are_rejected(self) -> None:
        for action in (
            TapAction(selector_id=UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON),
            TapAction(selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON),
            TapListEntryAction(), TapPointAction(x=100, y=100),
            InputTextAction(text="message"), KeyEventAction(key_code="KEYCODE_ENTER"),
            WaitAction(milliseconds=1001), WaitAction(milliseconds=-1),
        ):
            with self.subTest(action=type(action).__name__):
                with self.assertRaises(ValueError):
                    validate_probe_action(action)

    def test_source_screen_policy_is_selector_specific(self) -> None:
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_selectors=frozenset(
                {
                    UiElementId.PNC_MORE_MANAGE_CHAR,
                    UiElementId.PNC_BOTTOM_NAV_QUEST,
                    UiElementId.PNC_POPUP_CLOSE_BUTTON,
                }
            ),
            allowed_selector_screens=PROBE_SELECTOR_SCREENS,
            allowed_back_screens=PROBE_BACK_SCREENS,
        )

        policy.validate(
            TapAction(selector_id=UiElementId.PNC_MORE_MANAGE_CHAR),
            make_observation(ScreenType.PNC_SETTINGS),
        )
        with self.assertRaises(SelectorResolutionError):
            policy.validate(
                TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_QUEST),
                make_observation(ScreenType.PNC_POPUP),
            )

    def test_all_typed_routes_have_safe_entry_declarations(self) -> None:
        self.assertEqual(set(ProbeRoute), set(ROUTE_DECLARATIONS))
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_selectors=ALLOWED_TAPS,
            allowed_selector_screens=PROBE_SELECTOR_SCREENS,
            allowed_back_screens=PROBE_BACK_SCREENS,
        )
        for declaration in ROUTE_DECLARATIONS.values():
            self.assertTrue(declaration.read_only)
            for selector in declaration.entry_selectors:
                allowed_screens = next(
                    screens for allowed_id, screens in PROBE_SELECTOR_SCREENS if allowed_id == selector
                )
                source_screen = next(
                    iter((declaration.entry_screens | declaration.destination_screens) & allowed_screens),
                    None,
                )
                self.assertIsNotNone(source_screen, declaration.route.value)
                policy.validate(
                    TapAction(selector_id=selector),
                    make_observation(source_screen),
                )

    def test_route_validation_happens_before_runtime_selection(self) -> None:
        with self.assertRaises(ValueError):
            require_probe_route("unsupported_route")

    def test_navigation_selector_validation_is_catalog_backed_and_read_only(self) -> None:
        self.assertEqual(
            (UiElementId.PNC_MORE_SETTINGS,),
            validate_navigation_selector_ids((UiElementId.PNC_MORE_SETTINGS,)),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "specific complete recognized Bag row"):
            validate_navigation_selector_ids((UiElementId.PNC_BAG_USE_BUTTON,))
        with self.assertRaisesRegex(ValueError, "not a reviewed navigation"):
            validate_navigation_selector_ids((UiElementId.PNC_LOGIN_USERNAME_FIELD,))

    def test_navigation_selector_route_rejects_empty_requests_before_runtime(self) -> None:
        with TemporaryDirectory() as directory, patch("tools.validate_visual_navigation.build_application_runner") as build:
            with self.assertRaisesRegex(ValueError, "requires at least one selector"):
                run_probe(
                    Path("config.yaml"),
                    "testing",
                    Path(directory),
                    route=ProbeRoute.NAVIGATION_SELECTORS,
                )
            build.assert_not_called()

    def test_navigation_selector_cli_runs_each_declared_source_independently(self) -> None:
        with TemporaryDirectory() as directory:
            summaries = []
            for index in range(2):
                path = Path(directory) / f"summary-{index}.json"
                path.write_text(json.dumps({"status": "passed", "navigation_report": "report.yaml"}), encoding="utf-8")
                summaries.append(path)
            argv = [
                "validate_navigation_selectors.py",
                "--account", "testing",
                "--selector", "PNC_BOTTOM_NAV_MORE",
                "--output-dir", directory,
            ]
            with patch("sys.argv", argv), patch.object(
                validate_navigation_selectors,
                "run_probe",
                side_effect=summaries,
            ) as run_probe:
                self.assertEqual(0, validate_navigation_selectors.main())
            self.assertEqual(2, run_probe.call_count)
            self.assertEqual(
                [ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU],
                [call.kwargs["navigation_source_screen"] for call in run_probe.call_args_list],
            )
            self.assertTrue(all(
                call.kwargs["route"] == ProbeRoute.NAVIGATION_SELECTORS
                for call in run_probe.call_args_list
            ))

    def test_navigation_selector_route_shares_unknown_budget_across_validator_settles(self) -> None:
        castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        manage = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={"kingdom": castle.kingdom},
                    selected=True,
                ),
            ),
        )
        home = make_observation(
            ScreenType.PNC_HOME_CITY,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )

        class _UnknownSettlingValidator:
            def __init__(self, *, observation_service, **kwargs) -> None:
                del kwargs
                self.observation_service = observation_service

            def validate(self, *, selector_ids, source_screen):
                del selector_ids, source_screen
                for index in range(5):
                    self.observation_service.capture_observation(f"fake_unknown_settle_{index}")
                raise AssertionError("global UNKNOWN budget should stop the validator first")

        runtime = _FakeRuntime(
            [home, manage, home, *([make_observation(ScreenType.UNKNOWN)] * 5)],
            ProbeRoute.NAVIGATION_SELECTORS,
        )
        app = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: object()),
                build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=runtime),
                observation_builder=SimpleNamespace(selector_registry=object()),
                logger=SimpleNamespace(info=lambda *args, **kwargs: None),
            )
        )
        with TemporaryDirectory() as directory, patch(
            "tools.validate_visual_navigation.build_application_runner",
            return_value=app,
        ), patch(
            "tools.validate_visual_navigation.NavigationSelectorValidator",
            _UnknownSettlingValidator,
        ):
            with self.assertRaisesRegex(RuntimeError, "Read-only proof failed"):
                run_probe(
                    Path("config.yaml"),
                    "testing",
                    Path(directory),
                    route=ProbeRoute.NAVIGATION_SELECTORS,
                    navigation_selectors=(UiElementId.PNC_MORE_SETTINGS,),
                    navigation_source_screen=ScreenType.PNC_MORE_MENU,
                )
            summaries = list(Path(directory).rglob("summary.json"))
            self.assertEqual(1, len(summaries))
            self.assertEqual("failed", json.loads(summaries[0].read_text(encoding="utf-8"))["status"])
            self.assertEqual(7, runtime.observation_service.capture_count)
            unknown_labels = [
                label for label in runtime.observation_service.labels if "fake_unknown_settle_" in label
            ]
            self.assertEqual(4, len(unknown_labels))
            self.assertFalse(any(label.endswith("_fake_unknown_settle_4") for label in unknown_labels))

    def test_navigation_selector_route_refreshes_and_unwinds_to_home(self) -> None:
        """The validator's terminal More state is freshly observed and safely unwound."""

        castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        manage = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={"kingdom": castle.kingdom},
                    selected=True,
                ),
            ),
        )
        home = make_observation(
            ScreenType.PNC_HOME_CITY,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )
        more = make_observation(
            ScreenType.PNC_MORE_MENU,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )

        class _FakeNavigationValidator:
            def __init__(self, *, observation_service, **kwargs) -> None:
                del kwargs
                self.observation_service = observation_service

            def validate(self, *, selector_ids, source_screen):
                self.observation_service.capture_observation("fake_validator_terminal_more")
                return NavigationSelectorValidationReport(
                    results=(
                        NavigationSelectorValidationResult(
                            selector_id=selector_ids[0],
                            source_screen=source_screen,
                            status=NavigationValidationStatus.PASSED,
                            reason="fake passed",
                            expected_target_screens=(ScreenType.PNC_SETTINGS,),
                        ),
                    ),
                )

        runtime = _FakeRuntime([home, manage, home, more, more, home], ProbeRoute.NAVIGATION_SELECTORS)
        app = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: object()),
                build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=runtime),
                observation_builder=SimpleNamespace(selector_registry=object()),
                logger=SimpleNamespace(info=lambda *args, **kwargs: None),
            )
        )
        with TemporaryDirectory() as directory, patch(
            "tools.validate_visual_navigation.build_application_runner",
            return_value=app,
        ), patch(
            "tools.validate_visual_navigation.NavigationSelectorValidator",
            _FakeNavigationValidator,
        ):
            summary_path = run_probe(
                Path("config.yaml"),
                "testing",
                Path(directory),
                route=ProbeRoute.NAVIGATION_SELECTORS,
                navigation_selectors=(UiElementId.PNC_MORE_SETTINGS,),
                navigation_source_screen=ScreenType.PNC_MORE_MENU,
            )
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            trace_text = Path(payload["trace"]).read_text(encoding="utf-8")

        self.assertEqual("passed", payload["status"])
        self.assertEqual("PNC_MORE_MENU", payload["navigation_source_screen"])
        self.assertEqual("PNC_HOME_CITY", payload["final"]["screen"])
        self.assertEqual("match", payload["final_identity_verification"]["status"])
        self.assertEqual("fake", payload["runtime"]["instance_display_name"])
        self.assertEqual("fake-instance", payload["runtime"]["instance_id"])
        self.assertTrue(payload["runtime"]["foreground_before"])
        self.assertTrue(payload["runtime"]["foreground_after"])
        self.assertEqual("unknown", payload["runtime"]["startup_origin"])
        self.assertEqual(payload["input_attempts"], payload["actions"])
        self.assertEqual(payload["route_steps"], payload["actions"])
        self.assertIn('"event": "navigation_validation_case"', trace_text)
        self.assertIn('"source_screen": "PNC_MORE_MENU"', trace_text)

        class _FailedNavigationValidator(_FakeNavigationValidator):
            def validate(self, *, selector_ids, source_screen):
                self.observation_service.capture_observation("fake_validator_terminal_more")
                return NavigationSelectorValidationReport(
                    results=(
                        NavigationSelectorValidationResult(
                            selector_id=selector_ids[0],
                            source_screen=source_screen,
                            status=NavigationValidationStatus.FAILED,
                            reason="fake failed",
                            expected_target_screens=(ScreenType.PNC_SETTINGS,),
                        ),
                    ),
                )

        failed_runtime = _FakeRuntime([home, manage, home, more, more, home], ProbeRoute.NAVIGATION_SELECTORS)
        failed_app = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: object()),
                build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=failed_runtime),
                observation_builder=SimpleNamespace(selector_registry=object()),
                logger=SimpleNamespace(info=lambda *args, **kwargs: None),
            )
        )
        with TemporaryDirectory() as directory, patch(
            "tools.validate_visual_navigation.build_application_runner",
            return_value=failed_app,
        ), patch(
            "tools.validate_visual_navigation.NavigationSelectorValidator",
            _FailedNavigationValidator,
        ):
            with self.assertRaisesRegex(RuntimeError, "Read-only proof failed"):
                run_probe(
                    Path("config.yaml"),
                    "testing",
                    Path(directory),
                    route=ProbeRoute.NAVIGATION_SELECTORS,
                    navigation_selectors=(UiElementId.PNC_MORE_SETTINGS,),
                    navigation_source_screen=ScreenType.PNC_MORE_MENU,
                )
            summaries = list(Path(directory).rglob("summary.json"))
            self.assertEqual(1, len(summaries))
            self.assertEqual("failed", json.loads(summaries[0].read_text(encoding="utf-8"))["status"])

    def test_read_only_routes_do_not_allow_chat_mail_or_claim_inputs(self) -> None:
        self.assertNotIn(UiElementId.PNC_CHAT_INPUT_FIELD, ALLOWED_TAPS)
        self.assertNotIn(UiElementId.PNC_MAIL_THREAD_ROW, ALLOWED_TAPS)
        self.assertNotIn(UiElementId.PNC_MAIL_THREAD_DELETE_BUTTON, ALLOWED_TAPS)
        self.assertNotIn(UiElementId.PNC_MORE_VIP, ALLOWED_TAPS)

    def test_alliance_join_is_safe_to_unwind_but_not_to_enter_or_join(self) -> None:
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_selectors=ALLOWED_TAPS,
            allowed_selector_screens=PROBE_SELECTOR_SCREENS,
            allowed_back_screens=PROBE_BACK_SCREENS,
        )
        policy.validate(
            KeyEventAction(key_code="KEYCODE_BACK"),
            make_observation(ScreenType.PNC_ALLIANCE_JOIN),
        )
        with self.assertRaises(SelectorResolutionError):
            policy.validate(
                TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_ALLIANCE),
                make_observation(ScreenType.PNC_ALLIANCE_JOIN),
            )

    def test_summary_exposes_typed_guard_layout_and_rows(self) -> None:
        state = summarize(make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual("PNC_HOME_CITY", state["screen"])
        self.assertEqual("clear", state["guard"])
        self.assertIn("layout_id", state)
        self.assertIn("rows", state)
        self.assertIn("context_metrics", state)
        self.assertIn("context_diagnostics", state)

    def test_summary_uses_capture_ocr_context_metrics_and_diagnostics(self) -> None:
        context = SimpleNamespace(
            metrics=SimpleNamespace(
                requests=3,
                engine_calls=1,
                processed_pixel_area=240,
                cache_hits=1,
                fullframe_reuses=1,
                engine_seconds=0.25,
            ),
            read_diagnostics=(),
        )
        state = summarize(make_observation(ScreenType.PNC_HOME_CITY), ocr_context=context)

        self.assertEqual(3, state["context_metrics"]["requests"])
        self.assertEqual(1, state["context_metrics"]["fullframe_reuses"])
        self.assertEqual([], state["context_diagnostics"])

    def test_foreground_failure_happens_before_any_input_or_capture(self) -> None:
        castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        runtime = _FakeRuntime(
            [
                make_observation(ScreenType.PNC_HOME_CITY),
                make_observation(
                    ScreenType.PNC_CASTLE_SELECTION,
                    current_castle=castle,
                    current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
                    list_entries=(
                        make_entry(
                            ListEntryKind.CASTLE,
                            title=castle.castle_name,
                            metadata={"kingdom": castle.kingdom},
                            selected=True,
                        ),
                    ),
                ),
            ],
            ProbeRoute.FIELDS,
            foreground_after=False,
        )
        app = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: object()),
                build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=runtime),
            )
        )
        with TemporaryDirectory() as directory, patch(
            "tools.validate_visual_navigation.build_application_runner", return_value=app
        ):
            with self.assertRaisesRegex(RuntimeError, "Read-only proof failed"):
                run_probe(Path("config.yaml"), "testing", Path(directory), route=ProbeRoute.FIELDS)

        self.assertEqual(0, runtime.action_executor.action_executor.input_attempts)
        self.assertEqual(0, runtime.observation_service.capture_count)

    def test_capture_profiles_come_from_decision_without_second_recognition(self) -> None:
        decision = ScreenDecision(
            base_screen=ScreenType.PNC_HOME_CITY,
            effective_screen=ScreenType.PNC_HOME_CITY,
            guard=GuardVerdict.CLEAR,
            evidence=(
                ScreenEvidence(
                    ScreenType.PNC_HOME_CITY,
                    "visual_anchor:home_city",
                    layout_id="home_city_profile",
                ),
            ),
        )
        observation = make_observation(ScreenType.PNC_HOME_CITY, decision=decision)
        self.assertEqual(("home_city_profile",), _visual_profile_ids(observation))
        runtime = _FakeRuntime([observation], ProbeRoute.FIELDS)
        app = SimpleNamespace(
            script_runner=SimpleNamespace(
                config=SimpleNamespace(require_account=lambda account_id: object()),
                build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=runtime),
            )
        )
        with TemporaryDirectory() as directory, patch(
            "tools.validate_visual_navigation.build_application_runner", return_value=app
        ):
            with self.assertRaisesRegex(RuntimeError, "Read-only proof failed"):
                run_probe(Path("config.yaml"), "testing", Path(directory), route=ProbeRoute.FIELDS)

        self.assertEqual(0, runtime.observation_service.recognizer.calls)

    def test_manage_identity_requires_exact_evidence_and_one_selected_matching_row(self) -> None:
        castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={"kingdom": castle.kingdom},
                    selected=True,
                ),
            ),
        )

        self.assertEqual(
            {
                "evidence_kind": "exact",
                "selected_castle_rows": 1,
                "matching_selected_castle_rows": 1,
            },
            _verify_manage_identity(observation),
        )

    def test_manage_identity_rejects_weak_or_ambiguous_castle_rows(self) -> None:
        castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
        weak = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.NAME_ONLY,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={"kingdom": castle.kingdom},
                    selected=True,
                ),
            ),
        )
        ambiguous = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            current_castle=castle,
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title=castle.castle_name,
                    metadata={"kingdom": castle.kingdom},
                    selected=True,
                ),
                make_entry(
                    ListEntryKind.CASTLE,
                    title="other castle",
                    metadata={"kingdom": "K288"},
                    selected=True,
                ),
            ),
        )

        for candidate in (weak, ambiguous):
            with self.assertRaises(RuntimeError):
                _verify_manage_identity(candidate)

    def test_invalid_run_route_is_rejected_before_runtime_creation(self) -> None:
        """A typo cannot create output or initialize the connected runtime."""

        with TemporaryDirectory() as directory, patch("tools.validate_visual_navigation.build_application_runner") as build:
            with self.assertRaises(ValueError):
                run_probe(Path("config.yaml"), "testing", Path(directory), route="invalid")
            build.assert_not_called()

    def test_fake_fields_route_records_explicit_name_abstention_and_weak_final_identity(self) -> None:
        """Fields proves Lord Info while allowing a typed name abstention and cached weak Home identity."""

        payload = _run_fake_probe(ProbeRoute.FIELDS)

        self.assertEqual("abstained", payload["fields_identity"]["name_status"])
        self.assertEqual("insufficient_evidence", payload["final_identity_verification"]["status"])

    def test_fields_reads_the_canonical_lord_info_name_fact(self) -> None:
        observation = make_observation(
            ScreenType.PNC_LORD_INFO,
            current_castle=CastleIdentity(kingdom="", castle_name="Observed lord"),
            current_castle_evidence=CurrentCastleEvidenceKind.NAME_ONLY,
        )
        self.assertEqual("observed", _fields_identity_summary(observation)["name_status"])
        self.assertEqual(CurrentCastleEvidenceKind.NAME_ONLY, observation.current_castle_evidence)

    def test_fake_coordinates_route_requires_fresh_p2_coordinate_and_guard_before_home(self) -> None:
        """Coordinate-only P1 is followed by same-coordinate guarded P2 before the Home tap."""

        payload = _run_fake_probe(ProbeRoute.COORDINATES)

        self.assertEqual([123, 456], payload["coordinates"]["coordinate"])
        self.assertEqual("clear", payload["coordinates"]["p2"]["guard"])
        self.assertFalse(payload["coordinates"]["p2"]["coordinate_only"])


def _run_fake_probe(route: ProbeRoute) -> dict[str, object]:
    """Run one route against a typed fake runtime without creating a live session."""

    castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
    manage = make_observation(
        ScreenType.PNC_CASTLE_SELECTION,
        current_castle=castle,
        current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        list_entries=(
            make_entry(
                ListEntryKind.CASTLE,
                title=castle.castle_name,
                metadata={"kingdom": castle.kingdom},
                selected=True,
            ),
        ),
    )
    weak_home = make_observation(
        ScreenType.PNC_HOME_CITY,
        current_castle=CastleIdentity(kingdom="", castle_name=castle.castle_name),
        current_castle_evidence=CurrentCastleEvidenceKind.NAME_ONLY,
    )
    observations = [make_observation(ScreenType.PNC_HOME_CITY), manage, weak_home]
    if route == ProbeRoute.FIELDS:
        observations.extend((make_observation(ScreenType.PNC_LORD_INFO), weak_home))
    else:
        p1 = _fake_world_observation(coordinate_only=True, guard=GuardVerdict.CLEAR)
        p2 = _fake_world_observation(coordinate_only=False, guard=GuardVerdict.CLEAR)
        observations.extend((p1, p1, p2, weak_home))
    runtime = _FakeRuntime(observations, route)
    app = SimpleNamespace(
        script_runner=SimpleNamespace(
            config=SimpleNamespace(require_account=lambda account_id: object()),
            build_connected_runtime_bundle=lambda account: SimpleNamespace(runtime=runtime),
        )
    )
    with TemporaryDirectory() as directory, patch("tools.validate_visual_navigation.build_application_runner", return_value=app):
        summary_path = run_probe(Path("config.yaml"), "testing", Path(directory), route=route)
        return json.loads(summary_path.read_text(encoding="utf-8"))


def _fake_world_observation(*, coordinate_only: bool, guard: GuardVerdict):
    """Build a deterministic World Map P1 or P2 observation at one coordinate."""

    decision = ScreenDecision(
        base_screen=ScreenType.PNC_WORLD_MAP,
        effective_screen=ScreenType.PNC_WORLD_MAP,
        guard=guard,
        coordinate_only=coordinate_only,
        evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP, "fake_world_proof"),),
    )
    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        decision=decision,
        spatial_surface=make_spatial_surface(SpatialSurfaceType.WORLD_MAP, x=123, y=456),
    )


class _FakeRuntime:
    """Minimal typed runtime surface exercised by the route proof tests."""

    def __init__(self, observations: list, route: ProbeRoute, *, foreground_after: bool = True) -> None:
        self.observation_service = _FakeObservationService(observations)
        self.action_executor = _FakeObservedExecutor()
        self.flow_planner = _FakeFlowPlanner(route)
        foreground_states = iter((True, foreground_after))
        self.session = SimpleNamespace(
            instance=SimpleNamespace(display_name="fake", id="fake-instance"),
            is_app_foregrounded=lambda: next(foreground_states),
            ensure_app_foregrounded=lambda: None,
        )

    def require_observed_action_executor(self, reason: str):
        del reason
        return self.action_executor


class _FakeObservationService:
    """Returns prebuilt observations in capture order."""

    def __init__(self, observations: list) -> None:
        self._observations = list(observations)
        self.capture_count = 0
        self.labels: list[str] = []
        self.recognizer = _FakeVisualRecognizer()
        self.observation_builder = SimpleNamespace(visual_recognizer=self.recognizer)

    def configure_read_only_probe_mode(self) -> None:
        return None

    def capture_observation(self, label: str, *, request=None):
        del request
        self.capture_count += 1
        self.labels.append(label)
        return SimpleNamespace(
            observation=self._observations.pop(0),
            screenshot=SimpleNamespace(image=None),
            ocr_context=SimpleNamespace(
                metrics=SimpleNamespace(
                    requests=0,
                    engine_calls=0,
                    processed_pixel_area=0,
                    cache_hits=0,
                    fullframe_reuses=0,
                    engine_seconds=0.0,
                ),
                read_diagnostics=(),
            ),
        )


class _FakeVisualRecognizer:
    """Fails the test if the validator performs a second visual recognition pass."""

    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, image):
        del image
        self.calls += 1
        raise AssertionError("visual recognition must be performed by ObservationBuilder only")


class _FakeObservedExecutor:
    """Executes one fake action by consuming exactly one post-action observation."""

    def __init__(self) -> None:
        self.action_executor = SimpleNamespace(
            input_attempts=0,
            configure_input_attempt_budget=lambda max_attempts, duration_seconds: None,
        )

    def configure_read_only_probe_mode(self, **kwargs) -> None:
        del kwargs

    def execute_actions(self, actions, current, *, observe):
        del current
        self.action_executor.input_attempts += len(actions)
        action = actions[0]
        return SimpleNamespace(observation=observe("fake_post_action", action.follow_up_request))


class _FakeFlowPlanner:
    """Produces only the typed transitions needed by the fake route proofs."""

    def __init__(self, route: ProbeRoute) -> None:
        self.route = route

    def ensure_home_city(self, observation):
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return []
        return [KeyEventAction(reason="fake_back")]

    def open_castle_selection(self, observation):
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return [TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_MORE, reason="fake_manage")]
        return []

    def ensure_world_map_ready(self, observation):
        if observation.screen_type == ScreenType.PNC_HOME_CITY:
            return [TapAction(selector_id=UiElementId.PNC_HOME_WORLD_SWITCH, reason="fake_world")]
        return []

    def open_lord_info(self, observation):
        return [TapAction(selector_id=UiElementId.PNC_HOME_LORD_INFO_SHORTCUT, reason="fake_fields")]

    def close_blocking_popup(self, observation):
        del observation
        return []


if __name__ == "__main__":
    unittest.main()
