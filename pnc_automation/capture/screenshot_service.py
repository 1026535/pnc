"""Screenshot acquisition, validation, and artifact persistence."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from pnc_automation.capture.artifact_store import ArtifactRecord, ArtifactStore
from pnc_automation.emulator.session import BlueStacksSession
from pnc_automation.errors import ScreenshotCaptureError


@dataclass(frozen=True, slots=True)
class CapturedScreenshot:
    """Owns the decoded image and persisted artifact metadata for one capture."""

    artifact: ArtifactRecord
    image: Image.Image
    image_format: str


@dataclass(slots=True)
class ScreenshotService:
    """Captures screenshots and persists them as first-class debugging artifacts."""

    artifact_store: ArtifactStore
    screenshot_format: str = "png"

    def capture(self, session: BlueStacksSession, *, artifact_directory: str, label: str) -> CapturedScreenshot:
        """Captures a screenshot and persists it under the provided per-castle artifact directory."""

        payload = session.capture_screenshot_bytes()
        image = _decode_image(payload)
        artifact = self.artifact_store.persist_bytes(
            artifact_directory=artifact_directory,
            label=label,
            extension=self.screenshot_format,
            payload=payload,
        )
        return CapturedScreenshot(
            artifact=artifact,
            image=image,
            image_format=image.format or self.screenshot_format.upper(),
        )


def _decode_image(payload: bytes) -> Image.Image:
    """Decodes and fully loads one screenshot image or fails fast."""

    try:
        image = Image.open(BytesIO(payload))
        image.load()
        return image
    except (UnidentifiedImageError, OSError) as error:
        raise ScreenshotCaptureError("Screenshot payload was not a valid image.") from error
