"""Current-frame ownership of the captured portrait Alliance invitation."""

from __future__ import annotations

from pathlib import Path
import unittest

from PIL import Image, ImageDraw

from pnc_automation.app.pnc.domain.observation import Observation, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.popup import PopupControlKind
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationAdditions, reconcile_visual_modal_guard,
)
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot

from tests.integration.vision.test_alliance_remaining_visual_contracts import (
    _BoundedOcrService, _builder, _capture, _perception,
)


FIXTURE = Path(__file__).parents[2] / "data/screen_recognition/alliance_variants/alliance_invitation_portrait.png"
CANCEL = Bounds(326, 874, 217, 72)


def _scale(bounds: Bounds, size: tuple[int, int]) -> Bounds:
    """Map reviewed native capture bounds to one supported viewport."""
    return Bounds(
        round(bounds.x * size[0] / 900), round(bounds.y * size[1] / 1600),
        round(bounds.width * size[0] / 900), round(bounds.height * size[1] / 1600),
    )


def _lines(size: tuple[int, int]) -> tuple[OcrLine, ...]:
    """Provide the invitation parser's recorded text, independent of visual proof."""
    return tuple(OcrLine(text, _scale(bounds, size), 1.0) for text, bounds in (
        ("Join our alliance and get strong", Bounds(323, 651, 479, 34)),
        ("together!", Bounds(323, 690, 146, 32)),
        ("Cancel", Bounds(380, 893, 112, 34)),
        ("Join/Apply", Bounds(610, 893, 176, 34)),
    ))


class AllianceInvitationCapturedTests(unittest.TestCase):
    """A qualified portrait layout owns Cancel without borrowing compact-panel geometry."""

    def _image(self, size: tuple[int, int] = (900, 1600)) -> Image.Image:
        with Image.open(FIXTURE) as source:
            return source.convert("RGB").resize(size, Image.Resampling.LANCZOS)

    def _observe(
        self, image: Image.Image, path: str, *, lines: tuple[OcrLine, ...],
    ) -> tuple[Observation, CapturedScreenshot]:
        ocr = _BoundedOcrService(lines=lines)
        builder = _builder(ocr)
        capture = _capture(image, session_id=f"invitation-{path}")
        observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
        self.assertLessEqual(len(ocr.calls), 1)
        return observation, capture

    def test_current_cancel_survives_guard_text_hit_and_miss_through_both_paths(self) -> None:
        for size in ((540, 960), (900, 1600)):
            for path in ("builder", "navigation"):
                for lines in ((), _lines(size)):
                    with self.subTest(size=size, path=path, text=bool(lines)):
                        observation, capture = self._observe(self._image(size), path, lines=lines)
                        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                        self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                        self.assertEqual(observation.decision.layout_id, "alliance_invitation_footer")
                        self.assertEqual(set(observation.visible_elements), {UiElementId.PNC_POPUP_CLOSE_BUTTON})
                        cancel = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
                        self.assertEqual(cancel.source_kind, VisibleElementSourceKind.TEMPLATE)
                        self.assertTrue(_scale(CANCEL, size).contains_point(cancel.action_point))
                        self.assertEqual(cancel.frame_ref, capture.frame_ref)
                        self.assertEqual(cancel.source_screen, ScreenType.PNC_POPUP)
                        self.assertEqual(cancel.source_layout_id, observation.decision.layout_id)
                        self.assertIsNotNone(observation.popup_overlay)
                        assert observation.popup_overlay is not None
                        self.assertIsNotNone(observation.popup_overlay.candidate(PopupControlKind.CANCEL))
                        self.assertIsNone(observation.popup_overlay.candidate(PopupControlKind.CLOSE_TEXT))
                        self.assertIsNone(observation.popup_overlay.candidate(PopupControlKind.NEGATIVE_ACTION))

    def test_erased_cancel_cannot_be_recovered_from_ocr_text(self) -> None:
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                image = self._image()
                ImageDraw.Draw(image).rectangle((320, 868, 550, 953), fill=(26, 41, 75))
                observation, _ = self._observe(image, path, lines=_lines(image.size))
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                self.assertFalse(observation.visible_elements)

    def test_legacy_capture_retains_the_same_footer_layout_and_current_cancel(self) -> None:
        """The existing invitation capture keeps its safe control after migration."""
        with Image.open(FIXTURE.parents[1] / "alliance_invitation.png") as source:
            image = source.convert("RGB")
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                observation, capture = self._observe(image, path, lines=_lines(image.size))
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertEqual(observation.decision.layout_id, "alliance_invitation_footer")
                self.assertEqual(set(observation.visible_elements), {UiElementId.PNC_POPUP_CLOSE_BUTTON})
                cancel = observation.require(UiElementId.PNC_POPUP_CLOSE_BUTTON)
                self.assertTrue(Bounds(196, 524, 131, 45).contains_point(cancel.action_point))
                self.assertIsNotNone(observation.popup_overlay)
                assert observation.popup_overlay is not None
                self.assertIsNotNone(observation.popup_overlay.candidate(PopupControlKind.CANCEL))
                self.assertIsNone(observation.popup_overlay.candidate(PopupControlKind.CLOSE_TEXT))
                self.assertIsNone(observation.popup_overlay.candidate(PopupControlKind.NEGATIVE_ACTION))
                self.assertEqual(cancel.frame_ref, capture.frame_ref)

    def test_erased_identity_anchor_does_not_promote_cancel_and_invitation_text(self) -> None:
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                image = self._image()
                ImageDraw.Draw(image).rectangle((0, 515, 313, 960), fill=(26, 41, 75))
                observation, _ = self._observe(image, path, lines=_lines(image.size))
                self.assertEqual(observation.decision.guard, GuardVerdict.UNRESOLVED)
                self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                self.assertFalse(observation.visible_elements)

    def test_foreign_unresolved_guard_keeps_precedence_over_the_captured_profile(self) -> None:
        visual = load_visual_screen_recognizer().recognize(self._image())
        self.assertTrue(visual.evidence)
        foreign = ObservationAdditions(
            guard_verdict=GuardVerdict.UNRESOLVED,
            screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, "weak_unmeasured_ocr_update_required_popup"),),
        )
        self.assertEqual(reconcile_visual_modal_guard(visual, foreign), foreign)


if __name__ == "__main__":
    unittest.main()
