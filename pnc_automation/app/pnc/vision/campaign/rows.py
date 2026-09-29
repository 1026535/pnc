"""Typed Campaign row construction shared by map and path readers."""

from __future__ import annotations

from pnc_automation.app.pnc.domain.campaign import CampaignNodeFacts
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.core.vision.image.models import Bounds


def _node_entry(
    *,
    kind: ListEntryKind,
    bounds: Bounds,
    campaign_node: CampaignNodeFacts,
    row_status: RowRecognitionStatus,
    title_text: str | None = None,
    metadata: dict[str, int] | None = None,
    action_bounds: Bounds | None = None,
    action_point: tuple[int, int] | None = None,
) -> DetectedListEntry:
    """Build one typed Campaign row without inferring absent facts."""

    return DetectedListEntry(
        kind=kind,
        bounds=bounds,
        title_text=title_text,
        badge_present=campaign_node.locked is False,
        campaign_node=campaign_node,
        metadata={} if metadata is None else metadata,
        row_status=row_status,
        action_bounds=action_bounds,
        action_point=action_point,
    )
