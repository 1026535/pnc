"""Action pacing human mode."""

from __future__ import annotations

import random
import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, TapPointAction, WaitAction
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_observation


def _make_executor(*, sleeps: list[float], human_mode: bool) -> ActionExecutor:
    """Builds one executor whose configured delays are recorded in seconds."""

    return ActionExecutor(
        selector_registry=build_default_selector_registry(),
        session=FakeSession(),
        stable_click_delay_ms=300,
        post_action_observe_delay_ms=800,
        chat_stable_click_delay_ms=120,
        chat_post_action_observe_delay_ms=250,
        logger=build_logger(),
        sleep=sleeps.append,
        human_mode=human_mode,
        rng=random.Random(20260917),
    )


class ActionPacingTests(unittest.TestCase):
    """Proves human-mode pacing stays near configured delays and only affects actions."""

    def test_human_mode_jitters_action_pacing_within_a_tight_band(self) -> None:
        """Varies post-action delays slightly instead of repeating one exact pause."""

        sleeps: list[float] = []
        executor = _make_executor(sleeps=sleeps, human_mode=True)
        action = TapPointAction(x=100, y=200)

        for _ in range(20):
            executor.execute_action(action, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertGreater(len(set(sleeps)), 1)
        for delay in sleeps:
            self.assertGreaterEqual(delay, 0.27)
            self.assertLessEqual(delay, 0.33)

    def test_human_mode_leaves_observation_and_wait_pacing_exact(self) -> None:
        """Applies jitter only to action pacing, never to observe delays or authored waits."""

        sleeps: list[float] = []
        executor = _make_executor(sleeps=sleeps, human_mode=True)
        observation = make_observation(ScreenType.PNC_HOME_CITY)
        action = TapPointAction(x=100, y=200)

        executor.observe_action_follow_up(
            action=action,
            label_prefix="post_action_1",
            observe=lambda label, request: observation,
        )
        executor.execute_action(WaitAction(milliseconds=500), observation)

        self.assertEqual(sleeps, [0.8, 0.5])

    def test_action_pacing_stays_exact_when_human_mode_is_off(self) -> None:
        """Repeats the configured post-action delay exactly without human mode."""

        sleeps: list[float] = []
        executor = _make_executor(sleeps=sleeps, human_mode=False)
        action = TapPointAction(x=100, y=200)

        for _ in range(3):
            executor.execute_action(action, make_observation(ScreenType.PNC_HOME_CITY))

        self.assertEqual(sleeps, [0.3, 0.3, 0.3])

    def test_human_mode_paces_machine_key_bursts(self) -> None:
        """Inserts small varied pauses between rapid clear-and-delete key events."""

        sleeps: list[float] = []
        executor = _make_executor(sleeps=sleeps, human_mode=True)

        executor.execute_action(
            InputTextAction(
                selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
                text="hello",
                replace_existing=True,
            ),
            make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
                chat_draft_empty=False,
                chat_draft_text="existing",
            ),
        )

        self.assertEqual(len(sleeps), 28)
        for delay in sleeps[1:26]:
            self.assertGreaterEqual(delay, 0.025)
            self.assertLessEqual(delay, 0.07)
        for index in (0, 26, 27):
            self.assertGreaterEqual(sleeps[index], 0.27)
            self.assertLessEqual(sleeps[index], 0.33)


if __name__ == "__main__":
    unittest.main()
