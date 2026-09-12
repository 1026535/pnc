"""Opt-in live smoke coverage for one explicitly authorized typed chat send."""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from pnc_automation.app import build_application_runner
from pnc_automation.app.automation.engine.core_runtime import build_core_runtime
from pnc_automation.app.automation.engine.core_workflow import CoreWorkflowResult, CoreWorkflowRunner
from pnc_automation.app.automation.send_chat import SendChatResult, SendChatWorkflow
from pnc_automation.app.authoring.config.models import LiveAutomationRole
from pnc_automation.app.pnc.domain.chat import (
    ChatChannel,
    ChatMessageTaskParams,
    parse_chat_message_params,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import ScriptValidationError
from tests.live_smoke_support import live_session_cleanup_policy_from_environment


def _live_chat_smoke_enabled() -> bool:
    """Returns whether the explicit live chat smoke opt-in flag is enabled."""

    return os.getenv("PNC_RUN_LIVE_CHAT_SMOKE") == "1"


def _require_environment(name: str) -> str:
    """Returns one explicit non-empty live-smoke setting."""

    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Typed chat smoke requires explicit {name}.")
    return value


def _live_chat_inputs_from_environment() -> tuple[ChatChannel, ChatMessageTaskParams]:
    """Parses the one channel and message that the caller explicitly supplied."""

    channel_value = _require_environment("PNC_LIVE_CHAT_CHANNEL").strip().casefold()
    try:
        channel = ChatChannel(channel_value)
    except ValueError as error:
        raise ValueError("PNC_LIVE_CHAT_CHANNEL must be 'world' or 'alliance'.") from error
    params = parse_chat_message_params(
        {"message": _require_environment("PNC_LIVE_CHAT_MESSAGE")},
        task_label="live_chat_smoke",
    )
    return channel, params


class LiveChatSmokeConfigurationTests(unittest.TestCase):
    """Validates smoke payloads before application or connection construction."""

    @patch.dict(os.environ, {}, clear=True)
    def test_channel_and_message_are_required(self) -> None:
        """Missing channel fails before the live application can be built."""

        with self.assertRaisesRegex(ValueError, "PNC_LIVE_CHAT_CHANNEL"):
            _live_chat_inputs_from_environment()

    @patch.dict(os.environ, {"PNC_LIVE_CHAT_CHANNEL": "world"}, clear=True)
    def test_message_is_required(self) -> None:
        """Missing message fails before the live application can be built."""

        with self.assertRaisesRegex(ValueError, "PNC_LIVE_CHAT_MESSAGE"):
            _live_chat_inputs_from_environment()

    @patch.dict(
        os.environ,
        {"PNC_LIVE_CHAT_CHANNEL": "guild", "PNC_LIVE_CHAT_MESSAGE": "hello"},
        clear=True,
    )
    def test_channel_must_be_supported(self) -> None:
        """The smoke accepts only the two typed, reviewed chat channels."""

        with self.assertRaisesRegex(ValueError, "world.*alliance"):
            _live_chat_inputs_from_environment()

    @patch.dict(
        os.environ,
        {"PNC_LIVE_CHAT_CHANNEL": "world", "PNC_LIVE_CHAT_MESSAGE": "hello\r\nagain"},
        clear=True,
    )
    def test_message_parser_rejects_multiline_payload(self) -> None:
        """The shared parser rejects multiline input before any connection."""

        with self.assertRaises(ScriptValidationError):
            _live_chat_inputs_from_environment()


@unittest.skipUnless(
    _live_chat_smoke_enabled(),
    "Set PNC_RUN_LIVE_CHAT_SMOKE=1 to run the typed live chat smoke.",
)
class LiveChatWorkflowSmokeTests(unittest.TestCase):
    """Runs one explicit typed send and proves its receipt and Home exit."""

    @classmethod
    def setUpClass(cls) -> None:
        """Builds one reserved typed runtime and executes exactly one requested send."""

        # Resolve the payload before building the application or acquiring a lease.
        cls.channel, cls.params = _live_chat_inputs_from_environment()
        cls.config_path = Path(os.getenv("PNC_LIVE_CHAT_CONFIG", "config/accounts.yaml"))
        cls.account_id = os.getenv("PNC_LIVE_CHAT_ACCOUNT", "testing")
        cls.application = build_application_runner(cls.config_path)
        cls.script_runner = cls.application.script_runner
        cls.account = cls.script_runner.config.require_account(cls.account_id)
        cls.account.require_live_role(LiveAutomationRole.SMOKE_TEST)
        cls.lease_bundle = cls.application.reserve_accounts((cls.account_id,))
        cls.addClassCleanup(cls.lease_bundle.close)
        core_runtime = build_core_runtime(
            cls.script_runner,
            cls.account,
            cls.account.artifact_directory_name,
            required_role=LiveAutomationRole.SMOKE_TEST,
            session_cleanup_policy=live_session_cleanup_policy_from_environment(),
        )
        cls.core_runtime = core_runtime
        cls.addClassCleanup(core_runtime.close)

        # This bounded roster proof reads the exact active identity and never selects a castle.
        cls.active_castle = core_runtime.preflight_active_castle_identity()
        cls.workflow = SendChatWorkflow(
            params=cls.params,
            active_castle=cls.active_castle,
            channel=cls.channel,
        )
        cls.result = CoreWorkflowRunner[SendChatResult](core_runtime).run(cls.workflow)

    def test_one_typed_send_has_a_visible_receipt_and_returns_home(self) -> None:
        """Requires positive typed receipt metadata followed by the reviewed Home exit."""

        self.assertIsInstance(self.result, CoreWorkflowResult)
        self.assertTrue(self.result.succeeded)
        self.assertIsInstance(self.result.value, SendChatResult)
        expected_name = (
            "send_alliance_chat"
            if self.channel == ChatChannel.ALLIANCE
            else "send_kingdom_chat"
        )
        self.assertEqual(self.workflow.spec.name, expected_name)
        self.assertEqual(self.result.value.channel, self.channel)
        self.assertEqual(self.result.value.message, self.params.message)
        self.assertGreater(self.result.value.receipt_count, 0)
        self.assertTrue(self.result.value.sent_proof)
        self.assertEqual(self.result.exit_screen, ScreenType.PNC_HOME_CITY)


if __name__ == "__main__":
    unittest.main()
