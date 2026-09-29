"""Shared captured Bag publication fixtures and boundary assertions.

The tab-family and preview suites use these helpers to keep fresh OCR/frame
records per case while avoiding duplicate wiring and provenance assertions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

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
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.observation_builder import ObservationBuilder
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot, FrameRef
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrResult, OcrService
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.paths import TEST_DATA_ROOT
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service
from tests.support.pnc.publication import make_publication_pair

FIXTURES = TEST_DATA_ROOT / "screen_recognition"
_BAG_LAYOUT_ID = "bag"
_ARENA_LAYOUT_ID = "bag_arena_chest_preview"
_COMMON_LAYOUT_ID = "bag_common_victory_preview"

_SPEEDUP_CARDS: tuple[tuple[int, int], ...] = (
    (5, 50), (10, 14), (15, 3), (30, 4), (60, 39), (180, 1),
)
_BONUS_CARDS: tuple[tuple[BagItemApplicability, int, int], ...] = (
    (BagItemApplicability.BUILD, 10, 1),
    (BagItemApplicability.BUILD, 30, 7),
    (BagItemApplicability.RESEARCH, 10, 1),
    (BagItemApplicability.RESEARCH, 30, 3),
    (BagItemApplicability.TRAINING, 10, 1),
    (BagItemApplicability.TRAINING, 30, 5),
)
_TREASURE_CARDS: tuple[tuple[TreasureIdentity, int, bool, RowRecognitionStatus], ...] = (
    (TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST), 8, True, RowRecognitionStatus.COMPLETE),
    (TreasureIdentity(TreasureKind.PINBALL), 2, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 3), 1, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DIAMOND_CHEST), 5800, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DEMON_CHEST, 21), 2, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DEMON_CHEST, 41), 8, True, RowRecognitionStatus.NO_ACTION),
)
_VICTORY_CARDS: tuple[tuple[TreasureIdentity, int, bool, RowRecognitionStatus], ...] = (
    (TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST), 57, True, RowRecognitionStatus.COMPLETE),
    (TreasureIdentity(TreasureKind.RARE_FIRST_VICTORY_CHEST), 4, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.PINBALL), 5, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.STARNA_DICE), 5, False, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.OATH_RUNE_CHEST, 23), 1, True, RowRecognitionStatus.NO_ACTION),
    (TreasureIdentity(TreasureKind.DIAMOND_CHEST), 6900, False, RowRecognitionStatus.NO_ACTION),
)
_ARENA_REWARDS: tuple[tuple[str, int | None, int | None, int | None], ...] = (
    ("30-min Speedup", 1, 5, 4),
    ("30-min Research Speedup", 1, 5, 0),
    ("30-min Heal Speedup", 1, 5, 10),
    ("Elros Frag.", 1, 2, None),
)
_COMMON_REWARDS: tuple[tuple[str, int | None, int | None, int | None], ...] = (
    ("Lost Project Book", 200, 200, 0),
    ("Lost Project Book", 500, 500, 0),
    ("Lost Project Book", 1000, 1000, 0),
    ("MithrilOre", 1000, 1000, None),
)
_MILITARY_CARDS: tuple[tuple[MilitaryItemIdentity, int], ...] = (
    (MilitaryItemIdentity(MilitaryKind.ANTI_SCOUT, 360), 7),
    (MilitaryItemIdentity(MilitaryKind.ANTI_SCOUT, 720), 4),
    (MilitaryItemIdentity(MilitaryKind.TROOP_ATK_BOOST, 720, 20), 6),
    (MilitaryItemIdentity(MilitaryKind.TROOP_DEF_BOOST, 720, 20), 4),
    (MilitaryItemIdentity(MilitaryKind.TROOP_SIZE_BOOST, 120, 25), 5),
    (MilitaryItemIdentity(MilitaryKind.SHIELD_OF_GRACE, 120), 154),
)
_MISC_CARDS: tuple[tuple[MiscItemIdentity, int], ...] = (
    (MiscItemIdentity(MiscKind.SANDSEA_MINING_SHOVEL), 60),
    (MiscItemIdentity(MiscKind.PICKAXE), 15),
    (MiscItemIdentity(MiscKind.LORD_EXP, 500), 2915),
    (MiscItemIdentity(MiscKind.CHALLENGE_KEY), 1),
    (MiscItemIdentity(MiscKind.WISH_CRYSTAL), 20),
    (MiscItemIdentity(MiscKind.BOW_AND_ARROW), 7),
)


@dataclass(slots=True)
class BoundedRapidOcrService:
    """Use shared RapidOCR while rejecting whole-frame reads."""

    delegate: OcrService
    capture_size: tuple[int, int] | None = None
    calls: list[tuple[Bounds | None, tuple[int, int]]] = field(default_factory=list)

    def bind(self, image_size: tuple[int, int]) -> None:
        self.capture_size = image_size
        self.calls.clear()

    def read_result(self, image: Image.Image, region: Bounds | None = None) -> OcrResult:
        self.calls.append((region, image.size))
        whole = None if self.capture_size is None else Bounds(0, 0, *self.capture_size)
        if region == whole or (region is None and self.capture_size == image.size):
            raise AssertionError("Bag content test reached RapidOCR without a strict crop")
        return self.delegate.read_result(image, region)

    def read_lines(self, image: Image.Image, region: Bounds | None = None) -> tuple[OcrLine, ...]:
        return self.read_result(image, region).lines

    def read_text(self, image: Image.Image, region: Bounds) -> str:
        return "\n".join(line.text for line in self.read_result(image, region).lines)


def capture(
    name: str,
    *,
    session_id: str,
    capture_sequence: int = 1,
    reference_size: tuple[int, int] | None = None,
) -> CapturedScreenshot:
    """Load a tracked capture with explicit frame provenance."""

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


def wire(ocr_service: BoundedRapidOcrService) -> tuple[ObservationBuilder, NavigationPerception]:
    """Wire both production publishers over the real recognition stack."""

    registry = build_default_selector_registry()
    matcher = OpenCvTemplateMatcher()
    enricher = PncObservationEnricher(selector_registry=registry)
    return make_publication_pair(
        selector_registry=registry,
        enricher=enricher,
        matcher=matcher,
        ocr_service=ocr_service,
    )


def build_both(
    builder: ObservationBuilder,
    navigation: NavigationPerception,
    backend: BoundedRapidOcrService,
    capture: CapturedScreenshot,
    screen_type: ScreenType,
) -> tuple[Observation, Observation]:
    """Publish one fresh capture through both production paths."""

    backend.bind(capture.image.size)
    return (
        builder.build(
            capture,
            request=ObservationRequest.source_screen_retry(screen_type),
            ocr_context=builder.create_ocr_context(capture),
        ),
        navigation.build(capture, include_content=True),
    )


def compact(text: str | None) -> str:
    return "" if text is None else "".join(text.split())


class BagPublicationAssertions:
    """Assertions shared by tab-family and preview publication suites."""

    def assert_bag_identity(self, observation: Observation, capture: CapturedScreenshot, tab: BagTab) -> None:
        self.assertEqual(ScreenType.PNC_BAG, observation.screen_type)
        self.assertEqual(GuardVerdict.CLEAR, observation.decision.guard)
        self.assertEqual(_BAG_LAYOUT_ID, observation.decision.layout_id)
        self.assertEqual(tab, observation.active_bag_tab)
        self.assertEqual(capture.frame_ref, observation.frame_ref)
        self.assertIsNone(observation.bag_preview)
        self.assertTrue(any(e.screen_type == ScreenType.PNC_BAG for e in observation.decision.evidence))

    def assert_entry_provenance(
        self,
        entry: DetectedListEntry,
        capture: CapturedScreenshot,
        screen: ScreenType,
        layout_id: str,
    ) -> None:
        self.assertEqual(capture.frame_ref, entry.frame_ref)
        self.assertEqual(screen, entry.source_screen)
        self.assertEqual(layout_id, entry.source_layout_id)

    def assert_speedup_row(self, entry: DetectedListEntry, expected_minutes: int, expected_owned: int, capture: CapturedScreenshot) -> None:
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self.assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
        self.assertIsNone(entry.action_point)
        self.assertIsNone(entry.action_bounds)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(BagTab.SPEEDUP, facts.selected_tab)
        self.assertEqual(TimeReductionIdentity(BagItemApplicability.GENERAL, expected_minutes), facts.identity)
        self.assertEqual(expected_owned, facts.owned_count)
        self.assertFalse(facts.inspection_glyph_present)
        self.assertEqual(f"time_reduction:general:{expected_minutes}", entry.metadata.get("identity"))

    def assert_bonus_row(self, entry: DetectedListEntry, expected: tuple[BagItemApplicability, int, int], capture: CapturedScreenshot) -> None:
        applicability, percent, owned = expected
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self.assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
        self.assertEqual(RowRecognitionStatus.NO_ACTION, entry.row_status)
        self.assertIsNone(entry.action_point)
        facts = entry.bag_item_facts
        self.assertIsNotNone(facts)
        assert facts is not None
        self.assertEqual(SpeedBonusIdentity(applicability, percent, 60), facts.identity)
        self.assertEqual(owned, facts.owned_count)
        self.assertFalse(facts.inspection_glyph_present)
        self.assertEqual(f"speed_bonus:{applicability.value}:{percent}:60", entry.metadata.get("identity"))

    def assert_treasure_row(self, entry: DetectedListEntry, expected: tuple[TreasureIdentity, int, bool, RowRecognitionStatus], capture: CapturedScreenshot) -> None:
        identity, owned, glyph, status = expected
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self.assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
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

    def assert_typed_row(self, entry: DetectedListEntry, *, tab: BagTab, identity: MilitaryItemIdentity | MiscItemIdentity, expected_owned: int | None, capture: CapturedScreenshot) -> None:
        self.assertEqual(ListEntryKind.BAG_ITEM, entry.kind)
        self.assert_entry_provenance(entry, capture, ScreenType.PNC_BAG, _BAG_LAYOUT_ID)
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

    def assert_preview(self, observation: Observation, capture: CapturedScreenshot, layout_id: str, identity: TreasureIdentity, expected_rows: tuple[tuple[str, int | None, int | None, int | None], ...]) -> None:
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
        self.assertEqual(len(expected_rows), len(observation.list_entries))
        for index, (entry, (name, qmin, qmax, owned)) in enumerate(zip(observation.list_entries, expected_rows, strict=True)):
            self.assertEqual(ListEntryKind.BAG_PREVIEW_REWARD, entry.kind)
            self.assert_entry_provenance(entry, capture, ScreenType.PNC_BAG_CHEST_PREVIEW, layout_id)
            self.assertEqual(RowRecognitionStatus.CLIPPED if index == 3 else RowRecognitionStatus.NO_ACTION, entry.row_status)
            self.assertIsNone(entry.action_point)
            self.assertIsNone(entry.action_bounds)
            facts = entry.bag_reward_facts
            self.assertIsNotNone(facts)
            assert facts is not None
            self.assertIsInstance(facts, BagPreviewRewardFacts)
            self.assertEqual(compact(name), compact(facts.reward_name_text))
            self.assertEqual(qmin, facts.quantity_min)
            self.assertEqual(qmax, facts.quantity_max)
            self.assertEqual(owned, facts.displayed_owned_count)


__all__ = [
    "BagPublicationAssertions",
    "BoundedRapidOcrService",
    "_ARENA_LAYOUT_ID",
    "_ARENA_REWARDS",
    "_BAG_LAYOUT_ID",
    "_BONUS_CARDS",
    "_COMMON_LAYOUT_ID",
    "_COMMON_REWARDS",
    "_MILITARY_CARDS",
    "_MISC_CARDS",
    "_SPEEDUP_CARDS",
    "_TREASURE_CARDS",
    "_VICTORY_CARDS",
    "build_both",
    "capture",
    "compact",
    "wire",
]
