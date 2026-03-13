"""Top-level application wiring for the automation platform."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.adb.client import AdbClient
from pnc_automation.automation.runner import RunResult, StepRunResult
from pnc_automation.automation.script_runner import ScriptRunner
from pnc_automation.automation.task import TaskId
from pnc_automation.automation.scripts.registry import build_default_task_registry
from pnc_automation.capture.artifact_store import ArtifactStore
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.config.castle_roster_store import CastleRosterStore
from pnc_automation.config.loader import load_app_config
from pnc_automation.config.models import CastleIdentity
from pnc_automation.diagnostics.logging_setup import configure_logging
from pnc_automation.vision.observation_builder import (
    ObservationBuilder,
    PillowSelectorEngine,
)
from pnc_automation.vision.ocr_service import CachedOcrService, RapidOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier
from pnc_automation.vision.selectors import build_default_selector_registry
from pnc_automation.vision.template_matcher import PillowTemplateMatcher


@dataclass(slots=True)
class ApplicationRunner:
    """Owns the configured runtime used by the CLI entry point."""

    script_runner: ScriptRunner

    def run(self, *, account_id: str, script_path: str) -> RunResult:
        """Executes one account/script combination."""

        return self.script_runner.run(account_id=account_id, script_path=script_path)

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
    ) -> RunResult:
        """Runs the canonical login-and-optional-castle-alignment preparation path."""

        return self.script_runner.prepare_account_session(account_id=account_id, castle=castle)

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
        castle: CastleIdentity | None = None,
    ) -> StepRunResult:
        """Runs one direct task call against the current live session state."""

        return self.script_runner.run_task(account_id=account_id, task_id=task_id, params=params, castle=castle)


def build_application_runner(
    config_path: str | Path,
    *,
    verbose: bool = False,
    catalog_path: Path | None = None,
) -> ApplicationRunner:
    """Builds the configured application runtime for the provided config and selector catalog."""

    root_logger = configure_logging(verbose=verbose)
    logger = logging.LoggerAdapter(root_logger, extra={})
    app_config = load_app_config(config_path)

    artifact_store = ArtifactStore(root=app_config.artifact_root)
    screenshot_service = ScreenshotService(
        artifact_store=artifact_store,
        screenshot_format=app_config.defaults.screenshot_format,
    )
    ocr_service = CachedOcrService(RapidOcrService())
    selector_registry = build_default_selector_registry(catalog_path=catalog_path)
    observation_builder = ObservationBuilder(
        selector_registry=selector_registry,
        selector_engine=PillowSelectorEngine(
            template_matcher=PillowTemplateMatcher(),
            ocr_service=ocr_service,
        ),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(
            ocr_service=ocr_service,
            selector_registry=selector_registry,
        ),
    )
    script_runner = ScriptRunner(
        config=app_config,
        task_registry=build_default_task_registry(),
        screenshot_service=screenshot_service,
        observation_builder=observation_builder,
        castle_roster_store=CastleRosterStore(
            path=app_config.castle_roster_path,
            rosters=app_config.castle_rosters,
        ),
        adb_client=AdbClient(adb_path=app_config.defaults.adb_path),
        logger=logger,
    )
    return ApplicationRunner(script_runner=script_runner)
