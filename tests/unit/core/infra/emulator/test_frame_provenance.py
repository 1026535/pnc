"""Offline proofs for session-bound frame authorization."""

from __future__ import annotations

import io
import logging
import time
import unittest
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from PIL import Image

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutionPolicy, ObservedActionExecutor
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.pnc.domain.action_requests import TapAction, TapPointAction, TapSpatialObjectAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.errors import DeviceConnectionError, FrameProvenanceError, ScreenshotCaptureError, SelectorResolutionError
from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.emulator.session import BlueStacksSession
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation


@dataclass(slots=True)
class _CaptureAdb:
    shell_result: CommandResult
    capture_callback: object | None = None
    taps: int = 0

    def connect(self, device_id: str) -> CommandResult:
        del device_id
        return _result(stdout_text="connected")

    def get_state(self, device_id: str) -> CommandResult:
        del device_id
        return _result(stdout_text="device")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        del device_id, arguments, timeout_seconds
        self.taps += 1
        return self.shell_result

    def exec_out(self, device_id: str, *arguments: str, timeout_seconds: float | None = 20) -> CommandResult:
        del device_id, arguments, timeout_seconds
        if self.capture_callback is not None:
            callback = self.capture_callback
            self.capture_callback = None
            callback()
        return _result(stdout=build_png_bytes())


class FrameProvenanceTests(unittest.TestCase):
    def test_frame_proof_is_single_use_and_input_invalidates_capture(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        frame = session.capture_screenshot_frame()

        with session.authorized_input(frame.frame_ref):
            session.tap_point(10, 20)
        with self.assertRaises(FrameProvenanceError):
            session.validate_and_consume_frame(frame.frame_ref)

        next_frame = session.capture_screenshot_frame()
        adb.shell_result = _result(returncode=1, stderr_text="tap failed")
        with self.assertRaises(DeviceConnectionError):
            session.tap_point(1, 2)
        with self.assertRaises(FrameProvenanceError):
            session.validate_and_consume_frame(next_frame.frame_ref)

    def test_capture_rejects_input_started_while_screenshot_backend_is_running(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        adb.capture_callback = lambda: session.tap_point(1, 2)

        with self.assertRaisesRegex(ScreenshotCaptureError, "overlapped session input or epoch change"):
            session.capture_screenshot_frame()

    def test_capture_rejects_older_backend_completion_after_newer_capture_started(self) -> None:
        """Prevents an out-of-order backend completion from publishing stale pixels as newest."""

        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        adb.capture_callback = lambda: session.capture_screenshot_frame()

        with self.assertRaisesRegex(ScreenshotCaptureError, "newer capture began"):
            session.capture_screenshot_frame()

    def test_capture_rejects_session_epoch_restart_during_backend_capture(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        adb.capture_callback = session.connect

        with self.assertRaisesRegex(ScreenshotCaptureError, "epoch change"):
            session.capture_screenshot_frame()

    def test_actual_session_age_rejects_expired_frame(self) -> None:
        """Rejects a real captured frame after the bounded monotonic age window."""

        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = BlueStacksSession(
            adb_client=adb,
            instance=BlueStacksInstance(
                id="bs-main",
                display_name="testing",
                device_id="127.0.0.1:5555",
                app_package="com.global.tmslg",
            ),
            provenance_max_age_seconds=0.001,
        )
        frame = session.capture_screenshot_frame()
        time.sleep(0.01)

        with self.assertRaisesRegex(FrameProvenanceError, "bounded frame age"):
            session.validate_and_consume_frame(frame.frame_ref)

    def test_newest_capture_invalidates_previous_frame_without_input(self) -> None:
        """Rejects an older capture as soon as a newer capture becomes the latest frame."""

        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        first = session.capture_screenshot_frame()
        second = session.capture_screenshot_frame()

        with self.assertRaisesRegex(FrameProvenanceError, "stale"):
            session.validate_and_consume_frame(first.frame_ref)
        session.validate_and_consume_frame(second.frame_ref)

    def test_failed_dispatch_is_not_replayed_by_action_executor(self) -> None:
        session = _FailingInputSession()
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
            frame_ref=_frame_ref("action-test", 1),
        )
        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=logging.LoggerAdapter(logging.getLogger("frame-provenance"), extra={}),
            sleep=lambda _: None,
        )

        with self.assertRaises(DeviceConnectionError):
            executor.execute_action(
                TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON),
                observation,
            )
        self.assertEqual(session.attempts, 1)

    def test_observed_executor_preserves_adb_failure_without_refresh_or_retry(self) -> None:
        session = _FailingInputSession()
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
            frame_ref=_frame_ref("observed-failure", 1),
        )
        refresh_labels: list[str] = []
        observed = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=_build_executor(session),
            logger=build_logger(),
            canonical_observe=lambda label, request=None: refresh_labels.append(label) or observation,
        )

        with self.assertRaises(DeviceConnectionError):
            observed.execute_action(
                TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON),
                observation,
            )
        self.assertEqual(session.attempts, 1)
        self.assertEqual(refresh_labels, [])

    def test_action_executor_rejects_missing_and_foreign_proofs(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        executor = _build_executor(session)
        action = TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON)

        missing = replace(
            make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
            ),
            frame_ref=None,
        )
        with self.assertRaisesRegex(SelectorResolutionError, "requires a screenshot with session provenance"):
            executor.execute_action(
                action,
                missing,
            )
        with self.assertRaises(FrameProvenanceError):
            session.validate_and_consume_frame(_frame_ref("foreign-session", 1))

    def test_observed_executor_refreshes_only_stale_proof_and_retries_once(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        first = session.capture_screenshot_frame()
        initial = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
            frame_ref=first.frame_ref,
        )
        session.tap_point(2, 3)
        refreshed = session.capture_screenshot_frame()
        refreshed_observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
            frame_ref=refreshed.frame_ref,
        )
        observed = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=_build_executor(session),
            logger=build_logger(),
            canonical_observe=lambda label, request=None: refreshed_observation,
        )

        self.assertTrue(
            observed.execute_action(
                TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON),
                initial,
            )
        )
        self.assertEqual(adb.taps, 2)

    def test_read_only_policy_rejects_unknown_selector_source_and_update_recovery(self) -> None:
        selector = UiElementId.PNC_HOME_BUILD_BUTTON
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_selectors=frozenset({selector}),
            allowed_selector_screens=((selector, frozenset({ScreenType.PNC_HOME_CITY})),),
        )
        with self.assertRaises(SelectorResolutionError):
            policy.validate(
                TapAction(selector_id=selector),
                make_observation(ScreenType.UNKNOWN, visible_ids=(selector,)),
            )
        observed = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=_build_executor(_FailingInputSession()),
            logger=build_logger(),
            policy=ObservedActionExecutionPolicy(read_only_policy=policy),
        )
        update = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "refuses required-update recovery"):
            observed.execute_actions((), update, observe=lambda label, request=None: update)

    def test_read_only_allowed_tap_does_not_confirm_post_action_update(self) -> None:
        """Stops after an allowed tap when the resulting observation is a required update."""

        selector = UiElementId.PNC_HOME_BUILD_BUTTON
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_selectors=frozenset({selector}),
            allowed_selector_screens=((selector, frozenset({ScreenType.PNC_HOME_CITY})),),
        )
        session = _RecordingInputSession()
        initial = make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(selector,))
        update = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
        )
        observed = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=_build_executor(session),
            logger=build_logger(),
            policy=ObservedActionExecutionPolicy(read_only_policy=policy),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "refuses required-update recovery"):
            observed.execute_actions(
                (TapAction(selector_id=selector, observe_after=True),),
                initial,
                observe=lambda label, request=None: update,
            )
        self.assertEqual(session.taps, 1)

    def test_blocked_screen_rejects_spatial_target_point(self) -> None:
        """A blocking overlay may authorize its selector controls, never a raw spatial point."""

        session = _RecordingInputSession()
        executor = _build_executor(session)
        observation = make_observation(
            ScreenType.PNC_POPUP,
            blocking_popup=True,
            frame_ref=_frame_ref("blocked-spatial", 1),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "blocked screen authorizes only controls"):
            executor.execute_action(
                TapSpatialObjectAction(target_point=(40, 50)),
                observation,
            )
        self.assertEqual(session.taps, 0)

    def test_low_level_input_budget_counts_actual_attempts(self) -> None:
        session = _RecordingInputSession()
        executor = _build_executor(session)
        executor.configure_input_attempt_budget(1)
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,),
        )
        executor.execute_action(TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON), observation)
        with self.assertRaisesRegex(SelectorResolutionError, "exhausted"):
            executor.execute_action(TapAction(selector_id=UiElementId.PNC_HOME_BUILD_BUTTON), make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_HOME_BUILD_BUTTON,)))
        self.assertEqual(session.taps, 1)

    def test_observed_executor_rejects_stale_raw_coordinate_reuse(self) -> None:
        adb = _CaptureAdb(shell_result=_result(stdout_text=""))
        session = _make_session(adb)
        initial_frame = session.capture_screenshot_frame()
        initial = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=initial_frame.frame_ref)
        session.tap_point(4, 5)
        refreshed_frame = session.capture_screenshot_frame()
        refreshed = make_observation(ScreenType.PNC_HOME_CITY, frame_ref=refreshed_frame.frame_ref)
        observed = ObservedActionExecutor(
            selector_registry=build_default_selector_registry(),
            action_executor=_build_executor(session),
            logger=build_logger(),
            canonical_observe=lambda label, request=None: refreshed,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "coordinate proof"):
            observed.execute_action(TapPointAction(x=10, y=20), initial)
        self.assertEqual(adb.taps, 1)


@dataclass(slots=True)
class _FailingInputSession:
    attempts: int = 0

    @contextmanager
    def authorized_input(self, frame_ref: FrameRef):
        del frame_ref
        yield

    def tap_point(self, x: int, y: int) -> None:
        del x, y
        self.attempts += 1
        raise DeviceConnectionError("ADB tap failed after dispatch attempt.")


@dataclass(slots=True)
class _RecordingInputSession:
    taps: int = 0

    @contextmanager
    def authorized_input(self, frame_ref: FrameRef):
        del frame_ref
        yield

    def tap_point(self, x: int, y: int) -> None:
        del x, y
        self.taps += 1


def _make_session(adb: _CaptureAdb) -> BlueStacksSession:
    return BlueStacksSession(
        adb_client=adb,
        instance=BlueStacksInstance(
            id="bs-main",
            display_name="testing",
            device_id="127.0.0.1:5555",
            app_package="com.global.tmslg",
        ),
        connect_attempts=1,
        sleep=lambda _: None,
    )


def _build_executor(session: object) -> ActionExecutor:
    """Builds a zero-delay executor for provenance tests."""

    return ActionExecutor(
        selector_registry=build_default_selector_registry(),
        session=session,
        stable_click_delay_ms=0,
        post_action_observe_delay_ms=0,
        chat_stable_click_delay_ms=0,
        chat_post_action_observe_delay_ms=0,
        logger=build_logger(),
        sleep=lambda _: None,
    )


def _frame_ref(session_id: str, capture_sequence: int) -> FrameRef:
    return FrameRef(
        session_id=session_id,
        session_epoch=1,
        capture_sequence=capture_sequence,
        input_sequence=0,
        captured_at=datetime.now(tz=UTC),
        captured_monotonic=__import__("time").monotonic(),
    )


def build_png_bytes() -> bytes:
    """Builds one valid screenshot payload for the capture seam."""

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _result(*, returncode: int = 0, stdout: bytes = b"", stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout if stdout else stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


if __name__ == "__main__":
    unittest.main()
