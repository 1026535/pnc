"""Synthetic MailWorkflowFixtures fixture."""

from __future__ import annotations

from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner

from tests.support.core.logging import build_logger



class MailWorkflowFixtures:
    """Shared setup only; deliberately not a TestCase."""

    def setUp(self) -> None:
        """Builds shared runtime inputs used across mail workflow tests."""

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
        self.defaults = DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0)
        self.flows = ScreenFlowPlanner()
        self.logger = build_logger()
