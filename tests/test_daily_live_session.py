"""Offline checks for connected Daily Quest update recovery."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from tests.test_support import make_observation


class ConnectedDailyQuestSessionTests(unittest.TestCase):
    """Proves Daily observations resume after shared required-update recovery."""

    def test_daily_observation_reopens_daily_after_update_recovery(self) -> None:
        """Returns a fresh Daily frame after update recovery restores Home."""

        update = make_observation(
            ScreenType.PNC_POPUP,
            visible_ids=(UiElementId.PNC_UPDATE_CONFIRM_BUTTON,),
            blocking_popup=True,
        )
        home = make_observation(ScreenType.PNC_HOME_CITY)
        daily = make_observation(ScreenType.PNC_QUEST_DAILY)
        observer = Mock()
        observer.observe.side_effect = (update, home, daily)
        actions = Mock()
        actions.recover_update_if_required.return_value = home
        runner = Mock()
        session = ConnectedDailyQuestSession(runner, observer, actions)

        result = session.observe_daily_quest("claim_reconcile")

        self.assertEqual(result, daily)
        actions.recover_update_if_required.assert_called_once()
        runner.execute_flow_until.assert_called_once()
        self.assertEqual(3, observer.observe.call_count)


if __name__ == "__main__":
    unittest.main()
