"""Qualify reviewed centered Compose frames and their bounded field facts."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
import unittest

from PIL import Image

from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ImageSelectorEngine, ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    OcrLine,
    OcrRequiredFieldStatus,
    OcrResult,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.modal_overlay import with_update_modal
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.integration.vision.test_chat_mail_captured_content import _BoundedRapidOcrService


FIXTURE_ROOT = TEST_DATA_ROOT / "screen_recognition" / "mail_compose_variants"
REFERENCE_SIZE = (540, 960)
FIELD_IDS = (
    UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD,
    UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD,
    UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD,
)
CONTROL_IDS = (
    UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON,
    UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
)


@dataclass(slots=True)
class _BoundedOcrService:
    """Return only controlled labels contained by each requested crop."""

    lines: tuple[OcrLine, ...]
    calls: list[Bounds | None] = field(default_factory=list)
    image_sizes: list[tuple[int, int]] = field(default_factory=list)

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject full-frame acquisition and retain only lines in the crop."""

        self.calls.append(region)
        self.image_sizes.append(image.size)
        if region is None or region == Bounds(0, 0, image.width, image.height):
            raise AssertionError("Compose qualification must use bounded OCR regions.")
        lines = tuple(line for line in self.lines if region.contains_bounds(line.bounds))
        return OcrResult(lines=lines, words=tuple(word for line in lines for word in line.words))

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        """Expose the OCR protocol's line helper through the same bounded read."""

        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        """Expose the OCR protocol's text helper through the same bounded read."""

        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _scale_bounds(bounds: Bounds, image_size: tuple[int, int]) -> Bounds:
    """Scale a reference-space OCR label to one of the reviewed viewports."""

    width, height = image_size
    return Bounds(
        round(bounds.x * width / REFERENCE_SIZE[0]),
        round(bounds.y * height / REFERENCE_SIZE[1]),
        round(bounds.width * width / REFERENCE_SIZE[0]),
        round(bounds.height * height / REFERENCE_SIZE[1]),
    )


def _lines_for(
    image_size: tuple[int, int],
    state: str,
    *,
    include_update: bool = False,
) -> tuple[OcrLine, ...]:
    """Return the reviewed Compose labels and authored field text for one frame."""

    labels: list[tuple[str, Bounds]] = []
    if not include_update:
        labels.extend(
            (
                ("Edit Mail", Bounds(218, 229, 105, 22)),
                ("Send", Bounds(243, 667, 55, 22)),
            )
        )
        if state in {"subject", "body"}:
            labels.append(("Recognition validation", Bounds(95, 352, 183, 16)))
        if state == "body":
            labels.append(("Recognition validation - no action needed", Bounds(52, 404, 302, 14)))
        else:
            labels.append(("Can enter up to 1000 characters", Bounds(52, 404, 228, 14)))
    if include_update:
        labels.extend(
            (
                ("New version detected. Tap Confirm to update.", Bounds(58, 380, 420, 28)),
                ("Confirm", Bounds(221, 531, 90, 27)),
            )
        )
    return tuple(OcrLine(text, _scale_bounds(bounds, image_size), 1.0) for text, bounds in labels)


def _load_fixture(name: str) -> Image.Image:
    """Load one sanitized Compose fixture."""

    with Image.open(FIXTURE_ROOT / name) as source:
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
    """Wire the production registry, selector engine, enricher, and recognizer."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    return ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=PncObservationEnricher(selector_registry=registry),
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
        ocr_service=ocr,
        ocr_backend_revision="mail-compose-qualification",
    )


def _perception(builder: ObservationBuilder) -> NavigationPerception:
    """Wire the replacement navigator against the same production components."""

    assert builder.visual_recognizer is not None
    return NavigationPerception(
        builder.visual_recognizer,
        builder.enricher,
        builder.screen_classifier,
        builder.create_ocr_context,
    )


def _assert_bounded(test: unittest.TestCase, service: _BoundedOcrService) -> None:
    """Require every backend request to name a strict crop."""

    test.assertTrue(service.calls)
    test.assertTrue(all(region is not None for region in service.calls))
    test.assertTrue(
        all(
            (region.x, region.y, region.width, region.height) != (0, 0, width, height)
            for region, (width, height) in zip(service.calls, service.image_sizes)
            if region is not None
        )
    )


def _field_values(observation) -> dict[UiElementId, tuple[str | None, bool | None]]:
    """Project typed field states to a compact assertion shape."""

    return {
        selector_id: (
            observation.text_field_states[selector_id].text,
            observation.text_field_states[selector_id].empty,
        )
        for selector_id in FIELD_IDS
    }


class MailComposeCapturedFieldTests(unittest.TestCase):
    """Keep the centered Compose visual identity and field reads frame-local."""

    def test_real_ocr_preserves_captured_body_word_spaces_and_punctuation(self) -> None:
        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        original = _load_fixture("mail_compose_body.png")
        for size in (REFERENCE_SIZE, (900, 1600)):
            image = original.resize(size, Image.Resampling.LANCZOS)
            for path in ("builder", "navigation"):
                with self.subTest(size=size, path=path):
                    backend.bind(image.size)
                    builder = _builder(backend)
                    capture = _capture(image, session_id=f"compose-spacing:{size}:{path}")
                    observation = (
                        builder.build(capture, request=ObservationRequest.mail_compose_follow_up())
                        if path == "builder" else _perception(builder).build(capture, include_content=True)
                    )
                    self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
                    self.assertEqual(
                        observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD).text,
                        "Recognition validation - no action needed",
                    )
                    self.assertEqual(
                        observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).text,
                        "Recognition validation",
                    )
                    self.assertEqual(observation.require(UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON).frame_ref,
                                     capture.frame_ref)

    def test_reviewed_frames_match_controls_and_fields_through_both_paths(self) -> None:
        """Builder and navigator preserve controls, provenance, and bounded field facts."""

        cases = (
            ("mail_compose_empty.png", "empty", (None, None, True)),
            ("mail_compose_subject.png", "subject", (None, False, True)),
            ("mail_compose_body.png", "body", (None, False, False)),
        )
        for fixture_name, state, expected_subject_body in cases:
            with self.subTest(fixture=fixture_name):
                base = _load_fixture(fixture_name)
                for size in (REFERENCE_SIZE, (900, 1600)):
                    with self.subTest(size=size):
                        image = base.resize(size, Image.Resampling.LANCZOS) if size != base.size else base
                        expected_fields = {
                            FIELD_IDS[0]: (None, None),
                            FIELD_IDS[1]: (
                                None if state == "empty" else "Recognition validation",
                                expected_subject_body[1],
                            ),
                            FIELD_IDS[2]: (
                                None if state != "body" else "Recognition validation - no action needed",
                                expected_subject_body[2],
                            ),
                        }
                        builder_ocr = _BoundedOcrService(_lines_for(size, state))
                        builder = _builder(builder_ocr)
                        capture = _capture(image, session_id=f"builder:{state}:{size}")
                        built = builder.build(
                            capture,
                            request=ObservationRequest.source_screen_retry(ScreenType.PNC_MAIL_COMPOSE_POPUP),
                        )
                        self.assertEqual(built.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
                        self.assertEqual(built.decision.guard, GuardVerdict.BLOCKED)
                        self.assertEqual(built.decision.layout_id, "mail_compose_centered")
                        self.assertEqual(_field_values(built), expected_fields)
                        self.assertTrue(
                            all(
                                built.visible_elements[selector_id].frame_ref == capture.frame_ref
                                and built.visible_elements[selector_id].source_screen
                                == ScreenType.PNC_MAIL_COMPOSE_POPUP
                                and built.visible_elements[selector_id].source_layout_id == "mail_compose_centered"
                                for selector_id in CONTROL_IDS
                            )
                        )
                        self.assertTrue(
                            all(
                                built.visible_elements[selector_id].source_kind.name == "TEMPLATE"
                                for selector_id in CONTROL_IDS
                            )
                        )
                        _assert_bounded(self, builder_ocr)

                        navigation_ocr = _BoundedOcrService(_lines_for(size, state))
                        navigation_builder = _builder(navigation_ocr)
                        navigation_capture = _capture(image, session_id=f"navigation:{state}:{size}")
                        perceived = _perception(navigation_builder).build(
                            navigation_capture,
                            include_content=True,
                        )
                        self.assertEqual(perceived.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
                        self.assertEqual(perceived.decision.guard, GuardVerdict.BLOCKED)
                        self.assertEqual(perceived.decision.layout_id, "mail_compose_centered")
                        self.assertEqual(_field_values(perceived), expected_fields)
                        self.assertTrue(
                            all(
                                perceived.visible_elements[selector_id].frame_ref == navigation_capture.frame_ref
                                and perceived.visible_elements[selector_id].source_screen
                                == ScreenType.PNC_MAIL_COMPOSE_POPUP
                                and perceived.visible_elements[selector_id].source_layout_id == "mail_compose_centered"
                                for selector_id in CONTROL_IDS
                            )
                        )
                        _assert_bounded(self, navigation_ocr)

    def test_subject_only_request_reads_and_publishes_only_subject_crop(self) -> None:
        """A narrowed request does not acquire the other Compose fields or body refinement."""

        image = _load_fixture("mail_compose_body.png")
        ocr = _BoundedOcrService(_lines_for(image.size, "body"))
        builder = _builder(ocr)
        request = replace(
            ObservationRequest.source_screen_retry(ScreenType.PNC_MAIL_COMPOSE_POPUP),
            text_field_selectors=frozenset({UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD}),
        )
        observation = builder.build(
            _capture(image, session_id="compose:subject-only"),
            request=request,
        )

        self.assertEqual(
            set(observation.text_field_states),
            {UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD},
        )
        self.assertEqual(
            observation.require_text_field_state(UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD).text,
            "Recognition validation",
        )
        self.assertEqual(
            ocr.calls,
            [Bounds(91, 343, 406, 33)],
        )

    def test_navigation_without_content_keeps_only_reviewed_controls(self) -> None:
        """The cheap navigation path does not publish field values without content scope."""

        image = _load_fixture("mail_compose_body.png")
        ocr = _BoundedOcrService(_lines_for(image.size, "body"))
        builder = _builder(ocr)
        observed = _perception(builder).build(
            _capture(image, session_id="navigation:no-content"),
            include_content=False,
        )
        self.assertEqual(observed.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
        self.assertEqual(observed.decision.guard, GuardVerdict.BLOCKED)
        self.assertEqual(
            set(observed.visible_elements),
            {
                UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON,
                UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
            },
        )
        self.assertEqual(observed.text_field_states, {})
        # Compose is a recognized base surface; no popup guard crop runs.
        self.assertEqual(ocr.calls, [])

    def test_update_overlay_owns_the_frame_and_hides_compose_controls(self) -> None:
        """The existing update guard suppresses Compose controls and field content."""

        image = with_update_modal(_load_fixture("mail_compose_body.png"))
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                ocr = _BoundedOcrService(_lines_for(image.size, "empty", include_update=True))
                builder = _builder(ocr)
                capture = _capture(image, session_id=f"update:{path}")
                observation = (
                    builder.build(
                        capture,
                        request=ObservationRequest.source_screen_retry(ScreenType.PNC_MAIL_COMPOSE_POPUP),
                    )
                    if path == "builder"
                    else _perception(builder).build(capture, include_content=True)
                )
                self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                self.assertTrue(observation.blocking_popup)
                self.assertIn(UiElementId.PNC_UPDATE_CONFIRM_BUTTON, observation.visible_elements)
                self.assertFalse(any(selector_id in observation.visible_elements for selector_id in CONTROL_IDS))
                self.assertEqual(observation.text_field_states, {})
                _assert_bounded(self, ocr)

    def test_required_subject_diagnostic_and_field_regions_cover_reviewed_right_edges(self) -> None:
        """A missing subject is explicit, while measured interiors contain authored text extents."""

        image = _load_fixture("mail_compose_empty.png").resize((900, 1600), Image.Resampling.LANCZOS)
        ocr = _BoundedOcrService(_lines_for(image.size, "empty"))
        builder = _builder(ocr)
        capture = _capture(image, session_id="field-bounds")
        context = builder.create_ocr_context(capture)
        observation = builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_MAIL_COMPOSE_POPUP),
            ocr_context=context,
        )
        subject_diagnostics = tuple(
            diagnostic
            for diagnostic in context.required_field_diagnostics
            if diagnostic.required_fact == UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD.value
        )
        self.assertTrue(subject_diagnostics)
        self.assertEqual(subject_diagnostics[-1].status, OcrRequiredFieldStatus.MISSING)

        registry = build_default_selector_registry()
        field_regions = {
            selector_id: registry.require(selector_id).relative_bounds.materialize_region(image_size=image.size)
            for selector_id in FIELD_IDS
        }
        self.assertEqual(field_regions[FIELD_IDS[0]], Bounds(152, 484, 676, 55))
        self.assertEqual(field_regions[FIELD_IDS[1]], Bounds(152, 572, 676, 55))
        self.assertEqual(field_regions[FIELD_IDS[2]], Bounds(75, 670, 750, 362))
        placeholder_line = next(line for line in _lines_for(image.size, "empty") if line.text.startswith("Can enter"))
        self.assertLessEqual(
            placeholder_line.bounds.x + placeholder_line.bounds.width,
            field_regions[FIELD_IDS[2]].x + field_regions[FIELD_IDS[2]].width,
        )
        self.assertEqual(observation.screen_type, ScreenType.PNC_MAIL_COMPOSE_POPUP)
        _assert_bounded(self, ocr)

    def test_visual_profile_requires_all_static_compose_identity_anchors(self) -> None:
        """Removing the reviewed title prevents a Compose identity claim."""

        image = _load_fixture("mail_compose_empty.png")
        recognizer = load_visual_screen_recognizer()
        self.assertEqual(recognizer.recognize(image).profile_ids, ("mail_compose_centered",))
        image.paste((9, 18, 33), (200, 215, 350, 275))
        self.assertEqual(recognizer.recognize(image).profile_ids, ())

    def test_ocr_context_rejects_a_wrong_frame_for_compose_retry(self) -> None:
        """Compose field reads cannot cross the captured frame provenance boundary."""

        image = _load_fixture("mail_compose_body.png")
        builder = _builder(_BoundedOcrService(_lines_for(image.size, "body")))
        capture = _capture(image, session_id="provenance-a")
        context = builder.create_ocr_context(capture)
        other_capture = _capture(image.copy(), session_id="provenance-b")
        with self.assertRaises(ValueError):
            builder.build(
                other_capture,
                request=ObservationRequest.source_screen_retry(ScreenType.PNC_MAIL_COMPOSE_POPUP),
                ocr_context=context,
            )


if __name__ == "__main__":
    unittest.main()
