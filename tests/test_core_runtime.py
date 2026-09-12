"""Offline tests for replacement-core runtime composition and content preservation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from pnc_automation.app.automation.engine.core_runtime import CoreRuntime, build_core_runtime
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.navigation_core import NavigationPolicy
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.entrypoints.app import ApplicationRunner
from pnc_automation.app.pnc.domain.observation import (
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    VisibleElement,
)
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.screen_classifier import ScreenEvidence
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition, load_visual_screen_recognizer
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.storage.artifact_store import ArtifactRecord
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrResult, OcrService
from tests.test_support import FakeSession, build_logger


class CoreRuntimeTests(unittest.TestCase):
    """Covers one-runtime composition and pure content identity preservation."""

    def test_initial_settle_passively_waits_for_loading_then_known_stable_screen(self) -> None:
        """Settling consumes loading frames and never invokes navigation actions."""

        clock = _FakeClock()
        navigation = _SettleNavigation(clock)
        runtime = _SequencedCoreRuntime(
            navigation,
            [
                _frame(ScreenType.PNC_LOADING, 0),
                _frame(ScreenType.PNC_HOME_CITY, 1),
                _frame(ScreenType.PNC_HOME_CITY, 2),
            ],
        )

        settled = runtime._settle_initial_screen()

        self.assertEqual(ScreenType.PNC_HOME_CITY, settled.screen_type)
        self.assertEqual(3, runtime.observation_count)
        self.assertEqual([], navigation.navigate_calls)
        self.assertEqual(2, len(navigation.sleep_calls))

    def test_preflight_settle_accepts_black_frame_classified_as_loading(self) -> None:
        """A cold-start black capture enters the existing bounded passive settle path."""

        class _Recognizer:
            reference_size = (10, 10)

            def recognize(self, image: Image.Image) -> VisualRecognition:
                del image
                return VisualRecognition()

        class _Guard:
            def detect_interruption(self, image, *, owned_dismiss_bounds=()):
                del image, owned_dismiss_bounds
                return ObservationAdditions()

        black_capture = CapturedScreenshot(
            artifact=None,
            image=Image.new("RGB", (10, 10), (5, 5, 5)),
            image_format="PNG",
            ephemeral_captured_at=datetime(2026, 9, 10, tzinfo=UTC),
        )
        black = NavigationPerception(_Recognizer(), _Guard()).build(black_capture)
        self.assertEqual(ScreenType.PNC_LOADING, black.screen_type)

        clock = _FakeClock()
        navigation = _SettleNavigation(clock)
        runtime = _SequencedCoreRuntime(
            navigation,
            [black, _frame(ScreenType.PNC_HOME_CITY, 1), _frame(ScreenType.PNC_HOME_CITY, 2)],
        )

        settled = runtime._settle_initial_screen()

        self.assertEqual(ScreenType.PNC_HOME_CITY, settled.screen_type)
        self.assertEqual(3, runtime.observation_count)
        self.assertEqual([], navigation.navigate_calls)

    def test_initial_unknown_and_popup_stop_immediately_without_action(self) -> None:
        """Unknown and interrupted startup frames fail closed before any passive wait."""

        for interrupted in (_frame(ScreenType.UNKNOWN, 0), _frame(ScreenType.PNC_HOME_CITY, 0, blocking_popup=True)):
            clock = _FakeClock()
            navigation = _SettleNavigation(clock)
            runtime = _SequencedCoreRuntime(navigation, [interrupted])

            with self.assertRaisesRegex(RuntimeError, "unknown screen|blocking popup"):
                runtime._settle_initial_screen()

            self.assertEqual([], navigation.navigate_calls)
            self.assertEqual([], navigation.sleep_calls)
            self.assertEqual(1, runtime.observation_count)

    def test_initial_settle_rejects_stale_frames(self) -> None:
        """Passive settling requires strictly newer capture timestamps."""

        clock = _FakeClock()
        navigation = _SettleNavigation(clock)
        runtime = _SequencedCoreRuntime(
            navigation,
            [_frame(ScreenType.PNC_HOME_CITY, 0), _frame(ScreenType.PNC_HOME_CITY, 0)],
        )

        with self.assertRaisesRegex(RuntimeError, "stale capture"):
            runtime._settle_initial_screen()

        self.assertEqual(2, runtime.observation_count)
        self.assertEqual([], navigation.navigate_calls)

    def test_initial_settle_cannot_succeed_after_capture_exhausts_time_budget(self) -> None:
        """A late capture is rejected even when it would complete stability."""

        clock = _FakeClock()
        navigation = _SettleNavigation(clock, max_seconds=1.0)
        runtime = _SequencedCoreRuntime(
            navigation,
            [_frame(ScreenType.PNC_HOME_CITY, 0), _frame(ScreenType.PNC_HOME_CITY, 1)],
            capture_delays=[0.0, 2.0],
        )

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            runtime._settle_initial_screen()

        self.assertEqual(2, runtime.observation_count)
        self.assertEqual([], navigation.navigate_calls)

    def test_initial_settle_restarts_budget_after_recovery_episode(self) -> None:
        """A recovered Home frame starts a fresh passive stability window."""

        clock = _FakeClock()
        navigation = _SettleNavigation(clock, max_seconds=1.0)
        runtime = _SequencedCoreRuntime(
            navigation,
            [_frame(ScreenType.PNC_HOME_CITY, 0), _frame(ScreenType.PNC_HOME_CITY, 1)],
            capture_delays=[2.0, 0.0],
            recovered_flags=[True, False],
        )

        settled = runtime._settle_initial_screen()

        self.assertEqual(ScreenType.PNC_HOME_CITY, settled.screen_type)
        self.assertEqual(2, runtime.observation_count)
        self.assertEqual(1, len(navigation.sleep_calls))

    def test_capture_event_is_retained_when_perception_raises(self) -> None:
        """Persists the screenshot metadata before a parser exception can abort observation."""

        captured_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "trace.jsonl"
            artifact_path = Path(temporary_directory) / "private_identity.png"
            screenshot = CapturedScreenshot(
                artifact=ArtifactRecord(
                    path=artifact_path,
                    label="capture",
                    captured_at=captured_at,
                    size_bytes=1,
                    sha256="sha",
                ),
                image=Image.new("RGB", (2, 2)),
                image_format="PNG",
            )
            screenshot_service = Mock()
            screenshot_service.capture.return_value = screenshot
            connected = SimpleNamespace(
                session=object(),
                observation_service=SimpleNamespace(screenshot_service=screenshot_service),
            )
            perception = Mock()
            perception.build.side_effect = RuntimeError("parser failed")
            runtime = CoreRuntime(
                runtime=connected,
                navigation=Mock(),
                artifact_directory="account",
                trace_path=trace_path,
                _perception=perception,
                _run_id="run",
            )

            with self.assertRaisesRegex(RuntimeError, "parser failed"):
                runtime.observe("identity")

            lines = trace_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(lines))
            self.assertIn('"event": "capture"', lines[0])
            self.assertIn('"artifact": "private_identity.png"', lines[0])
            self.assertNotIn("parser failed", lines[0])

    def test_observation_boundary_recovers_popup_through_connected_executor(self) -> None:
        """Recovery captures a fresh frame through CoreRuntime and preserves content mode."""

        captured_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
        screenshots = [
            CapturedScreenshot(
                artifact=ArtifactRecord(
                    path=Path("popup.png"), captured_at=captured_at,
                    size_bytes=1, sha256="popup", label="popup",
                ),
                image=Image.new("RGB", (2, 2)), image_format="PNG",
            ),
            CapturedScreenshot(
                artifact=ArtifactRecord(
                    path=Path("home.png"), captured_at=captured_at + timedelta(seconds=1),
                    size_bytes=1, sha256="home", label="home",
                ),
                image=Image.new("RGB", (2, 2)), image_format="PNG",
            ),
        ]
        screenshot_service = Mock()
        screenshot_service.capture.side_effect = screenshots
        observation_service = SimpleNamespace(screenshot_service=screenshot_service)
        popup = _frame_at(ScreenType.PNC_POPUP, captured_at, blocking_popup=True)
        home = _frame_at(ScreenType.PNC_HOME_CITY, captured_at + timedelta(seconds=1))
        perception = Mock()
        perception.build.side_effect = [popup, home]
        executor = Mock()

        def recover(observation, *, label_prefix, observe):
            self.assertIs(popup, observation)
            self.assertIn("interruption", label_prefix)
            return observe("followup", request=ObservationRequest.full_runtime_default())

        executor.recover_interruption_if_required.side_effect = recover
        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "trace.jsonl"
            runtime = CoreRuntime(
                runtime=SimpleNamespace(session=object(), observation_service=observation_service),
                navigation=Mock(),
                artifact_directory="account",
                trace_path=trace_path,
                _perception=perception,
                _run_id="run",
                _observed_action_executor=executor,
            )

            result = runtime.observe("entry", include_content=True)

            self.assertIs(home, result)
            self.assertEqual(2, runtime.observation_count)
            self.assertEqual([True, True], [call.kwargs["include_content"] for call in perception.build.call_args_list])
            self.assertEqual(2, screenshot_service.capture.call_count)
            self.assertTrue(all(call.kwargs["persist"] for call in screenshot_service.capture.call_args_list))
            trace = trace_path.read_text(encoding="utf-8")
            self.assertEqual(2, trace.count('"event": "capture"'))
            self.assertEqual(2, trace.count('"event": "observation"'))

    def test_observation_boundary_dispatches_real_popup_fixture_close_selector(self) -> None:
        """Carries a measured fixture close point from perception into popup recovery dispatch."""

        fixture_directory = Path("tests/data/screen_recognition")
        with (
            Image.open(fixture_directory / "generic_popup_offer_real_sanitized.png") as popup_source,
            Image.open(fixture_directory / "home_city_core.png") as home_source,
        ):
            popup_image = popup_source.convert("RGB")
            home_image = home_source.convert("RGB")
        ocr = Mock(spec=OcrService)
        ocr.read_result.return_value = OcrResult(lines=(), words=())
        perception = NavigationPerception(
            load_visual_screen_recognizer(),
            PncObservationEnricher(ocr),
        )
        captured_at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

        def screenshot(image: Image.Image, name: str, offset: int) -> CapturedScreenshot:
            return CapturedScreenshot(
                artifact=ArtifactRecord(
                    path=Path(name),
                    captured_at=captured_at + timedelta(seconds=offset),
                    size_bytes=1,
                    sha256=name,
                    label=name,
                ),
                image=image.copy(),
                image_format="PNG",
            )

        screenshot_service = Mock()
        screenshot_service.capture.side_effect = [
            screenshot(popup_image, "popup.png", 0),
            screenshot(home_image, "home.png", 1),
        ]
        session = FakeSession()
        observed_executor = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=ActionExecutor(
                session=session,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            ),
            logger=build_logger(),
            sleep=lambda _: None,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime = CoreRuntime(
                runtime=SimpleNamespace(
                    session=session,
                    observation_service=SimpleNamespace(screenshot_service=screenshot_service),
                ),
                navigation=Mock(),
                artifact_directory="account",
                trace_path=Path(temporary_directory) / "trace.jsonl",
                _perception=perception,
                _run_id="run",
                _observed_action_executor=observed_executor,
            )

            expected_popup = perception.build(screenshot(popup_image, "expected.png", 0))
            result = runtime.observe("entry")

        self.assertEqual(ScreenType.PNC_HOME_CITY, result.screen_type)
        self.assertEqual(1, len(session.taps))
        self.assertEqual(expected_popup.popup_overlay.candidates[0].action_point, session.taps[0])

    def test_application_preflights_identity_before_workflow_and_blocks_failure(self) -> None:
        """Application wiring runs identity preflight before constructing workflow execution."""

        account = SimpleNamespace(artifact_directory_name="account")
        script_runner = Mock()
        script_runner.config.require_account.return_value = account
        core_runtime = Mock()
        events: list[str] = []
        core_runtime.preflight_active_castle_identity.side_effect = lambda: events.append("preflight")

        class _Runner:
            @classmethod
            def __class_getitem__(cls, item):
                del item
                return cls

            def __init__(self, runtime) -> None:
                del runtime

            def run(self, workflow):
                del workflow
                events.append("workflow")
                return "result"

        with (
            patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=core_runtime),
            patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", _Runner),
        ):
            result = ApplicationRunner(script_runner).run_daily_quest_status(account_id="account")

        self.assertEqual("result", result)
        self.assertEqual(["preflight", "workflow"], events)

        core_runtime.preflight_active_castle_identity.side_effect = RuntimeError("identity absent")
        with (
            patch("pnc_automation.app.entrypoints.app.build_core_runtime", return_value=core_runtime),
            patch("pnc_automation.app.entrypoints.app.CoreWorkflowRunner", side_effect=_Runner) as runner_factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "identity absent"):
                ApplicationRunner(script_runner).run_daily_quest_status(account_id="account")
        runner_factory.assert_not_called()

    def test_identity_preflight_rejects_stale_or_blocked_content_before_return_home(self) -> None:
        """Identity content must be fresh and unblocked relative to Manage Characters navigation."""

        identity = Observation(
            screen_type=ScreenType.PNC_CASTLE_SELECTION,
            visible_elements={},
            captured_at=datetime(2026, 9, 10, 12, 0, 1, tzinfo=UTC),
            blocking_popup=False,
            current_castle=CastleIdentity("K1", "Castle", 22),
            current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
        )
        for frame, error in (
            (
                _frame_at(ScreenType.PNC_CASTLE_SELECTION, datetime(2026, 9, 10, 12, 0, 1, tzinfo=UTC)),
                "stale",
            ),
            (
                _frame_at(ScreenType.PNC_CASTLE_SELECTION, datetime(2026, 9, 10, 11, 59, 59, tzinfo=UTC)),
                "blocked",
            ),
        ):
            identity_frame = identity if error == "stale" else Observation(
                screen_type=identity.screen_type,
                visible_elements={},
                captured_at=identity.captured_at + timedelta(seconds=1),
                blocking_popup=True,
                current_castle=identity.current_castle,
                current_castle_evidence=identity.current_castle_evidence,
            )
            navigation = Mock()
            navigation.navigate.return_value = frame
            runtime = CoreRuntime(
                runtime=SimpleNamespace(session=Mock()),
                navigation=navigation,
                artifact_directory="account",
                trace_path=Path("trace.jsonl"),
                _perception=Mock(),
                _run_id="run",
            )

            with (
                patch.object(CoreRuntime, "_settle_initial_screen", return_value=_frame(ScreenType.PNC_HOME_CITY, 0)),
                patch.object(CoreRuntime, "observe", autospec=True, return_value=identity_frame),
            ):
                with self.assertRaisesRegex(RuntimeError, error):
                    runtime.preflight_active_castle_identity()

            navigation.navigate.assert_called_once_with(ScreenType.PNC_CASTLE_SELECTION)

    def test_identity_scan_rewinds_then_finds_selected_row_without_row_tap(self) -> None:
        """Searches both roster directions through the constrained swipe operation."""

        navigation = Mock()
        initial = _castle_roster_frame("K1", "First")
        selected = _castle_roster_frame("K2", "Selected", selected=True)
        navigation.scroll_castle_roster.side_effect = (initial, selected)
        runtime = CoreRuntime(
            runtime=SimpleNamespace(session=Mock()),
            navigation=navigation,
            artifact_directory="account",
            trace_path=Path("trace.jsonl"),
            _perception=Mock(),
            _run_id="run",
        )

        result = runtime._scan_active_castle_identity(initial)

        self.assertEqual(CastleIdentity("K2", "Selected", 22), result.current_castle)
        self.assertEqual(
            ["down", "up"],
            [call.args[0] for call in navigation.scroll_castle_roster.call_args_list],
        )

    def test_identity_scan_stops_at_repeated_boundaries(self) -> None:
        """Fails after one bounded swipe at each unchanged roster boundary."""

        navigation = Mock()
        initial = _castle_roster_frame("K1", "First")
        navigation.scroll_castle_roster.return_value = initial
        runtime = CoreRuntime(
            runtime=SimpleNamespace(session=Mock()),
            navigation=navigation,
            artifact_directory="account",
            trace_path=Path("trace.jsonl"),
            _perception=Mock(),
            _run_id="run",
        )

        with self.assertRaisesRegex(RuntimeError, "bounded roster scan"):
            runtime._scan_active_castle_identity(initial)

        self.assertEqual(
            ["down", "up"],
            [call.args[0] for call in navigation.scroll_castle_roster.call_args_list],
        )


    def test_factory_builds_one_connected_runtime_and_core_graph(self) -> None:
        """Uses one ScriptRunner runtime and does not construct a legacy observer graph."""

        connected = Mock()
        connected.require_observed_action_executor.return_value = SimpleNamespace(action_executor=object())
        connected.observation_service.observation_builder.visual_recognizer = object()
        connected.observation_service.observation_builder.enricher = object()
        script_runner = Mock()
        script_runner.build_connected_runtime.return_value = connected

        with tempfile.TemporaryDirectory() as temporary_directory:
            trace_path = Path(temporary_directory) / "trace.jsonl"
            with (
                patch("pnc_automation.app.automation.engine.core_runtime.NavigationPerception") as perception,
                patch("pnc_automation.app.automation.engine.core_runtime.NavigationCore") as navigation,
            ):
                result = build_core_runtime(
                    script_runner,
                    SimpleNamespace(artifact_directory_name="account"),
                    "account",
                    trace_path=trace_path,
                )

        script_runner.build_connected_runtime.assert_called_once()
        connected.require_observed_action_executor.assert_called_once()
        perception.assert_called_once()
        navigation.assert_called_once()
        self.assertIs(result.runtime, connected)
        self.assertEqual(trace_path, result.trace_path)

    def test_navigation_perception_preserves_typed_castle_content(self) -> None:
        """Content enrichment can provide identity without changing visual screen controls."""

        identity = CastleIdentity("K1", "Castle", 22)

        class _Recognizer:
            reference_size = (20, 20)

            def recognize(self, image: Image.Image) -> VisualRecognition:
                del image
                return VisualRecognition(
                    evidence=(ScreenEvidence(ScreenType.PNC_CASTLE_SELECTION, "test"),),
                    controls=(
                        VisibleElement(
                            selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                            bounds=Bounds(1, 1, 2, 2),
                            confidence=1.0,
                        ),
                    ),
                )

        class _Guard:
            def detect_interruption(self, image, *, owned_dismiss_bounds=()):
                del image, owned_dismiss_bounds
                return ObservationAdditions()

            def enrich(self, image, screen_type, visible_elements, request):
                del image, screen_type, visible_elements, request
                return ObservationAdditions(
                    current_castle=identity,
                    current_castle_evidence=CurrentCastleEvidenceKind.EXACT,
                )

        screenshot = CapturedScreenshot(
            artifact=None,
            image=Image.new("RGB", (20, 20)),
            image_format="PNG",
            ephemeral_captured_at=datetime.now(tz=UTC),
        )
        observation = NavigationPerception(_Recognizer(), _Guard()).build(screenshot, include_content=True)

        self.assertEqual(ScreenType.PNC_CASTLE_SELECTION, observation.screen_type)
        self.assertEqual(identity, observation.current_castle)
        self.assertEqual(CurrentCastleEvidenceKind.EXACT, observation.current_castle_evidence)
        self.assertEqual(1, len(observation.visible_elements))


class _FakeClock:
    """Deterministic monotonic clock for passive-settle tests."""

    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _SettleNavigation:
    """Navigation surface exposing only policy timing and action-call evidence."""

    def __init__(self, clock: _FakeClock, *, max_seconds: float = 10.0) -> None:
        self._clock = clock
        self.policy = NavigationPolicy(
            max_observations=4,
            max_seconds=max_seconds,
            poll_seconds=0.25,
            stable_observations=2,
        )
        self.navigate_calls: list[ScreenType] = []
        self.sleep_calls: list[float] = []

    def clock(self) -> float:
        return self._clock.clock()

    def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        self._clock.sleep(seconds)

    def navigate(self, target: ScreenType) -> None:
        self.navigate_calls.append(target)


class _SequencedCoreRuntime(CoreRuntime):
    """Core runtime with deterministic typed frames in place of screenshots."""

    __slots__ = ("_frames", "_capture_delays", "_recovered_flags", "_clock")

    def __init__(
        self,
        navigation: _SettleNavigation,
        frames: list[Observation],
        *,
        capture_delays: list[float] | None = None,
        recovered_flags: list[bool] | None = None,
    ) -> None:
        super().__init__(
            runtime=SimpleNamespace(),
            navigation=navigation,
            artifact_directory="account",
            trace_path=Path("trace.jsonl"),
            _perception=Mock(),
            _run_id="test",
        )
        self._frames = list(frames)
        self._capture_delays = list(capture_delays or [0.0] * len(frames))
        self._recovered_flags = list(recovered_flags or [False] * len(frames))
        self._clock = navigation._clock

    def observe(self, label: str, *, include_content: bool = False) -> Observation:
        del label, include_content
        self._capture_count += 1
        self._clock.advance(self._capture_delays.pop(0))
        self._last_observe_recovered = self._recovered_flags.pop(0)
        observation = self._frames.pop(0)
        self._last_observation = observation
        return observation


def _frame(screen: ScreenType, seconds: int, *, blocking_popup: bool = False) -> Observation:
    """Builds a minimal typed frame for runtime startup tests."""

    return _frame_at(
        screen,
        datetime(2026, 9, 10, tzinfo=UTC) + timedelta(seconds=seconds),
        blocking_popup=blocking_popup,
    )


def _frame_at(
    screen: ScreenType,
    captured_at: datetime,
    *,
    blocking_popup: bool = False,
) -> Observation:
    """Builds a minimal typed frame at an explicit capture time."""

    return Observation(
        screen_type=screen,
        visible_elements={},
        captured_at=captured_at,
        blocking_popup=blocking_popup,
    )


def _castle_roster_frame(kingdom: str, name: str, *, selected: bool = False) -> Observation:
    """Build one typed Manage Characters viewport for bounded scan tests."""

    identity = CastleIdentity(kingdom, name, 22)
    return Observation(
        screen_type=ScreenType.PNC_CASTLE_SELECTION,
        visible_elements={},
        list_entries=(
            DetectedListEntry(
                kind=ListEntryKind.CASTLE,
                bounds=Bounds(0, 70, 540, 100),
                title_text=name,
                selected=selected,
                metadata={"kingdom": kingdom, "castle_level": 22},
            ),
        ),
        captured_at=datetime.now(tz=UTC),
        current_castle=identity if selected else None,
        current_castle_evidence=CurrentCastleEvidenceKind.EXACT if selected else None,
    )


if __name__ == "__main__":
    unittest.main()
