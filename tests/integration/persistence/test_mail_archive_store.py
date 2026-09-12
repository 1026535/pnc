"""Mail archive store: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStore
from pnc_automation.app.pnc.domain.mail import MailArchiveMode

from tests.support.core.images import build_png_bytes
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures
from tests.support.pnc.mail.mail_archive_record import _mail_archive_record


class MailArchiveStoreTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves mail archive store."""

    def test_mail_archive_store_reuses_existing_fingerprint(self) -> None:
        """Skips duplicate archive creation when the same fingerprint already exists for the mailbox."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = MailArchiveStore(root=Path(temp_directory) / "mail")
            screenshot_path = Path(temp_directory) / "source.png"
            screenshot_path.write_bytes(build_png_bytes())
            record = _mail_archive_record()

            first = store.persist(
                record=record,
                archive_mode=MailArchiveMode.BOTH,
                screenshot_source_path=screenshot_path,
                skip_existing=True,
            )
            second = store.persist(
                record=record,
                archive_mode=MailArchiveMode.BOTH,
                screenshot_source_path=screenshot_path,
                skip_existing=True,
            )

            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.directory, second.directory)

    def test_required_payload_failure_does_not_create_completion_marker_and_retry_succeeds(self) -> None:
        """An incomplete candidate never suppresses a later valid capture."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            screenshot_path = Path(temp_directory) / "source.png"
            screenshot_path.write_bytes(build_png_bytes())
            record = _mail_archive_record()
            real_atomic_write = __import__(
                "pnc_automation.app.pnc.persistence.mail_archive_store",
                fromlist=["atomic_write_bytes"],
            ).atomic_write_bytes

            def fail_metadata(destination: Path, payload: bytes, **kwargs: object) -> None:
                if destination.name == "metadata.json":
                    raise OSError("injected metadata publication failure")
                real_atomic_write(destination, payload, **kwargs)

            with patch("pnc_automation.app.pnc.persistence.mail_archive_store.atomic_write_bytes", side_effect=fail_metadata):
                with self.assertRaises(OSError):
                    store.persist(
                        record=record,
                        archive_mode=MailArchiveMode.BOTH,
                        screenshot_source_path=screenshot_path,
                        skip_existing=True,
                    )
            self.assertEqual((), tuple(root.rglob("metadata.json")))
            self.assertFalse(store.has_fingerprint(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
            ))
            retry = store.persist(
                record=record,
                archive_mode=MailArchiveMode.BOTH,
                screenshot_source_path=screenshot_path,
                skip_existing=True,
            )
            self.assertTrue(retry.created)
            self.assertTrue((retry.directory / "metadata.json").is_file())
            self.assertEqual(screenshot_path.read_bytes(), (retry.directory / "thread.png").read_bytes())

    def test_legacy_metadata_only_directory_is_not_a_completion_marker(self) -> None:
        """Old marker-first directories remain inspectable but are retryable."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            legacy_directory = store._build_directory(record)
            legacy_directory.mkdir(parents=True)
            (legacy_directory / "metadata.json").write_text(
                '{"active_castle":"Main","mailbox_type":"player","fingerprint":"deadbeef",'
                '"normalized_thread_text":"Greetings"}',
                encoding="utf-8",
            )
            self.assertFalse(store.has_fingerprint(
                active_castle="Main", mailbox_type="player", fingerprint="deadbeef"
            ))
            retry = store.persist(record=record, archive_mode=MailArchiveMode.TEXT, skip_existing=True)
            self.assertTrue(retry.created)
            self.assertEqual("Greetings\nWelcome to automation.", (retry.directory / "thread.txt").read_text(encoding="utf-8"))

    def test_skip_existing_false_preserves_completed_payload_bytes_with_collision_suffix(self) -> None:
        """A forced second capture never overwrites the first immutable payload set."""

        with tempfile.TemporaryDirectory() as temp_directory:
            store = MailArchiveStore(root=Path(temp_directory) / "mail")
            record = _mail_archive_record()
            first = store.persist(record=record, archive_mode=MailArchiveMode.TEXT, skip_existing=True)
            second = store.persist(record=record, archive_mode=MailArchiveMode.TEXT, skip_existing=False)
            self.assertNotEqual(first.directory, second.directory)
            self.assertFalse(first.directory.name == second.directory.name)
            self.assertEqual(
                (first.directory / "thread.txt").read_bytes(),
                (second.directory / "thread.txt").read_bytes(),
            )
