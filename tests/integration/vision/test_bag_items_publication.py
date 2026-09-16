"""Captured Bag item and chest-preview publication through both production observers.

Qualifies the V10/V11 shared path on the ``bag`` layout (Speedup and Treasure
tabs) and the qualified ``bag_arena_chest_preview``/``bag_common_victory_preview``
layouts: real selector registry, packaged visual recognizer, production
enricher, and the real RapidOCR backend. ``ObservationBuilder`` and
``NavigationPerception`` must agree on typed rows, canonical identities, the
read-only magnifier actions, independently parsed preview source identities,
and frame/layout provenance on every published fact.

Fixture provenance (``tests/data/screen_recognition/manifest.json`` and
``manual_annotations.json``):
``bag_speedup_tab.png``/``bag_treasure_tab.png`` are native 900x1600 captures
from the 2026-09-15 live tour; ``bag_speedup_bonus_tab.png`` and
``bag_treasure_victory_tab.png`` are independent mega_old_acc captures from
the accepted V09 live run 20260916T055657Z_a7e1320c;
``bag_arena_chest_preview.png`` is the 540x960 reference copy of the tour-24
capture; ``bag_common_victory_preview_20260916.png`` is the lead-qualified
native 900x1600 Common preview (frame 0031, run 20260916T110400Z_1483bb20);
``bag_military_tab.png``/``bag_misc_tab.png`` are native 900x1600 mega_old_acc
captures from the lead-qualified non-spending V12 run 20260916T130610Z_4b194a06
(frames 0032/0037, same capture group). The 540x960 passes are same-capture
reference-size resizes, not independent evidence.
"""

from __future__ import annotations

import hashlib
import unittest
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagItemApplicability,
    BagPreviewRewardFacts,
    MilitaryItemIdentity,
    MilitaryKind,
    MiscItemIdentity,
    MiscKind,
    SpeedBonusIdentity,
    TimeReductionIdentity,
    TreasureIdentity,
    TreasureKind,
    bag_item_identity_key,
)
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
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
    OcrLine,
    OcrResult,
    RapidOcrService,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


FIXTURES = TEST_DATA_ROOT / "screen_recognition"

_BAG_LAYOUT_ID = "bag"
_ARENA_LAYOUT_ID = "bag_arena_chest_preview"
_COMMON_LAYOUT_ID = "bag_common_victory_preview"

# Reviewed card facts of the tour Speedup-tab capture (flat time reductions).
_SPEEDUP_CARDS: tuple[tuple[int, int], ...] = (
    (5, 50), (10, 14), (15, 3), (30, 4), (60, 39), (180, 1),
)

# Reviewed facts of the independent percentage-bonus Speedup capture:
# (applicability, percent, owned) for each of the six cards in order.
_BONUS_CARDS: tuple[tuple[BagItemApplicability, int, int], ...] = (
    (BagItemApplicability.BUILD, 10, 1),
    (BagItemApplicability.BUILD, 30, 7),
    (BagItemApplicability.RESEARCH, 10, 1),
    (BagItemApplicability.RESEARCH, 30, 3),
    (BagItemApplicability.TRAINING, 10, 1),
    (BagItemApplicability.TRAINING, 30, 5),
)

# Reviewed facts of the tour Treasure-tab capture:
# (identity, owned, magnifier, qualified-action status).
_TREASURE_CARDS: tuple[tuple[TreasureIdentity, int, bool, RowRecognitionStatus], ...] = (
    (TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST), 8, True, RowRecognitionStatus.COMPLETE),
    (TreasureIdentity(TreasureKind.PINBALL), 2, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 3), 1, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DIAMOND_CHEST), 5800, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DEMON_CHEST, 21), 2, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DEMON_CHEST, 41), 8, True, RowRecognitionStatus.NO_ACTION),
)

# Reviewed facts of the independent Victory Treasure-tab capture.
_VICTORY_CARDS: tuple[tuple[TreasureIdentity, int, bool, RowRecognitionStatus], ...] = (
    (TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST), 57, True, RowRecognitionStatus.COMPLETE),
    (TreasureIdentity(TreasureKind.RARE_FIRST_VICTORY_CHEST), 4, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.PINBALL), 5, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.STARNA_DICE), 5, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 23), 1, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DIAMOND_CHEST), 6900, False, RowRecognitionStatus.NO_ACTION),
)

# Reviewed reward rows of the Arena reference preview (Owned on row 4 is absent).
_ARENA_REWARDS: tuple[tuple[str, int | None, int | None, int | None], ...] = (
    ("30-min Speedup", 1, 5, 4),
    ("30-min Research Speedup", 1, 5, 0),
    ("30-min Heal Speedup", 1, 5, 10),
    ("Elros Frag.", 1, 2, None),
)

# Reviewed reward rows of the lead-qualified native Common preview. The three
# Lost Project Book offers are distinct displayed rows and must never merge;
# the clipped Mithril Ore row keeps its Owned count unknown.
_COMMON_REWARDS: tuple[tuple[str, int | None, int | None, int | None], ...] = (
    ("Lost Project Book", 200, 200, 0),
    ("Lost Project Book", 500, 500, 0),
    ("Lost Project Book", 1000, 1000, 0),
    ("MithrilOre", 1000, 1000, None),
)

# Reviewed facts of the V12 Military-tab capture (same-capture group as Misc,
# run 20260916T130610Z_4b194a06, frame 0032). Same-art Anti-Scout variants are
# distinguished by duration; boost variants carry percent plus duration.
_MILITARY_CARDS: tuple[tuple[MilitaryItemIdentity, int], ...] = (
    (MilitaryItemIdentity(MilitaryKind.ANTI_SCOUT, 360), 7),
    (MilitaryItemIdentity(MilitaryKind.ANTI_SCOUT, 720), 4),
    (MilitaryItemIdentity(MilitaryKind.TROOP_ATK_BOOST, 720, 20), 6),
    (MilitaryItemIdentity(MilitaryKind.TROOP_DEF_BOOST, 720, 20), 4),
    (MilitaryItemIdentity(MilitaryKind.TROOP_SIZE_BOOST, 120, 25), 5),
    (MilitaryItemIdentity(MilitaryKind.SHIELD_OF_GRACE, 120), 154),
)

# Reviewed facts of the V12 Misc-tab capture (frame 0037). The 500 Lord EXP
# amount is the displayed denomination, never the 2,915 owned count. At the
# 540x960 reference size that clipped Owned label is unreadable and stays
# unknown; every identity still resolves.
_MISC_CARDS: tuple[tuple[MiscItemIdentity, int], ...] = (
    (MiscItemIdentity(MiscKind.SANDSEA_MINING_SHOVEL), 60),
    (MiscItemIdentity(MiscKind.PICKAXE), 15),
    (MiscItemIdentity(MiscKind.LORD_EXP, 500), 2915),
    (MiscItemIdentity(MiscKind.CHALLENGE_KEY), 1),
    (MiscItemIdentity(MiscKind.WISH_CRYSTAL), 20),
    (MiscItemIdentity(MiscKind.BOW_AND_ARROW), 7),
)


@dataclass(slots=True)
class _BoundedRapidOcrService:
    """Use shared RapidOCR while recording calls and rejecting whole-frame reads."""

    delegate: RapidOcrService
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
            raise AssertionError("Bag content test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def _capture(
    name: str,
    *,
    session_id: str,
    capture_sequence: int = 1,
    reference_size: tuple[int, int] | None = None,
) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance and no payload shortcut.

    ``reference_size`` performs a same-capture resize only; it is never
    independent validation evidence.
    """

    with Image.open(FIXTURES / name) as source:
        image = source.convert("RGB")
    if reference_size is not None:
        image = image.resize(reference_size)
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


def _compact(text: str | None) -> str:
    return "" if text is None else "".join(text.split())


class BagItemsPublicationTests(unittest.TestCase):
    """Replayed Bag captures qualify the shared observation contract on both paths."""

    def _assert_bag_identity(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        tab: BagTab,
    ) -> None:
        """Require independent Bag identity, a clear decision, and the typed tab."""

        self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(tab, observation.active_bag_tab)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertIsNone(observation.bag_preview)
        self.assertTrue(
            any(
                evidence.screen_type == ScreenType.PNC_BAG
                for evidence in observation.decision.evidence
            ),
            "independent visual anchor evidence must own the bag layout",
        )

    def _assert_entry_provenance(
        self,
        entry: DetectedListEntry,
        capture: CapturedScreenshot,
        screen: ScreenType,
        layout_id: str,
    ) -> None:
        self.assertEqual(capture.frame_ref, entry.frame_ref)
        self.assertEqual(screen, entry.source_screen)
        self.assertEqual(layout_id, entry.source_layout_id)

    def _assert_speedup_row(
        self,
        entry: DetectedListEntry,
        expected_minutes: int,
        expected_owned: int,
        capture: CapturedScreenshot,
    ) -> None:
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self._assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
        self.assertIsNone(entry.action_point)
        self.assertIsNone(entry.action_bounds)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(BagTab.SPEEDUP, facts.selected_tab)
        self.assertEqual(
            TimeReductionIdentity(BagItemApplicability.GENERAL, expected_minutes),
            facts.identity,
        )
        self.assertEqual(expected_owned, facts.owned_count)
        self.assertFalse(facts.inspection_glyph_present)
        self.assertEqual(
            f"time_reduction:general:{expected_minutes}",
            entry.metadata.get("identity"),
        )

    def _assert_bonus_row(
        self,
        entry: DetectedListEntry,
        expected: tuple[BagItemApplicability, int, int],
        capture: CapturedScreenshot,
    ) -> None:
        applicability, percent, owned = expected
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self._assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
        self.assertIsNone(entry.action_point)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(
            SpeedBonusIdentity(applicability, percent, 60),
            facts.identity,
        )
        self.assertEqual(owned, facts.owned_count)
        self.assertFalse(facts.inspection_glyph_present)
        self.assertEqual(
            f"speed_bonus:{applicability.value}:{percent}:60",
            entry.metadata.get("identity"),
        )

    def _assert_treasure_row(
        self,
        entry: DetectedListEntry,
        expected: tuple[TreasureIdentity, int, bool, RowRecognitionStatus],
        capture: CapturedScreenshot,
    ) -> None:
        identity, owned, glyph, status = expected
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self._assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(status, entry.row_status)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(BagTab.TREASURE, facts.selected_tab)
        self.assertEqual(identity, facts.identity)
        self.assertEqual(owned, facts.owned_count)
        self.assertEqual(glyph, facts.inspection_glyph_present)
        self.assertEqual(bag_item_identity_key(identity), entry.metadata.get("identity"))
        if status == RowRecognitionStatus.COMPLETE:
            self.assertIsNotNone(entry.action_bounds)
            self.assertIsNotNone(entry.action_point)
            assert entry.action_bounds is not None and entry.action_point is not None
            self.assertTrue(entry.bounds.contains_bounds(entry.action_bounds))
            self.assertTrue(entry.action_bounds.contains_point(entry.action_point))
        else:
            self.assertIsNone(entry.action_point)
            self.assertIsNone(entry.action_bounds)

    def _assert_typed_row(
        self,
        entry: DetectedListEntry,
        *,
        tab: BagTab,
        identity: MilitaryItemIdentity | MiscItemIdentity,
        expected_owned: int | None,
        capture: CapturedScreenshot,
    ) -> None:
        """Require a resolved observation-only row on the measured tab."""

        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self._assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
        self.assertIsNone(entry.action_point)
        self.assertIsNone(entry.action_bounds)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(tab, facts.selected_tab)
        self.assertEqual(identity, facts.identity)
        self.assertEqual(expected_owned, facts.owned_count)
        self.assertFalse(facts.inspection_glyph_present)
        self.assertEqual(bag_item_identity_key(identity), entry.metadata.get("identity"))

    def test_speedup_capture_publishes_flat_time_reductions_on_both_paths(self):
        """The tour Speedup tab yields six typed observation-only rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("bag_variants/bag_speedup_tab.png", session_id="v10-speedup")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_BAG
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity(observation, capture, BagTab.SPEEDUP)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, (minutes, owned) in zip(entries, _SPEEDUP_CARDS, strict=True):
                    self._assert_speedup_row(entry, minutes, owned, capture)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_bonus_capture_publishes_percentage_bonuses_on_both_paths(self):
        """The independent bonus tab yields six typed percentage-bonus rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "bag_variants/bag_speedup_bonus_tab.png", session_id="v10-speedup-bonus"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_BAG
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity(observation, capture, BagTab.SPEEDUP)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _BONUS_CARDS, strict=True):
                    self._assert_bonus_row(entry, expected, capture)
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_treasure_capture_publishes_typed_identities_on_both_paths(self):
        """The tour Treasure tab resolves every identity; only Arena is actionable."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture("bag_variants/bag_treasure_tab.png", session_id="v11-treasure")

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_BAG
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity(observation, capture, BagTab.TREASURE)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _TREASURE_CARDS, strict=True):
                    self._assert_treasure_row(entry, expected, capture)
                actionable = [
                    entry for entry in entries
                    if entry.row_status == RowRecognitionStatus.COMPLETE
                ]
                self.assertEqual(1, len(actionable))
                self.assertEqual(
                    "treasure:arena_surprise_chest",
                    actionable[0].metadata.get("identity"),
                )
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_victory_capture_publishes_common_as_the_qualified_target(self):
        """The independent Victory tab resolves Common as the only actionable row."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "bag_variants/bag_treasure_victory_tab.png", session_id="v11-victory"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_BAG
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_bag_identity(observation, capture, BagTab.TREASURE)
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry, expected in zip(entries, _VICTORY_CARDS, strict=True):
                    self._assert_treasure_row(entry, expected, capture)
                actionable = [
                    entry for entry in entries
                    if entry.row_status == RowRecognitionStatus.COMPLETE
                ]
                self.assertEqual(1, len(actionable))
                self.assertEqual(
                    "treasure:common_first_victory_chest",
                    actionable[0].metadata.get("identity"),
                )
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)

    def test_military_capture_publishes_typed_rows_on_both_paths(self):
        """The V12 Military tab resolves six observation-only typed rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        # Native 900x1600 plus a same-capture reference-size resize (the resize
        # is not independent evidence).
        for reference_size in (None, (540, 960)):
            capture = _capture(
                "bag_variants/bag_military_tab.png",
                session_id=f"v12-military:{reference_size}",
                reference_size=reference_size,
            )
            builder_observation, navigation_observation = _build_both(
                builder, navigation, backend, capture, ScreenType.PNC_BAG
            )
            for name, observation in (
                ("observation_builder", builder_observation),
                ("navigation_perception", navigation_observation),
            ):
                with self.subTest(publisher=name, reference_size=reference_size):
                    self._assert_bag_identity(observation, capture, BagTab.MILITARY)
                    entries = observation.entries(ListEntryKind.BAG_ITEM)
                    self.assertEqual(6, len(entries))
                    for entry, (identity, owned) in zip(
                        entries, _MILITARY_CARDS, strict=True
                    ):
                        self._assert_typed_row(
                            entry, tab=BagTab.MILITARY, identity=identity,
                            expected_owned=owned, capture=capture,
                        )
                    # The Misc unselected-label template publishes the measured
                    # control that select_bag_tab(BagTab.MISC) requires; the
                    # selected tab itself has none (same-tab short-circuit).
                    misc_control = observation.visible_elements.get(
                        UiElementId.PNC_BAG_SUBTAB_MISC
                    )
                    self.assertIsNotNone(misc_control)
                    assert misc_control is not None
                    self.assertEqual(
                        VisibleElementSourceKind.TEMPLATE, misc_control.source_kind
                    )
                    self.assertIsNone(
                        observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MILITARY)
                    )
            self.assertEqual(
                builder_observation.list_entries, navigation_observation.list_entries
            )

    def test_misc_capture_publishes_typed_rows_on_both_paths(self):
        """The V12 Misc tab resolves six observation-only typed rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        for reference_size in (None, (540, 960)):
            capture = _capture(
                "bag_variants/bag_misc_tab.png",
                session_id=f"v12-misc:{reference_size}",
                reference_size=reference_size,
            )
            builder_observation, navigation_observation = _build_both(
                builder, navigation, backend, capture, ScreenType.PNC_BAG
            )
            for name, observation in (
                ("observation_builder", builder_observation),
                ("navigation_perception", navigation_observation),
            ):
                with self.subTest(publisher=name, reference_size=reference_size):
                    self._assert_bag_identity(observation, capture, BagTab.MISC)
                    entries = observation.entries(ListEntryKind.BAG_ITEM)
                    self.assertEqual(6, len(entries))
                    for index, (entry, (identity, owned)) in enumerate(
                        zip(entries, _MISC_CARDS, strict=True)
                    ):
                        self._assert_typed_row(
                            entry, tab=BagTab.MISC, identity=identity,
                            expected_owned=owned, capture=capture,
                        )
                    military_control = observation.visible_elements.get(
                        UiElementId.PNC_BAG_SUBTAB_MILITARY
                    )
                    self.assertIsNotNone(military_control)
                    assert military_control is not None
                    self.assertEqual(
                        VisibleElementSourceKind.TEMPLATE, military_control.source_kind
                    )
                    self.assertIsNone(
                        observation.visible_elements.get(UiElementId.PNC_BAG_SUBTAB_MISC)
                    )
            self.assertEqual(
                builder_observation.list_entries, navigation_observation.list_entries
            )

    def test_tab_switch_publishes_only_current_family_rows(self):
        """Switching Military -> Misc clears the prior family through both paths."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        military_capture = _capture(
            "bag_variants/bag_military_tab.png", session_id="v12-switch:military"
        )
        misc_capture = _capture(
            "bag_variants/bag_misc_tab.png", session_id="v12-switch:misc"
        )
        _build_both(builder, navigation, backend, military_capture, ScreenType.PNC_BAG)
        misc_builder, misc_navigation = _build_both(
            builder, navigation, backend, misc_capture, ScreenType.PNC_BAG
        )

        for name, observation in (
            ("observation_builder", misc_builder),
            ("navigation_perception", misc_navigation),
        ):
            with self.subTest(publisher=name):
                entries = observation.entries(ListEntryKind.BAG_ITEM)
                self.assertEqual(6, len(entries))
                for entry in entries:
                    facts = entry.bag_item_facts
                    self.assertIsNotNone(facts)
                    assert facts is not None
                    self.assertEqual(BagTab.MISC, facts.selected_tab)
                    self.assertIsInstance(facts.identity, MiscItemIdentity)
                    self.assertNotIn(
                        "military:", entry.metadata.get("identity") or ""
                    )

    def _assert_preview(
        self,
        observation: Observation,
        capture: CapturedScreenshot,
        layout_id: str,
        identity: TreasureIdentity,
        expected_rows: tuple[tuple[str, int | None, int | None, int | None], ...],
    ) -> None:
        """Require the qualified preview layout, rows, and parsed source identity."""

        self.assertEqual(ScreenType.PNC_BAG_CHEST_PREVIEW, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(layout_id, observation.decision.layout_id)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertIsNone(observation.active_bag_tab)
        close = observation.require(UiElementId.PNC_BAG_CHEST_PREVIEW_CLOSE)
        self.assertEqual(capture.frame_ref, close.frame_ref)

        preview = observation.bag_preview
        self.assertIsNotNone(preview)
        assert preview is not None
        self.assertEqual(identity, preview.source_identity)
        self.assertEqual(capture.frame_ref, preview.frame_ref)
        self.assertEqual(ScreenType.PNC_BAG_CHEST_PREVIEW, preview.source_screen)
        self.assertEqual(layout_id, preview.source_layout_id)

        entries = observation.list_entries
        self.assertEqual(len(expected_rows), len(entries))
        for index, (entry, (name, qmin, qmax, owned)) in enumerate(
            zip(entries, expected_rows, strict=True)
        ):
            self.assertEqual(ListEntryKind.BAG_PREVIEW_REWARD, entry.kind)
            self._assert_entry_provenance(
                entry, capture, ScreenType.PNC_BAG_CHEST_PREVIEW, layout_id
            )
            self.assertEqual(
                RowRecognitionStatus.CLIPPED if index == 3 else RowRecognitionStatus.NO_ACTION,
                entry.row_status,
            )
            self.assertIsNone(entry.action_point)
            self.assertIsNone(entry.action_bounds)
            facts = entry.bag_reward_facts
            self.assertIsNotNone(facts)
            assert facts is not None
            self.assertIsInstance(facts, BagPreviewRewardFacts)
            self.assertEqual(_compact(name), _compact(facts.reward_name_text))
            self.assertEqual(qmin, facts.quantity_min)
            self.assertEqual(qmax, facts.quantity_max)
            self.assertEqual(owned, facts.displayed_owned_count)

    def test_arena_preview_publishes_rewards_on_both_paths(self):
        """Reference and independent native previews yield the same owned rows."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        for fixture in (
            "bag_arena_chest_preview.png",
            "bag_arena_chest_preview_holdout_20260915.png",
        ):
            capture = _capture(fixture, session_id=f"v11-arena:{fixture}")
            builder_observation, navigation_observation = _build_both(
                builder, navigation, backend, capture, ScreenType.PNC_BAG_CHEST_PREVIEW
            )
            for name, observation in (
                ("observation_builder", builder_observation),
                ("navigation_perception", navigation_observation),
            ):
                with self.subTest(fixture=fixture, publisher=name):
                    self._assert_preview(
                        observation, capture, _ARENA_LAYOUT_ID,
                        TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST), _ARENA_REWARDS,
                    )
            self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
            self.assertEqual(builder_observation.bag_preview, navigation_observation.bag_preview)

    def test_common_preview_publishes_duplicate_rows_on_both_paths(self):
        """The native Common preview keeps three distinct Lost Project Book offers."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)
        capture = _capture(
            "bag_common_victory_preview_20260916.png", session_id="v11-common-preview"
        )

        builder_observation, navigation_observation = _build_both(
            builder, navigation, backend, capture, ScreenType.PNC_BAG_CHEST_PREVIEW
        )

        for name, observation in (
            ("observation_builder", builder_observation),
            ("navigation_perception", navigation_observation),
        ):
            with self.subTest(publisher=name):
                self._assert_preview(
                    observation,
                    capture,
                    _COMMON_LAYOUT_ID,
                    TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST),
                    _COMMON_REWARDS,
                )
                names = [
                    entry.bag_reward_facts.reward_name_text
                    for entry in observation.list_entries
                    if entry.bag_reward_facts is not None
                ]
                # Duplicate displayed names are legitimate separate offers.
                self.assertEqual(3, names.count("Lost Project Book"))
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
        self.assertEqual(builder_observation.bag_preview, navigation_observation.bag_preview)

    def test_bag_frames_publish_no_preview_and_previews_publish_no_bag_items(self):
        """Typed content never leaks across the Bag/preview screen boundary."""

        backend = _BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = _wire(backend)

        bag_capture = _capture("bag_variants/bag_treasure_tab.png", session_id="v11-boundary-bag")
        bag_observation = builder.build(
            bag_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            ocr_context=builder.create_ocr_context(bag_capture),
        )
        self.assertIsNone(bag_observation.bag_preview)
        self.assertEqual(
            (), bag_observation.entries(ListEntryKind.BAG_PREVIEW_REWARD)
        )

        backend.bind(bag_capture.image.size)
        preview_capture = _capture(
            "bag_arena_chest_preview.png", session_id="v11-boundary-preview"
        )
        preview_observation = navigation.build(preview_capture, include_content=True)
        self.assertEqual(
            (), preview_observation.entries(ListEntryKind.BAG_ITEM)
        )
        self.assertIsNotNone(preview_observation.bag_preview)


if __name__ == "__main__":
    unittest.main()
