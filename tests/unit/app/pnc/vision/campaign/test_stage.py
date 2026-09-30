"""Unit tests for bounded Campaign stage-detail reads and abstention."""

from __future__ import annotations
from datetime import UTC, datetime
import unittest
from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.campaign import build_campaign_additions
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_STAGE_ACTION_POINTS_REGION,
    CAMPAIGN_STAGE_CENTER_ACTION_POINTS_REGION,
    CAMPAIGN_STAGE_TITLE_REGION,
    campaign_stage_challenge_cost_bounds,
)
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
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

def _line_result(*lines: OcrLine) -> OcrResult:
    return OcrResult(lines=tuple(lines), words=())


class CampaignStageDetailProducerTests(unittest.TestCase):
    """Stage-detail facts publish only from bounded credible reads."""

    def setUp(self) -> None:
        self.image = Image.new("RGB", (540, 960), (0, 0, 0))

    def _additions(
        self, results: list[OcrResult]
    ) -> tuple[ObservationAdditions, _QueuedOcrBackend]:
        context, backend = _ocr_context(self.image, results)
        additions = build_campaign_additions(
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

    def test_single_row_title_fragments_follow_horizontal_order(self) -> None:
        # Native 6-4/6-5 shows one visual title row. A few pixels of OCR
        # top-edge jitter must not move its rightmost words before "Marsh".
        for stage in (4, 5):
            with self.subTest(stage=stage):
                title = _line_result(
                    OcrLine(f"[6-{stage}]", Bounds(151, 196, 59, 24), 0.98),
                    OcrLine("of Tear", Bounds(303, 198, 87, 22), 0.95),
                    OcrLine("Marsh", Bounds(222, 201, 76, 20), 0.95),
                )
                additions, _backend = self._additions(
                    [title] + self._reads(title=None)[1:]
                )
                detail = additions.campaign_stage
                assert detail is not None
                self.assertEqual((6, stage, "Marsh of Tear"), (
                    detail.chapter_number, detail.stage_number, detail.name,
                ))
                self.assertEqual((150, 120, 12), (
                    detail.action_points, detail.max_action_points,
                    detail.challenge_cost,
                ))

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
        detail = build_campaign_additions(
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
        additions, backend = self._additions(
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
        self.assertEqual(3, len(backend.regions))

    def test_centered_gauge_fallback_preserves_cost_and_bounded_reads(self) -> None:
        reads = self._reads(gauge="126/120")
        additions, backend = self._additions(
            reads[:1] + [_line_result()] + reads[1:]
        )

        detail = additions.campaign_stage
        assert detail is not None
        self.assertEqual(126, detail.action_points)
        self.assertEqual(120, detail.max_action_points)
        self.assertEqual(12, detail.challenge_cost)
        self.assertEqual(
            [
                CAMPAIGN_STAGE_TITLE_REGION,
                CAMPAIGN_STAGE_ACTION_POINTS_REGION,
                CAMPAIGN_STAGE_CENTER_ACTION_POINTS_REGION,
                campaign_stage_challenge_cost_bounds(Bounds(178, 643, 184, 54)),
            ],
            backend.regions,
        )

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
        self.assertEqual(4, len(backend.regions))

    def test_non_campaign_screens_publish_no_stage_detail(self) -> None:
        context, _backend = _ocr_context(self.image, [])
        for screen in (ScreenType.PNC_HOME_CITY, ScreenType.PNC_CAMPAIGN_CHAPTER):
            with self.subTest(screen=screen):
                additions = build_campaign_additions(
                    image=self.image,
                    screen_type=screen,
                    ocr_context=context,
                    template_matcher=None,
                )
                self.assertIsNone(additions.campaign_stage)


if __name__ == "__main__":
    unittest.main()
