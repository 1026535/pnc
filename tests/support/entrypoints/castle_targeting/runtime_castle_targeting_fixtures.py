"""Synthetic RuntimeCastleTargetingFixtures fixture."""

from __future__ import annotations

from pnc_automation.app.authoring.config.models import (
    AccountConfig,
    CredentialSource,
    DefaultsConfig,
    ResolvedCredentials,
)
from pnc_automation.app.pnc.domain.castles import CastleIdentity



class RuntimeCastleTargetingFixtures:
    """Shared setup only; deliberately not a TestCase."""

    def setUp(self) -> None:
        """Builds shared account and castle identities for runtime-targeting tests."""

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
        self.target_castle = CastleIdentity(kingdom="K230", castle_name="Main", castle_level=8)
