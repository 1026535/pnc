"""Observation roster persistence at the explicit castle-parser boundary."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.castles import (
    CastleIdentity,
    PncAccountCastleRosterConfig,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
    ObservationService,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry
from tests.support.pnc.capture_vision.navigation_semantic_parsers import (
    _build_castle_selection_semantic_additions,
)
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.mail.build_observation import _build_accepted_observation
from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService


class _AcceptedCastleObservationBuilder:
    """Builds the captured frame through an explicitly accepted roster parser."""

    def __init__(self, inner: ObservationBuilder, lines: tuple[OcrLine, ...]) -> None:
        self._inner = inner
        self._lines = lines

    def create_ocr_context(self, screenshot: CapturedScreenshot) -> ObservationOcrContext:
        """Create the frame-scoped OCR context owned by the real builder."""

        return self._inner.create_ocr_context(screenshot)

    def build(
        self,
        screenshot: CapturedScreenshot,
        *,
        request: ObservationRequest | None = None,
        ocr_context: ObservationOcrContext | None = None,
    ):
        """Publish supplied OCR through the canonical castle-selection parser."""

        return _build_accepted_observation(
            builder=self._inner,
            screenshot=screenshot,
            request=request or ObservationRequest.full_runtime_default(),
            lines=self._lines,
            accepted_screen=ScreenType.PNC_CASTLE_SELECTION,
            semantic_parser=_build_castle_selection_semantic_additions,
            ocr_context=ocr_context,
        )


def _build_roster_service(
    *,
    root: Path,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    roster: PncAccountCastleRosterConfig,
) -> ObservationService:
    """Build a service whose capture and persistence seams remain production-owned."""

    screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
    inner_builder = ObservationBuilder(
        selector_registry=_minimal_runtime_registry(),
        selector_engine=ImageSelectorEngine(template_matcher=OpenCvTemplateMatcher()),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(),
        ocr_service=_FakeOcrService(lines=lines),
    )
    roster_store = CastleRosterStore(
        path=root / "castles.yaml",
        rosters=(roster,),
    )
    return ObservationService(
        screenshot_service=screenshot_service,
        observation_builder=_AcceptedCastleObservationBuilder(inner_builder, lines),
        session=_FakeScreenshotSession(_encode_png(image)),
        artifact_directory="k230_lv_5_hellhound",
        pnc_account_id="inline_user",
        castle_roster_store=roster_store,
    )


def _build_castle_roster_image() -> Image.Image:
    """Return the original selected-row geometry used by this persistence contract."""

    image = Image.new("RGB", (540, 960), (15, 28, 68))
    for x in range(410, 470):
        for y in range(520, 590):
            image.putpixel((x, y), (40, 200, 70))
    return image


class ObservationRosterPersistenceTests(unittest.TestCase):
    """Prove roster persistence separately from visual screen identity."""

    def test_observation_service_syncs_castle_roster_cache_only_after_account_verification(self) -> None:
        """Persist discovered castles when the explicit roster matches the trusted snapshot."""

        lines = (
            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
            _ocr_line("K226 Kingdom", x=98, y=603, width=128, height=18),
            _ocr_line("please b gentle", x=99, y=630, width=150, height=19),
            _ocr_line("Castle Level 11", x=98, y=657, width=132, height=18),
        )
        roster = PncAccountCastleRosterConfig(
            pnc_account_id="inline_user",
            castles=(
                CastleIdentity(kingdom="K230", castle_name="Lv.5 Hellhound", castle_level=8),
                CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=10),
            ),
        )

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            service = _build_roster_service(
                root=root,
                image=_build_castle_roster_image(),
                lines=lines,
                roster=roster,
            )

            observation = service.observe("scan")

            persisted = (root / "castles.yaml").read_text(encoding="utf-8")
            self.assertEqual(observation.verified_pnc_account_id, "inline_user")
            self.assertIn("inline_user", persisted)
            self.assertIn("ordering: unknown", persisted)
            self.assertIn("Lv.5 Hellhound", persisted)
            self.assertIn("castle_level: 9", persisted)
            self.assertIn("please b gentle", persisted)
            self.assertIn("castle_level: 11", persisted)

    def test_observation_service_does_not_sync_castle_roster_cache_without_account_verification(self) -> None:
        """Leave the cache untouched when the explicit roster cannot prove ownership."""

        lines = (
            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
        )
        roster = PncAccountCastleRosterConfig(
            pnc_account_id="inline_user",
            castles=(CastleIdentity(kingdom="K999", castle_name="Other Castle", castle_level=1),),
        )

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            service = _build_roster_service(
                root=root,
                image=_build_castle_roster_image(),
                lines=lines,
                roster=roster,
            )

            observation = service.observe("scan")

            self.assertIsNone(observation.verified_pnc_account_id)
            self.assertFalse((root / "castles.yaml").exists())
