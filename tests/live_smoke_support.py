"""Shared helpers for opt-in live BlueStacks smoke tests."""

from __future__ import annotations

from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.models import AccountConfig
from pnc_automation.emulator.bluestacks_instance import BlueStacksInstance
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.vision.observation_builder import ObservationService


def build_live_session(*, config_account: AccountConfig, script_runner: object) -> BlueStacksSession:
    """Creates and connects one live BlueStacks session using the authoritative runtime wiring."""

    config = script_runner.config
    instance = BlueStacksInstance.from_config(config.require_instance(config_account.instance_id))
    session = BlueStacksSession(adb_client=script_runner.adb_client, instance=instance)
    session.connect()
    session.ensure_responsive()
    return session


def build_observation_service(
    *,
    config_account: AccountConfig,
    script_runner: object,
    session: BlueStacksSession,
) -> ObservationService:
    """Builds one live observation service from the same runtime components used by the application."""

    return ObservationService(
        screenshot_service=require_screenshot_service(script_runner),
        observation_builder=script_runner.observation_builder,
        session=session,
        artifact_directory=config_account.artifact_directory_name,
        pnc_account_id=config_account.pnc_account_id,
        castle_roster_store=script_runner.castle_roster_store,
    )


def require_screenshot_service(script_runner: object) -> ScreenshotService:
    """Returns the configured screenshot service or fails fast when the runner shape changes."""

    screenshot_service = getattr(script_runner, "screenshot_service", None)
    if not isinstance(screenshot_service, ScreenshotService):
        raise AssertionError("Live smoke tests require ScriptRunner.screenshot_service.")
    return screenshot_service
