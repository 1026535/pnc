"""Opt-in live smoke tests for the reusable chat workflow."""

from __future__ import annotations

import os
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from pnc_automation.app import build_application_runner
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.live_smoke_support import build_live_runtime


def _live_chat_smoke_enabled() -> bool:
    """Returns whether the explicit live chat smoke opt-in flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_CHAT_SMOKE") == "1"


@dataclass(frozen=True, slots=True)
class _LiveChatSendResult:
    """Captures the outcome and timing of one live reusable chat send."""

    channel: ChatChannel
    before: Observation
    after: Observation
    duration_seconds: float


@unittest.skipUnless(_live_chat_smoke_enabled(), "Set PNC_RUN_LIVE_CHAT_SMOKE=1 to run live chat smoke tests.")
class LiveChatWorkflowSmokeTests(unittest.TestCase):
    """Validates the reusable chat workflow against a configured live BlueStacks session."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds the live runtime and executes one send for each supported chat channel."""

        cls.config_path = Path(os.getenv("PNC_LIVE_CHAT_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_CHAT_ACCOUNT", "testing")
        cls.baseline_seconds = float(os.getenv("PNC_LIVE_CHAT_BASELINE_SECONDS", "10.5"))
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        runtime = build_live_runtime(
            config_account=cls.account,
            script_runner=cls.script_runner,
        )
        cls.session = runtime.session
        cls.observation_service = runtime.observation_service
        cls.flows = runtime.flow_planner
        if runtime.observed_action_executor is None:
            raise SelectorResolutionError("Live chat smoke requires a connected observed-action executor.")
        cls.action_executor = runtime.observed_action_executor
        cls.alliance_result = cls._run_live_send(ChatChannel.ALLIANCE)
        cls.world_result = cls._run_live_send(ChatChannel.WORLD)

    @classmethod
    def _run_live_send(cls, channel: ChatChannel) -> _LiveChatSendResult:
        """Recovers to home city, executes incremental chat-send planning, and returns the final observation and timing."""

        before = cls._ensure_home_city(label_prefix=f"live_chat_{channel.value}_prepare")
        message = f"chat smoke {channel.value} {int(time.time())}"
        start = time.perf_counter()
        observation = before
        send_confirmed = False
        for step_index in range(8):
            actions = cls.flows.send_chat_message(observation, message=message, channel=channel)
            execution = cls.action_executor.execute_actions(
                actions,
                observation,
                observe=lambda label, request=None: cls.observation_service.observe(
                    f"live_chat_{channel.value}_{step_index + 1}_{label}",
                    request=request,
                ),
            )
            observation = execution.observation
            send_confirmed = any(getattr(action, "reason", "") == "send_chat_message" for action in actions)
            if (
                send_confirmed
                and observation.screen_type == ScreenType.PNC_CHAT
                and observation.active_chat_channel == channel
                and observation.chat_draft_empty
            ):
                break
        else:
            raise AssertionError(f"Could not complete the incremental live chat send for '{channel.value}'.")
        duration_seconds = time.perf_counter() - start
        return _LiveChatSendResult(
            channel=channel,
            before=before,
            after=observation,
            duration_seconds=duration_seconds,
        )

    @classmethod
    def _ensure_home_city(cls, *, label_prefix: str) -> Observation:
        """Returns the live session to home city before one reusable chat send."""

        observation = cls.observation_service.observe(f"{label_prefix}_before")
        for step_index in range(10):
            if observation.screen_type == ScreenType.PNC_HOME_CITY and not observation.blocking_popup:
                return observation
            execution = cls.action_executor.execute_actions(
                cls.flows.ensure_home_city(observation),
                observation,
                observe=lambda label, request=None: cls.observation_service.observe(
                    f"{label_prefix}_{step_index + 1}_{label}",
                    request=request,
                ),
            )
            observation = execution.observation
        raise AssertionError(f"Could not recover the live session to home city before '{label_prefix}'.")

    def test_live_alliance_send_stays_in_chat_and_clears_the_draft(self) -> None:
        """Verifies the live alliance send finishes on chat with the alliance tab active and an empty draft."""

        self.assertEqual(self.alliance_result.before.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(self.alliance_result.after.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(self.alliance_result.after.active_chat_channel, ChatChannel.ALLIANCE)
        self.assertTrue(self.alliance_result.after.chat_draft_empty)

    def test_live_world_send_stays_in_chat_and_clears_the_draft(self) -> None:
        """Verifies the live world send finishes on chat with the kingdom tab active and an empty draft."""

        self.assertEqual(self.world_result.before.screen_type, ScreenType.PNC_HOME_CITY)
        self.assertEqual(self.world_result.after.screen_type, ScreenType.PNC_CHAT)
        self.assertEqual(self.world_result.after.active_chat_channel, ChatChannel.WORLD)
        self.assertTrue(self.world_result.after.chat_draft_empty)

    def test_live_chat_sends_beat_the_previous_home_city_baseline(self) -> None:
        """Checks that the optimized home-city chat sends stay below the configured live baseline."""

        self.assertLess(self.alliance_result.duration_seconds, self.baseline_seconds)
        self.assertLess(self.world_result.duration_seconds, self.baseline_seconds)
