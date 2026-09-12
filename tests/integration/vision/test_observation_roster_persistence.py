"""Observation roster persistence: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.persistence.castle_roster_store import CastleRosterStore
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ObservationService,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class ObservationRosterPersistenceTests(unittest.TestCase):
    """Proves observation roster persistence."""

    def test_observation_service_syncs_castle_roster_cache_only_after_account_verification(self) -> None:
        """Persists discovered castle rosters only when the visible roster matches a trusted snapshot."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            for x in range(410, 470):
                for y in range(520, 590):
                    image.putpixel((x, y), (40, 200, 70))
            observation_builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
                            _ocr_line("K226 Kingdom", x=98, y=603, width=128, height=18),
                            _ocr_line("please b gentle", x=99, y=630, width=150, height=19),
                            _ocr_line("Castle Level 11", x=98, y=657, width=132, height=18),
                        )
                    )
                )
            roster_store = CastleRosterStore(
                path=root / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(
                            CastleIdentity(kingdom="K230", castle_name="Lv.5 Hellhound", castle_level=8),
                            CastleIdentity(kingdom="K226", castle_name="please b gentle", castle_level=10),
                        ),
                    ),
                ),
            )
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=observation_builder,
                session=_FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_lv_5_hellhound",
                pnc_account_id="inline_user",
                castle_roster_store=roster_store,
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
        """Leaves the cache untouched when the visible castle roster cannot prove account ownership."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            image = Image.new("RGB", (540, 960), (15, 28, 68))
            for x in range(410, 470):
                for y in range(520, 590):
                    image.putpixel((x, y), (40, 200, 70))
            observation_builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Manage Char.", x=132, y=18, width=152, height=24),
                            _ocr_line("K230 Kingdom", x=98, y=494, width=128, height=18),
                            _ocr_line("Lv.5 Hellhound", x=99, y=522, width=139, height=19),
                            _ocr_line("Castle Level 9", x=98, y=549, width=126, height=18),
                        )
                    )
                )
            roster_store = CastleRosterStore(
                path=root / "castles.yaml",
                rosters=(
                    PncAccountCastleRosterConfig(
                        pnc_account_id="inline_user",
                        castles=(CastleIdentity(kingdom="K999", castle_name="Other Castle", castle_level=1),),
                    ),
                ),
            )
            service = ObservationService(
                screenshot_service=screenshot_service,
                observation_builder=observation_builder,
                session=_FakeScreenshotSession(_encode_png(image)),
                artifact_directory="k230_lv_5_hellhound",
                pnc_account_id="inline_user",
                castle_roster_store=roster_store,
            )

            observation = service.observe("scan")

            self.assertIsNone(observation.verified_pnc_account_id)
            self.assertFalse((root / "castles.yaml").exists())
