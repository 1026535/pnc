"""Unit tests for bounded Campaign OCR and abstention."""

from __future__ import annotations
from datetime import UTC, datetime
import unittest
from PIL import Image
from pnc_automation.app.pnc.vision.campaign import ocr
from pnc_automation.app.pnc.vision.campaign_ocr_regions import CAMPAIGN_CHAPTER_TITLE_REGION, CAMPAIGN_REFERENCE_SIZE, scale_campaign_bounds
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult

def _frame_ref() -> FrameRef:
    """Builds deterministic provenance for one offline OCR context."""

    return FrameRef(
        session_id="campaign-unit-test",
        session_epoch=1,
        capture_sequence=1,
        input_sequence=0,
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

class _QueuedOcrBackend:
    """Returns one configured OCR result per backend read, in call order."""

    def __init__(self, results: list[OcrResult]) -> None:
        self.results = list(results)
        self.regions: list[Bounds | None] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Consume the next configured result and record the bounded region."""

        self.regions.append(region)
        if not self.results:
            return OcrResult(lines=(), words=())
        return self.results.pop(0)

def _ocr_context(
    image: Image.Image, results: list[OcrResult]
) -> tuple[ObservationOcrContext, _QueuedOcrBackend]:
    """Bind one queued backend to the canonical OCR context."""

    backend = _QueuedOcrBackend(results)
    return (
        ObservationOcrContext(image, backend, _frame_ref(), "campaign-unit-test"),
        backend,
    )

def _numeric_result(text: str, confidence: float) -> OcrResult:
    """One OCR line fixture carrying a numeric read at a given confidence."""

    return OcrResult(
        lines=(OcrLine(text=text, bounds=Bounds(0, 0, 8, 8), confidence=confidence),),
        words=(),
    )

def _line_result(*lines: OcrLine) -> OcrResult:
    return OcrResult(lines=tuple(lines), words=())

class CampaignDiscNumberTests(unittest.TestCase):
    """Badge numerals require a unique credible positive value."""

    def setUp(self) -> None:
        self.image = Image.new("RGB", (540, 960), (0, 0, 0))
        self.disc = Bounds(100, 100, 50, 50)

    def _read(self, results: list[OcrResult]) -> tuple[int | None, _QueuedOcrBackend]:
        context, backend = _ocr_context(self.image, results)
        value = ocr._read_disc_number(
            image=self.image,
            disc_ref=self.disc,
            ocr_context=context,
            required_fact="campaign_stage_number",
        )
        return value, backend

    def test_single_credible_numeral_resolves_without_retry(self) -> None:
        value, backend = self._read([_numeric_result("5", 0.85)])
        self.assertEqual(5, value)
        self.assertEqual(1, len(backend.regions))

    def test_inner_core_retry_recovers_a_ring_degraded_read(self) -> None:
        value, backend = self._read(
            [_numeric_result("5.", 0.99), _numeric_result("5", 0.9994)]
        )
        self.assertEqual(5, value)
        self.assertEqual(2, len(backend.regions))
        ordinary, core = backend.regions
        self.assertTrue(self.disc.contains_bounds(ordinary))
        self.assertTrue(ordinary.contains_bounds(core))
        self.assertGreater(ordinary.width, core.width)

    def test_low_confidence_numeral_is_not_credible(self) -> None:
        value, backend = self._read(
            [_numeric_result("5", 0.787), _numeric_result("5", 0.9994)]
        )
        self.assertEqual(5, value)
        self.assertEqual(2, len(backend.regions))

    def test_conflicting_credible_numerals_stay_unresolved(self) -> None:
        result = _line_result(
            OcrLine(text="3", bounds=Bounds(0, 0, 8, 8), confidence=0.9),
            OcrLine(text="5", bounds=Bounds(20, 0, 8, 8), confidence=0.9),
        )
        value, backend = self._read([result])
        self.assertIsNone(value)
        self.assertEqual(1, len(backend.regions))

    def test_zero_and_empty_reads_abstain_before_the_domain_model(self) -> None:
        value, _backend = self._read([_numeric_result("0", 0.99), OcrResult(lines=(), words=())])
        self.assertIsNone(value)

    def test_retry_conflict_also_abstains(self) -> None:
        result = _line_result(
            OcrLine(text="3", bounds=Bounds(0, 0, 8, 8), confidence=0.95),
            OcrLine(text="5", bounds=Bounds(20, 0, 8, 8), confidence=0.95),
        )
        value, _backend = self._read([OcrResult(lines=(), words=()), result])
        self.assertIsNone(value)

if __name__ == "__main__":
    unittest.main()



class CampaignOcrPlanTests(unittest.TestCase):
    """Pure reference-space OCR plan calculations stay below integration."""

    def test_campaign_ocr_regions_scale_reference_geometry(self) -> None:
            """Scale the reviewed Campaign regions without changing their native reference geometry."""

            self.assertEqual(CAMPAIGN_REFERENCE_SIZE, (540, 960))
            self.assertEqual(
                scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, (900, 1600)),
                Bounds(342, 63, 542, 100),
            )
            self.assertEqual(
                scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, CAMPAIGN_REFERENCE_SIZE),
                CAMPAIGN_CHAPTER_TITLE_REGION,
            )
            with self.assertRaisesRegex(ValueError, "positive image dimensions"):
                scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, (0, 960))


if __name__ == "__main__":
    unittest.main()
