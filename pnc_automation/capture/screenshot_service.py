"""Screenshot acquisition, validation, and artifact persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from pnc_automation.capture.artifact_store import ArtifactRecord, ArtifactStore
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import ScreenshotCaptureError


@dataclass(frozen=True, slots=True)
class CapturedScreenshot:
    """Owns the decoded image and persisted artifact metadata for one capture."""

    artifact: ArtifactRecord | None
    image: Image.Image
    image_format: str
    payload: bytes | None = None
    ephemeral_captured_at: datetime | None = None

    @property
    def artifact_path(self) -> Path | None:
        """Returns the persisted artifact path when this capture wrote one."""

        if self.artifact is None:
            return None
        return self.artifact.path

    @property
    def captured_at(self) -> datetime:
        """Returns the canonical capture timestamp for persisted and ephemeral captures."""

        if self.artifact is not None:
            return self.artifact.captured_at
        if self.ephemeral_captured_at is not None:
            return self.ephemeral_captured_at
        raise ScreenshotCaptureError("CapturedScreenshot is missing its capture timestamp.")


@dataclass(slots=True)
class ScreenshotService:
    """Captures screenshots and persists them as first-class debugging artifacts."""

    artifact_store: ArtifactStore
    screenshot_format: str = "png"

    def capture(
        self,
        session: BlueStacksSession,
        *,
        artifact_directory: str,
        label: str,
        persist: bool = True,
    ) -> CapturedScreenshot:
        """Captures a screenshot and optionally persists it under the provided artifact directory."""

        payload = session.capture_screenshot_bytes()
        image = _decode_image(payload)
        artifact = (
            self.artifact_store.persist_bytes(
                artifact_directory=artifact_directory,
                label=label,
                extension=self.screenshot_format,
                payload=payload,
            )
            if persist
            else None
        )
        return CapturedScreenshot(
            artifact=artifact,
            image=image,
            image_format=image.format or self.screenshot_format.upper(),
            payload=payload,
            ephemeral_captured_at=None if persist else datetime.now(tz=UTC),
        )


def _decode_image(payload: bytes) -> Image.Image:
    """Decodes and fully loads one screenshot image or fails fast."""

    try:
        image = Image.open(BytesIO(payload))
        image.load()
        return image
    except (UnidentifiedImageError, OSError) as error:
        raise ScreenshotCaptureError("Screenshot payload was not a valid image.") from error
