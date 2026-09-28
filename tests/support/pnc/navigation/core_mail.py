"""Shared core mail doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


def mail_frame(
    screen: ScreenType,
    *,
    selector: UiElementId | None = None,
    entries: tuple[DetectedListEntry, ...] = (),
    captured_at: datetime | None = None,
    blocked: bool = False,
) -> Observation:
    """Build one typed mail frame with optional current-frame template control."""

    visible_elements = {}
    if selector is not None:
        visible_elements[selector] = VisibleElement(
            selector,
            Bounds(10, 20, 40, 40),
            1.0,
            source_kind=VisibleElementSourceKind.TEMPLATE,
        )
    return Observation(
        screen_type=screen,
        visible_elements=visible_elements,
        list_entries=entries,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def mailbox_category(mailbox: MailboxType, *, available: bool) -> DetectedListEntry:
    """Build one typed mail-hub category entry for constrained navigation tests."""

    return DetectedListEntry(
        kind=ListEntryKind.MAILBOX_CATEGORY,
        bounds=Bounds(20, 150, 500, 80),
        title_text=f"{mailbox.value} mail",
        action_point=(480, 190),
        metadata={"mailbox_type": mailbox.value, "available": available},
    )


def mail_thread_entry(title: str = "Lux") -> DetectedListEntry:
    """Build one canonical dynamic mailbox row."""

    return DetectedListEntry(
        kind=ListEntryKind.MAIL_THREAD,
        bounds=Bounds(20, 160, 500, 100),
        title_text=title,
        subtitle_text="Daily Donation Rank Reward",
        action_point=(270, 210),
        metadata={"date_text": "2026/09/11 20:02:00"},
    )
