"""Collect mail archive: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.automation.tasks.collect_mail_task import CollectMailTask
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, TapPointAction
from pnc_automation.app.pnc.domain.mail import CollectMailParams, MailArchiveMode, MailboxType
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.core.images import build_png_bytes
from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.make_task_context import _make_task_context


class CollectMailArchiveTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves collect mail archive."""

    def test_collect_mail_task_archives_a_visible_thread(self) -> None:
        """Persists metadata, text, and screenshot evidence through the canonical archive store."""

        with tempfile.TemporaryDirectory() as temp_directory:
            screenshot_path = Path(temp_directory) / "thread.png"
            screenshot_path.write_bytes(build_png_bytes())
            task = CollectMailTask()
            context = _make_task_context(
                self,
                params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.BOTH),
                task_id=TaskId.COLLECT_MAIL,
                mail_archive_store=MailArchiveStore(root=Path(temp_directory) / "mail"),
                target_castle=CastleIdentity(kingdom="K230", castle_name="Main"),
            )
            mailbox_observation = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", action_point=(120, 90)),),
            )
            thread_observation = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Greetings"),
                    make_entry(ListEntryKind.MAIL_MESSAGE, title="Welcome to automation."),
                ),
                artifact_path=screenshot_path,
            )

            actions = task.plan(context, mailbox_observation)
            result = task.verify(context, mailbox_observation, thread_observation)

            self.assertEqual(len(actions), 1)
            self.assertEqual(result.status.value, "replan")
            archived_files = sorted((Path(temp_directory) / "mail").rglob("*"))
            self.assertTrue(any(path.name == "metadata.json" for path in archived_files))
            self.assertTrue(any(path.name == "thread.txt" for path in archived_files))
            self.assertTrue(any(path.name == "thread.png" for path in archived_files))
            self.assertTrue(any("Main" in path.parts for path in archived_files))

    def test_collect_mail_task_scrolls_to_collect_more_than_the_first_visible_window(self) -> None:
        """Continues mailbox traversal across windows until the requested per-mailbox limit is reached."""

        with tempfile.TemporaryDirectory() as temp_directory:
            task = CollectMailTask()
            context = _make_task_context(
                self,
                params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT, limit_per_mailbox=2),
                task_id=TaskId.COLLECT_MAIL,
                mail_archive_store=MailArchiveStore(root=Path(temp_directory) / "mail"),
                target_castle=CastleIdentity(kingdom="K230", castle_name="Main"),
            )
            first_mailbox = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Bob", subtitle="One", action_point=(120, 90)),),
            )
            second_mailbox = make_observation(
                ScreenType.PNC_MAILBOX_LIST,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_THREAD, title="Enemy Alice", subtitle="Two", action_point=(140, 110)),),
            )
            first_thread = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="First collected thread"),),
            )
            second_thread = make_observation(
                ScreenType.PNC_MAIL_THREAD,
                mailbox_type=MailboxType.PLAYER,
                list_entries=(make_entry(ListEntryKind.MAIL_MESSAGE, title="Second collected thread"),),
            )

            first_actions = task.plan(context, first_mailbox)
            first_result = task.verify(context, first_mailbox, first_thread)
            scroll_actions = task.plan(context, first_mailbox)
            scroll_result = task.verify(context, first_mailbox, second_mailbox)
            second_actions = task.plan(context, second_mailbox)
            second_result = task.verify(context, second_mailbox, second_thread)
            done_actions = task.plan(context, second_mailbox)
            done_result = task.verify(context, second_mailbox, second_mailbox)

            self.assertEqual(len(first_actions), 1)
            self.assertIsInstance(first_actions[0], TapPointAction)
            self.assertEqual(first_result.status.value, "replan")
            self.assertEqual(len(scroll_actions), 1)
            self.assertIsInstance(scroll_actions[0], SwipeAction)
            self.assertEqual(scroll_result.status.value, "replan")
            self.assertEqual(len(second_actions), 1)
            self.assertIsInstance(second_actions[0], TapPointAction)
            self.assertEqual(second_result.status.value, "replan")
            self.assertEqual(done_actions, [])
            self.assertEqual(done_result.status.value, "success")

    def test_collect_mail_task_uses_lord_info_flow_to_resolve_active_castle_before_archiving(self) -> None:
        """Uses the shared self-profile flow to resolve the active castle instead of archiving under an account-level fallback."""

        task = CollectMailTask()
        context = _make_task_context(
            self,
            params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT),
            task_id=TaskId.COLLECT_MAIL,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            visible_ids=(UiElementId.PNC_HOME_LORD_INFO_SHORTCUT,),
        )

        actions = task.plan(context, observation)

        self.assertEqual(actions, self.flows.open_lord_info(observation))

    def test_collect_mail_task_fails_fast_when_active_castle_cannot_be_resolved_from_mailbox_screen(self) -> None:
        """Rejects archive work from a mailbox screen when neither the active castle nor an explicit target is available."""

        task = CollectMailTask()
        context = _make_task_context(
            self,
            params=CollectMailParams(mailboxes=(MailboxType.PLAYER,), archive_mode=MailArchiveMode.TEXT),
            task_id=TaskId.COLLECT_MAIL,
        )

        with self.assertRaises(SelectorResolutionError):
            task.plan(
                context,
                make_observation(
                    ScreenType.PNC_MAILBOX_LIST,
                    mailbox_type=MailboxType.PLAYER,
                ),
            )
