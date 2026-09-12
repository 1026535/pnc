"""Deterministic tests for the typed replacement-core collect-mail workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from pnc_automation.app.automation.collect_mail import (
    CollectMailMailboxResult,
    CollectMailResult,
    CollectMailWorkflow,
)
from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.pnc.domain.mail import (
    CollectMailParams,
    MailArchiveRecord,
    MailArchiveMode,
    MailboxAvailability,
    MailboxType,
    compute_mail_thread_fingerprint,
    mail_thread_row_key,
    normalize_mail_thread_text,
)
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.core.errors import TaskVerificationError
from pnc_automation.core.vision.image.models import Bounds


class CollectMailCoreWorkflowTests(unittest.TestCase):
    """Covers typed mailbox traversal, persistence, deduplication, and bounded scrolls."""

    def test_unavailable_mailbox_returns_typed_skip_without_list_or_scroll(self) -> None:
        """Unavailable categories remain on the hub and never request list content or a gesture."""

        context = _FakeMailContext(availability=MailboxAvailability.UNAVAILABLE)
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = _workflow(temporary_directory).execute(context)

        mailbox = result.mailboxes[0]
        self.assertEqual(MailboxAvailability.UNAVAILABLE, mailbox.availability)
        self.assertEqual((0, 0, 0, 0), _counts(mailbox))
        self.assertEqual([("navigate", ScreenType.PNC_MAIL_HUB), ("open_mailbox", MailboxType.PLAYER)], context.calls)

    def test_empty_available_mailbox_returns_zero_counts_without_scroll(self) -> None:
        """An available mailbox with no rows completes without fabricating thread content."""

        context = _FakeMailContext(
            availability=MailboxAvailability.AVAILABLE,
            content=(_mailbox((), captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC), empty=True),),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = _workflow(temporary_directory).execute(context)

        mailbox = result.mailboxes[0]
        self.assertEqual(MailboxAvailability.AVAILABLE, mailbox.availability)
        self.assertEqual((0, 0, 0, 0), _counts(mailbox))
        self.assertEqual(
            [
                ("navigate", ScreenType.PNC_MAIL_HUB),
                ("open_mailbox", MailboxType.PLAYER),
                ("observe_content", ScreenType.PNC_MAILBOX_LIST),
                ("navigate", ScreenType.PNC_MAIL_HUB),
            ],
            context.calls,
        )

    def test_collects_and_deduplicates_opened_rows_then_stops_on_repeated_scroll(self) -> None:
        """Persists one fingerprint, counts an in-run duplicate as skipped, and issues one bounded swipe."""

        first = _row("Sender", "First")
        second = _row("Sender", "Second")
        listing = _mailbox(
            (first, second),
            captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        )
        after_thread = _mailbox(
            (first, second),
            captured_at=datetime(2026, 9, 11, 12, 1, tzinfo=UTC),
        )
        thread = _thread(datetime(2026, 9, 11, 12, 2, tzinfo=UTC))
        context = _FakeMailContext(
            availability=MailboxAvailability.AVAILABLE,
            content=(listing, thread, after_thread, thread, after_thread),
            scroll_result=after_thread,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "thread.png"
            source.write_bytes(b"png")
            context.content = tuple(
                observation if observation.artifact_path is not None else _with_artifact(observation, source)
                for observation in context.content
            )
            result = _workflow(
                temporary_directory,
                limit=3,
                archive_mode=MailArchiveMode.BOTH,
            ).execute(context)

            mailbox = result.mailboxes[0]
            self.assertEqual((2, 1, 1, 1), _counts(mailbox))
            self.assertEqual(1, result.total_archived_count)
            self.assertEqual(1, result.total_skipped_existing_count)
            self.assertEqual(1, result.total_scroll_count)
            archive_root = Path(temporary_directory) / "mail"
            metadata_paths = tuple(archive_root.rglob("metadata.json"))
            self.assertEqual(1, len(metadata_paths))
            archived = metadata_paths[0].parent
            self.assertIn("Main", archived.parts)
            self.assertEqual(source.read_bytes(), (archived / "thread.png").read_bytes())
            self.assertEqual("Reward message", (archived / "thread.txt").read_text(encoding="utf-8"))
        self.assertIn(("scroll_mailbox", None), context.calls)

    def test_existing_fingerprint_is_counted_as_skipped(self) -> None:
        """Only-new collection consults the canonical archive and skips an existing fingerprint."""

        row = _row("Sender", "First")
        listing = _mailbox((row,), captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC))
        after_thread = Observation(
            screen_type=ScreenType.PNC_MAILBOX_LIST,
            visible_elements={},
            list_entries=(row,),
            captured_at=datetime(2026, 9, 11, 12, 3, tzinfo=UTC),
            mailbox_type=MailboxType.PLAYER,
            mailbox_empty=True,
        )
        thread = _thread(datetime(2026, 9, 11, 12, 2, tzinfo=UTC))
        context = _FakeMailContext(
            availability=MailboxAvailability.AVAILABLE,
            content=(listing, thread, after_thread),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_store = MailArchiveStore(root=Path(temporary_directory) / "mail")
            fingerprint = compute_mail_thread_fingerprint(
                mailbox_type=MailboxType.PLAYER,
                sender_name="Sender",
                timestamp_text="Sep 11",
                normalized_thread_text=normalize_mail_thread_text(("Reward message",)),
            )
            archive_store.persist(
                record=MailArchiveRecord(
                    account_id="account",
                    pnc_account_id="pnc-account",
                    active_castle="Main",
                    mailbox_type=MailboxType.PLAYER,
                    sender_name="Sender",
                    thread_timestamp_text="Sep 11",
                    fingerprint=fingerprint,
                    captured_at=datetime(2026, 9, 11, 11, 0, tzinfo=UTC),
                    normalized_thread_text="Reward message",
                ),
                archive_mode=MailArchiveMode.TEXT,
                skip_existing=True,
            )
            workflow = _workflow(temporary_directory)
            result = workflow.execute(context)

        self.assertEqual((1, 0, 1, 0), _counts(result.mailboxes[0]))

    def test_screenshot_archive_requires_existing_thread_artifact_before_persistence(self) -> None:
        """Screenshot and combined modes fail closed when the fresh thread frame was not persisted."""

        row = _row("Sender", "First")
        context = _FakeMailContext(
            availability=MailboxAvailability.AVAILABLE,
            content=(
                _mailbox((row,), captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC)),
                _thread(datetime(2026, 9, 11, 12, 1, tzinfo=UTC)),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            workflow = _workflow(temporary_directory, archive_mode=MailArchiveMode.BOTH)
            with self.assertRaisesRegex(TaskVerificationError, "existing persisted thread artifact"):
                workflow.execute(context)
            self.assertFalse(any(Path(temporary_directory).rglob("metadata.json")))

    def test_text_archive_allows_thread_without_screenshot_artifact(self) -> None:
        """Text-only mode persists from typed content even when no screenshot path is available."""

        row = _row("Sender", "First")
        context = _FakeMailContext(
            availability=MailboxAvailability.AVAILABLE,
            content=(
                _mailbox((row,), captured_at=datetime(2026, 9, 11, 12, 0, tzinfo=UTC)),
                _thread(datetime(2026, 9, 11, 12, 1, tzinfo=UTC)),
                Observation(
                    screen_type=ScreenType.PNC_MAILBOX_LIST,
                    visible_elements={},
                    list_entries=(row,),
                    captured_at=datetime(2026, 9, 11, 12, 2, tzinfo=UTC),
                    mailbox_type=MailboxType.PLAYER,
                    mailbox_empty=True,
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = _workflow(temporary_directory, archive_mode=MailArchiveMode.TEXT).execute(context)
            self.assertEqual((1, 1, 0, 0), _counts(result.mailboxes[0]))
            self.assertTrue(any(path.name == "metadata.json" for path in Path(temporary_directory).rglob("*")))

    def test_result_rejects_empty_identity_and_duplicate_mailbox_results(self) -> None:
        """Typed result models reject missing aggregate identity and duplicate mailbox rows."""

        with self.assertRaises(ValueError):
            CollectMailResult(mailboxes=())
        item = CollectMailMailboxResult(
            mailbox=MailboxType.PLAYER,
            availability=MailboxAvailability.UNAVAILABLE,
            processed_count=0,
            archived_count=0,
            skipped_existing_count=0,
            scroll_count=0,
        )
        for availability, counters in (
            (MailboxAvailability.AVAILABLE, (1, 0, 0, 0)),
            (MailboxAvailability.AVAILABLE, (1, 1, 1, 0)),
            (MailboxAvailability.UNAVAILABLE, (0, 0, 0, 1)),
            (MailboxAvailability.AVAILABLE, (-1, 0, 0, 0)),
        ):
            with self.subTest(counters=counters):
                with self.assertRaises(ValueError):
                    CollectMailMailboxResult(
                        mailbox=MailboxType.PLAYER,
                        availability=availability,
                        processed_count=counters[0],
                        archived_count=counters[1],
                        skipped_existing_count=counters[2],
                        scroll_count=counters[3],
                    )
        with self.assertRaises(ValueError):
            CollectMailResult(mailboxes=(item, item))
        self.assertEqual(
            "",
            mail_thread_row_key(
                DetectedListEntry(kind=ListEntryKind.MAIL_THREAD, bounds=Bounds(0, 0, 1, 1))
            ),
        )


def _workflow(
    root: str,
    *,
    limit: int = 25,
    archive_mode: MailArchiveMode = MailArchiveMode.TEXT,
) -> CollectMailWorkflow:
    """Builds one workflow using the canonical archive store in a temporary root."""

    return CollectMailWorkflow(
        params=CollectMailParams(
            mailboxes=(MailboxType.PLAYER,),
            archive_mode=archive_mode,
            limit_per_mailbox=limit,
            only_new=True,
        ),
        account_id="account",
        pnc_account_id="pnc-account",
        active_castle="Main",
        archive_store=MailArchiveStore(root=Path(root) / "mail"),
    )


def _counts(result: CollectMailMailboxResult) -> tuple[int, int, int, int]:
    """Returns counters in the compact order used by assertions."""

    return (
        result.processed_count,
        result.archived_count,
        result.skipped_existing_count,
        result.scroll_count,
    )


def _row(sender: str, subtitle: str) -> DetectedListEntry:
    """Builds one deterministic visible mailbox row."""

    return DetectedListEntry(
        kind=ListEntryKind.MAIL_THREAD,
        bounds=Bounds(5, 5, 100, 40),
        title_text=sender,
        subtitle_text=subtitle,
        metadata={"date_text": "Sep 11"},
        action_point=(50, 25),
    )


def _mailbox(
    rows: tuple[DetectedListEntry, ...],
    *,
    captured_at: datetime,
    empty: bool = False,
) -> Observation:
    """Builds one fresh typed mailbox-list observation."""

    return Observation(
        screen_type=ScreenType.PNC_MAILBOX_LIST,
        visible_elements={},
        list_entries=rows,
        captured_at=captured_at,
        mailbox_type=MailboxType.PLAYER,
        mailbox_empty=empty,
    )


def _thread(captured_at: datetime) -> Observation:
    """Builds one typed thread with a stable message fingerprint."""

    return Observation(
        screen_type=ScreenType.PNC_MAIL_THREAD,
        visible_elements={},
        list_entries=(
            DetectedListEntry(
                kind=ListEntryKind.MAIL_MESSAGE,
                bounds=Bounds(5, 5, 100, 40),
                title_text="Reward message",
                metadata={"timestamp_text": "Sep 11"},
            ),
        ),
        captured_at=captured_at,
        mailbox_type=MailboxType.PLAYER,
    )


def _with_artifact(observation: Observation, artifact_path: Path) -> Observation:
    """Returns a copy of one fixture observation with persisted screenshot evidence."""

    from dataclasses import replace

    return replace(observation, artifact_path=artifact_path)


class _FakeMailContext:
    """Minimal constrained context double exposing only the mail workflow methods."""

    def __init__(
        self,
        *,
        availability: MailboxAvailability,
        content: tuple[Observation, ...] = (),
        scroll_result: Observation | None = None,
    ) -> None:
        self.availability = availability
        self.content = content
        self.scroll_result = scroll_result
        self.calls: list[tuple[str, object]] = []
        self._content_index = 0

    def navigate(self, target: ScreenType) -> Observation:
        self.calls.append(("navigate", target))
        return Observation(screen_type=target, visible_elements={})

    def open_mailbox(self, mailbox: MailboxType) -> MailboxAvailability:
        self.calls.append(("open_mailbox", mailbox))
        return self.availability

    def observe_content(self, *, expected_screen: ScreenType) -> Observation:
        self.calls.append(("observe_content", expected_screen))
        if self._content_index >= len(self.content):
            raise AssertionError(f"No fixture content remains for {expected_screen}.")
        observation = self.content[self._content_index]
        self._content_index += 1
        if observation.screen_type != expected_screen:
            raise AssertionError(f"Expected {expected_screen}, got {observation.screen_type}.")
        return observation

    def open_mail_thread(self, row_key: str) -> Observation:
        self.calls.append(("open_mail_thread", row_key))
        return Observation(screen_type=ScreenType.PNC_MAIL_THREAD, visible_elements={})

    def scroll_mailbox(self) -> Observation:
        self.calls.append(("scroll_mailbox", None))
        if self.scroll_result is None:
            raise AssertionError("A scroll fixture is required.")
        return self.scroll_result


if __name__ == "__main__":
    unittest.main()
