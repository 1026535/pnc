"""Captured visual qualification for the Alliance Join landing surface."""

from __future__ import annotations

from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import (
    PopupControlKind,
    PopupEvidenceKind,
    decide_popup_recovery,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.image.models import Bounds

from tests.integration.vision.test_alliance_remaining_visual_contracts import (
    _BoundedOcrService,
    _builder,
    _capture,
    _perception,
)


TESTS_ROOT = Path(__file__).parents[2]
SCREEN_ROOT = TESTS_ROOT / "data" / "screen_recognition"
FIXTURE = SCREEN_ROOT / "alliance_variants" / "alliance_join_landing.png"
PROFILE_ID = "alliance_join_landing"
SCREEN = ScreenType.PNC_ALLIANCE_JOIN
NATIVE_SIZE = (900, 1600)
REFERENCE_SIZE = (540, 960)
ODIN = Bounds(285, 100, 340, 420)
BANNER = Bounds(280, 620, 350, 70)


def _image(path: Path, size: tuple[int, int]) -> Image.Image:
    """Load one reviewed fixture at a supported viewport size."""

    with Image.open(path) as source:
        image = source.convert("RGB")
    return image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)


def _scaled(bounds: Bounds, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Map a native reviewed box into one supported viewport."""

    return (
        round(bounds.x * size[0] / NATIVE_SIZE[0]),
        round(bounds.y * size[1] / NATIVE_SIZE[1]),
        round((bounds.x + bounds.width) * size[0] / NATIVE_SIZE[0]),
        round((bounds.y + bounds.height) * size[1] / NATIVE_SIZE[1]),
    )


class AllianceJoinLandingCapturedTests(unittest.TestCase):
    """Keep Join landing identity anchored while the reviewed mask dismissal ships."""

    def _observe(
        self,
        image: Image.Image,
        path: str,
        *,
        assert_single_global_read: bool = True,
    ):
        """Build through one production perception path with bounded guard OCR."""

        ocr = _BoundedOcrService()
        builder = _builder(ocr)
        capture = _capture(image, session_id=f"alliance-join:{path}:{image.size}")
        observation = (
            builder.build(
                capture,
                request=ObservationRequest.source_screen_retry(SCREEN),
            )
            if path == "builder"
            else _perception(builder).build(capture, include_content=True)
        )
        if assert_single_global_read:
            self.assertLessEqual(len(ocr.calls), 1)
        self.assertTrue(all(region is not None for region in ocr.calls))
        self.assertTrue(
            all(region != Bounds(0, 0, *image.size) for region in ocr.calls)
        )
        return observation, capture

    def test_captured_join_landing_stays_clear_and_publishes_mask_dismissal(self) -> None:
        """Odin and the banner establish Join landing and own its reviewed mask dismissal.

        UnionGuide binds only the mutating Join/Create buttons, but its embedded
        CommonModelWin chrome binds the ScreenShotMask dimmer to
        OnBgClickHandler -> BackToLastWindow -> CloseWin (isClickBgClose
        defaults true), so the landing publishes the reviewed fixed_region mask
        band as a typed BACKGROUND_DISMISS candidate. The screen stays CLEAR and
        non-blocking; Join/Create remain unpublished.
        """

        expected = {
            REFERENCE_SIZE: ((30, 830, 140, 70), (100, 865)),
            NATIVE_SIZE: ((50, 1383, 233, 117), (166, 1441)),
        }
        for size in (REFERENCE_SIZE, NATIVE_SIZE):
            with self.subTest(size=size):
                image = _image(FIXTURE, size)
                for path in ("builder", "navigation"):
                    with self.subTest(path=path):
                        observation, capture = self._observe(image, path)
                        self.assertEqual(observation.screen_type, SCREEN)
                        self.assertEqual(observation.decision.layout_id, PROFILE_ID)
                        self.assertEqual(observation.decision.guard, GuardVerdict.CLEAR)
                        self.assertFalse(observation.blocking_popup)
                        self.assertEqual(observation.frame_ref, capture.frame_ref)
                        self.assertFalse(observation.list_entries)
                        (bounds_tuple, action_point) = expected[size]
                        dismissal = observation.visible_elements[
                            UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK
                        ]
                        self.assertEqual(Bounds(*bounds_tuple), dismissal.bounds)
                        self.assertEqual(action_point, dismissal.action_point)
                        self.assertEqual(
                            VisibleElementSourceKind.GEOMETRY, dismissal.source_kind
                        )
                        self.assertFalse(dismissal.identity_evidence)
                        overlay = observation.popup_overlay
                        self.assertIsNotNone(overlay)
                        assert overlay is not None
                        self.assertEqual(overlay.layout_id, PROFILE_ID)
                        self.assertEqual(
                            PopupEvidenceKind.KNOWN_LAYOUT, overlay.evidence_kind
                        )
                        candidate = overlay.candidate(PopupControlKind.BACKGROUND_DISMISS)
                        self.assertIsNotNone(candidate)
                        assert candidate is not None
                        self.assertEqual(Bounds(*bounds_tuple), candidate.bounds)
                        self.assertEqual(action_point, candidate.action_point)
                        decision = decide_popup_recovery(
                            screen_type=observation.screen_type,
                            blocking_popup=observation.blocking_popup,
                            visible_selector_ids=frozenset(observation.visible_elements),
                            popup_overlay=overlay,
                        )
                        self.assertIsNotNone(decision)
                        assert decision is not None
                        self.assertEqual(
                            UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK,
                            decision.selector_id,
                        )
                        self.assertEqual(
                            PopupControlKind.BACKGROUND_DISMISS, decision.control_kind
                        )
                        self.assertFalse(
                            any(
                                element.action_point is not None
                                for selector, element in observation.visible_elements.items()
                                if selector is not UiElementId.PNC_ALLIANCE_JOIN_DISMISS_MASK
                            ),
                            "Only the reviewed mask may be actionable; Join/Create stay unpublished.",
                        )

    def test_erased_identity_anchor_abstains_in_both_paths(self) -> None:
        """Removing either independently measured identity crop cannot promote the surface."""

        for size in (REFERENCE_SIZE, NATIVE_SIZE):
            for erased in (ODIN, BANNER):
                with self.subTest(size=size, erased=erased):
                    image = _image(FIXTURE, size)
                    ImageDraw.Draw(image).rectangle(_scaled(erased, size), fill=(8, 20, 38))
                    for path in ("builder", "navigation"):
                        with self.subTest(path=path):
                            observation, _capture_info = self._observe(image, path)
                            self.assertNotEqual(observation.screen_type, SCREEN)
                            self.assertNotEqual(observation.decision.layout_id, PROFILE_ID)
                            self.assertFalse(observation.visible_elements)

    def test_invitation_home_and_update_foreign_surfaces_do_not_match(self) -> None:
        """Related popup, Home, and update overlay captures cannot borrow Join identity."""

        foreign = (
            "alliance_invitation.png",
            "home_city_core.png",
            "update_over_bag.png",
        )
        for name in foreign:
            with self.subTest(fixture=name):
                source = _image(SCREEN_ROOT / name, REFERENCE_SIZE)
                for size in (REFERENCE_SIZE, NATIVE_SIZE):
                    image = source if size == REFERENCE_SIZE else source.resize(
                        size,
                        Image.Resampling.LANCZOS,
                    )
                    for path in ("builder", "navigation"):
                        with self.subTest(size=size, path=path):
                            observation, _capture_info = self._observe(
                                image,
                                path,
                                assert_single_global_read=False,
                            )
                            self.assertNotEqual(observation.screen_type, SCREEN)
                            self.assertNotEqual(observation.decision.layout_id, PROFILE_ID)


if __name__ == "__main__":
    unittest.main()
