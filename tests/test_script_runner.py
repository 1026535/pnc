"""Script-runner runtime wiring tests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path

from pnc_automation.core.infra.adb.command_result import CommandResult
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.app.runtime.observation_artifacts import ObservationArtifactKind, observation_artifact_selection
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    AppConfig,
    BlueStacksInstanceConfig,
    DefaultsConfig,
    RuntimeConfig,
)
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from tests.test_support import build_logger
from tests.test_support import build_png_bytes, make_observation, make_spatial_object, make_spatial_surface


@dataclass(slots=True)
class _FakeAdbClient:
    """Records canonical session-connect calls while returning ready command results."""

    connect_calls: list[str] = field(default_factory=list)
    state_calls: list[str] = field(default_factory=list)
    shell_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    exec_out_calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def connect(self, device_id: str) -> CommandResult:
        """Records one ADB connect call and returns success."""

        self.connect_calls.append(device_id)
        return _command_result(returncode=0, stdout_text="connected")

    def get_state(self, device_id: str) -> CommandResult:
        """Records one ADB get-state call and returns a ready device."""

        self.state_calls.append(device_id)
        return _command_result(returncode=0, stdout_text="device")

    def shell(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Records one shell command and returns a non-empty readiness response."""

        del timeout_seconds
        self.shell_calls.append((device_id, arguments))
        return _command_result(returncode=0, stdout_text="BlueStacks")

    def exec_out(self, device_id: str, *arguments: str, timeout_seconds: float | None = 10) -> CommandResult:
        """Records one binary adb exec-out call and returns a deterministic PNG payload."""

        del timeout_seconds
        self.exec_out_calls.append((device_id, arguments))
        return _binary_command_result(returncode=0, stdout=build_png_bytes(size=(40, 40), color=(15, 28, 68, 255)))


@dataclass(slots=True)
class _FakeInstanceResolver:
    """Returns one seeded runtime BlueStacks instance while recording the requested config."""

    resolved_instance: BlueStacksInstance
    requested_configs: list[BlueStacksInstanceConfig] = field(default_factory=list)

    def resolve(self, config: BlueStacksInstanceConfig) -> BlueStacksInstance:
        """Records the authored instance config and returns the seeded runtime instance."""

        self.requested_configs.append(config)
        return self.resolved_instance


class ScriptRunnerTests(unittest.TestCase):
    """Validates canonical runtime session construction in the script runner."""

    def test_build_connected_session_uses_resolved_runtime_device_id(self) -> None:
        """Connects through the resolver-provided device id instead of any authored endpoint field."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            authored_instance = BlueStacksInstanceConfig(
                id="bs-main",
                display_name="serious_stuff",
                app_package="com.global.tmslg",
            )
            account = AccountConfig(
                id="account_a",
                instance_id="bs-main",
                pnc_account_id="inline_user",
            )
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5566",
                    app_package="com.global.tmslg",
                )
            )
            adb_client = _FakeAdbClient()
            script_runner = ScriptRunner(
                config=_make_app_config(root=root, instance=authored_instance, account=account),
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=object(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            session = script_runner.build_connected_session(account=account)

            self.assertEqual(resolver.requested_configs, [authored_instance])
            self.assertEqual(session.instance.device_id, "127.0.0.1:5566")
            self.assertEqual(adb_client.connect_calls, ["127.0.0.1:5566"])
            self.assertEqual(adb_client.state_calls, ["127.0.0.1:5566"])
            self.assertEqual(adb_client.shell_calls, [("127.0.0.1:5566", ("getprop", "ro.product.model"))])

    def test_build_connected_runtime_exposes_the_canonical_session_and_observation_service(self) -> None:
        """Builds one reusable connected runtime bundle for tooling through the same canonical wiring."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            authored_instance = BlueStacksInstanceConfig(
                id="bs-main",
                display_name="serious_stuff",
                app_package="com.global.tmslg",
            )
            account = AccountConfig(
                id="account_a",
                instance_id="bs-main",
                pnc_account_id="inline_user",
            )
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5566",
                    app_package="com.global.tmslg",
                )
            )
            adb_client = _FakeAdbClient()
            screenshot_service = object()
            defaults = DefaultsConfig(
                bluestacks_config_path=root / "bluestacks.conf",
                stable_click_delay_ms=111,
                post_action_observe_delay_ms=222,
                chat_stable_click_delay_ms=333,
                chat_post_action_observe_delay_ms=444,
                world_map_movement_stable_click_delay_ms=555,
                world_map_movement_post_action_observe_delay_ms=666,
            )
            observation_builder = type(
                "FakeObservationBuilder",
                (),
                {"selector_registry": build_default_selector_registry()},
            )()
            script_runner = ScriptRunner(
                config=_make_app_config(root=root, instance=authored_instance, account=account, defaults=defaults),
                task_registry=object(),
                screenshot_service=screenshot_service,
                observation_builder=observation_builder,
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            runtime = script_runner.build_connected_runtime(account=account)

            self.assertEqual(runtime.session.instance.device_id, "127.0.0.1:5566")
            self.assertIs(runtime.observation_service.screenshot_service, screenshot_service)
            self.assertIs(runtime.observation_service.observation_builder, observation_builder)
            self.assertIs(runtime.observation_service.session, runtime.session)
            self.assertEqual(runtime.observation_service.artifact_directory, account.artifact_directory_name)
            self.assertEqual(runtime.observation_service.mode, ObservationMode.DEBUG)
            self.assertIs(runtime.world_map_survey_recorder.observation_service, runtime.observation_service)
            self.assertEqual(runtime.world_map_survey_recorder.debug_store.root, root / "artifacts")
            self.assertIs(runtime.world_map_search_service.screen_flows, runtime.flow_planner)
            self.assertIs(runtime.world_map_search_service.survey_recorder, runtime.world_map_survey_recorder)
            self.assertIs(runtime.world_map_movement_calibration_service.screen_flows, runtime.flow_planner)
            self.assertIs(runtime.world_map_movement_calibration_service.survey_recorder, runtime.world_map_survey_recorder)
            self.assertIsNotNone(runtime.observed_action_executor)
            assert runtime.observed_action_executor is not None
            action_executor = runtime.observed_action_executor.action_executor
            self.assertIs(action_executor.session, runtime.session)
            self.assertEqual(action_executor.stable_click_delay_ms, 111)
            self.assertEqual(action_executor.post_action_observe_delay_ms, 222)
            self.assertEqual(action_executor.chat_stable_click_delay_ms, 333)
            self.assertEqual(action_executor.chat_post_action_observe_delay_ms, 444)
            self.assertEqual(action_executor.world_map_movement_stable_click_delay_ms, 555)
            self.assertEqual(action_executor.world_map_movement_post_action_observe_delay_ms, 666)
            self.assertIs(runtime.world_map_search_service.action_executor, runtime.observed_action_executor)
            self.assertIs(runtime.world_map_movement_calibration_service.action_executor, runtime.observed_action_executor)
            self.assertEqual(runtime.world_map_movement_calibration_store.root, root / "artifacts")
            runner = script_runner.build_connected_automation_runner(account=account)
            self.assertIs(runner.world_map_search_service.survey_recorder, runner.world_map_survey_recorder)

    def test_build_connected_runtime_bundle_shares_runtime_services_with_runner(self) -> None:
        """Builds one runtime-plus-runner graph when a live tool needs shared mutable service identity."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            authored_instance = BlueStacksInstanceConfig(
                id="bs-main",
                display_name="serious_stuff",
                app_package="com.global.tmslg",
            )
            account = AccountConfig(
                id="account_a",
                instance_id="bs-main",
                pnc_account_id="inline_user",
            )
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5566",
                    app_package="com.global.tmslg",
                )
            )
            adb_client = _FakeAdbClient()
            observation_builder = type(
                "FakeObservationBuilder",
                (),
                {"selector_registry": build_default_selector_registry()},
            )()
            script_runner = ScriptRunner(
                config=_make_app_config(root=root, instance=authored_instance, account=account),
                task_registry=object(),
                screenshot_service=object(),
                observation_builder=observation_builder,
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            connected = script_runner.build_connected_runtime_bundle(account=account)

            self.assertEqual(resolver.requested_configs, [authored_instance])
            self.assertEqual(adb_client.connect_calls, ["127.0.0.1:5566"])
            self.assertIs(connected.runner.observation_service, connected.runtime.observation_service)
            self.assertIs(connected.runner.action_executor, connected.runtime.observed_action_executor)
            self.assertIs(connected.runner.flow_planner, connected.runtime.flow_planner)
            self.assertIs(connected.runner.world_map_survey_recorder, connected.runtime.world_map_survey_recorder)
            self.assertIs(connected.runner.world_map_search_service, connected.runtime.world_map_search_service)
            self.assertIs(
                connected.runtime.world_map_movement_calibration_service.search_service,
                connected.runtime.world_map_search_service,
            )

    def test_build_connected_runtime_wires_world_map_survey_recorder_through_real_runtime_capture(self) -> None:
        """Builds the recorder through ScriptRunner and persists one real runtime checkpoint dump under artifacts."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            authored_instance = BlueStacksInstanceConfig(
                id="bs-main",
                display_name="serious_stuff",
                app_package="com.global.tmslg",
            )
            account = AccountConfig(
                id="account_a",
                instance_id="bs-main",
                pnc_account_id="inline_user",
            )
            resolver = _FakeInstanceResolver(
                resolved_instance=BlueStacksInstance(
                    id="bs-main",
                    display_name="serious_stuff",
                    device_id="127.0.0.1:5566",
                    app_package="com.global.tmslg",
                )
            )
            adb_client = _FakeAdbClient()
            script_runner = ScriptRunner(
                config=_make_app_config(
                    root=root,
                    instance=authored_instance,
                    account=account,
                    observation_mode=ObservationMode.LIGHT,
                ),
                task_registry=object(),
                screenshot_service=ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")),
                observation_builder=_WorldMapObservationBuilder(),
                castle_roster_store=None,
                mail_archive_store=None,
                chat_archive_store=None,
                adb_client=adb_client,
                instance_resolver=resolver,
                logger=build_logger(),
            )

            runtime = script_runner.build_connected_runtime(account=account)
            result = runtime.world_map_survey_recorder.capture_checkpoint(
                "survey_step",
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.WORLD_MAP_SURVEY_STATE),
            )

            self.assertIsNone(result.capture.screenshot.artifact_path)
            self.assertIsNotNone(result.debug_dump)
            assert result.debug_dump is not None
            self.assertEqual(result.debug_dump.path.parent.name, "world_map_surveys")
            self.assertEqual(result.debug_dump.path.parent.parent.name, account.artifact_directory_name)
            self.assertTrue(result.debug_dump.path.is_file())
            self.assertEqual(adb_client.exec_out_calls, [("127.0.0.1:5566", ("screencap", "-p"))])
            self.assertEqual(
                result.debug_dump.document["checkpoint"]["artifact_directory"],
                account.artifact_directory_name,
            )
            self.assertEqual(
                result.debug_dump.document["checkpoint"]["surface_type"],
                SpatialSurfaceType.WORLD_MAP.value,
            )


@dataclass(slots=True)
class _WorldMapObservationBuilder:
    """Builds one deterministic world-map observation while preserving screenshot provenance."""

    def build(self, screenshot: object, *, request: ObservationRequest | None = None) -> object:
        """Returns a typed world-map observation with the current screenshot path and capture time."""

        del request
        return replace(
            make_observation(
                ScreenType.PNC_WORLD_MAP,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.WORLD_MAP,
                    x=253,
                    y=447,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="VisibleCastle",
                            kingdom="K287",
                            viewport_offset=(4, 252),
                            viewport_offset_ratio=(4 / 900, 252 / 1184),
                            estimated_world_coordinate=(201, 659),
                        ),
                    ),
                ),
            ),
            artifact_path=screenshot.artifact_path,
            captured_at=screenshot.captured_at,
        )


def _make_app_config(
    *,
    root: Path,
    instance: BlueStacksInstanceConfig,
    account: AccountConfig,
    defaults: DefaultsConfig | None = None,
    observation_mode: ObservationMode = ObservationMode.DEBUG,
) -> AppConfig:
    """Builds one minimal validated-looking app config for script-runner session tests."""

    artifact_root = root / "artifacts"
    archive_root = root / "archives"
    artifact_root.mkdir()
    archive_root.mkdir()
    return AppConfig(
        config_path=root / "accounts.yaml",
        castle_roster_path=root / "castles.yaml",
        castle_targets_path=root / "castle_targets.yaml",
        mail_definitions_path=root / "mail_definitions.yaml",
        mail_schedules_path=root / "mail_schedules.yaml",
        artifact_root=artifact_root,
        archive_root=archive_root,
        defaults=defaults or DefaultsConfig(bluestacks_config_path=root / "bluestacks.conf"),
        runtime=RuntimeConfig(observation_mode=observation_mode),
        instances=(instance,),
        accounts=(account,),
    )


def _command_result(*, returncode: int, stdout_text: str = "", stderr_text: str = "") -> CommandResult:
    """Builds one deterministic raw ADB command result for runtime wiring tests."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout_text.encode("utf-8"),
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


def _binary_command_result(*, returncode: int, stdout: bytes = b"", stderr_text: str = "") -> CommandResult:
    """Builds one deterministic raw ADB command result for binary stdout payloads."""

    return CommandResult(
        command=("adb",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr_text.encode("utf-8"),
        duration_seconds=0.01,
    )


if __name__ == "__main__":
    unittest.main()
