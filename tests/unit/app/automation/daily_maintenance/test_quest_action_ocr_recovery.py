"""Focused tests for same-frame Quest action-label OCR recovery."""

from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestRowState
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.daily_quest_rows import (
    find_missing_quest_action_candidates,
    parse_daily_quest_screen,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_quest_additions
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine, OcrResult


class _QuestBackend:
    """Returns body OCR and a separately scripted action-control crop."""

    def __init__(
        self,
        body_lines: tuple[OcrLine, ...],
        action_lines: tuple[OcrLine, ...],
        *,
        full_size: tuple[int, int] = (540, 960),
        ocr_bounds: Bounds = Bounds(383, 415, 141, 41),
    ) -> None:
        self.body_lines = body_lines
        self.action_lines = action_lines
        self.full_size = full_size
        self.ocr_bounds = ocr_bounds
        self.regions: list[Bounds | None] = []
        self.image_inputs: list[tuple[int, int, str]] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        self.regions.append(region)
        self.image_inputs.append((image.width, image.height, image.mode))
        if image.size == self.full_size or (region is not None and region.width == self.full_size[0]):
            return OcrResult(lines=self.body_lines, words=())
        return OcrResult(
            lines=tuple(
                OcrLine(
                    text=line.text,
                    bounds=Bounds(
                        line.bounds.x - self.ocr_bounds.x,
                        line.bounds.y - self.ocr_bounds.y,
                        line.bounds.width,
                        line.bounds.height,
                    ),
                    confidence=line.confidence,
                    words=line.words,
                )
                for line in self.action_lines
            ),
            words=(),
        )


class QuestActionOcrRecoveryTests(unittest.TestCase):
    """Keep action-label recovery bounded and fail closed on unsafe evidence."""

    def test_recovers_missing_go_despite_pinned_full_frame_and_caches_crop(self) -> None:
        image = _quest_image()
        header = _quest_header_lines()
        body = _row_lines(title="Upgrade building 1x", progress="(0/1)")
        backend = _QuestBackend(body, (_line("Go", 430, 428, 42, 16),))
        context = ObservationOcrContext(image, backend, None, "test")
        context.read_result(image)

        additions = _build_quest_additions(
            image=image,
            lines=header,
            proved_screen=ScreenType.PNC_QUEST_DAILY,
            ocr_context=context,
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(additions)
        self.assertEqual(1, len(additions.list_entries))
        row = additions.list_entries[0]
        self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
        self.assertEqual(DailyQuestRowState.GO.value, row.metadata["row_state"])
        self.assertIsNotNone(row.action_point)
        self.assertEqual(2, context.metrics.engine_calls)
        self.assertEqual(None, backend.regions[0])
        self.assertEqual((540, 960, "RGB"), backend.image_inputs[0])
        self.assertEqual((141, 41, "RGB"), backend.image_inputs[1])
        self.assertEqual(1, context.metrics.fullframe_reuses)
        self.assertEqual(540 * 960 + 141 * 41, context.metrics.processed_pixel_area)
        self.assertTrue(row.action_bounds.contains_point(row.action_point))
        self.assertTrue(any(
            "fallback=missing_quest_action_label" in (diagnostic.detail or "")
            for diagnostic in context.read_diagnostics
        ))

        repeated = _build_quest_additions(
            image=image,
            lines=header,
            proved_screen=ScreenType.PNC_QUEST_DAILY,
            ocr_context=context,
            selector_registry=build_default_selector_registry(),
        )
        self.assertIsNotNone(repeated)
        self.assertEqual(RowRecognitionStatus.COMPLETE, repeated.list_entries[0].row_status)
        self.assertEqual(2, context.metrics.engine_calls)
        self.assertEqual(2, len(backend.regions))

    def test_recovers_missing_go_without_prior_full_frame_read(self) -> None:
        image = _quest_image()
        body = _row_lines(title="Upgrade building 1x", progress="(0/1)")
        backend = _QuestBackend(body, (_line("Go", 430, 428, 42, 16),))
        context = ObservationOcrContext(image, backend, None, "test")

        additions = _build_quest_additions(
            image=image,
            lines=_quest_header_lines(),
            proved_screen=ScreenType.PNC_QUEST_DAILY,
            ocr_context=context,
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(additions)
        self.assertEqual(2, len(backend.regions))
        self.assertEqual(0, context.metrics.fullframe_reuses)
        self.assertEqual(2, context.metrics.engine_calls)
        self.assertNotEqual(backend.regions[0], backend.regions[1])
        self.assertEqual((141, 41, "RGB"), backend.image_inputs[1])

    def test_reviewed_padding_recovers_at_900_by_1600(self) -> None:
        image = _quest_image_900()
        body = _row_lines_900(title="Upgrade tech 1x", progress="(0/1)")
        backend = _QuestBackend(
            body,
            (_line("Go", 730, 681, 52, 35),),
            full_size=(900, 1600),
            ocr_bounds=Bounds(640, 655, 233, 90),
        )
        context = ObservationOcrContext(image, backend, None, "test")

        additions = _build_quest_additions(
            image=image,
            lines=_quest_header_lines(),
            proved_screen=ScreenType.PNC_QUEST_DAILY,
            ocr_context=context,
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(additions)
        row = additions.list_entries[0]
        self.assertEqual(RowRecognitionStatus.COMPLETE, row.row_status)
        self.assertEqual(DailyQuestRowState.GO.value, row.metadata["row_state"])
        self.assertTrue(row.action_bounds.contains_point(row.action_point))
        self.assertEqual((233, 90, "RGB"), backend.image_inputs[1])

    def test_existing_outside_control_label_and_contradiction_do_not_retry(self) -> None:
        image = _quest_image()
        body = _row_lines(title="Upgrade building 1x", progress="(0/1)")
        outside = _line("Go", 430, 455, 42, 12)
        backend = _QuestBackend(body + (outside,), (_line("Go", 430, 428, 42, 16),))
        context = ObservationOcrContext(image, backend, None, "test")

        additions = _build_quest_additions(
            image=image,
            lines=_quest_header_lines(),
            proved_screen=ScreenType.PNC_QUEST_DAILY,
            ocr_context=context,
            selector_registry=build_default_selector_registry(),
        )

        self.assertIsNotNone(additions)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, additions.list_entries[0].row_status)
        self.assertEqual(1, context.metrics.engine_calls)

        contradictory = body + (
            _line("Go", 430, 428, 42, 16),
            _line("Claim", 430, 440, 52, 10),
        )
        parsed = parse_daily_quest_screen(
            image=image,
            lines=_quest_header_lines() + contradictory,
            proved_screen=ScreenType.PNC_QUEST_DAILY,
        )
        self.assertEqual(RowRecognitionStatus.AMBIGUOUS, parsed.rows[0].row_status)
        self.assertEqual((), find_missing_quest_action_candidates(
            image=image,
            lines=contradictory,
            result=parsed,
        ))

    def test_duplicate_identity_and_missing_or_clipped_rows_are_not_candidates(self) -> None:
        image = _quest_image(row_count=2)
        duplicate_lines = (
            _row_lines(title="Upgrade building 1x", progress="(0/1)", top=372)
            + _row_lines(title="Upgrade building 1x", progress="(0/1)", top=487)
        )
        duplicate = parse_daily_quest_screen(
            image=image,
            lines=_quest_header_lines() + duplicate_lines,
            proved_screen=ScreenType.PNC_QUEST_DAILY,
        )
        self.assertEqual((), find_missing_quest_action_candidates(
            image=image,
            lines=duplicate_lines,
            result=duplicate,
        ))

        missing_progress = parse_daily_quest_screen(
            image=_quest_image(),
            lines=_quest_header_lines() + _row_lines(title="Upgrade building 1x", progress=None),
            proved_screen=ScreenType.PNC_QUEST_DAILY,
        )
        self.assertEqual(RowRecognitionStatus.UNREADABLE, missing_progress.rows[0].row_status)
        self.assertEqual((), find_missing_quest_action_candidates(
            image=_quest_image(),
            lines=_row_lines(title="Upgrade building 1x", progress=None),
            result=missing_progress,
        ))

        clipped_image = _quest_image(top=850)
        ImageDraw.Draw(clipped_image).rectangle((9, 850, 526, 959), fill=(38, 50, 77))
        ImageDraw.Draw(clipped_image).rectangle((388, 898, 518, 928), fill=(45, 104, 170))
        clipped_lines = _row_lines(title="Upgrade building 1x", progress="(0/1)", top=850)
        clipped = parse_daily_quest_screen(
            image=clipped_image,
            lines=_quest_header_lines() + clipped_lines,
            proved_screen=ScreenType.PNC_QUEST_DAILY,
        )
        self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.rows[0].row_status)
        self.assertEqual((), find_missing_quest_action_candidates(
            image=clipped_image,
            lines=clipped_lines,
            result=clipped,
        ))

    def test_crop_conflict_or_wrong_action_never_authorizes_a_row(self) -> None:
        image = _quest_image()
        body = _row_lines(title="Upgrade building 1x", progress="(0/1)")
        for crop_lines in (
            (_line("Go", 430, 428, 42, 16), _line("Claim", 430, 440, 52, 10)),
            (_line("Claim", 430, 428, 52, 16),),
        ):
            with self.subTest(crop_lines=tuple(line.text for line in crop_lines)):
                backend = _QuestBackend(body, crop_lines)
                context = ObservationOcrContext(image, backend, None, "test")
                additions = _build_quest_additions(
                    image=image,
                    lines=_quest_header_lines(),
                    proved_screen=ScreenType.PNC_QUEST_DAILY,
                    ocr_context=context,
                    selector_registry=build_default_selector_registry(),
                )

                self.assertIsNotNone(additions)
                row = additions.list_entries[0]
                self.assertIn(row.row_status, {
                    RowRecognitionStatus.AMBIGUOUS,
                    RowRecognitionStatus.NO_ACTION,
                })
                self.assertIsNone(row.action_point)
                self.assertEqual("upgrade_building", row.metadata["quest_id"])
                self.assertEqual(0, row.metadata["progress_current"])
                self.assertEqual(1, row.metadata["progress_required"])


def _quest_image(*, row_count: int = 1, top: int = 372) -> Image.Image:
    image = Image.new("RGB", (540, 960), (19, 28, 44))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 50, 179, 108), fill=(25, 42, 72))
    draw.rectangle((180, 50, 359, 108), fill=(140, 103, 50))
    draw.rectangle((360, 50, 539, 108), fill=(25, 42, 72))
    for index in range(row_count):
        row_top = top + index * 115
        row_bottom = min(959, row_top + 98)
        draw.rectangle((9, row_top, 526, row_bottom), fill=(38, 50, 77))
        draw.rectangle((388, row_top + 48, 518, min(959, row_top + 78)), fill=(45, 104, 170))
    return image


def _quest_image_900() -> Image.Image:
    image = Image.new("RGB", (900, 1600), (19, 28, 44))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 100, 299, 184), fill=(25, 42, 72))
    draw.rectangle((300, 100, 599, 184), fill=(140, 103, 50))
    draw.rectangle((600, 100, 899, 184), fill=(25, 42, 72))
    draw.rectangle((10, 622, 889, 822), fill=(38, 50, 77))
    draw.rectangle((648, 663, 864, 736), fill=(45, 104, 170))
    return image


def _quest_header_lines() -> tuple[OcrLine, ...]:
    return (
        _line("Quest", 10, 10, 80, 25),
        _line("Main Quest", 20, 70, 110, 20),
        _line("Daily Quest", 220, 70, 110, 20),
        _line("Alliance Activity", 420, 70, 100, 20),
    )


def _row_lines(*, title: str, progress: str | None, top: int = 372) -> tuple[OcrLine, ...]:
    lines = [_line(title, 155, top + 15, 220, 20)]
    if progress is not None:
        lines.append(_line(progress, 154, top + 55, 70, 20))
    return tuple(lines)


def _row_lines_900(*, title: str, progress: str | None) -> tuple[OcrLine, ...]:
    lines = [_line(title, 260, 657, 300, 30)]
    if progress is not None:
        lines.append(_line(progress, 260, 720, 90, 30))
    return tuple(lines)


def _line(text: str, x: int, y: int, width: int, height: int) -> OcrLine:
    return OcrLine(text=text, bounds=Bounds(x, y, width, height), confidence=0.95)


if __name__ == "__main__":
    unittest.main()
