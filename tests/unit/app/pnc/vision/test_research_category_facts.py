"""Category identity and honest level-badge semantics for shared research."""

import unittest
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import (
    ResearchNodeFacts, ResearchNodeId, research_node_for_label,
)
from pnc_automation.app.pnc.vision.research import ResearchContentProducer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, OcrTextOrientation


class ResearchCategoryFactsTests(unittest.TestCase):
    def test_category_membership_disambiguates_shared_and_foreign_labels(self):
        self.assertEqual(ResearchNodeId.FOOD_OUTPUT_I, research_node_for_label(
            "Food Output I", category=ResearchCategory.ECONOMY,
        ))
        self.assertEqual(ResearchNodeId.FOOD_OUTPUT_I, research_node_for_label(
            "Food Output I", category=ResearchCategory.DEVELOPMENT,
        ))
        self.assertIsNone(research_node_for_label("Construction I", category=ResearchCategory.ECONOMY))
        self.assertIsNone(research_node_for_label("Infantry HP II", category=ResearchCategory.MILITARY))
        self.assertEqual(ResearchNodeId.DEFENDER_ATK_I, research_node_for_label(
            "Defender ATK\nI", category=ResearchCategory.FORTIFICATION,
        ))

    def test_label_fragments_read_left_to_right_and_wrapped_rows_read_top_down(self):
        producer = ResearchContentProducer()
        for lines, expected in (
            ((OcrLine("Speedi", Bounds(443, 289, 101, 33), .89),
              OcrLine("March", Bounds(366, 290, 90, 29), .85)), ResearchNodeId.MARCH_SPEED_I),
            ((OcrLine("Survival I", Bounds(395, 914, 121, 29), .87),
              OcrLine("Miraculous", Bounds(384, 889, 140, 30), .99)), ResearchNodeId.MIRACULOUS_SURVIVAL_I),
        ):
            with self.subTest(expected=expected):
                context = Mock()
                context.read_lines.return_value = lines
                candidate = producer._node_candidate(
                    image=Image.new("RGB", (900, 1600)), component=Bounds(365, 278, 179, 59),
                    ocr_context=context, category=None,
                )
                self.assertEqual(expected, candidate.node_id)
                self.assertEqual(OcrTextOrientation.UPRIGHT,
                                 context.read_lines.call_args.kwargs["orientation"])
                context.read_preprocessed_result.assert_not_called()

    def test_label_retry_preserves_upright_contract_and_abstains_on_partial_words(self):
        context = Mock()
        context.read_lines.return_value = (OcrLine("Food", Bounds(369, 304, 72, 28), .99),)
        context.read_preprocessed_result.return_value = OcrResult(
            lines=context.read_lines.return_value, words=(),
        )
        candidate = ResearchContentProducer()._node_candidate(
            image=Image.new("RGB", (900, 1600)), component=Bounds(365, 294, 179, 55),
            ocr_context=context, category=ResearchCategory.ECONOMY,
        )
        self.assertIsNone(candidate.node_id)
        context.read_preprocessed_result.assert_called_once()
        self.assertEqual(OcrTextOrientation.UPRIGHT,
                         context.read_preprocessed_result.call_args.kwargs["orientation"])

    def test_level_badges_have_one_owned_coherent_interpretation(self):
        image = Image.new("RGB", (540, 960))
        producer = ResearchContentProducer()
        for texts, expected in (
            (("MAX",), (None, None, True)),
            (("2/3",), (2, 3, False)),
            (("3/3",), (3, 3, True)),
            (("4/3",), None),
            (("2/3", "1/3"), None),
            (("2/3", "MAX"), None),
            (("M AXIMUM",), None),
            ((), None),
        ):
            with self.subTest(texts=texts):
                context = Mock()
                context.read_lines.return_value = tuple(
                    OcrLine(text, Bounds(100, 100, 45, 20), 1.0) for text in texts
                )
                actual = producer._read_node_level(
                    image=image, icon_bounds=Bounds(100, 100, 100, 100), ocr_context=context,
                )
                self.assertEqual(expected, actual)
                expected_reads = 2 if texts in (("4/3",), ("M AXIMUM",), ()) else 1
                self.assertEqual(expected_reads, context.read_lines.call_count)

    def test_split_counter_and_one_bounded_retry_keep_maximum_semantics(self):
        producer = ResearchContentProducer()
        split = (
            OcrLine("/3", Bounds(116, 100, 20, 20), 1.0),
            OcrLine("3", Bounds(100, 100, 16, 20), 1.0),
        )
        fragmented = (
            OcrLine("1", Bounds(100, 100, 12, 20), .89),
            OcrLine("13", Bounds(112, 100, 24, 20), .84),
        )
        for reads, expected_calls in (([split], 1), ([(), split], 2), ([fragmented, split], 2)):
            with self.subTest(expected_calls=expected_calls):
                context = Mock()
                context.read_lines.side_effect = reads
                self.assertEqual((3, 3, True), producer._read_node_level(
                    image=Image.new("RGB", (540, 960)),
                    icon_bounds=Bounds(100, 100, 100, 100), ocr_context=context,
                ))
                self.assertEqual(expected_calls, context.read_lines.call_count)
                if expected_calls == 2:
                    first_region = context.read_lines.call_args_list[0].args[1]
                    retry_region = context.read_lines.call_args_list[1].args[1]
                    self.assertEqual(first_region.x, retry_region.x)
                    self.assertEqual(first_region.y, retry_region.y)
                    self.assertEqual(first_region.width, retry_region.width)
                    self.assertLess(retry_region.height, first_region.height)
                    self.assertTrue(first_region.contains_bounds(retry_region))

    def test_maximum_fact_does_not_require_an_invented_numeric_cap(self):
        facts = ResearchNodeFacts(maximum_reached=True)
        self.assertIsNone(facts.current_level)
        self.assertIsNone(facts.max_level)
        with self.assertRaises(ValueError):
            ResearchNodeFacts(current_level=2, max_level=3, maximum_reached=True)

    def test_contradictory_header_cannot_override_qualified_category(self):
        producer = ResearchContentProducer()
        context = Mock()
        additions = producer.additions_for_tree(
            image=Image.new("RGB", (540, 960)),
            lines=(OcrLine("Military", Bounds(100, 10, 100, 30), 1.0),),
            ocr_context=context, layout_id="research_tree_economy",
        )
        self.assertEqual((), additions.list_entries)
        context.read_lines.assert_not_called()
