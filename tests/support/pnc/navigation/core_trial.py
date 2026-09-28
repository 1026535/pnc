"""Shared core trial doubles and fixtures."""

from datetime import UTC, datetime

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
from pnc_automation.app.pnc.domain.trial_challenge import (
    TrialApplicableStatsDetail,
    TrialCardFacts,
    TrialCategory,
    trial_category_title,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType


def trial_card_entry(
    category: TrialCategory = TrialCategory.GEAR,
    *,
    status: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
) -> DetectedListEntry:
    """Build one typed Trial category card with measured Stats chip geometry."""

    action_bounds = Bounds(215, 628, 45, 44)
    complete = status == RowRecognitionStatus.COMPLETE
    return DetectedListEntry(
        kind=ListEntryKind.TRIAL_CATEGORY,
        bounds=Bounds(14, 562, 511, 124),
        title_text=trial_category_title(category),
        action_point=action_bounds.center() if complete else None,
        action_bounds=action_bounds if complete else None,
        metadata={"category": category.value},
        row_status=status,
        trial_card_facts=TrialCardFacts(category=category),
    )


def trial_list_frame(
    entries: tuple[DetectedListEntry, ...] = (),
    *,
    proved: bool = True,
    captured_at: datetime | None = None,
    blocked: bool = False,
) -> Observation:
    """Build one Trial Challenge list frame with reviewed visual-anchor proof."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_TRIAL_CHALLENGE,
            effective_screen=ScreenType.PNC_TRIAL_CHALLENGE,
            guard=GuardVerdict.BLOCKED if blocked else GuardVerdict.CLEAR,
            evidence=(
                (ScreenEvidence(ScreenType.PNC_TRIAL_CHALLENGE, "visual_anchor:trial_challenge_live"),)
                if proved
                else ()
            ),
        ),
        list_entries=entries,
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def trial_stats_detail_frame(
    category: TrialCategory | None = TrialCategory.GEAR,
    *,
    proved: bool = True,
    captured_at: datetime | None = None,
) -> Observation:
    """Build one Applicable Stats detail frame with its typed footer fact."""

    return Observation(
        decision=ScreenDecision(
            base_screen=ScreenType.PNC_TRIAL_APPLICABLE_STATS,
            effective_screen=ScreenType.PNC_TRIAL_APPLICABLE_STATS,
            guard=GuardVerdict.CLEAR,
            evidence=(
                (ScreenEvidence(ScreenType.PNC_TRIAL_APPLICABLE_STATS, "visual_anchor:trial_gear_applicable_stats"),)
                if proved
                else ()
            ),
        ),
        image_size=(540, 960),
        captured_at=captured_at or datetime.now(UTC),
        trial_stats_detail=TrialApplicableStatsDetail(category=category),
    )
