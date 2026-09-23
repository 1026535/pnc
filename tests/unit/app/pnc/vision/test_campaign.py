"""Unit coverage for the Campaign producer's measured feature arithmetic."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision import campaign
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrResult,
)


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


def _row(bounds: Bounds) -> DetectedListEntry:
    return DetectedListEntry(
        kind=ListEntryKind.CAMPAIGN_STAGE,
        bounds=bounds,
        row_status=RowRecognitionStatus.UNREADABLE,
    )


class CampaignFeatureArithmeticTests(unittest.TestCase):
    """White and high-red pixels must never classify as navy interiors."""

    def test_node_features_do_not_wrap_bright_pixels_into_navy(self) -> None:
        disc = Bounds(20, 20, 60, 60)
        for name, color in (
            ("white", (255, 255, 255)),
            ("bright_red", (240, 30, 30)),
        ):
            with self.subTest(fill=name):
                pixels = np.zeros((100, 100, 3), dtype=np.uint8)
                pixels[:, :] = color
                features = campaign._node_features(pixels, disc)
                self.assertEqual(0.0, features["blue"])
                self.assertEqual(0.0, features["navy_band"])

        pixels = np.zeros((100, 100, 3), dtype=np.uint8)
        pixels[:, :] = (20, 20, 120)
        features = campaign._node_features(pixels, disc)
        self.assertGreater(features["blue"], 0.9)

    def test_nameplate_navy_check_does_not_count_white_or_red_trim(self) -> None:
        plate = Bounds(0, 0, 60, 20)
        for name, color, expected in (
            ("white", (255, 255, 255), False),
            ("bright_red", (240, 30, 30), False),
        ):
            with self.subTest(fill=name):
                pixels = np.zeros((40, 80, 3), dtype=np.uint8)
                pixels[:, :] = color
                self.assertIs(
                    campaign._nameplate_supported(pixels, plate, gold=False), expected
                )

        pixels = np.zeros((40, 80, 3), dtype=np.uint8)
        pixels[:, :] = (15, 15, 25)
        pixels[:, :20] = (30, 30, 140)
        self.assertTrue(campaign._nameplate_supported(pixels, plate, gold=False))


class CampaignDedupTests(unittest.TestCase):
    """Duplicate ownership is decided by marker geometry, not row envelopes."""

    def test_distinct_nearby_markers_survive_overlapping_row_envelopes(self) -> None:
        rows = [
            (Bounds(10, 10, 30, 30), _row(Bounds(10, 10, 160, 60))),
            (Bounds(120, 20, 30, 30), _row(Bounds(50, 15, 160, 60))),
        ]
        kept = campaign._deduplicate_marked(rows)
        self.assertEqual(2, len(kept))

    def test_overlapping_markers_collapse_to_the_first_row(self) -> None:
        rows = [
            (Bounds(10, 10, 30, 30), _row(Bounds(10, 10, 160, 60))),
            (Bounds(20, 15, 30, 30), _row(Bounds(30, 12, 160, 60))),
        ]
        kept = campaign._deduplicate_marked(rows)
        self.assertEqual(1, len(kept))
        self.assertIs(kept[0], rows[0][1])


class CampaignDiscNumberTests(unittest.TestCase):
    """Badge numerals require a unique credible positive value."""

    def setUp(self) -> None:
        self.image = Image.new("RGB", (540, 960), (0, 0, 0))
        self.disc = Bounds(100, 100, 50, 50)

    def _read(self, results: list[OcrResult]) -> tuple[int | None, _QueuedOcrBackend]:
        context, backend = _ocr_context(self.image, results)
        value = campaign._read_disc_number(
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


class CampaignStageDetailProducerTests(unittest.TestCase):
    """Stage-detail facts publish only from bounded credible reads."""

    def setUp(self) -> None:
        self.image = Image.new("RGB", (540, 960), (0, 0, 0))

    def _additions(
        self, results: list[OcrResult]
    ) -> tuple[campaign.ObservationAdditions, _QueuedOcrBackend]:
        context, backend = _ocr_context(self.image, results)
        additions = campaign.build_campaign_additions(
            image=self.image,
            screen_type=ScreenType.PNC_CAMPAIGN_STAGE,
            ocr_context=context,
            template_matcher=None,
            challenge_bounds=Bounds(178, 643, 184, 54),
        )
        return additions, backend

    def _reads(
        self,
        *,
        title: str | None = "[10-3] Grandia Ruins",
        gauge: str | None = "150/120",
        cost: str | None = "12",
        confidence: float = 0.9,
    ) -> list[OcrResult]:
        return [
            _line_result(
                *([] if title is None else [OcrLine(text=title, bounds=Bounds(0, 0, 8, 8), confidence=confidence)])
            ),
            _line_result(
                *([] if gauge is None else [OcrLine(text=gauge, bounds=Bounds(0, 0, 8, 8), confidence=confidence)])
            ),
            _line_result(
                *([] if cost is None else [OcrLine(text=cost, bounds=Bounds(0, 0, 8, 8), confidence=confidence)])
            ),
        ]

    def test_stage_detail_publishes_title_gauge_and_cost_from_bounded_regions(self) -> None:
        additions, backend = self._additions(self._reads())

        detail = additions.campaign_stage
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(10, detail.chapter_number)
        self.assertEqual(3, detail.stage_number)
        self.assertEqual("Grandia Ruins", detail.name)
        self.assertEqual(150, detail.action_points)
        self.assertEqual(120, detail.max_action_points)
        self.assertEqual(12, detail.challenge_cost)
        self.assertIsNone(detail.mode)
        self.assertEqual((), additions.list_entries)
        self.assertIsNone(additions.campaign_chapter)
        self.assertEqual(3, len(backend.regions))
        self.assertTrue(all(region is not None for region in backend.regions))

    def test_unreadable_title_keeps_ordinals_and_name_unknown(self) -> None:
        additions, _backend = self._additions(self._reads(title="Grandia Ruins"))

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.chapter_number)
        self.assertIsNone(detail.stage_number)
        self.assertIsNone(detail.name)
        self.assertEqual(150, detail.action_points)
        self.assertEqual(12, detail.challenge_cost)

    def test_missing_measured_challenge_does_not_read_or_invent_its_cost(self) -> None:
        context, backend = _ocr_context(self.image, self._reads())
        detail = campaign.build_campaign_additions(
            image=self.image, screen_type=ScreenType.PNC_CAMPAIGN_STAGE,
            ocr_context=context, template_matcher=None,
        ).campaign_stage
        self.assertIsNotNone(detail)
        self.assertIsNone(detail.challenge_cost)
        self.assertEqual(2, len(backend.regions))

    def test_title_with_nonpositive_ordinals_abstains(self) -> None:
        additions, _backend = self._additions(self._reads(title="[0-0] Grandia Ruins"))

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.chapter_number)
        self.assertIsNone(detail.stage_number)

    def test_conflicting_gauge_reads_abstain(self) -> None:
        additions, _backend = self._additions(
            self._reads()[:1]
            + [
                _line_result(
                    OcrLine(text="150/120", bounds=Bounds(0, 0, 8, 8), confidence=0.9),
                    OcrLine(text="90/60", bounds=Bounds(20, 0, 8, 8), confidence=0.9),
                )
            ]
            + self._reads(title=None, gauge=None)[2:]
        )

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.action_points)
        self.assertIsNone(detail.max_action_points)

    def test_low_confidence_or_conflicting_title_does_not_publish_identity(self) -> None:
        for lines in (
            (OcrLine(text="[10-3] Grandia Ruins", bounds=Bounds(0, 0, 80, 18), confidence=0.5),),
            (
                OcrLine(text="[10-3] Grandia Ruins", bounds=Bounds(0, 0, 80, 18), confidence=0.95),
                OcrLine(text="[10-5] Grandia Ruins", bounds=Bounds(0, 20, 80, 18), confidence=0.95),
            ),
        ):
            with self.subTest(lines=lines):
                additions, _backend = self._additions([_line_result(*lines)] + self._reads()[1:])
                detail = additions.campaign_stage
                assert detail is not None
                self.assertIsNone(detail.chapter_number)
                self.assertIsNone(detail.stage_number)
                self.assertIsNone(detail.name)
                self.assertEqual(12, detail.challenge_cost)

    def test_low_confidence_gauge_read_abstains(self) -> None:
        additions, _backend = self._additions(self._reads(gauge="150/120", confidence=0.9)[:1] + [
            _line_result(OcrLine(text="150/120", bounds=Bounds(0, 0, 8, 8), confidence=0.5))
        ] + self._reads(title=None, gauge=None)[2:])

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.action_points)
        self.assertIsNone(detail.max_action_points)

    def test_gauge_with_zero_max_abstains_before_the_domain_model(self) -> None:
        additions, _backend = self._additions(self._reads(gauge="150/0"))

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.action_points)
        self.assertIsNone(detail.max_action_points)

    def test_conflicting_cost_reads_abstain(self) -> None:
        additions, _backend = self._additions(
            self._reads()[:2]
            + [
                _line_result(
                    OcrLine(text="12", bounds=Bounds(0, 0, 8, 8), confidence=0.9),
                    OcrLine(text="8", bounds=Bounds(20, 0, 8, 8), confidence=0.9),
                )
            ]
        )

        detail = additions.campaign_stage
        assert detail is not None
        self.assertIsNone(detail.challenge_cost)

    def test_nonpositive_or_low_confidence_cost_abstains(self) -> None:
        for cost, confidence in (("0", 0.99), ("12", 0.5)):
            with self.subTest(cost=cost, confidence=confidence):
                additions, _backend = self._additions(
                    self._reads(cost=cost, confidence=0.9)[:2]
                    + [_line_result(OcrLine(text=cost, bounds=Bounds(0, 0, 8, 8), confidence=confidence))]
                )
                detail = additions.campaign_stage
                assert detail is not None
                self.assertIsNone(detail.challenge_cost)

    def test_fully_unreadable_reads_publish_no_stage_detail(self) -> None:
        additions, backend = self._additions(self._reads(title=None, gauge=None, cost=None))

        self.assertIsNone(additions.campaign_stage)
        self.assertEqual(3, len(backend.regions))

    def test_non_campaign_screens_publish_no_stage_detail(self) -> None:
        context, _backend = _ocr_context(self.image, [])
        for screen in (ScreenType.PNC_HOME_CITY, ScreenType.PNC_CAMPAIGN_CHAPTER):
            with self.subTest(screen=screen):
                additions = campaign.build_campaign_additions(
                    image=self.image,
                    screen_type=screen,
                    ocr_context=context,
                    template_matcher=None,
                )
                self.assertIsNone(additions.campaign_stage)


if __name__ == "__main__":
    unittest.main()
