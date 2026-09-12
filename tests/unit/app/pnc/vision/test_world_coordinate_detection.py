"""World coordinate detection."""

from __future__ import annotations

import unittest

from PIL import Image

from pnc_automation.app.pnc.vision.pnc_observation_enricher import (
    _find_world_map_root_coordinate_line,
)

from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class WorldCoordinateDetectionTests(unittest.TestCase):
    """Proves world coordinate detection."""

    def test_world_map_root_coordinate_detection_uses_canonical_coordinate_parser(self) -> None:
        """Uses the same coordinate grammar for coarse root evidence, including omitted X colons."""

        image = Image.new("RGB", (900, 1600), (15, 28, 68))
        coordinate_line = _ocr_line("X253 Y\uff1a987", x=73, y=67, width=160, height=24)

        self.assertIs(
            _find_world_map_root_coordinate_line(
                image=image,
                lines=(coordinate_line,),
            ),
            coordinate_line,
        )
