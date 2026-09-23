"""Captured Trial Challenge publication through both production observers.

Qualifies the V15 shared path on the proved ``trial_challenge_live`` and
``trial_applicable_stats`` layouts: real selector registry, packaged visual
recognizer, production enricher, and the real RapidOCR backend. Both
``ObservationBuilder`` and ``NavigationPerception`` must agree on identity,
the six typed category cards, the toolbar counter, the Gear Stats row action,
and the bounded Applicable Stats detail, with frame/layout provenance on
every published fact.

Fixture provenance (``tests/data/screen_recognition/manifest.json``):
``trial_challenge.png`` is a scaled reference copy of the 2026-09-15 tour29
capture; ``trial_challenge_completed_20260916.png`` is an independent
mega_old_acc completion variant; ``trial_gear_stats_20260916.png`` is the
lead-qualified Gear Applicable Stats destination from the separate
v15_stats_qualification run.
"""

from __future__ import annotations

import hashlib
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.domain.trial_challenge import TrialCategory
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ImageSelectorEngine,
    ObservationBuilder,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrLine,
    OcrResult,
    OcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"

_TRIAL_LAYOUT_ID = "trial_challenge_live"
_STATS_LAYOUT_ID = "trial_applicable_stats"

# Reviewed card facts of the frozen reference capture trial_challenge.png.
_REFERENCE_CARDS: tuple[dict[str, Any], ...] = (
    {"category": "hero", "title": "Hero Trial", "progress": (0, 140), "weekday": "Mon"},
    {"category": "curio", "title": "Curio Trial", "locked": True, "required_castle_level": 20, "weekday": "Mon"},
    {"category": "tech", "title": "Tech Trial", "progress": (0, 140), "countdown": "07:34:35", "trial_button": True},
    {"category": "gear", "title": "Gear Trial", "progress": (0, 200), "weekday": "Wed", "complete": True},
    {"category": "rune", "title": "Rune Trial", "locked": True, "required_castle_level": 31, "weekday": "Wed"},
    {"category": "sauroi", "title": "Sauroi Trial", "progress": (0, 100), "weekday": "Thu"},
)

# Reviewed card facts of the independent completed-card capture.
_COMPLETED_CARDS: tuple[dict[str, Any], ...] = (
    {"category": "hero", "progress": (43, 140), "chest": True},
    {"category": "curio", "progress": (4, 160), "chest": True, "weekday": "Mon"},
    {"category": "tech", "progress": (17, 140), "chest": True, "weekday": "Tue"},
    {"category": "gear", "progress": (41, 200), "countdown": "17:21:23", "trial_button": True, "complete": True},
    {"category": "rune", "locked": True, "required_castle_level": 31, "countdown": "17:21:23"},
    {"category": "sauroi", "progress": (5, 100), "chest": True},
)

# Lead-qualified Gear Applicable Stats fixture rows (literal OCR preserved).
_STATS_ROWS: tuple[tuple[str, int], ...] = (
    ("Infantry ATK", 48),
    ("Infantry DEF", 114),
    ("Infantry HP", 104),
    ("Ranged ATK", 48),
    ("Ranged DEF", 82),
    ("Ranged HP", 72),
    ("Cavalry ATK", 176),
    ("Cavalry DEF", 96),
    ("Cavalry HP", 96),
)
_STATS_BACK_BOUNDS = Bounds(25, 11, 52, 32)


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Use shared RapidOCR while recording calls and rejecting whole-frame reads."""

    delegate: OcrService
    capture_size: tuple[int, int] | None = None
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)

    def bind(self, image_size: tuple[int, int]) -> None:
        """Bind a fresh frame and reset native-call accounting."""

        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        """Reject ``None`` on the full image and explicit whole-frame bounds."""

        self.calls.append((region, image.size))
        whole = None if self.capture_size is None else Bounds(0, 0, *self.capture_size)
        if region == whole or (region is None and self.capture_size == image.size):
            raise AssertionError("Trial content test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _capture(name: str, *, session_id: str, capture_sequence: int = 1) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance and no payload shortcut."""

    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    captured_at = datetime.now(UTC)
    return CapturedScreenshot(
        None,
        image,
        "PNG",
        frame_ref=FrameRef(
            session_id=session_id,
            session_epoch=1,
            capture_sequence=capture_sequence,
            input_sequence=0,
            captured_at=captured_at,
        ),
        ephemeral_captured_at=captured_at,
    )


def _wire(
    ocr_service: _BoundedRapidOcrService,
) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publishers over the real packaged recognition stack."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    builder = ObservationBuilder(
        selector_registry=registry,
        selector_engine=ImageSelectorEngine(matcher),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        ocr_service=ocr_service,
        visual_recognizer=load_visual_screen_recognizer(matcher=matcher),
    )
    navigation = NavigationPerception(
        builder.visual_recognizer,
        enricher,
        ScreenClassifier(),
        builder.create_ocr_context,
    )
    return builder, navigation


def _build_both(
    builder: ObservationBuilder,
    navigation: NavigationPerception,
    backend: _BoundedRapidOcrService,
    capture: CapturedScreenshot,
    screen_type: ScreenType,
) -> tuple[Observation, Observation]:
    """Publish one capture through both production paths with content enabled."""

    backend.bind(capture.image.size)
    return (
        builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(screen_type),
            ocr_context=builder.create_ocr_context(capture),
        ),
        navigation.build(capture, include_content=True),
    )


class TrialChallengePublicationTests(unittest.TestCase):
    """Replayed Trial captures qualify the shared observation contract on both paths."""

    def _assert_trial_identity(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
    ) -> None:
        """Require independent Trial identity, a clear decision, and the back control."""

        self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(_TRIAL_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertEqual(
            hashlib.sha256(capture.image.tobytes()).hexdigest(),
            observation.frame_fingerprint,
        )
        self.assertTrue(
            any(
                evidence.screen_type == ScreenType.PNC_TRIAL_CHALLENGE
                and evidence.layout_id == _TRIAL_LAYOUT_ID
                for evidence in observation.decision.evidence
            ),
            "independent visual anchor evidence must own the trial layout",
        )
        back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
        self.assertEqual(capture.frame_ref, back.frame_ref)
        self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, back.source_screen)
        self.assertEqual(_TRIAL_LAYOUT_ID, back.source_layout_id)
        # Content OCR alone never grants toolbar or card actions.
        self.assertEqual({UiElementId.PNC_BACK_BUTTON_TOP_LEFT}, set(observation.visible_elements))

    def _assert_card_provenance(self, entry: DetectedListEntry, capture: CapturedScreenshot) -> None:
        self.assertEqual(capture.frame_ref, entry.frame_ref)
        self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, entry.source_screen)
        self.assertEqual(_TRIAL_LAYOUT_ID, entry.source_layout_id)

    def _assert_card_facts(
        self,
        entry: DetectedListEntry,
        expected: dict[str, Any],
        capture: CapturedScreenshot,
    ) -> None:
        """Compare one published card row with its reviewed fixture facts."""

        self.assertEqual(ListEntryKind.TRIAL_CATEGORY, entry.kind)
        self._assert_card_provenance(entry, capture)
        facts = entry.trial_card_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(TrialCategory(expected["category"]), facts.category)
        self.assertEqual(expected["category"], entry.metadata.get("category"))
        self.assertEqual(expected.get("progress"), (
            (facts.progress_current, facts.progress_required)
            if facts.progress_current is not None
            else None
        ))
        self.assertEqual(expected.get("required_castle_level"), facts.required_castle_level)
        self.assertEqual(expected.get("countdown"), facts.countdown_text)
        self.assertEqual(expected.get("weekday"), facts.weekday_text)
        self.assertEqual(expected.get("locked", False), facts.locked)
        self.assertEqual(expected.get("chest", False), facts.reward_chest_present)
        self.assertEqual(expected.get("trial_button", False), facts.trial_button_present)
        if expected.get("title"):
            self.assertEqual(expected["title"], entry.title_text)
        if expected.get("complete"):
            self.assertEqual(RowRecognitionStatus.COMPLETE, entry.row_status)
            self.assertIsNotNone(entry.action_bounds)
            self.assertIsNotNone(entry.action_point)
            assert entry.action_bounds is not None and entry.action_point is not None
            self.assertTrue(entry.bounds.contains_bounds(entry.action_bounds))
            self.assertTrue(entry.action_bounds.contains_point(entry.action_point))
        else:
            self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
            self.assertIsNone(entry.action_point)
            self.assertIsNone(entry.action_bounds)

    def test_reference_capture_publishes_six_typed_cards_on_both_paths(self) -> None:
        """The frozen tour29 reference yields the same reviewed cards on both publishers."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("trial_challenge.png", session_id="v15-trial-reference")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_TRIAL_CHALLENGE
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_trial_identity(observation, capture)
                entries = observation.list_entries
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _REFERENCE_CARDS, strict=True):
                    self._assert_card_facts(entry, expected, capture)
                # A lone '0' counter glyph is honestly unreadable on this capture.
                summary = observation.trial_summary
                self.assertTrue(
                    summary is None or summary.observed_counter is None,
                    "unreadable toolbar counter must stay unknown",
                )
                self.assertIsNone(observation.trial_stats_detail)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
        self.assertEqual(builder_observation.trial_summary, navigation_observation.trial_summary)

    def test_completed_capture_publishes_independent_state_differences(self) -> None:
        """The completed-card variant shows chest, progress, and lock/timer combinations."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "trial_challenge_completed_20260916.png", session_id="v15-trial-completed"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_TRIAL_CHALLENGE
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_trial_identity(observation, capture)
                entries = observation.list_entries
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _COMPLETED_CARDS, strict=True):
                    self._assert_card_facts(entry, expected, capture)
                curio = next(
                    entry for entry in entries
                    if entry.trial_card_facts is not None
                    and entry.trial_card_facts.category == TrialCategory.CURIO
                )
                assert curio.trial_card_facts is not None
                # Curio is castle-locked on the reference but progressed here;
                # the lock glyph and progress are independent measured facts.
                self.assertFalse(curio.trial_card_facts.locked)
                self.assertEqual((4, 160), (
                    curio.trial_card_facts.progress_current,
                    curio.trial_card_facts.progress_required,
                ))
                rune = next(
                    entry for entry in entries
                    if entry.trial_card_facts is not None
                    and entry.trial_card_facts.category == TrialCategory.RUNE
                )
                assert rune.trial_card_facts is not None
                # A countdown can coexist with a castle lock.
                self.assertTrue(rune.trial_card_facts.locked)
                self.assertEqual(31, rune.trial_card_facts.required_castle_level)
                self.assertEqual("17:21:23", rune.trial_card_facts.countdown_text)
                summary = observation.trial_summary
                self.assertIsNotNone(summary)
                assert summary is not None
                self.assertEqual(12712, summary.observed_counter)
                self.assertIsNotNone(summary.counter_bounds)
                self.assertEqual(capture.frame_ref, summary.frame_ref)
                self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, summary.source_screen)
                self.assertEqual(_TRIAL_LAYOUT_ID, summary.source_layout_id)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
        self.assertEqual(builder_observation.trial_summary, navigation_observation.trial_summary)

    def test_gear_stats_capture_publishes_detail_on_both_paths(self) -> None:
        """The lead-qualified destination yields the nine bounded rows and Gear footer."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("trial_gear_stats_20260916.png", session_id="v15-trial-stats")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_TRIAL_APPLICABLE_STATS
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self.assertEqual(ScreenType.PNC_TRIAL_APPLICABLE_STATS, observation.screen_type)
                self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
                self.assertEqual(_STATS_LAYOUT_ID, observation.decision.layout_id)
                self.assertEqual(capture.frame_ref, observation.frame_ref)
                self.assertTrue(
                    any(
                        evidence.screen_type == ScreenType.PNC_TRIAL_APPLICABLE_STATS
                        and evidence.layout_id == _STATS_LAYOUT_ID
                        for evidence in observation.decision.evidence
                    ),
                    "independent visual anchor evidence must own the stats layout",
                )
                back = observation.require(UiElementId.PNC_BACK_BUTTON_TOP_LEFT)
                self.assertEqual(_STATS_BACK_BOUNDS, back.bounds)
                self.assertEqual(capture.frame_ref, back.frame_ref)
                # List facts never leak onto the detail screen.
                self.assertEqual((), observation.list_entries)
                self.assertIsNone(observation.trial_summary)
                detail = observation.trial_stats_detail
                self.assertIsNotNone(detail)
                assert detail is not None
                self.assertEqual(TrialCategory.GEAR, detail.category)
                self.assertEqual(capture.frame_ref, detail.frame_ref)
                self.assertEqual(ScreenType.PNC_TRIAL_APPLICABLE_STATS, detail.source_screen)
                self.assertEqual(_STATS_LAYOUT_ID, detail.source_layout_id)
                self.assertIsNotNone(detail.footer_text)
                self.assertEqual(9, len(detail.stats))
                for stat, (expected_label, expected_value) in zip(
                    detail.stats, _STATS_ROWS, strict=True
                ):
                    self.assertEqual(expected_label.replace(" ", ""), stat.label_text.replace(" ", ""))
                    self.assertEqual(expected_value, stat.percent_value)
                    self.assertTrue(stat.percent_text.strip())
                    self.assertTrue(
                        Bounds(0, 0, *capture.image.size).contains_bounds(stat.bounds)
                    )
                # The misread '%96' literal is preserved beside the numeric value.
                percent_literals = tuple(stat.percent_text for stat in detail.stats)
                self.assertIn("%96", percent_literals)
        self.assertEqual(builder_observation.trial_stats_detail, navigation_observation.trial_stats_detail)

    def test_trial_content_is_demand_driven(self) -> None:
        """Unrequested builds keep visual identity but publish no card or detail facts."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("trial_challenge.png", session_id="v15-trial-demand")

        backend.bind(capture.image.size)
        builder_observation = builder.build(
            capture,
            request=ObservationRequest.base(),
            ocr_context=builder.create_ocr_context(capture),
        )
        navigation_observation = navigation.build(capture, include_content=False)

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self.assertEqual(ScreenType.PNC_TRIAL_CHALLENGE, observation.screen_type)
                self.assertEqual(_TRIAL_LAYOUT_ID, observation.decision.layout_id)
                self.assertEqual((), observation.list_entries)
                self.assertIsNone(observation.trial_summary)
                self.assertIsNone(observation.trial_stats_detail)


if __name__ == "__main__":
    unittest.main()
