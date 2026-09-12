"""Mail archive store: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pnc_automation.app.pnc.persistence.mail_archive_store import MailArchiveStorageError, MailArchiveStore
from pnc_automation.app.pnc.domain.mail import MailArchiveMode, MailThreadFingerprint

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

    def test_invalid_record_identity_is_rejected_before_mail_archive_mutation(self) -> None:
        """Unclassifiable records cannot allocate control paths or payload destinations."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            before = tuple(path.relative_to(root) for path in root.rglob("*"))
            with self.assertRaisesRegex(MailArchiveStorageError, "aware datetime"):
                store.persist(
                    record=replace(record, captured_at=datetime(2026, 1, 1, 12)),
                    archive_mode=MailArchiveMode.BOTH,
                    screenshot_source_path=Path(temp_directory) / "missing.png",
                )
            with self.assertRaisesRegex(MailArchiveStorageError, "lowercase hexadecimal"):
                store.persist(
                    record=replace(record, fingerprint=MailThreadFingerprint("ABCDEF12")),
                    archive_mode=MailArchiveMode.BOTH,
                    screenshot_source_path=Path(temp_directory) / "missing.png",
                )
            self.assertEqual(before, tuple(path.relative_to(root) for path in root.rglob("*")))

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
                json.dumps({
                    "active_castle": record.active_castle,
                    "mailbox_type": record.mailbox_type.value,
                    "fingerprint": record.fingerprint.value,
                    "normalized_thread_text": record.normalized_thread_text,
                }),
                encoding="utf-8",
            )
            self.assertFalse(store.has_fingerprint(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
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

    def test_versioned_metadata_contradiction_does_not_suppress_retry(self) -> None:
        """A complete-looking versioned directory is retryable when its identity disagrees internally."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            first = store.persist(record=record, archive_mode=MailArchiveMode.TEXT)
            metadata_path = first.directory / "metadata.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["normalized_thread_text"] = "Contradictory text"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

            self.assertFalse(store.has_fingerprint(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
            ))
            retry = store.persist(record=record, archive_mode=MailArchiveMode.TEXT, skip_existing=True)
            self.assertTrue(retry.created)
            self.assertNotEqual(first.directory, retry.directory)

    def test_skip_existing_prefers_manifest_verified_versioned_capture_over_legacy(self) -> None:
        """A later dedup lookup selects the suffixed verified capture and retains both diagnostics."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            legacy_directory = store._build_directory(record)
            legacy_directory.mkdir(parents=True)
            (legacy_directory / "metadata.json").write_text(json.dumps({
                "active_castle": record.active_castle,
                "mailbox_type": record.mailbox_type.value,
                "fingerprint": record.fingerprint.value,
                "normalized_thread_text": record.normalized_thread_text,
            }), encoding="utf-8")
            (legacy_directory / "thread.txt").write_text(record.normalized_thread_text, encoding="utf-8")

            versioned = store.persist(
                record=record,
                archive_mode=MailArchiveMode.TEXT,
                skip_existing=False,
            )
            self.assertTrue(versioned.created)
            self.assertTrue(versioned.directory.name.endswith("-1"))

            reused = store.persist(record=record, archive_mode=MailArchiveMode.TEXT, skip_existing=True)
            self.assertFalse(reused.created)
            self.assertEqual(versioned.directory, reused.directory)
            self.assertEqual(
                ("complete", "complete"),
                tuple(diagnostic.status.value for diagnostic in store.last_candidate_diagnostics),
            )

    def test_existing_complete_record_is_reused_before_requiring_new_screenshot(self) -> None:
        """Deduplication does not fail merely because a retry lacks its source screenshot."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            source = Path(temp_directory) / "source.png"
            source.write_bytes(build_png_bytes())
            record = _mail_archive_record()
            first = store.persist(record=record, archive_mode=MailArchiveMode.BOTH, screenshot_source_path=source)
            source.unlink()
            reused = store.persist(record=record, archive_mode=MailArchiveMode.BOTH, screenshot_source_path=source)
            self.assertFalse(reused.created)
            self.assertEqual(first.directory, reused.directory)

    def test_empty_screenshot_is_rejected_for_screenshot_and_both_modes(self) -> None:
        """Zero-byte screenshot files cannot become usable completion evidence."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            source = Path(temp_directory) / "empty.png"
            source.write_bytes(b"")
            record = _mail_archive_record()
            for mode in (MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH):
                with self.subTest(mode=mode):
                    with self.assertRaisesRegex(Exception, "non-empty"):
                        MailArchiveStore(root=root).persist(
                            record=record, archive_mode=mode, screenshot_source_path=source,
                        )
            self.assertEqual((), tuple(root.rglob("metadata.json")))

    def test_text_screenshot_and_both_modes_publish_their_required_payloads(self) -> None:
        """Each archive mode publishes exactly the payloads its completion metadata requires."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            source = Path(temp_directory) / "source.png"
            source.write_bytes(build_png_bytes())
            for mode in (MailArchiveMode.TEXT, MailArchiveMode.SCREENSHOT, MailArchiveMode.BOTH):
                with self.subTest(mode=mode):
                    record = _mail_archive_record()
                    stored = MailArchiveStore(root=root).persist(
                        record=record,
                        archive_mode=mode,
                        screenshot_source_path=source if mode != MailArchiveMode.TEXT else None,
                        skip_existing=False,
                    )
                    self.assertTrue(stored.created)
                    self.assertEqual(mode != MailArchiveMode.SCREENSHOT, stored.thread_text_path is not None)
                    self.assertEqual(mode != MailArchiveMode.TEXT, stored.screenshot_path is not None)
                    self.assertEqual(1, len(tuple(stored.directory.glob("metadata.json"))))

    def test_metadata_replace_effect_then_error_is_reused_on_retry(self) -> None:
        """A marker replacement that took effect remains a valid completion on retry."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            source = Path(temp_directory) / "source.png"
            source.write_bytes(build_png_bytes())
            record = _mail_archive_record()
            store = MailArchiveStore(root=root)
            real_atomic_write = __import__(
                "pnc_automation.app.pnc.persistence.mail_archive_store",
                fromlist=["atomic_write_bytes"],
            ).atomic_write_bytes

            def fail_after_metadata_replace(source_path: str | os.PathLike[str], target_path: str | os.PathLike[str]) -> None:
                os.replace(source_path, target_path)
                if Path(target_path).name == "metadata.json":
                    raise OSError("injected post-replace error")

            def patched_atomic(destination: Path, payload: bytes, **kwargs: object) -> None:
                if destination.name == "metadata.json":
                    kwargs["replace"] = fail_after_metadata_replace
                real_atomic_write(destination, payload, **kwargs)

            with patch("pnc_automation.app.pnc.persistence.mail_archive_store.atomic_write_bytes", side_effect=patched_atomic):
                with self.assertRaisesRegex(OSError, "post-replace"):
                    store.persist(record=record, archive_mode=MailArchiveMode.BOTH, screenshot_source_path=source)
            reused = store.persist(record=record, archive_mode=MailArchiveMode.BOTH, screenshot_source_path=None)
            self.assertFalse(reused.created)

    def test_corrupt_top_level_metadata_does_not_hide_valid_candidate(self) -> None:
        """A list or malformed candidate is ignored without masking a valid sibling."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            valid = store.persist(record=record, archive_mode=MailArchiveMode.TEXT)
            corrupt = valid.directory.with_name(valid.directory.name + "-1")
            corrupt.mkdir()
            (corrupt / "metadata.json").write_text("[]", encoding="utf-8")
            self.assertTrue(store.has_fingerprint(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
            ))
            self.assertEqual(
                ("complete", "corrupt"),
                tuple(diagnostic.status.value for diagnostic in store.last_candidate_diagnostics),
            )
            self.assertTrue(store.last_candidate_diagnostics[1].candidate_name.endswith("-1"))
            reused = store.persist(record=record, archive_mode=MailArchiveMode.TEXT)
            self.assertFalse(reused.created)
            self.assertEqual(valid.directory, reused.directory)

    def test_legacy_empty_screenshot_is_not_usable_evidence(self) -> None:
        """Legacy metadata remains conservative when its only screenshot is empty."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            store = MailArchiveStore(root=root)
            record = _mail_archive_record()
            directory = store._build_directory(record)
            directory.mkdir(parents=True)
            (directory / "metadata.json").write_text(
                json.dumps({
                    "active_castle": record.active_castle,
                    "mailbox_type": record.mailbox_type.value,
                    "fingerprint": record.fingerprint.value,
                    "normalized_thread_text": record.normalized_thread_text,
                }),
                encoding="utf-8",
            )
            (directory / "thread.png").write_bytes(b"")
            self.assertFalse(store.has_fingerprint(
                active_castle=record.active_castle,
                mailbox_type=record.mailbox_type.value,
                fingerprint=record.fingerprint.value,
            ))

    def test_same_fingerprint_lookup_and_create_are_serialized(self) -> None:
        """Concurrent stores produce one complete record and one deduplicated result."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory) / "mail"
            source = Path(temp_directory) / "source.png"
            source.write_bytes(build_png_bytes())
            record = _mail_archive_record()
            barrier = threading.Barrier(2)
            results: list[object] = []

            def persist() -> None:
                try:
                    barrier.wait(timeout=5)
                    results.append(MailArchiveStore(root=root).persist(
                        record=record,
                        archive_mode=MailArchiveMode.BOTH,
                        screenshot_source_path=source,
                    ))
                except BaseException as error:
                    results.append(error)

            threads = [threading.Thread(target=persist) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
            self.assertEqual(2, len(results))
            self.assertTrue(all(not isinstance(result, BaseException) for result in results), results)
            self.assertEqual(1, sum(result.created for result in results if not isinstance(result, BaseException)))
            self.assertEqual(1, len(tuple(root.rglob("metadata.json"))))
