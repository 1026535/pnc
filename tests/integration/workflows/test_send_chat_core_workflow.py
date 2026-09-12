"""Deterministic tests for the typed replacement-core chat workflow."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
import unittest

from pnc_automation.app.automation.engine.core_workflow import WorkflowEffect
from pnc_automation.app.automation.send_chat import SendChatWorkflow
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatMessageTaskParams
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.support.pnc.observations import make_entry, make_observation


@dataclass
class _FakeSendContext:
    """Provides the constrained operations used by the typed chat workflow."""

    result_observation: Observation
    calls: list[tuple[str, object]] = field(default_factory=list)

    def navigate(self, target: ScreenType) -> Observation:
        self.calls.append(("navigate", target))
        return self.result_observation

    def send_chat_message(
        self,
        channel: ChatChannel,
        message: str,
        active_castle: CastleIdentity,
    ) -> Observation:
        self.calls.append(("send", channel, message, active_castle))
        return self.result_observation

class SendChatCoreWorkflowTests(unittest.TestCase):
    """Covers both fixed channels through one typed receipt result contract."""

    def test_workflow_rejects_untyped_channel(self) -> None:
        """Requires callers to choose one of the two typed chat channels."""

        with self.assertRaisesRegex(ValueError, "supported ChatChannel"):
            SendChatWorkflow(
                params=ChatMessageTaskParams(message="hello"),
                active_castle=CastleIdentity("K1", "free cookies"),
                channel="world",  # type: ignore[arg-type]
            )

    def test_world_workflow_uses_generic_send_operation_and_returns_receipt(self) -> None:
        captured_at = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
        castle = CastleIdentity("K1", "free cookies")
        observation = replace(
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.WORLD,
                chat_draft_empty=True,
                list_entries=(
                    make_entry(
                        ListEntryKind.CHAT_MESSAGE,
                        title="[NAX] freecookies",
                        metadata={
                            "chat_entry_kind": "player",
                            "message_text": "hello",
                            "visible_order": 0,
                        },
                    ),
                ),
                artifact_path=Path("chat.png"),
            ),
            captured_at=captured_at,
        )
        context = _FakeSendContext(observation)

        workflow = SendChatWorkflow(
            params=ChatMessageTaskParams(message="hello"),
            active_castle=castle,
            channel=ChatChannel.WORLD,
        )
        result = workflow.execute(context)

        self.assertEqual(ChatChannel.WORLD, result.channel)
        self.assertEqual("hello", result.message)
        self.assertEqual(1, result.receipt_count)
        self.assertTrue(result.sent_proof)
        self.assertEqual(WorkflowEffect.NONSPENDING_STATE_CHANGE, workflow.spec.effect)
        self.assertEqual(
            [
                ("navigate", ScreenType.PNC_CHAT),
                ("send", ChatChannel.WORLD, "hello", castle),
            ],
            context.calls,
        )

    def test_alliance_workflow_uses_same_nonspending_operation_and_name(self) -> None:
        captured_at = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
        castle = CastleIdentity("K1", "free cookies")
        observation = replace(
            make_observation(
                ScreenType.PNC_CHAT,
                active_chat_channel=ChatChannel.ALLIANCE,
                chat_draft_empty=True,
                list_entries=(
                    make_entry(
                        ListEntryKind.CHAT_MESSAGE,
                        title="[NAX] freecookies",
                        metadata={
                            "chat_entry_kind": "player",
                            "message_text": "hello",
                            "visible_order": 0,
                        },
                    ),
                ),
            ),
            captured_at=captured_at,
        )
        context = _FakeSendContext(observation)

        workflow = SendChatWorkflow(
            params=ChatMessageTaskParams(message="hello"),
            active_castle=castle,
            channel=ChatChannel.ALLIANCE,
        )
        result = workflow.execute(context)

        self.assertEqual(ChatChannel.ALLIANCE, result.channel)
        self.assertEqual("send_alliance_chat", workflow.spec.name)
        self.assertEqual(WorkflowEffect.NONSPENDING_STATE_CHANGE, workflow.spec.effect)
        self.assertEqual(
            [
                ("navigate", ScreenType.PNC_CHAT),
                ("send", ChatChannel.ALLIANCE, "hello", castle),
            ],
            context.calls,
        )


if __name__ == "__main__":
    unittest.main()
