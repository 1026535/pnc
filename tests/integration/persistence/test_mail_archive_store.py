"""Mail archive store: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
