"""Shared active-castle resolution coverage retained after typed selection migration."""

from __future__ import annotations

import unittest

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.active_castle_resolution import remember_active_castle_identity
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.automation.task_context.flow_and_task_fixtures import FlowAndTaskFixtures
from tests.support.pnc.observations import make_observation


class ActiveCastleResolutionTests(FlowAndTaskFixtures, unittest.TestCase):
    """Proves the legacy archive-task identity helper remains available to its callers."""

    def test_name_only_identity_prefers_exact_roster_variant(self) -> None:
        target = CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=12)
        observed_variant = CastleIdentity(kingdom="K226", castle_name="please bgentle", castle_level=12)
        roster = PncAccountCastleRosterConfig(
            pnc_account_id=self.account.pnc_account_id,
            castles=(target, observed_variant),
        )
        context = self._make_context(
            params=None,
            task_id=TaskId.COLLECT_KINGDOM_CHAT,
            castle_roster_provider=lambda: roster,
        )

        resolved = remember_active_castle_identity(
            context,
            make_observation(ScreenType.PNC_LORD_INFO, current_castle_name="please bgentle"),
        )

        self.assertEqual(resolved, observed_variant)


if __name__ == "__main__":
    unittest.main()
