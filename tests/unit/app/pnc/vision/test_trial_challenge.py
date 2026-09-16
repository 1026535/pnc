"""Unit tests for the Trial Challenge card and Applicable Stats producer."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.trial_challenge import (
    TrialApplicableStatsDetail,
    TrialCardFacts,
    TrialCategory,
    trial_category_for_label,
    trial_category_title,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.trial_challenge import (
    TRIAL_CHALLENGE_LAYOUT_ID,
    TRIAL_STATS_LAYOUT_ID,
    TrialContentProducer,
    _CardLine,
    _countdown_text,
    _footer_category,
    _mark_duplicate_categories,
    _parse_stat_rows,
    _percent_value,
    _progress_values,
    _required_castle_level,
    _scaled_region,
    _weekday_text,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


def _line(text: str, bounds: Bounds) -> OcrLine:
    return OcrLine(text=text, bounds=bounds, confidence=0.9)


def _card_line(text: str, *, rel_x: int, rel_y: int) -> _CardLine:
    return _CardLine(line=_line(text, Bounds(0, 0, 10, 10)), rel_x=rel_x, rel_y=rel_y)


class TrialCategoryTests(unittest.TestCase):
    """Category labels resolve only through their canonical card titles."""

    def test_canonical_titles_resolve(self) -> None:
        for category, title in (
            (TrialCategory.HERO, "Hero Trial"),
            (TrialCategory.CURIO, "Curio Trial"),
            (TrialCategory.TECH, "Tech Trial"),
            (TrialCategory.GEAR, "Gear Trial"),
            (TrialCategory.RUNE, "Rune Trial"),
            (TrialCategory.SAUROI, "Sauroi Trial"),
        ):
            with self.subTest(category=category):
                self.assertEqual(title, trial_category_title(category))
                self.assertEqual(category, trial_category_for_label(title))
                self.assertEqual(category, trial_category_for_label(title.lower()))

    def test_partial_or_unknown_labels_do_not_resolve(self) -> None:
        for label in ("Gear", "Trial", "Stats", "Gear Trials", "", "Hero Trail"):
            with self.subTest(label=label):
                self.assertIsNone(trial_category_for_label(label))


class TrialCardFactsTests(unittest.TestCase):
    """Typed card facts reject partial or malformed observations."""

    def test_progress_pair_must_be_complete(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            TrialCardFacts(category=TrialCategory.GEAR, progress_current=41)
        facts = TrialCardFacts(
            category=TrialCategory.GEAR, progress_current=41, progress_required=200
        )
        self.assertEqual(41, facts.progress_current)

    def test_negative_or_bool_values_rejected(self) -> None:
        with self.assertRaises(SelectorResolutionError):
            TrialCardFacts(category=TrialCategory.GEAR, required_castle_level=-1)
        with self.assertRaises(TypeError):
            TrialCardFacts(category=TrialCategory.GEAR, locked="yes")  # type: ignore[arg-type]


class CardFieldParsingTests(unittest.TestCase):
    """Bounded card-field parsers keep independent facts independent."""

    def test_progress_reads_displayed_fraction(self) -> None:
        lines = [_card_line("Progress 43/140", rel_x=250, rel_y=120)]
        self.assertEqual((43, 140), _progress_values(lines))
        self.assertEqual((None, None), _progress_values([_card_line("Gear Trial", rel_x=250, rel_y=30)]))

    def test_required_level_reads_requirement_line(self) -> None:
        lines = [_card_line("Requires Lv.20 Castle", rel_x=260, rel_y=140)]
        self.assertEqual(20, _required_castle_level(lines))
        self.assertIsNone(_required_castle_level([_card_line("Requires Castle", rel_x=260, rel_y=140)]))

    def test_countdown_stays_in_schedule_slot(self) -> None:
        self.assertEqual(
            "17:21:23",
            _countdown_text([_card_line("17:21:23", rel_x=640, rel_y=30)]),
        )
        # The same digits outside the top-right schedule slot are not a countdown.
        self.assertIsNone(_countdown_text([_card_line("17:21:23", rel_x=300, rel_y=150)]))

    def test_weekday_returns_literal_text_or_stays_unknown(self) -> None:
        self.assertEqual("Mon", _weekday_text([_card_line("Mon", rel_x=640, rel_y=30)]))
        # Partial or occluded fragments never reconstruct a weekday.
        self.assertIsNone(_weekday_text([_card_line("on", rel_x=640, rel_y=30)]))
        self.assertIsNone(_weekday_text([]))

    def test_lock_and_countdown_are_independent_facts(self) -> None:
        lines = [
            _card_line("17:21:23", rel_x=640, rel_y=30),
            _card_line("Requires Lv.31 Castle", rel_x=260, rel_y=140),
        ]
        self.assertEqual("17:21:23", _countdown_text(lines))
        self.assertEqual(31, _required_castle_level(lines))


class StatsDetailParsingTests(unittest.TestCase):
    """Applicable Stats rows pair bounded labels with their row percentage."""

    def test_rows_pair_label_and_percent_on_the_same_row(self) -> None:
        lines = (
            _line("Infantry ATK", Bounds(152, 158, 200, 29)),
            _line("48%", Bounds(700, 160, 46, 27)),
            _line("Cavalry DEF", Bounds(152, 571, 220, 31)),
            _line("%96", Bounds(700, 573, 46, 29)),
        )

        stats = _parse_stat_rows(lines, reference_scale_x=1.0, reference_scale_y=1.0)

        self.assertEqual(2, len(stats))
        self.assertEqual("Infantry ATK", stats[0].label_text)
        self.assertEqual("48%", stats[0].percent_text)
        self.assertEqual(48, stats[0].percent_value)
        self.assertEqual("%96", stats[1].percent_text)
        self.assertEqual(96, stats[1].percent_value)

    def test_label_without_value_is_not_published(self) -> None:
        lines = (
            _line("Infantry ATK", Bounds(152, 158, 200, 29)),
            _line("Infantry DEF", Bounds(152, 218, 200, 27)),
            _line("114%", Bounds(700, 220, 46, 25)),
        )

        stats = _parse_stat_rows(lines, reference_scale_x=1.0, reference_scale_y=1.0)

        self.assertEqual(1, len(stats))
        self.assertEqual("Infantry DEF", stats[0].label_text)

    def test_far_apart_label_and_value_never_pair(self) -> None:
        lines = (
            _line("Infantry ATK", Bounds(152, 158, 200, 29)),
            _line("48%", Bounds(700, 400, 46, 27)),
        )
        self.assertEqual((), _parse_stat_rows(lines, reference_scale_x=1.0, reference_scale_y=1.0))

    def test_percent_value_tolerates_misread_sign(self) -> None:
        self.assertEqual(48, _percent_value("48%"))
        self.assertEqual(96, _percent_value("%96"))
        self.assertIsNone(_percent_value("abc"))

    def test_footer_category_comes_only_from_the_bounded_sentence(self) -> None:
        footer = (_line("In Gear Trial, only gear stats are applicable.", Bounds(30, 1480, 700, 30)),)
        self.assertEqual(TrialCategory.GEAR, _footer_category(footer))
        self.assertEqual(
            TrialCategory.HERO,
            _footer_category((_line("In Hero Trial, only hero stats are applicable.", Bounds(30, 1480, 700, 30)),)),
        )
        self.assertIsNone(_footer_category((_line("Applicable Stats", Bounds(30, 1480, 300, 30)),)))
        self.assertIsNone(_footer_category(()))


class ProducerDispatchTests(unittest.TestCase):
    """Trial content only publishes under its own proved screen and layout."""

    def test_dispatch_requires_the_trial_screens_and_layouts(self) -> None:
        producer = TrialContentProducer()
        context = Mock()
        for screen_type, layout_id in (
            (ScreenType.PNC_TRIAL_CHALLENGE, "other_layout"),
            (ScreenType.PNC_TRIAL_APPLICABLE_STATS, TRIAL_CHALLENGE_LAYOUT_ID),
            (ScreenType.PNC_TRIAL_CHALLENGE, TRIAL_STATS_LAYOUT_ID),
            (ScreenType.PNC_BAG, TRIAL_CHALLENGE_LAYOUT_ID),
            (ScreenType.PNC_HOME_CITY, None),
        ):
            with self.subTest(screen=screen_type, layout=layout_id):
                self.assertIsNone(
                    producer.additions_for_screen(
                        image=Image.new("RGB", (540, 960)),
                        screen_type=screen_type,
                        ocr_context=context,
                        layout_id=layout_id,
                    )
                )
        context.read_lines.assert_not_called()

    def test_duplicate_categories_mark_rows_ambiguous_and_remove_actions(self) -> None:
        def entry(action: bool) -> DetectedListEntry:
            bounds = Bounds(100, 100, 50, 50)
            return DetectedListEntry(
                kind=ListEntryKind.TRIAL_CATEGORY,
                bounds=Bounds(20, 20, 800, 200),
                title_text="Gear Trial",
                metadata={"category": "gear"},
                row_status=RowRecognitionStatus.COMPLETE if action else RowRecognitionStatus.NO_ACTION,
                action_bounds=bounds if action else None,
                action_point=bounds.center() if action else None,
                trial_card_facts=TrialCardFacts(category=TrialCategory.GEAR),
            )

        marked = _mark_duplicate_categories((entry(True), entry(False)))

        self.assertTrue(all(row.row_status == RowRecognitionStatus.AMBIGUOUS for row in marked))
        self.assertTrue(all(row.action_point is None and row.action_bounds is None for row in marked))

    def test_scaled_region_projects_and_clamps_to_the_image(self) -> None:
        image = Image.new("RGB", (540, 960))
        self.assertEqual(
            Bounds(30, 60, 240, 120),
            _scaled_region(Bounds(50, 100, 400, 200), image),
        )
        clamped = _scaled_region(Bounds(800, 1500, 400, 400), image)
        self.assertEqual(540, clamped.x + clamped.width)
        self.assertEqual(960, clamped.y + clamped.height)


class StatsDetailModelTests(unittest.TestCase):
    """The typed detail rejects unbound or malformed observations."""

    def test_detail_requires_typed_stats(self) -> None:
        with self.assertRaises(TypeError):
            TrialApplicableStatsDetail(stats=(object(),))  # type: ignore[arg-type]

    def test_detail_allows_unknown_category(self) -> None:
        detail = TrialApplicableStatsDetail()
        self.assertIsNone(detail.category)
        self.assertEqual((), detail.stats)


if __name__ == "__main__":
    unittest.main()
