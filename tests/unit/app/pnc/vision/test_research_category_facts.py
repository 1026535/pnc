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
from pnc_automation.core.vision.ocr.ocr_service import OcrLine


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
                self.assertEqual(1, context.read_lines.call_count)

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
