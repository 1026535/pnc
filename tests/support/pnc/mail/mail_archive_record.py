"""Synthetic mail_archive_record fixture."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.mail import MailboxType



def _mail_archive_record() -> MailArchiveRecord:
    """Builds one deterministic mail archive record for store tests."""

    from datetime import UTC, datetime
    from pnc_automation.app.pnc.domain.mail import MailArchiveRecord, MailboxType, MailThreadFingerprint

    return MailArchiveRecord(
        account_id="account_a",
        pnc_account_id="user@example.com",
        active_castle="Main",
        mailbox_type=MailboxType.PLAYER,
        sender_name="Enemy Bob",
        thread_timestamp_text="1 min ago",
        fingerprint=MailThreadFingerprint("deadbeef"),
        captured_at=datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC),
        normalized_thread_text="Greetings\nWelcome to automation.",
    )
