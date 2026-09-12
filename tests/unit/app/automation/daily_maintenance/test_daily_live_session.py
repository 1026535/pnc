"""Offline checks for connected Daily Quest update recovery."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.daily_maintenance.live_session import ConnectedDailyQuestSession
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

from tests.support.pnc.observations import make_observation


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
        actions.recover_interruption_if_required.side_effect = (home, None, None)
        runner = Mock()
        session = ConnectedDailyQuestSession(runner, observer, actions)

        result = session.observe_daily_quest("claim_reconcile")

        self.assertEqual(result, daily)
        self.assertEqual(actions.recover_interruption_if_required.call_count, 3)
        runner.execute_flow_until.assert_called_once()
        self.assertEqual(3, observer.observe.call_count)

    def test_return_home_uses_full_runtime_scope_for_non_quest_sources(self) -> None:
        """Recognizes maintenance screens before handing them to safe-root navigation."""

        for source_screen in (
            ScreenType.PNC_HERO_HALL,
            ScreenType.PNC_BAG,
            ScreenType.PNC_DAILY_TO_DO,
        ):
            with self.subTest(source_screen=source_screen):
                start = make_observation(source_screen)
                home = make_observation(ScreenType.PNC_HOME_CITY)
                observer = Mock()
                observer.observe.return_value = start
                actions = Mock()
                actions.recover_interruption_if_required.return_value = None
                runner = Mock()
                session = ConnectedDailyQuestSession(runner, observer, actions)

                session.return_to_home()

                observer.observe.assert_called_once_with(
                    "daily_return_home_start",
                    request=ObservationRequest.full_runtime_default(),
                )
                flow_call = runner.execute_flow_until.call_args
                self.assertIsNotNone(flow_call)
                self.assertEqual(flow_call.kwargs["start_observation"], start)
                self.assertEqual(flow_call.kwargs["max_steps"], 4)
                self.assertTrue(flow_call.kwargs["done"](home))
                self.assertFalse(flow_call.kwargs["done"](start))


if __name__ == "__main__":
    unittest.main()
