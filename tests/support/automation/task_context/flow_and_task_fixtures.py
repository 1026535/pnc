"""Shared FlowAndTaskFixtures setup."""

from __future__ import annotations

from collections.abc import Callable

from pnc_automation.app.authoring.scripts.models import ScriptStep
from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.engine.task_context import TaskContext
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner

from tests.support.core.logging import build_logger


class FlowAndTaskFixtures:
    """Shared setup without connected workflow composition."""

    def setUp(self) -> None:
        """Builds shared task context inputs."""

        self.account = AccountConfig(
            id="account_a",
            instance_id="bs-main",
            pnc_account_id="user@example.com",
            credentials=ResolvedCredentials(
                username="user@example.com",
                password="secret",
                source=CredentialSource.INLINE,
            ),
        )
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.flows = ScreenFlowPlanner()
        self.logger = build_logger()

    def _make_context(
        self,
        *,
        params: object,
        task_id: TaskId = TaskId.ENSURE_GAME_RUNNING,
        target_castle: CastleIdentity | None = None,
        castle_roster_provider: Callable[[], PncAccountCastleRosterConfig | None] | None = None,
        castle_roster_store: CastleRosterStore | None = None,
    ) -> TaskContext:
        """Builds one task context with the shared test account and flow planner."""

        return TaskContext(
            account=self.account,
            castle_roster_provider=(lambda: None) if castle_roster_provider is None else castle_roster_provider,
            defaults=self.defaults,
            step=ScriptStep(task=task_id),
            params=params,
            flows=self.flows,
            logger=self.logger,
            target_castle=target_castle,
            castle_roster_store=castle_roster_store,
        )
