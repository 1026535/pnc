"""Navigation core research edges tests."""

import unittest

from pnc_automation.app.automation.engine.navigation_core import (
    reviewed_navigation_edges,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId

from tests.support.pnc.navigation.core_recording import RecordedFramesCore


class NavigationCoreTests(RecordedFramesCore, unittest.TestCase):
    def test_development_research_tree_edges_are_limited_to_observed_route(self):
        """Keeps only the measured Development entry and ResearchTree Back return edges."""

        edges = {
            (edge.source, edge.selector, edge.destinations)
            for edge in reviewed_navigation_edges()
        }

        self.assertIn(
            (
                ScreenType.PNC_INSTITUTE,
                UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                frozenset({ScreenType.PNC_RESEARCH_TREE}),
            ),
            edges,
        )
        self.assertIn(
            (
                ScreenType.PNC_RESEARCH_TREE,
                UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                frozenset({ScreenType.PNC_INSTITUTE}),
            ),
            edges,
        )
        self.assertEqual(
            {
                item
                for item in edges
                if (
                    item[0] == ScreenType.PNC_RESEARCH_TREE
                    or item[1] == UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON
                )
            },
            {
                (
                    ScreenType.PNC_INSTITUTE,
                    UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON,
                    frozenset({ScreenType.PNC_RESEARCH_TREE}),
                ),
                (
                    ScreenType.PNC_RESEARCH_TREE,
                    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                    frozenset({ScreenType.PNC_INSTITUTE}),
                ),
            },
        )
