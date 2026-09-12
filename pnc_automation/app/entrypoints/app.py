"""Top-level application wiring for the automation platform."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pnc_automation.core.infra.adb.client import AdbClient
from pnc_automation.core.vision.observation_policy import ObservationMode
from pnc_automation.app.automation.engine.runner import RunResult, StepRunResult
from pnc_automation.app.automation.engine.core_runtime import build_core_runtime
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult, CoreWorkflowRunner
from pnc_automation.app.automation.engine.script_runner import ScriptRunner
from pnc_automation.core.infra.emulator.session import BlueStacksSessionCleanupPolicy
from pnc_automation.core.lifecycle import close_preserving_error
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.open_building import OpenBuildingResult, build_open_building_workflow
from pnc_automation.app.automation.refresh_castle_roster import RefreshCastleRosterResult, RefreshCastleRosterWorkflow
from pnc_automation.app.automation.daily_maintenance.daily_quest_status import (
    DailyQuestStatusResult,
    DailyQuestStatusWorkflow,
)
from pnc_automation.app.entrypoints.task_registry import build_default_task_registry
from pnc_automation.app.automation.collect_mail import CollectMailResult, CollectMailWorkflow
from pnc_automation.app.automation.collect_kingdom_chat import (
    CollectKingdomChatResult,
    CollectKingdomChatWorkflow,
)
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.app.pnc.persistence.chat_archive_store import ChatArchiveStore
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.authoring.config.loader import load_app_config
from pnc_automation.app.authoring.config.models import AppConfig, LiveAutomationRole
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.mail import parse_collect_mail_params
from pnc_automation.core.infra.diagnostics.logging_setup import configure_logging
from pnc_automation.core.infra.emulator.bluestacks_instance_resolver import BlueStacksInstanceResolver
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ObservationDebugArtifactCollector,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import RapidOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.bluestacks_management.instance_lease import InstanceLeaseBundle
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher


@dataclass(slots=True)
class ApplicationRunner:
    """Owns the configured runtime used by the CLI entry point."""

    script_runner: ScriptRunner

    def reserve_accounts(self, account_ids: tuple[str, ...]) -> InstanceLeaseBundle:
        """Reserves every physical instance used by the supplied accounts."""

        return self.script_runner.reserve_accounts(account_ids)

    def run(
        self,
        *,
        account_id: str,
        script_path: str,
        castle_refs: list[str] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Executes one script for an account and optional ordered castle aliases."""

        return self.script_runner.run(
            account_id=account_id,
            script_path=script_path,
            castle_refs=castle_refs,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def prepare_account_session(
        self,
        *,
        account_id: str,
        castle: CastleIdentity | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Runs the canonical login-and-optional-castle-alignment preparation path."""

        return self.script_runner.prepare_account_session(
            account_id=account_id,
            castle=castle,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def run_task(
        self,
        *,
        account_id: str,
        task_id: TaskId,
        params: dict[str, object] | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> StepRunResult:
        """Runs one direct task call against the current live session state."""

        return self.script_runner.run_task(
            account_id=account_id,
            task_id=task_id,
            params=params,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def run_mail_schedules(
        self,
        *,
        account_id: str,
        schedule_ids: list[str] | None = None,
        scheduled_for_utc: datetime | None = None,
        required_role: LiveAutomationRole | None = None,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> RunResult:
        """Runs the authored scheduled-mail expansion path for one account."""

        return self.script_runner.run_mail_schedules(
            account_id=account_id,
            schedule_ids=schedule_ids,
            scheduled_for_utc=scheduled_for_utc,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )

    def run_daily_quest_status(
        self,
        *,
        account_id: str,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> CoreWorkflowResult[DailyQuestStatusResult]:
        """Preflights the active castle and reports one visible Daily Quest viewport."""

        account = self.script_runner.config.require_account(account_id)
        core_runtime = build_core_runtime(
            self.script_runner,
            account,
            account.artifact_directory_name,
            required_role=LiveAutomationRole.DAILY_CANARY,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            core_runtime.preflight_active_castle_identity()
            result = CoreWorkflowRunner[DailyQuestStatusResult](core_runtime).run(DailyQuestStatusWorkflow())
        except BaseException as error:
            close_preserving_error(
                core_runtime.close,
                error,
                message="Daily canary execution and BlueStacks phase cleanup both failed.",
            )
            raise
        core_runtime.close()
        return result

    def run_collect_mail(
        self,
        *,
        account_id: str,
        params: Mapping[str, object],
        required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> CoreWorkflowResult[CollectMailResult]:
        """Runs the typed collect-mail workflow after validation and active-castle preflight."""

        account = self.script_runner.config.require_account(account_id)
        parsed_params = parse_collect_mail_params(task_label=TaskId.COLLECT_MAIL, params=params)
        archive_store = self.script_runner.mail_archive_store
        if archive_store is None:
            raise RuntimeError(
                "Collect-mail replacement workflow requires a configured MailArchiveStore before connecting."
            )
        core_runtime = build_core_runtime(
            self.script_runner,
            account,
            account.artifact_directory_name,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            active_castle = core_runtime.preflight_active_castle_identity()
            workflow = CollectMailWorkflow(
                params=parsed_params,
                account_id=account.id,
                pnc_account_id=account.pnc_account_id,
                active_castle=active_castle.castle_name,
                archive_store=archive_store,
            )
            result = CoreWorkflowRunner[CollectMailResult](core_runtime).run(workflow)
        except BaseException as error:
            close_preserving_error(
                core_runtime.close,
                error,
                message="Collect-mail execution and BlueStacks phase cleanup both failed.",
            )
            raise
        core_runtime.close()
        return result

    def run_collect_kingdom_chat(
        self,
        *,
        account_id: str,
        required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> CoreWorkflowResult[CollectKingdomChatResult]:
        """Archives one typed Kingdom Chat viewport after exact active-castle preflight."""

        account = self.script_runner.config.require_account(account_id)
        archive_store = self.script_runner.chat_archive_store
        if archive_store is None:
            raise RuntimeError(
                "Kingdom Chat replacement workflow requires a configured ChatArchiveStore before connecting."
            )
        core_runtime = build_core_runtime(
            self.script_runner,
            account,
            account.artifact_directory_name,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            active_castle = core_runtime.preflight_active_castle_identity()
            workflow = CollectKingdomChatWorkflow(
                account_id=account.id,
                active_castle=active_castle,
                archive_store=archive_store,
            )
            result = CoreWorkflowRunner[CollectKingdomChatResult](core_runtime).run(workflow)
        except BaseException as error:
            close_preserving_error(
                core_runtime.close,
                error,
                message="Kingdom Chat execution and BlueStacks phase cleanup both failed.",
            )
            raise
        core_runtime.close()
        return result

    def run_open_building(
        self,
        *,
        account_id: str,
        building: str,
        required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> CoreWorkflowResult[OpenBuildingResult]:
        """Prevalidates and opens one modeled building through the replacement core."""

        workflow = build_open_building_workflow({"building": building})
        account = self.script_runner.config.require_account(account_id)
        core_runtime = build_core_runtime(
            self.script_runner,
            account,
            account.artifact_directory_name,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            core_runtime.preflight_active_castle_identity()
            result = CoreWorkflowRunner[OpenBuildingResult](core_runtime).run(workflow)
        except BaseException as error:
            close_preserving_error(
                core_runtime.close,
                error,
                message="Open-building execution and BlueStacks phase cleanup both failed.",
            )
            raise
        core_runtime.close()
        return result

    def run_refresh_castle_roster(
        self,
        *,
        account_id: str,
        required_role: LiveAutomationRole = LiveAutomationRole.LIVE_TESTING,
        session_cleanup_policy: BlueStacksSessionCleanupPolicy | None = None,
    ) -> CoreWorkflowResult[RefreshCastleRosterResult]:
        """Runs the typed full-roster scan after validating its store before connecting."""

        account = self.script_runner.config.require_account(account_id)
        roster_store = self.script_runner.castle_roster_store
        if roster_store is None:
            raise RuntimeError(
                "Refresh-castle-roster replacement workflow requires a configured CastleRosterStore before connecting."
            )
        core_runtime = build_core_runtime(
            self.script_runner,
            account,
            account.artifact_directory_name,
            required_role=required_role,
            session_cleanup_policy=session_cleanup_policy,
        )
        try:
            active_castle = core_runtime.preflight_active_castle_identity()
            workflow = RefreshCastleRosterWorkflow(
                account_id=account.id,
                pnc_account_id=account.pnc_account_id,
                active_castle=active_castle,
                roster_store=roster_store,
            )
            result = CoreWorkflowRunner[RefreshCastleRosterResult](core_runtime).run(workflow)
        except BaseException as error:
            close_preserving_error(
                core_runtime.close,
                error,
                message="Castle-roster refresh execution and BlueStacks phase cleanup both failed.",
            )
            raise
        core_runtime.close()
        return result


def build_application_runner(
    config_path: str | Path,
    *,
    verbose: bool = False,
    catalog_path: Path | None = None,
    observation_mode: ObservationMode | None = None,
) -> ApplicationRunner:
    """Builds the configured application runtime for the provided config and selector catalog."""

    root_logger = configure_logging(verbose=verbose)
    logger = logging.LoggerAdapter(root_logger, extra={})
    loaded_config = load_app_config(config_path)
    app_config = loaded_config if observation_mode is None else _override_observation_mode(
        loaded_config,
        observation_mode=observation_mode,
    )

    artifact_store = ArtifactStore(root=app_config.artifact_root)
    screenshot_service = ScreenshotService(
        artifact_store=artifact_store,
        screenshot_format=app_config.defaults.screenshot_format,
    )
    selector_registry = build_default_selector_registry(catalog_path=catalog_path)
    observation_builder = build_observation_builder(selector_registry)
    script_runner = ScriptRunner(
        config=app_config,
        task_registry=build_default_task_registry(),
        screenshot_service=screenshot_service,
        observation_builder=observation_builder,
        castle_roster_store=CastleRosterStore(
            path=app_config.castle_roster_path,
            rosters=app_config.castle_rosters,
        ),
        mail_archive_store=MailArchiveStore(root=app_config.archive_root / "mail"),
        chat_archive_store=ChatArchiveStore(root=app_config.archive_root / "chat"),
        adb_client=AdbClient(adb_path=app_config.defaults.adb_path),
        instance_resolver=BlueStacksInstanceResolver(config_path=app_config.defaults.bluestacks_config_path),
        logger=logger,
        p2_observation_builder_factory=lambda: build_observation_builder(selector_registry),
    )
    return ApplicationRunner(script_runner=script_runner)


def build_observation_builder(selector_registry: SelectorRegistry) -> ObservationBuilder:
    """Builds one independently owned observation pipeline and OCR engine."""

    ocr_service = RapidOcrService()
    template_matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=selector_registry,
        selector_engine=ImageSelectorEngine(
            template_matcher=template_matcher,
        ),
        screen_classifier=ScreenClassifier(),
        ocr_service=ocr_service,
        enricher=PncObservationEnricher(
            selector_registry=selector_registry,
        ),
        debug_artifact_collector=ObservationDebugArtifactCollector(),
        visual_recognizer=load_visual_screen_recognizer(matcher=template_matcher),
    )


def _override_observation_mode(config: AppConfig, *, observation_mode: ObservationMode) -> AppConfig:
    """Returns the loaded app config with one CLI-selected observation mode override applied."""

    from dataclasses import replace

    return replace(
        config,
        runtime=replace(config.runtime, observation_mode=observation_mode),
    )

