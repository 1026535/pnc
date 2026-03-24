"""Kingdom chat monitor tests covering archive persistence and heartbeat task behavior."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pnc_automation.automation.task import TaskId, TaskStatus
from pnc_automation.automation.task_context import TaskContext
from pnc_automation.automation.tasks.collect_kingdom_chat_task import CollectKingdomChatTask
from pnc_automation.capture.chat_archive_store import ChatArchiveStore
from pnc_automation.config.models import AccountConfig, CastleIdentity, CredentialSource, DefaultsConfig, ResolvedCredentials
from pnc_automation.pnc.chat import ChatChannel, ChatEntryKind, ObservedChatEntry
from pnc_automation.pnc.observation import ListEntryKind
from pnc_automation.pnc.screen_flows import ScreenFlowPlanner
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from tests.test_support import FakeObservationService, build_logger, make_entry, make_observation


class ChatMonitorTests(unittest.TestCase):
    """Validates durable Kingdom Chat archiving and the heartbeat task contract."""

    def setUp(self) -> None:
        """Builds the shared account, defaults, and flow planner used by chat monitor tests."""

        self.account = AccountConfig(
            id="testing",
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
        self.target_castle = CastleIdentity(kingdom="K304", castle_name="K304554ca2797", castle_level=12)

    def test_chat_archive_store_appends_first_snapshot_and_writes_screenshot(self) -> None:
        """Writes the initial daily transcript, state, and change screenshot under the durable archive root."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Need help on rally?", 1),
                )
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"fake_png_payload",
            )

            transcript = update.transcript_path.read_text(encoding="utf-8")
            self.assertTrue(update.changed)
            self.assertFalse(update.gap_detected)
            self.assertEqual(len(update.appended_entries), 2)
            self.assertTrue(update.screenshot_path is not None and update.screenshot_path.is_file())
            self.assertTrue(update.state_path.is_file())
            self.assertIn("Enemy Bob: Hello there", transcript)
            self.assertIn("Cutie Voj: Need help on rally?", transcript)
            self.assertEqual(update.directory.parts[-4:], ("2026-03-23", "testing", "k304_k304554ca2797", "kingdom"))

    def test_chat_archive_store_noops_when_snapshot_is_unchanged(self) -> None:
        """Does not append transcript content or write another durable screenshot for an idle repeat heartbeat."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),))
            first = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"first_payload",
            )
            second = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIsNone(second.screenshot_path)
            self.assertEqual(first.transcript_path.read_text(encoding="utf-8").count("Enemy Bob"), 1)

    def test_chat_archive_store_carries_previous_day_overlap_state_into_new_day(self) -> None:
        """Reuses the prior local-day state for overlap decisions when the new day has not written state yet."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "Hello there", 0),))
            local_before_midnight = datetime.now().astimezone().replace(hour=23, minute=59, second=0, microsecond=0)
            local_after_midnight = local_before_midnight + timedelta(minutes=2)

            first = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=local_before_midnight,
                snapshot=snapshot,
                screenshot_payload=b"first_payload",
            )
            second = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=local_after_midnight,
                snapshot=snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIsNone(second.screenshot_path)
            self.assertTrue(second.state_path.is_file())
            self.assertFalse(second.transcript_path.exists())

    def test_chat_archive_store_appends_only_the_non_overlapping_tail(self) -> None:
        """Appends only newly visible player rows once the previous window suffix overlaps the current prefix."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            first_snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "One", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Two", 1),
                )
            )
            second_snapshot = store.build_snapshot(
                (
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Cutie Voj", "Two", 0),
                    ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Alice", "Three", 1),
                )
            )
            store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=first_snapshot,
                screenshot_payload=b"first_payload",
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=second_snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertEqual([entry.sender_name for entry in update.appended_entries], ["Enemy Alice"])
            self.assertFalse(update.gap_detected)

    def test_chat_archive_store_marks_gap_when_overlap_is_missing(self) -> None:
        """Flags a visible gap and appends the whole current window when continuity is lost between heartbeats."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            first_snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Bob", "One", 0),))
            second_snapshot = store.build_snapshot((ObservedChatEntry(ChatEntryKind.PLAYER, "Enemy Alice", "Two", 0),))
            store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 15, 0, tzinfo=UTC),
                snapshot=first_snapshot,
                screenshot_payload=b"first_payload",
            )

            update = store.persist_heartbeat(
                account_id=self.account.id,
                castle=self.target_castle,
                channel=ChatChannel.WORLD,
                captured_at=datetime(2026, 3, 23, 10, 20, 0, tzinfo=UTC),
                snapshot=second_snapshot,
                screenshot_payload=b"second_payload",
            )

            self.assertTrue(update.changed)
            self.assertTrue(update.gap_detected)
            self.assertEqual([entry.sender_name for entry in update.appended_entries], ["Enemy Alice"])

    def test_collect_kingdom_chat_task_uses_the_shared_chat_channel_flow(self) -> None:
        """Delegates chat acquisition to the shared channel-alignment flow instead of reimplementing navigation."""

        task = CollectKingdomChatTask()
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_CHAT_SHORTCUT,),
        )
        context = self._make_context(params=None, target_castle=self.target_castle)

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.ensure_chat_channel(observation, ChatChannel.WORLD))

    def test_collect_kingdom_chat_task_archives_only_player_rows(self) -> None:
        """Archives player chat, ignores announcements, and reports a successful heartbeat append."""

        task = CollectKingdomChatTask()
        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            fake_observer = FakeObservationService(
                observations=[
                    make_observation(
                        ScreenType.PNC_CHAT,
                        active_chat_channel=ChatChannel.WORLD,
                        list_entries=(
                            make_entry(
                                ListEntryKind.CHAT_MESSAGE,
                                title="Enemy Bob",
                                subtitle="Hello there",
                                metadata={
                                    "chat_entry_kind": ChatEntryKind.PLAYER.value,
                                    "message_text": "Hello there",
                                    "visible_order": 0,
                                },
                            ),
                            make_entry(
                                ListEntryKind.CHAT_MESSAGE,
                                title="System notice",
                                metadata={
                                    "chat_entry_kind": ChatEntryKind.ANNOUNCEMENT.value,
                                    "message_text": "Castle battle begins soon",
                                    "visible_order": 1,
                                },
                                action_point=(0, 0),
                            ),
                        ),
                    ),
                ]
            )
            context = self._make_context(
                params=None,
                task_id=TaskId.COLLECT_KINGDOM_CHAT,
                target_castle=self.target_castle,
                chat_archive_store=store,
                observation_service=fake_observer,
            )

            result = task.verify(
                context,
                make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD),
                make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD),
            )

            transcript_path = next((Path(temp_directory) / "chat").rglob("transcript.log"))
            transcript = transcript_path.read_text(encoding="utf-8")
            self.assertEqual(result.status, TaskStatus.SUCCESS)
            self.assertIn("Archived 1 new Kingdom chat player message", result.message)
            self.assertIn("Enemy Bob: Hello there", transcript)
            self.assertNotIn("Castle battle begins soon", transcript)

    def test_collect_kingdom_chat_task_fails_on_unsupported_rows(self) -> None:
        """Fails safely instead of archiving transcript content when OCR marked visible rows as unsupported."""

        task = CollectKingdomChatTask()
        with tempfile.TemporaryDirectory() as temp_directory:
            store = ChatArchiveStore(root=Path(temp_directory) / "chat")
            fake_observer = FakeObservationService(
                observations=[
                    make_observation(
                        ScreenType.PNC_CHAT,
                        active_chat_channel=ChatChannel.WORLD,
                        list_entries=(
                            make_entry(
                                ListEntryKind.CHAT_MESSAGE,
                                title="???",
                                metadata={
                                    "chat_entry_kind": ChatEntryKind.UNSUPPORTED.value,
                                    "message_text": "???",
                                    "visible_order": 0,
                                },
                                action_point=(0, 0),
                            ),
                        ),
                    ),
                ]
            )
            context = self._make_context(
                params=None,
                task_id=TaskId.COLLECT_KINGDOM_CHAT,
                target_castle=self.target_castle,
                chat_archive_store=store,
                observation_service=fake_observer,
            )

            result = task.verify(
                context,
                make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD),
                make_observation(ScreenType.PNC_CHAT, active_chat_channel=ChatChannel.WORLD),
            )

            self.assertEqual(result.status, TaskStatus.FAILED)
            self.assertIn("unsupported rows", result.message)
            self.assertFalse(any((Path(temp_directory) / "chat").rglob("transcript.log")))

    def _make_context(
        self,
        *,
        params: object,
        task_id: TaskId = TaskId.COLLECT_KINGDOM_CHAT,
        target_castle: CastleIdentity | None = None,
        chat_archive_store: ChatArchiveStore | None = None,
        observation_service: FakeObservationService | None = None,
    ) -> TaskContext:
        """Builds one task context with the shared chat monitor test dependencies."""

        return TaskContext(
            account=self.account,
            castle_roster_provider=lambda: None,
            defaults=self.defaults,
            step=type("Step", (), {"task": task_id})(),
            params=params,
            flows=self.flows,
            logger=self.logger,
            target_castle=target_castle,
            chat_archive_store=chat_archive_store,
            observation_service=observation_service,
        )


if __name__ == "__main__":
    unittest.main()
