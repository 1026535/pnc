"""Synthetic FakeScriptRunner fixture."""

from __future__ import annotations

from pnc_automation.app.authoring.config.models import LiveAutomationRole



class _FakeScriptRunner:
    """Provides the canonical configuration surface used by CLI role checks."""

    def __init__(self) -> None:
        """Initializes one permissive role fixture."""

        self.config = self

    def require_account(self, account_id: str):
        """Returns an account-shaped role fixture."""

        del account_id
        return self

    def require_live_role(self, required_role: LiveAutomationRole) -> None:
        """Accepts the requested role for routing tests."""

        del required_role
