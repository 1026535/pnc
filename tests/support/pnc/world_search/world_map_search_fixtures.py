"""Shared WorldMapSearchFixtures setup."""

from __future__ import annotations

import tempfile

from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner


class WorldMapSearchFixtures:
    """Shared setup without connected workflow composition."""

    def setUp(self) -> None:
        """Builds the shared flow planner, action executor, and temp artifact root."""

        self.flows = ScreenFlowPlanner()
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
