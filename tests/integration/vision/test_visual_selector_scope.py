"""Production-stack regressions for visual selector scoping and OCR ownership."""

from __future__ import annotations

from datetime import UTC, datetime
import unittest

from PIL import Image, ImageEnhance

from pnc_automation.app.pnc.domain.mail import MailboxType
from pnc_automation.app.pnc.domain.observation import ListEntryKind, Observation
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.ocr_region_plan import (
    compile_guard_ocr_region_plans,
    compile_screen_content_ocr_region_plans,
)
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.recording_ocr_service import _RecordingOcrService


FIXTURES = TEST_DATA_ROOT / "screen_recognition"


def _image(name: str) -> Image.Image:
    """Load one committed fixture without retaining its file handle."""

    with Image.open(FIXTURES / name) as source:
        return source.convert("RGB")


def _capture(image: Image.Image) -> CapturedScreenshot:
    """Wrap one image in the canonical ephemeral capture model."""

    frame = make_captured_frame(_encode_png(image), session_id="visual-scope-test")
    return CapturedScreenshot(
        None, image, "PNG", payload=frame.payload, frame_ref=frame.frame_ref,
        ephemeral_captured_at=datetime.now(UTC),
    )


def _mail_hub_lines() -> tuple[OcrLine, ...]:
    """Return the reviewed mail-hub labels at the 540x960 reference viewport."""

    return (
        OcrLine("Mail", Bounds(186, 25, 66, 14), 1.0),
        OcrLine("Player Mail", Bounds(132, 190, 93, 23), 1.0),
        OcrLine("No report yet", Bounds(402, 192, 113, 21), 1.0),
        OcrLine("Alliance Mail", Bounds(132, 289, 106, 19), 1.0),
        OcrLine("No report yet", Bounds(402, 288, 113, 23), 1.0),
    )


def _builder(ocr_service: _RecordingOcrService) -> ObservationBuilder:
    """Build the real registry, selector engine, and visual recognizer stack."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )


def _player_mail_lines() -> tuple[OcrLine, ...]:
    """Return controlled OCR for the reviewed Player Mail list fixture."""

    return (
        OcrLine("Player Mail", Bounds(110, 12, 155, 28), 1.0),
        OcrLine("Mark All as Read", Bounds(177, 884, 184, 34), 1.0),
        OcrLine("Manage", Bounds(402, 884, 72, 30), 1.0),
    )


class _RegionRecordingOcrService(_RecordingOcrService):
    """Records every backend region so bounded ownership stays testable."""

    def __init__(self, *, lines: tuple[OcrLine, ...]) -> None:
        super().__init__(lines=lines)
        self.regions: list[Bounds | None] = []

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        self.regions.append(region)
        return super().read_result(image, region)


def _assert_bounded_regions(
    testcase: unittest.TestCase,
    service: _RegionRecordingOcrService,
    semantic_regions: set[Bounds],
) -> None:
    """Require backend reads to stay inside the declared semantic regions."""

    testcase.assertTrue(service.regions)
    testcase.assertTrue(all(region is not None for region in service.regions))
    testcase.assertTrue(
        all(
            region is not None
            and any(parent.contains_bounds(region) for parent in semantic_regions)
            for region in service.regions
        )
    )


def _production_observations(
    image: Image.Image,
    *,
    request: ObservationRequest,
    lines: tuple[OcrLine, ...] = (),
) -> tuple[CapturedScreenshot, dict[str, Observation]]:
    """Build one capture through both production perception paths with shared components."""

    capture = _capture(image)
    builder = _builder(_RecordingOcrService(lines=lines))
    assert builder.visual_recognizer is not None
    perception = NavigationPerception(
        builder.visual_recognizer,
        builder.enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )
    return capture, {
        "builder": builder.build(capture, request=request),
        "navigation": perception.build(capture),
    }


class VisualSelectorScopeTests(unittest.TestCase):
    """Keep visual identity scoping cheap while preserving guard and coordinate fallbacks."""

    def test_synthetic_building_level_without_visual_identity_remains_unknown(self) -> None:
        """Synthetic OCR without visual identity cannot promote a building screen or label."""

        level_bounds = Bounds(201, 408, 68, 31)
        capture, observations = _production_observations(
            Image.new("RGB", (900, 1600), (15, 28, 68)),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BUILDING_DETAILS),
            lines=(
                OcrLine("Farm", Bounds(180, 23, 123, 46), 1.0),
                OcrLine("Where Food is produced. Upgrade", Bounds(471, 245, 415, 26), 1.0),
                OcrLine("1/45", level_bounds, 1.0),
                OcrLine("Upgrade", Bounds(671, 440, 147, 37), 1.0),
                OcrLine("Time", Bounds(59, 552, 71, 29), 1.0),
                OcrLine("Requirement", Bounds(62, 713, 177, 27), 1.0),
                OcrLine("Materials required", Bounds(61, 865, 251, 26), 1.0),
                OcrLine("Effect", Bounds(60, 1035, 83, 31), 1.0),
            ),
        )
        builder = observations["builder"]
        self.assertEqual(builder.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(builder.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

        navigation = observations["navigation"]
        self.assertEqual(navigation.screen_type, ScreenType.UNKNOWN)
        self.assertFalse(navigation.has(UiElementId.PNC_BUILDING_LEVEL_LABEL))

    def test_player_mail_compose_is_published_by_both_visual_paths_with_frame_provenance(self) -> None:
        """Publishes the observed lower-left compose control only from the Player Mail profile."""

        image = _image("mail_player_list.png")
        capture, observations = _production_observations(
            image,
            request=ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            lines=_player_mail_lines(),
        )
        for path, observation in observations.items():
            with self.subTest(path=path):
                self.assertEqual(observation.screen_type, ScreenType.PNC_MAILBOX_LIST)
                compose = observation.require(UiElementId.PNC_MAIL_COMPOSE_BUTTON)
                self.assertEqual(compose.source_kind.name, "TEMPLATE")
                self.assertEqual(compose.bounds, Bounds(78, 866, 40, 60))
                self.assertEqual(compose.action_point, (98, 896))
                self.assertEqual(compose.source_screen, ScreenType.PNC_MAILBOX_LIST)
                self.assertEqual(compose.source_layout_id, "collect_mail_mailbox_list")
                self.assertEqual(compose.frame_ref, capture.frame_ref)
                self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_player_mail_compose_abstains_when_missing_wrong_mailbox_or_blocked(self) -> None:
        """Keeps a visually plausible compose action absent from unsupported or blocked mailbox frames."""

        cases = (
            ("mail_player_list_no_compose.png", _player_mail_lines(), ObservationRequest.mailbox_observation(MailboxType.PLAYER)),
            (
                "collect_mail_system_list.png",
                (OcrLine("System Message", Bounds(111, 12, 190, 28), 1.0),),
                ObservationRequest.base(),
            ),
            (
                "mail_player_list.png",
                _player_mail_lines()
                + (
                    OcrLine(
                        "New version detected. Tap Confirm to update.",
                        Bounds(58, 380, 420, 28),
                        1.0,
                    ),
                    OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
                ),
                ObservationRequest.mailbox_observation(MailboxType.PLAYER),
            ),
        )
        for name, lines, request in cases:
            capture, observations = _production_observations(_image(name), request=request, lines=lines)
            for path, observation in observations.items():
                with self.subTest(case=name, path=path):
                    self.assertNotIn(UiElementId.PNC_MAIL_COMPOSE_BUTTON, observation.visible_elements)
                    self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_hero_free_recruit_control_is_template_bound_across_reviewed_frames(self) -> None:
        """Publishes the gold Free Recruit 1x control on the reference, scaled, and holdout frames."""

        for name, size in (
            ("hero_hall.png", (540, 960)),
            ("hero_hall.png", (900, 1600)),
            ("hero_hall_aug29.png", (540, 960)),
        ):
            with self.subTest(name=name, size=size):
                image = _image(name).resize(size)
                capture, observations = _production_observations(
                    image,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
                )
                for path, observation in observations.items():
                    with self.subTest(path=path):
                        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
                        self.assertEqual(observation.decision.layout_id, "hero_hall")
                        free_control = observation.require(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON)
                        self.assertEqual(free_control.source_kind.name, "TEMPLATE")
                        self.assertEqual(free_control.source_screen, ScreenType.PNC_HERO_HALL)
                        self.assertEqual(free_control.source_layout_id, "hero_hall")
                        self.assertIsNotNone(free_control.action_point)
                        assert free_control.action_point is not None
                        self.assertTrue(free_control.bounds.contains_point(free_control.action_point))
                        self.assertEqual(free_control.frame_ref, capture.frame_ref)
                        self.assertEqual(observation.frame_ref, capture.frame_ref)
                        self.assertNotIn(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON, observation.visible_elements)

    def test_hero_free_template_control_does_not_create_generic_recruit_geometry(self) -> None:
        """Only the measured Free control is published despite generic Recruit OCR."""

        lines = (
            OcrLine("Hero Hall", Bounds(110, 10, 120, 28), 1.0),
            OcrLine("Recruit", Bounds(110, 70, 120, 28), 1.0),
            OcrLine("Exchange", Bounds(300, 70, 120, 28), 1.0),
            OcrLine("Daily attempts: 5", Bounds(68, 660, 220, 25), 1.0),
            OcrLine("Free", Bounds(68, 700, 170, 33), 1.0),
        )
        capture = _capture(_image("hero_hall.png"))
        observation = _builder(_RecordingOcrService(lines=lines)).build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
        )

        self.assertFalse(observation.has(UiElementId.PNC_HERO_HALL_RECRUIT_1X_BUTTON))
        free_control = observation.require(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON)
        self.assertEqual(free_control.source_kind.name, "TEMPLATE")
        self.assertEqual(free_control.frame_ref, capture.frame_ref)

    def test_hero_free_control_is_removed_for_paid_or_disabled_chrome(self) -> None:
        """Retains Hero Hall identity while rejecting non-Free button appearances."""

        source = _image("hero_hall.png")
        free_region = (56, 691, 240, 745)
        paid_region = (300, 691, 484, 745)
        variants = {}

        removed = source.copy()
        removed.paste((0, 0, 0), free_region)
        variants["removed"] = removed

        paid = source.copy()
        paid.paste(source.crop(paid_region), (56, 691))
        variants["paid_10x"] = paid

        disabled = source.copy()
        disabled.paste(ImageEnhance.Color(source.crop(free_region)).enhance(0.0), (56, 691))
        variants["desaturated_disabled"] = disabled

        for variant, image in variants.items():
            with self.subTest(variant=variant):
                capture, observations = _production_observations(
                    image,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
                )
                for path, observation in observations.items():
                    with self.subTest(path=path):
                        self.assertEqual(observation.screen_type, ScreenType.PNC_HERO_HALL)
                        self.assertEqual(observation.frame_ref, capture.frame_ref)
                        self.assertNotIn(
                            UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON,
                            observation.visible_elements,
                        )

    def test_bag_resource_subtab_is_template_bound_on_selected_frames(self) -> None:
        """Publishes the selected-gold Resource subtab on both reviewed Bag captures."""

        for name, size in (
            ("bag.png", (540, 960)),
            ("bag.png", (900, 1600)),
            ("bag_current_testing.png", (900, 1600)),
        ):
            with self.subTest(name=name, size=size):
                capture, observations = _production_observations(
                    _image(name).resize(size),
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                )
                for path, observation in observations.items():
                    with self.subTest(path=path):
                        self.assertEqual(observation.screen_type, ScreenType.PNC_BAG)
                        self.assertEqual(observation.decision.layout_id, "bag")
                        resource_tab = observation.require(UiElementId.PNC_BAG_SUBTAB_RESOURCE)
                        self.assertEqual(resource_tab.source_kind.name, "TEMPLATE")
                        self.assertEqual(resource_tab.source_screen, ScreenType.PNC_BAG)
                        self.assertEqual(resource_tab.source_layout_id, "bag")
                        self.assertIsNotNone(resource_tab.action_point)
                        assert resource_tab.action_point is not None
                        self.assertTrue(resource_tab.bounds.contains_point(resource_tab.action_point))
                        self.assertEqual(resource_tab.frame_ref, capture.frame_ref)
                        self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_bag_resource_control_is_removed_for_missing_or_unselected_chrome(self) -> None:
        """Retains Bag identity while rejecting removed and blue unselected Resource chrome."""

        source = _image("bag.png")
        resource_region = (0, 123, 107, 162)
        variants = {}

        removed = source.copy()
        removed.paste((0, 0, 0), resource_region)
        variants["removed"] = removed

        blue_unselected = source.copy()
        blue_unselected.paste(source.crop((107, 123, 214, 162)), (0, 123))
        variants["blue_unselected"] = blue_unselected

        for variant, image in variants.items():
            with self.subTest(variant=variant):
                capture, observations = _production_observations(
                    image,
                    request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
                )
                for path, observation in observations.items():
                    with self.subTest(path=path):
                        self.assertEqual(observation.screen_type, ScreenType.PNC_BAG)
                        self.assertEqual(observation.frame_ref, capture.frame_ref)
                        self.assertNotIn(UiElementId.PNC_BAG_SUBTAB_RESOURCE, observation.visible_elements)

    def test_mail_visual_identity_uses_bounded_ocr_reads_and_retains_content(self) -> None:
        ocr_service = _RegionRecordingOcrService(lines=_mail_hub_lines())
        capture = _capture(_image("collect_mail_hub.png"))
        builder = _builder(ocr_service)
        context = builder.create_ocr_context(capture)
        request = ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB)
        observation = builder.build(capture, request=request, ocr_context=context)

        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_HUB)
        allowed_regions = {
            plan.bounds
            for plan in (
                *compile_guard_ocr_region_plans(capture.image.size),
                *compile_screen_content_ocr_region_plans(
                    resolved_screen=ScreenType.PNC_MAIL_HUB,
                    request=request,
                    image_size=capture.image.size,
                ),
            )
        }
        _assert_bounded_regions(self, ocr_service, allowed_regions)
        self.assertTrue(all(diagnostic.region is not None for diagnostic in context.read_diagnostics))
        self.assertEqual(ocr_service.read_text_calls, 0)
        self.assertEqual(observation.empty_mailboxes, frozenset({MailboxType.PLAYER, MailboxType.ALLIANCE}))
        self.assertEqual(
            len(observation.entries(ListEntryKind.MAILBOX_CATEGORY)),
            2,
        )
        self.assertTrue(observation.has(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL))

    def test_absent_visual_identity_remains_unknown_without_visual_evidence(self) -> None:
        """Synthetic broad semantic OCR cannot promote a screen without visual identity."""

        image = Image.new("RGB", (540, 960), (15, 28, 68))
        builder = _builder(_RecordingOcrService(lines=_mail_hub_lines()))
        self.assertFalse(builder.visual_recognizer.recognize(image).evidence)

        observation = builder.build(
            _capture(image),
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB),
        )

        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertEqual(len(observation.entries(ListEntryKind.MAILBOX_CATEGORY)), 0)
        self.assertFalse(observation.has(UiElementId.PNC_MAIL_ROW_PLAYER_MAIL))

    def test_narrow_mail_caller_keeps_update_guard_in_front_of_visual_scope(self) -> None:
        ocr_service = _RegionRecordingOcrService(
            lines=(
                OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
                OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
            )
        )
        capture = _capture(_image("update_over_bag.png"))
        builder = _builder(ocr_service)
        context = builder.create_ocr_context(capture)
        observation = builder.build(
            capture,
            request=ObservationRequest.mail_navigation_follow_up(ScreenType.PNC_MAIL_HUB),
            ocr_context=context,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
        self.assertTrue(observation.blocking_popup)
        self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
        self.assertFalse(observation.has(UiElementId.PNC_BAG_USE_BUTTON))
        _assert_bounded_regions(
            self,
            ocr_service,
            {plan.bounds for plan in compile_guard_ocr_region_plans(capture.image.size)},
        )
        self.assertTrue(all(diagnostic.region is not None for diagnostic in context.read_diagnostics))

    def test_narrow_bag_caller_keeps_update_guard_in_front_of_visual_controls(self) -> None:
        """A blocking update overlay owns the frame and suppresses Bag controls."""

        ocr_service = _RecordingOcrService(
            lines=(
                OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
                OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
            )
        )
        capture, observations = _production_observations(
            _image("update_over_bag.png"),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            lines=ocr_service.lines,
        )
        for path, observation in observations.items():
            with self.subTest(path=path):
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertTrue(observation.blocking_popup)
                self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
                self.assertNotIn(UiElementId.PNC_BAG_SUBTAB_RESOURCE, observation.visible_elements)
                self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, observation.visible_elements)
                self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_narrow_hero_caller_keeps_update_guard_in_front_of_visual_controls(self) -> None:
        """A blocking update overlay owns the frame and suppresses Hero controls."""

        lines = (
            OcrLine("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28), 1.0),
            OcrLine("Confirm", Bounds(221, 531, 90, 27), 1.0),
        )
        capture, observations = _production_observations(
            with_update_modal(_image("hero_hall.png")),
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_HERO_HALL),
            lines=lines,
        )

        for path, observation in observations.items():
            with self.subTest(path=path):
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertTrue(observation.blocking_popup)
                self.assertTrue(observation.has(UiElementId.PNC_UPDATE_CONFIRM_BUTTON))
                self.assertNotIn(UiElementId.PNC_HERO_HALL_FREE_RECRUIT_1X_BUTTON, observation.visible_elements)
                self.assertNotIn(UiElementId.PNC_BACK_BUTTON_TOP_LEFT, observation.visible_elements)
                self.assertEqual(observation.frame_ref, capture.frame_ref)

    def test_world_coordinate_only_request_keeps_its_coordinate_parser(self) -> None:
        registry = build_default_selector_registry()
        image = Image.new("RGB", (540, 960), (15, 28, 68))
        coordinate = registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR).relative_bounds
        assert coordinate is not None
        bounds = coordinate.materialize_region(image_size=image.size)
        ocr_service = _RegionRecordingOcrService(
            lines=(
                OcrLine(
                    "X:230 Y:958",
                    Bounds(bounds.x + 4, bounds.y + 4, min(120, bounds.width - 4), max(18, bounds.height - 8)),
                    1.0,
                ),
                OcrLine("Lv.36 Monster", Bounds(180, 400, 120, 18), 1.0),
            )
        )
        builder = _builder(ocr_service)

        capture = _capture(image)
        context = builder.create_ocr_context(capture)
        observation = builder.build(
            capture,
            request=ObservationRequest.world_map_movement_proof_follow_up(),
            ocr_context=context,
        )

        self.assertEqual(observation.screen_type, ScreenType.PNC_WORLD_MAP)
        _assert_bounded_regions(self, ocr_service, {bounds})
        self.assertTrue(all(diagnostic.region is not None for diagnostic in context.read_diagnostics))
        self.assertEqual(ocr_service.read_text_calls, 0)
        self.assertIsNotNone(observation.spatial_surface)
        assert observation.spatial_surface is not None
        self.assertEqual(observation.spatial_surface.viewport.coordinate, (230, 958))
        self.assertEqual(observation.spatial_surface.objects, ())


if __name__ == "__main__":
    unittest.main()
