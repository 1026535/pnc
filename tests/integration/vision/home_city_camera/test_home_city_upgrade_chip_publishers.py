"""Selected-building Upgrade chip through both production publishers.

Replays the native 900x1600 live007 annotation-session frames, the failed
live009 production chip-source frame, and the failed live010 delayed pair
through ``ObservationBuilder`` and ``NavigationPerception``: the canonical
``PNC_HOME_SELECTED_BUILDING_UPGRADE_CHIP`` template selector must publish its
current-frame element through the measured-action channel on the selected
views with the lead-qualified bounds and full frame provenance, and must stay
absent on the unselected view and on the visibly-present-but-unqualified
live010 source. The element identifies the visible control only; no
destination or route is claimed.
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
    "home_city_selected_upgrade_chip_0034.png": (
        Bounds(633, 511, 78, 62),
        0.893282413482666,
    ),
    "home_city_selected_upgrade_chip_0037.png": (Bounds(624, 474, 78, 62), 1.0),
    "home_city_selected_upgrade_chip_0038.png": (
        Bounds(624, 496, 78, 62),
        0.8811300838694853,
    ),
    "home_city_selected_upgrade_chip_live010_0035.png": (
        Bounds(649, 474, 78, 62),
        0.8634350299835205,
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
        # The click targets the button, above the caption in this native match.
        self.assertEqual((expected_bounds.x + 39, expected_bounds.y + 22), element.action_point)
        self.assertEqual(expected_bounds.center(), element.bounds.center())
        self.assertEqual(capture.frame_ref, element.frame_ref)
        self.assertEqual(ScreenType.PNC_HOME_CITY, element.source_screen)
        self.assertEqual(observation.decision.layout_id, element.source_layout_id)

    def test_live009_source34_publishes_the_corrected_chip_point(self) -> None:
        """The live009 chip-source frame resolves action point (672,533) inside the current match."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "home_city_selected_upgrade_chip_0034.png",
            session_id="v44-chip-live009-source34",
            capture_sequence=34,
        )
        observations = self._build_both(builder, navigation, backend, capture)
        bounds, confidence = _EXPECTED["home_city_selected_upgrade_chip_0034.png"]
        for name, observation in (
            ("observation_builder", observations[0]),
            ("navigation_perception", observations[1]),
        ):
            with self.subTest(publisher=name):
                self._assert_chip_publication(observation, capture, bounds, confidence)
                self.assertEqual((672, 533), observation.visible_elements[CHIP_ID].action_point)
        self.assertEqual(
            observations[0].visible_elements[CHIP_ID],
            observations[1].visible_elements[CHIP_ID],
        )

    def test_seed37_publishes_the_chip_on_both_paths(self) -> None:
        """The native live007 seed frame measures bounds (624,474,78,62) score 1."""

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

    def test_live010_delayed_pair_republishes_the_same_chip(self) -> None:
        """Live010's unqualified source stays chipless; the later same-chain frame qualifies.

        Capture 34 visibly shows the chip yet scores ~0.7959 under the
        unchanged .85 gate, so both publishers must withhold the element. The
        next capture 35 of the same selected building — same synthetic
        session, epoch, and input sequence, no new input — qualifies at
        (649,474,78,62) ~0.863435 and resolves action point (688,496) on the
        current match. This is delayed recognition, not proof the control was
        absent on capture 34.
        """

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        first = _capture(
            "home_city_selected_upgrade_chip_live010_0034.png",
            session_id="v44-chip-live010-pair",
            capture_sequence=34,
        )
        first_pair = self._build_both(builder, navigation, backend, first)
        for name, observation in (
            ("observation_builder", first_pair[0]),
            ("navigation_perception", first_pair[1]),
        ):
            with self.subTest(publisher=name, stage="unqualified"):
                self.assertEqual(ScreenType.PNC_HOME_CITY, observation.screen_type)
                self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                self.assertNotIn(CHIP_ID, observation.visible_elements)

        second = _capture(
            "home_city_selected_upgrade_chip_live010_0035.png",
            session_id="v44-chip-live010-pair",
            capture_sequence=35,
        )
        self.assertEqual(first.frame_ref.session_id, second.frame_ref.session_id)
        self.assertEqual(first.frame_ref.session_epoch, second.frame_ref.session_epoch)
        self.assertEqual(first.frame_ref.input_sequence, second.frame_ref.input_sequence)
        self.assertLess(
            first.frame_ref.capture_sequence, second.frame_ref.capture_sequence,
        )
        second_pair = self._build_both(builder, navigation, backend, second)
        bounds, confidence = _EXPECTED[
            "home_city_selected_upgrade_chip_live010_0035.png"
        ]
        for name, observation in (
            ("observation_builder", second_pair[0]),
            ("navigation_perception", second_pair[1]),
        ):
            with self.subTest(publisher=name, stage="qualified"):
                self._assert_chip_publication(observation, second, bounds, confidence)
                self.assertEqual(
                    (688, 496), observation.visible_elements[CHIP_ID].action_point,
                )
        self.assertEqual(
            second_pair[0].visible_elements[CHIP_ID],
            second_pair[1].visible_elements[CHIP_ID],
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
