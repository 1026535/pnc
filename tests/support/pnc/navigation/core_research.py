"""Shared core research doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.domain.policy_models import ResearchCategory
from pnc_automation.app.pnc.domain.research import (
    ResearchDetail,
    ResearchNodeFacts,
    ResearchNodeId,
    research_node_title,
)
from pnc_automation.app.pnc.domain.screen_decision import (
    GuardVerdict,
    ScreenDecision,
    ScreenEvidence,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


def research_entry(
    node_id: ResearchNodeId,
    *,
    status: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
    category: ResearchCategory = ResearchCategory.DEVELOPMENT,
) -> DetectedListEntry:
    """Build one typed Development research row with measured tile geometry."""

    action_bounds = Bounds(140, 210, 80, 80)
    complete = status == RowRecognitionStatus.COMPLETE
    return DetectedListEntry(
        kind=ListEntryKind.RESEARCH,
        bounds=Bounds(100, 200, 180, 120),
        title_text=research_node_title(node_id),
        action_point=action_bounds.center() if complete else None,
        action_bounds=action_bounds if complete else None,
        metadata={"category": category.value},
        row_status=status,
        research_facts=ResearchNodeFacts(category=category, node_id=node_id),
    )


def research_tree_frame(
    entries: tuple[DetectedListEntry, ...] = (),
    *,
    proved: bool = True,
    captured_at: datetime | None = None,
    blocked: bool = False,
    category: ResearchCategory = ResearchCategory.DEVELOPMENT,
) -> Observation:
    """Build one Development tree frame with reviewed visual-anchor proof."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_RESEARCH_TREE,
            effective_screen=ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
            evidence=(
                (ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, f"visual_anchor:research_tree_{category.value}"),)
                if proved
                else ()
            ),
        ),
        list_entries=entries,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def research_detail_frame(
    node_id: ResearchNodeId | None,
    *,
    category: ResearchCategory | None = None,
    active: bool = False,
    max_level: bool = False,
    start: bool = True,
    captured_at: datetime | None = None,
    blocked: bool = False,
) -> Observation:
    """Build one typed node-detail frame with its measured anchor evidence."""

    anchor = (
        "visual_anchor:research_tree_node_detail_max"
        if max_level
        else "visual_anchor:research_tree_node_detail_active"
        if active
        else "visual_anchor:research_tree_node_detail"
    )
    visible_elements = {}
    if start:
        visible_elements[UiElementId.PNC_RESEARCH_START_BUTTON] = VisibleElement(
            UiElementId.PNC_RESEARCH_START_BUTTON,
            Bounds(304, 447, 135, 49),
            1.0,
            source_kind=VisibleElementSourceKind.TEMPLATE,
        )
    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_RESEARCH_TREE,
            effective_screen=ScreenType.PNC_RESEARCH_TREE,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
            evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, anchor),),
        ),
        visible_elements=visible_elements,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
        research_detail=ResearchDetail(node_id=node_id, category=category),
    )
