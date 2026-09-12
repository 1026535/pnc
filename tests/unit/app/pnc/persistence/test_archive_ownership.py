"""Managed archive path and alias-boundary tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pnc_automation.app.pnc.persistence.archive_ownership import (
    ArchiveOwnershipError,
    validate_chat_archive_file,
    validate_managed_path,
)


class ArchiveOwnershipTests(unittest.TestCase):
    """Rejects root escapes, non-regular targets, and unsafe layouts."""

    def test_root_escape_and_wrong_layout_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "archive"
            root.mkdir()
            with self.assertRaises(ArchiveOwnershipError):
                validate_managed_path(root, root.parent / "outside.txt", allow_missing_leaf=True)
            with self.assertRaises(ArchiveOwnershipError):
                validate_chat_archive_file(
                    root,
                    root / "not-a-day" / "account" / "castle" / "kingdom" / "transcript.log",
                    allowed_names={"transcript.log"},
                    allow_missing=True,
                )

    def test_nonregular_managed_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "archive"
            transcript = root / "2026-01-01" / "account" / "castle" / "kingdom" / "transcript.log"
            transcript.mkdir(parents=True)
            with self.assertRaises(ArchiveOwnershipError):
                validate_chat_archive_file(
                    root,
                    transcript,
                    allowed_names={"transcript.log"},
                    allow_missing=False,
                )


if __name__ == "__main__":
    unittest.main()
