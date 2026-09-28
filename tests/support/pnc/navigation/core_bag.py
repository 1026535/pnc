"""Shared core bag doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.bag import BagTab
from pnc_automation.app.pnc.domain.bag_items import (
    BagChestPreviewFacts,
    BagItemFacts,
    TreasureIdentity,
    TreasureKind,
    bag_item_identity_key,
    treasure_identity_title,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.domain.screen_decision import (
    GuardVerdict,
    ScreenDecision,
    ScreenEvidence,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


def bag_item_entry(
    identity: TreasureIdentity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
    *,
    status: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
    title: str | None = None,
) -> DetectedListEntry:
    """Build one typed Treasure card row with measured magnifier geometry."""

    action_bounds = Bounds(150, 290, 50, 45)
    complete = status == RowRecognitionStatus.COMPLETE
    return DetectedListEntry(
        kind=ListEntryKind.BAG_ITEM,
        bounds=Bounds(9, 286, 882, 202),
        title_text=title if title is not None else treasure_identity_title(identity),
        action_point=action_bounds.center() if complete else None,
        action_bounds=action_bounds if complete else None,
        metadata={"identity": bag_item_identity_key(identity)},
        row_status=status,
        bag_item_facts=BagItemFacts(
            selected_tab=BagTab.TREASURE,
            identity=identity,
            owned_count=5,
            inspection_glyph_present=True,
        ),
    )


def bag_treasure_frame(
    entries: tuple[DetectedListEntry, ...] = (),
    *,
    layout_id: str | None = "bag",
    tab: BagTab | None = BagTab.TREASURE,
    captured_at: datetime | None = None,
    blocked: bool = False,
) -> Observation:
    """Build one Bag Treasure-tab frame with the reviewed bag layout id."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_BAG,
            effective_screen=ScreenType.PNC_BAG,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
            layout_id=layout_id,
            evidence=(
                (ScreenEvidence(ScreenType.PNC_BAG, "visual_anchor:bag_treasure_tab", layout_id="bag"),)
                if layout_id == "bag"
                else ()
            ),
        ),
        list_entries=entries,
        active_bag_tab=tab,
        image_size=(900, 1600),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def bag_preview_frame(
    identity: TreasureIdentity = TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
    *,
    layout_id: str = "bag_arena_chest_preview",
    proved: bool = True,
    captured_at: datetime | None = None,
) -> Observation:
    """Build one chest preview frame with independently read title identity."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_BAG_CHEST_PREVIEW,
            effective_screen=ScreenType.PNC_BAG_CHEST_PREVIEW,
            guard=GuardVerdict.CLEAR,
            layout_id=layout_id,
            evidence=(
                (
                    ScreenEvidence(
                        ScreenType.PNC_BAG_CHEST_PREVIEW,
                        f"visual_anchor:{layout_id}",
                        layout_id=layout_id,
                    ),
                )
                if proved
                else ()
            ),
        ),
        image_size=(900, 1600),
        captured_at=captured_at or datetime.now(UTC),
        bag_preview=BagChestPreviewFacts(
            source_identity=identity,
            title_text=treasure_identity_title(identity) if identity is not None else None,
        ),
    )
