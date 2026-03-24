"""Screenshot capture and artifact persistence."""

from pnc_automation.capture.artifact_store import ArtifactRecord, ArtifactStore
from pnc_automation.capture.chat_archive_store import ChatArchiveStore, StoredChatArchiveUpdate
from pnc_automation.capture.mail_archive_store import MailArchiveStore, StoredMailArchiveRecord
from pnc_automation.capture.screenshot_service import CapturedScreenshot, ScreenshotService

__all__ = [
    "ArtifactRecord",
    "ArtifactStore",
    "ChatArchiveStore",
    "CapturedScreenshot",
    "MailArchiveStore",
    "ScreenshotService",
    "StoredChatArchiveUpdate",
    "StoredMailArchiveRecord",
]
