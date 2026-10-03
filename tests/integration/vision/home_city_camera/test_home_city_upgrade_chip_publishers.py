"""Selected-building Upgrade chip through both production publishers.

Replays the native 900x1600 turn047 frames through ``ObservationBuilder`` and
``NavigationPerception``: the canonical
``PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP`` template selector must publish its
current-frame element through the measured-action channel on the selected
views with the lead-qualified bounds and full frame provenance, and must stay
absent on the unselected view. The element identifies the visible control
only; no destination or route is claimed.
"""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.vision.image.models import Bounds
from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.home_city_camera.publication import (
    _BoundedRapidOcrService,
    _capture as _camera_capture,
    _wire,
    HomeCameraPublicationAssertions,
)


FIXTURES = TEST_DATA_ROOT / "home_city_controls"
CHIP_ID = UiElementId.PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP

# Lead-qualified measurements for each tracked frame: template bounds and the
# actual match confidence the canonical matcher produces on this exact image.
_EXPECTED = {
    "home_city_selected_upgrade_chip_0037.png": (Bounds(624, 474, 78, 62), 1.0),
    "home_city_selected_upgrade_chip_0038.png": (
        Bounds(624, 496, 78, 62),
        0.8811300838694853,
    ),
}


def _capture(name: str, *, session_id: str, capture_sequence: int):
    """Require authored RGBA size while reusing shared frame provenance."""

    capture = _camera_capture(
        name,
        session_id=session_id,
        capture_sequence=capture_sequence,
        fixture_root=FIXTURES,
    )
    if capture.image.mode != "RGBA" or capture.image.size != (900, 1600):
        raise AssertionError(
            f"chip fixture {name} must stay authored RGBA 900x1600, "
            f"got {capture.image.mode} {capture.image.size}"
        )
    return capture


class HomeCityUpgradeChipPublisherTests(HomeCameraPublicationAssertions, unittest.TestCase):
    """Both publishers emit the same provenanced chip element per frame."""

    def _assert_chip_publication(
        self,
        observation: Observation,
        capture,
        expected_bounds: Bounds,
        expected_confidence: float,
    ) -> None:
        """Require the qualified template element with current-frame provenance."""

        self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        element = observation.visible_elements.get(CHIP_ID)
        self.assertIsNotNone(element, "the selected view must publish the chip element")
        assert element is not None
        self.assertIs(VisibleElementSourceKind.TEMPLATE, element.source_kind)
        self.assertEqual(expected_bounds, element.bounds)
        self.assertAlmostEqual(expected_confidence, element.confidence, places=9)
        self.assertIsNone(element.action_point)
        self.assertEqual(expected_bounds.center(), element.bounds.center())
        self.assertEqual(capture.frame_ref, element.frame_ref)
        self.assertEqual(ScreenType.PNC_HOME_CITY, element.source_screen)
        self.assertEqual(observation.decision.layout_id, element.source_layout_id)

    def test_seed37_publishes_the_chip_on_both_paths(self) -> None:
        """The native turn047 frame measures bounds (624,474,78,62) score 1."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_selected_upgrade_chip_0037.png",
            session_id="v44-chip-seed37",
            capture_sequence=37,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        bounds, confidence = _EXPECTED["home_city_selected_upgrade_chip_0037.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_chip_publication(observation, capture, bounds, confidence)
        self.assertEqual(
            observations[0].visible_elements[CHIP_ID],
            observations[1].visible_elements[CHIP_ID],
        )

    def test_holdout38_publishes_the_chip_independently(self) -> None:
        """The translated holdout reproduces the chip at (624,496,78,62)."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_selected_upgrade_chip_0038.png",
            session_id="v44-chip-holdout38",
            capture_sequence=38,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        bounds, confidence = _EXPECTED["home_city_selected_upgrade_chip_0038.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_chip_publication(observation, capture, bounds, confidence)
        self.assertEqual(
            observations[0].visible_elements[CHIP_ID],
            observations[1].visible_elements[CHIP_ID],
        )

    def test_unselected_view_publishes_no_chip(self) -> None:
        """The unselected source view must never invent the control."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_unselected_0035.png",
            session_id="v44-chip-negative35",
            capture_sequence=35,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self.assertNotIn(CHIP_ID, observation.visible_elements)


if __name__ == "__main__":
    unittest.main()
