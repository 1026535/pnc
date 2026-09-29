"""Captured Research queue publication acceptance coverage."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.domain.research import ResearchQueueState
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType

from tests.support.pnc.research.publication import (
    image as _image,
    observe as _observe,
    production_components as _production_components,
)


class ResearchQueuePublicationTests(unittest.TestCase):
    """Pin queue rows and frame isolation independently from tree/detail suites."""

    def test_queue_capture_publishes_typed_idle_row_with_provenance(self) -> None:
        """The queue surface resolves its measured row and frame-scoped fields."""

        builder, perception = _production_components()
        image = _image("research_queue_core.png")

        for observation in _observe(builder, perception, image, session_id="queue"):
            with self.subTest(path=type(observation).__name__):
                self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_QUEUE)
                self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertEqual(observation.decision.layout_id, "research_queue")
                rows = observation.research_queue_rows
                self.assertEqual(1, len(rows))
                row = rows[0]
                self.assertEqual("1stResearchQueue", row.title_text)
                self.assertEqual(ResearchQueueState.IDLE, row.state)
                self.assertIsNone(row.timer_text)
                self.assertEqual(observation.frame_ref, row.frame_ref)
                self.assertEqual(ScreenType.PNC_RESEARCH_QUEUE, row.source_screen)
                self.assertEqual("research_queue", row.source_layout_id)
                self.assertIsNone(observation.research_detail)
                self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))

    def test_fresh_frames_carry_no_prior_research_facts(self) -> None:
        """Detail and queue facts never survive onto a later tree or unknown frame."""

        builder, perception = _production_components()
        _observe(builder, perception, _image("research_node_detail.png"), session_id="prior-detail")

        tree_builder, tree_perception = _observe(
            builder, perception, _image("research_tree_development.png"), session_id="fresh-tree"
        )
        for observation in (tree_builder, tree_perception):
            self.assertIsNone(observation.research_detail)
            self.assertEqual((), observation.research_queue_rows)
            self.assertEqual(6, len(observation.entries(ListEntryKind.RESEARCH)))

        unknown_builder, unknown_perception = _observe(
            builder,
            perception,
            Image.new("RGB", (540, 960), (80, 80, 80)),
            session_id="unknown-frame",
        )
        for observation in (unknown_builder, unknown_perception):
            self.assertEqual(ScreenType.UNKNOWN, observation.screen_type)
            self.assertIsNone(observation.research_detail)
            self.assertEqual((), observation.research_queue_rows)
            self.assertEqual((), observation.entries(ListEntryKind.RESEARCH))


if __name__ == "__main__":
    unittest.main()
