"""Captured visual contracts for remaining Alliance and remote profile surfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame


TESTS_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = TESTS_ROOT / "data" / "screen_recognition" / "alliance_variants"
PROFILE_FIXTURE_ROOT = TESTS_ROOT / "data" / "screen_recognition" / "player_profile_variants"
CATALOG_PATH = TESTS_ROOT.parent / "pnc_automation" / "app" / "pnc" / "vision" / "data" / "screen_anchors.json"
REFERENCE_SIZE = (540, 960)
BG = (9, 18, 33)


@dataclass(slots=True)
class _BoundedOcrService:
    """Return only controlled labels contained by each requested crop."""

    lines: tuple[OcrLine, ...] = ()
    calls: list[Bounds | None] = field(default_factory=list)
    image_sizes: list[tuple[int, int]] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject full-frame acquisition and retain only lines in the crop."""

        self.calls.append(region)
        self.image_sizes.append(image.size)
        if region is None or region == Bounds(0, 0, image.width, image.height):
            raise AssertionError("Captured visual contract must use bounded OCR regions.")
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Expose the OCR protocol's line helper through the same bounded read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Expose the OCR protocol's text helper through the same bounded read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _load_fixture(name: str) -> Image.Image:
    """Load one sanitized captured fixture."""

    root = PROFILE_FIXTURE_ROOT if name.startswith("remote_player_profile_") else FIXTURE_ROOT
    with Image.open(root / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach deterministic frame provenance to a fixture."""

    frame = make_captured_frame(_encode_png(image), session_id=session_id)
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _builder(ocr: _BoundedOcrService) -> ObservationBuilder:
    """Wire production components against the packaged catalog."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(CATALOG_PATH, matcher=matcher),
        ocr_service=ocr,
        ocr_backend_revision="alliance-remaining-proposal",
    )


def _perception(builder: ObservationBuilder) -> NavigationPerception:
    """Wire the replacement navigator against the same packaged recognizer."""

    assert builder.visual_recognizer is not None
    return NavigationPerception(
        builder.visual_recognizer,
        builder.enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )


def _scale(bounds: Bounds, size: tuple[int, int]) -> Bounds:
    """Scale one reference OCR line to a reviewed viewport."""

    return Bounds(
        round(bounds.x * size[0] / REFERENCE_SIZE[0]),
        round(bounds.y * size[1] / REFERENCE_SIZE[1]),
        round(bounds.width * size[0] / REFERENCE_SIZE[0]),
        round(bounds.height * size[1] / REFERENCE_SIZE[1]),
    )


def _update_lines(size: tuple[int, int]) -> tuple[OcrLine, ...]:
    """Return the exact existing update guard evidence used by offline tests."""

    return tuple(
        OcrLine(text, _scale(bounds, size), 1.0)
        for text, bounds in (
            ("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28)),
            ("Confirm", Bounds(221, 531, 90, 27)),
        )
    )


def _profile_lines(size: tuple[int, int]) -> tuple[OcrLine, ...]:
    """Return generic name plus static Gear support labels for remote-profile OCR."""

    labels = (
        ("Remote Player", Bounds(105, 12, 220, 28)),
        ("Gear", Bounds(20, 65, 80, 20)),
        ("Gem", Bounds(140, 65, 80, 20)),
        ("Saurgem", Bounds(235, 65, 90, 20)),
        ("Warsigil", Bounds(340, 65, 100, 20)),
    )
    return tuple(OcrLine(text, _scale(bounds, size), 1.0) for text, bounds in labels)


PROFILE_CASES = (
    (
        "alliance_remaining_member_list.png",
        "alliance_remaining_member_list",
        ScreenType.PNC_ALLIANCE_MEMBER_LIST,
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "alliance_remaining_member_reinforce.png",
        "alliance_remaining_member_reinforce",
        ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT},
    ),
    (
        "alliance_remaining_manage_leader.png",
        "alliance_remaining_manage_leader",
        ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
        {UiElementId.PNC_POPUP_CLOSE_BUTTON, UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON},
    ),
    (
        "alliance_remaining_manage_ordinary.png",
        "alliance_remaining_manage_ordinary",
        ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
        {UiElementId.PNC_POPUP_CLOSE_BUTTON, UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON},
    ),
    (
        "alliance_remaining_hall.png",
        "alliance_remaining_hall",
        ScreenType.PNC_ALLIANCE_HALL,
        {
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_ALLIANCE_HALL_UPGRADE_BUTTON,
            UiElementId.PNC_ALLIANCE_HALL_SEND_BACK_BUTTON,
            UiElementId.PNC_ALLIANCE_HALL_REINFORCE_BUTTON,
        },
    ),
    (
        "remote_player_profile_gear.png",
        "remote_player_profile_gear",
        ScreenType.PNC_PLAYER_PROFILE,
        {UiElementId.PNC_BACK_BUTTON_TOP_LEFT, UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON},
    ),
)


class AllianceRemainingVisualContractTests(unittest.TestCase):
    """Exercise measured static Alliance and remote profile evidence."""

    def test_catalog_loads_and_each_positive_is_mutually_exclusive(self) -> None:
        """Packaged catalog matches each layout and rejects negative holdouts."""

        recognizer = load_visual_screen_recognizer(CATALOG_PATH)
        self.assertGreaterEqual(len(recognizer.profiles), len(PROFILE_CASES))
        for fixture_name, profile_id, _screen, expected_controls in PROFILE_CASES:
            with self.subTest(fixture=fixture_name):
                image = _load_fixture(fixture_name)
                for size in (REFERENCE_SIZE, (900, 1600)):
                    with self.subTest(size=size):
                        view = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
                        recognition = recognizer.recognize(view)
                        self.assertEqual(recognition.profile_ids, (profile_id,))
                        self.assertEqual(
                            {control.selector_id for control in recognition.controls},
                            expected_controls,
                        )

        negative = recognizer.recognize(_load_fixture("alliance_remaining_transport_negative.png"))
        self.assertEqual(negative.profile_ids, ())
        self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON, negative.control_selector_ids)
        lord_negative = recognizer.recognize(_load_fixture("remote_player_profile_lord_negative.png"))
        self.assertEqual(lord_negative.profile_ids, ())
        self.assertNotIn(ScreenType.PNC_PLAYER_PROFILE, {item.screen_type for item in lord_negative.evidence})

    def test_both_production_paths_preserve_visual_layout_and_frame_provenance(self) -> None:
        """Builder and navigator retain independently matched layouts without rows."""

        for fixture_name, profile_id, screen, expected_controls in PROFILE_CASES:
            with self.subTest(fixture=fixture_name):
                image = _load_fixture(fixture_name)
                for size in (REFERENCE_SIZE, (900, 1600)):
                    with self.subTest(size=size):
                        view = image.resize(size, Image.Resampling.LANCZOS) if size != image.size else image
                        lines = _profile_lines(size) if screen == ScreenType.PNC_PLAYER_PROFILE else ()
                        builder_ocr = _BoundedOcrService(lines=lines)
                        builder = _builder(builder_ocr)
                        capture = _capture(view, session_id=f"builder:{profile_id}:{size}")
                        built = builder.build(
                            capture,
                            request=ObservationRequest.source_screen_retry(screen),
                        )
                        self.assertEqual(built.screen_type, screen)
                        self.assertEqual(built.decision.layout_id, profile_id)
                        self.assertEqual(built.frame_ref, capture.frame_ref)
                        if screen == ScreenType.PNC_PLAYER_PROFILE:
                            self.assertEqual(built.profile_player_name, "Remote Player")
                        self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON, built.visible_elements)
                        self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_REINFORCE_BUTTON, built.visible_elements)

                        navigation_ocr = _BoundedOcrService(lines=lines)
                        navigation_builder = _builder(navigation_ocr)
                        navigation_capture = _capture(view, session_id=f"navigation:{profile_id}:{size}")
                        perceived = _perception(navigation_builder).build(
                            navigation_capture,
                            include_content=True,
                        )
                        self.assertEqual(perceived.screen_type, screen)
                        self.assertEqual(perceived.decision.layout_id, profile_id)
                        self.assertEqual(perceived.frame_ref, navigation_capture.frame_ref)
                        if screen == ScreenType.PNC_PLAYER_PROFILE:
                            self.assertEqual(perceived.profile_player_name, "Remote Player")
                        self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON, perceived.visible_elements)
                        self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_REINFORCE_BUTTON, perceived.visible_elements)
                        self.assertTrue(
                            all(
                                element.frame_ref == navigation_capture.frame_ref
                                and element.source_screen == screen
                                and element.source_layout_id == profile_id
                                for element in perceived.visible_elements.values()
                            )
                        )
                        if screen != ScreenType.PNC_ALLIANCE_MEMBER_LIST:
                            self.assertTrue(expected_controls.intersection(perceived.visible_elements))
                        self.assertTrue(all(region is not None for region in builder_ocr.calls))
                        self.assertTrue(all(region is not None for region in navigation_ocr.calls))

    def test_manage_roles_and_mode_identity_do_not_cross_match(self) -> None:
        """Leader rules, ordinary Send, officer banner, and R5 icon stay distinct."""

        recognizer = load_visual_screen_recognizer(CATALOG_PATH)
        cases = (
            ("alliance_remaining_manage_leader.png", "alliance_remaining_manage_leader"),
            ("alliance_remaining_manage_ordinary.png", "alliance_remaining_manage_ordinary"),
            ("alliance_remaining_member_list.png", "alliance_remaining_member_list"),
            ("alliance_remaining_member_reinforce.png", "alliance_remaining_member_reinforce"),
        )
        for fixture_name, profile_id in cases:
            image = _load_fixture(fixture_name)
            with self.subTest(fixture=fixture_name):
                for other_name, _other_id in cases:
                    if other_name == fixture_name:
                        continue
                    other = _load_fixture(other_name)
                    # A profile ID must not be borrowed from a different captured layout.
                    self.assertNotIn(profile_id, recognizer.recognize(other).profile_ids)

    def test_remote_profile_requires_static_footer_pair_beyond_shared_gear(self) -> None:
        """The remote Gear profile rejects the Lord Gear holdout sharing its tab chrome."""

        recognizer = load_visual_screen_recognizer(CATALOG_PATH)
        positive = recognizer.recognize(_load_fixture("remote_player_profile_gear.png"))
        negative = recognizer.recognize(_load_fixture("remote_player_profile_lord_negative.png"))
        self.assertEqual(positive.profile_ids, ("remote_player_profile_gear",))
        self.assertEqual(negative.profile_ids, ())

    def test_remote_profile_name_survives_missing_mail_control(self) -> None:
        """A missing Mail template does not erase the bounded remote name fact."""

        image = _load_fixture("remote_player_profile_gear.png")
        image.paste(BG, (315, 845, 435, 960))
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                ocr = _BoundedOcrService(lines=_profile_lines(REFERENCE_SIZE))
                builder = _builder(ocr)
                capture = _capture(image, session_id=f"remote-profile-no-mail:{path}")
                observed = (
                    builder.build(
                        capture,
                        request=ObservationRequest.source_screen_retry(ScreenType.PNC_PLAYER_PROFILE),
                    )
                    if path == "builder"
                    else _perception(builder).build(capture, include_content=True)
                )
                self.assertEqual(observed.screen_type, ScreenType.PNC_PLAYER_PROFILE)
                self.assertEqual(observed.decision.layout_id, "remote_player_profile_gear")
                self.assertEqual(observed.profile_player_name, "Remote Player")
                self.assertNotIn(UiElementId.PNC_PLAYER_PROFILE_MAIL_BUTTON, observed.visible_elements)
                self.assertTrue(all(region is not None for region in ocr.calls))

    def test_missing_title_abstains_and_update_overlay_hides_alliance_surface(self) -> None:
        """Missing static identity and a known update guard both fail closed."""

        recognizer = load_visual_screen_recognizer(CATALOG_PATH)
        title_regions = {
            "alliance_remaining_member_list.png": (95, 0, 350, 75),
            "alliance_remaining_member_reinforce.png": (95, 0, 350, 75),
            "alliance_remaining_manage_leader.png": (200, 220, 360, 280),
            "alliance_remaining_manage_ordinary.png": (200, 220, 360, 280),
            "alliance_remaining_hall.png": (95, 0, 350, 75),
            "remote_player_profile_gear.png": (0, 54, 115, 60),
        }
        for fixture_name, region in title_regions.items():
            image = _load_fixture(fixture_name)
            image.paste(BG, region)
            self.assertEqual(recognizer.recognize(image).profile_ids, (), fixture_name)

        with Image.open(TESTS_ROOT / "data/screen_recognition/update_over_bag.png") as source:
            image = source.convert("RGB")
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                ocr = _BoundedOcrService(_update_lines(image.size))
                builder = _builder(ocr)
                capture = _capture(image, session_id=f"update:{path}")
                observed = (
                    builder.build(
                        capture,
                        request=ObservationRequest.source_screen_retry(ScreenType.PNC_ALLIANCE_HALL),
                    )
                    if path == "builder"
                    else _perception(builder).build(capture, include_content=True)
                )
                self.assertEqual(observed.screen_type, ScreenType.PNC_POPUP)
                self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, observed.visible_elements)
                self.assertNotIn(UiElementId.PNC_ALLIANCE_HALL_REINFORCE_BUTTON, observed.visible_elements)
                self.assertNotIn(UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON, observed.visible_elements)
                self.assertTrue(ocr.calls)


if __name__ == "__main__":
    unittest.main()
