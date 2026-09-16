"""Publication tests for the optional ``workshop`` field on ``Observation``.

Both production publishers must bind supplied Workshop content to the current
frame and keep every other fact intact. All content is supplied through typed
``ObservationAdditions`` test doubles; no Workshop parser exists yet (PW02),
and nothing here is live game evidence.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import Mock

from PIL import Image

from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationAdditions,
    ObservationBuilder,
    _merge_observation_additions,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import VisualRecognition
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds
from tests.support.pnc import pet_workshop as workshop_fixtures


IMAGE_SIZE = (540, 960)
FRAME = FrameRef(
    session_id="workshop-publication-test",
    session_epoch=1,
    capture_sequence=1,
    input_sequence=0,
    captured_at=datetime(2026, 9, 16, tzinfo=UTC),
)
OTHER_FRAME = FrameRef(
    session_id="workshop-publication-test",
    session_epoch=1,
    capture_sequence=2,
    input_sequence=0,
    captured_at=datetime(2026, 9, 16, tzinfo=UTC),
)
SCREEN = ScreenType.PNC_SETTINGS


class EmptySelectorEngine:
    """Returns no raw selector matches so content comes only from additions."""

    def detect(self, image, registry, *, selector_ids=None, ocr_context=None):
        """Suppresses selector matches so only the scripted typed additions drive publication."""
        del image, registry, selector_ids, ocr_context
        return ()


@dataclass
class ScriptedEnricher:
    """Returns deterministic guard and content additions without OCR or templates."""

    enrichments: list[ObservationAdditions]

    def recognize_guards(self, image, request, *, ocr_context):
        """Supplies a clear guard without invoking pixel recognition."""
        del image, request, ocr_context
        return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)

    def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
        """Supplies the scripted content through the production enrichment interface."""
        del image, screen_type, visible_elements, request, ocr_context, ocr_regions, layout_id
        if not self.enrichments:
            raise AssertionError("Scripted enricher received more calls than expected")
        return self.enrichments.pop(0)


@dataclass
class ScriptedNavigationGuard:
    """NavigationGuard double that supplies Workshop content additions."""

    content: ObservationAdditions

    def detect_interruption(self, image, *, ocr_context, owned_dismiss_bounds=(), owned_navigation_screen=None):
        """Supplies a clear navigation guard without running a live detector."""
        del image, ocr_context, owned_dismiss_bounds, owned_navigation_screen
        return ObservationAdditions(guard_verdict=GuardVerdict.CLEAR)

    def enrich(self, image, screen_type, visible_elements, request, *, ocr_context, ocr_regions, layout_id=None):
        """Supplies the scripted content through the production enrichment interface."""
        del image, screen_type, visible_elements, request, ocr_context, ocr_regions, layout_id
        return self.content


def _builder(enricher: ScriptedEnricher) -> ObservationBuilder:
    """Builds the production publisher with deterministic screen and content evidence."""
    return ObservationBuilder(
        selector_registry=build_default_selector_registry(),
        selector_engine=EmptySelectorEngine(),
        screen_classifier=ScreenClassifier(),
        enricher=enricher,
        visual_recognizer=Mock(
            recognize=Mock(
                return_value=VisualRecognition(
                    evidence=(ScreenEvidence(SCREEN, "workshop_test_visual", "test-layout"),),
                    controls=(),
                )
            )
        ),
    )


def _navigation(builder: ObservationBuilder, guard: ScriptedNavigationGuard) -> NavigationPerception:
    """Builds the navigation publisher sharing the same observation context owner."""
    return NavigationPerception(
        builder.visual_recognizer,
        guard,
        ScreenClassifier(),
        builder.create_ocr_context,
    )


def _screenshot(frame_ref: FrameRef = FRAME) -> CapturedScreenshot:
    """Creates an in-memory capture with explicit provenance and no emulator access."""
    return CapturedScreenshot(
        artifact=None,
        image=Image.new("RGB", IMAGE_SIZE, (8, 9, 10)),
        image_format="PNG",
        payload=b"workshop-frame",
        ephemeral_captured_at=frame_ref.captured_at,
        frame_ref=frame_ref,
    )


def _content(workshop=None, **extra) -> ObservationAdditions:
    """Supplies typed additions so publication tests exercise no recognition implementation."""
    return ObservationAdditions(workshop=workshop, **extra)


def _entry() -> DetectedListEntry:
    """Creates unrelated list content to detect accidental loss during Workshop publication."""
    return DetectedListEntry(
        kind=ListEntryKind.DAILY_QUEST,
        bounds=Bounds(x=20, y=20, width=40, height=20),
        title_text="Workshop row",
        action_point=(30, 30),
    )


class WorkshopPublicationTests(unittest.TestCase):
    """The optional workshop field survives both canonical publication paths."""

    def test_builder_publishes_workshop_with_bound_provenance(self) -> None:
        """Verifies that builder publishes workshop with bound provenance."""
        workshop = workshop_fixtures.make_observation()
        additions = _content(workshop=workshop, list_entries=(_entry(),))
        observation = _builder(ScriptedEnricher([additions])).build(
            _screenshot(), request=ObservationRequest.source_screen_retry(SCREEN),
        )
        self.assertIsNotNone(observation.workshop)
        self.assertEqual(observation.workshop.view.frame_ref, FRAME)
        self.assertEqual(observation.workshop.view.source_screen, SCREEN)
        self.assertEqual(observation.workshop.view.source_layout_id, "test-layout")
        # Existing content is preserved alongside the new field.
        self.assertEqual(len(observation.list_entries), 1)
        self.assertEqual(observation.list_entries[0].title_text, "Workshop row")
        self.assertEqual(observation.list_entries[0].frame_ref, FRAME)
        self.assertEqual(observation.screen_type, SCREEN)

    def test_navigation_publishes_workshop_with_bound_provenance(self) -> None:
        """Verifies that navigation publishes workshop with bound provenance."""
        workshop = workshop_fixtures.make_observation()
        builder = _builder(ScriptedEnricher([]))
        navigation = _navigation(builder, ScriptedNavigationGuard(_content(workshop=workshop)))
        observation = navigation.build(_screenshot(), include_content=True)
        self.assertIsNotNone(observation.workshop)
        self.assertEqual(observation.workshop.view.frame_ref, FRAME)
        self.assertEqual(observation.workshop.view.source_screen, SCREEN)
        self.assertEqual(observation.workshop.view.source_layout_id, "test-layout")

    def test_navigation_without_content_leaves_workshop_unset(self) -> None:
        """Verifies that navigation without content leaves workshop unset."""
        workshop = workshop_fixtures.make_observation()
        builder = _builder(ScriptedEnricher([]))
        navigation = _navigation(builder, ScriptedNavigationGuard(_content(workshop=workshop)))
        observation = navigation.build(_screenshot(), include_content=False)
        self.assertIsNone(observation.workshop)
        self.assertEqual(observation.screen_type, SCREEN)

    def test_both_paths_publish_equivalent_workshop_facts(self) -> None:
        """Verifies that both paths publish equivalent workshop facts."""
        workshop = workshop_fixtures.make_observation()
        builder = _builder(ScriptedEnricher([_content(workshop=workshop)]))
        via_builder = builder.build(
            _screenshot(), request=ObservationRequest.source_screen_retry(SCREEN),
        )
        navigation = _navigation(builder, ScriptedNavigationGuard(_content(workshop=workshop)))
        via_navigation = navigation.build(_screenshot(), include_content=True)
        self.assertEqual(via_builder.workshop, via_navigation.workshop)

    def test_additions_merge_preserves_workshop_from_either_side(self) -> None:
        """Verifies that additions merge preserves workshop from either side."""
        workshop = workshop_fixtures.make_observation()
        merged = _merge_observation_additions(
            ObservationAdditions(guard_verdict=GuardVerdict.BLOCKED),
            ObservationAdditions(workshop=workshop),
        )
        self.assertIs(merged.workshop, workshop)
        merged = _merge_observation_additions(
            ObservationAdditions(workshop=workshop),
            ObservationAdditions(workshop=workshop_fixtures.make_observation()),
        )
        self.assertIs(merged.workshop, workshop)

    def test_unresolved_decision_drops_workshop_with_other_content(self) -> None:
        """Verifies that unresolved decision drops workshop with other content."""
        workshop = workshop_fixtures.make_observation()
        additions = _content(workshop=workshop, list_entries=(_entry(),))
        builder = ObservationBuilder(
            selector_registry=build_default_selector_registry(),
            selector_engine=EmptySelectorEngine(),
            screen_classifier=ScreenClassifier(),
            enricher=ScriptedEnricher([additions]),
            visual_recognizer=Mock(recognize=Mock(return_value=VisualRecognition())),
        )
        observation = builder.build(
            _screenshot(), request=ObservationRequest.source_screen_retry(SCREEN),
        )
        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
        self.assertIsNone(observation.workshop)
        self.assertEqual(observation.list_entries, ())

    def test_contradictory_frame_provenance_is_rejected(self) -> None:
        """Verifies that contradictory frame provenance is rejected."""
        workshop = workshop_fixtures.make_observation(frame_ref=OTHER_FRAME)
        additions = _content(workshop=workshop)
        with self.assertRaises(SelectorResolutionError):
            _builder(ScriptedEnricher([additions])).build(
                _screenshot(), request=ObservationRequest.source_screen_retry(SCREEN),
            )

    def test_prebound_workshop_keeps_its_provenance(self) -> None:
        """Verifies that prebound workshop keeps its provenance."""
        workshop = workshop_fixtures.make_observation(frame_ref=FRAME)
        additions = _content(workshop=workshop)
        observation = _builder(ScriptedEnricher([additions])).build(
            _screenshot(), request=ObservationRequest.source_screen_retry(SCREEN),
        )
        self.assertEqual(observation.workshop.view.frame_ref, FRAME)


if __name__ == "__main__":
    unittest.main()
