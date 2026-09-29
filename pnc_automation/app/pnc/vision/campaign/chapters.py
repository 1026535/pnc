"""Campaign chapter path node reader."""

from __future__ import annotations

from PIL import Image
import numpy as np

from pnc_automation.app.pnc.domain.campaign import CampaignChapterIdentity, CampaignNodeFacts
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.vision.campaign_ocr_regions import CAMPAIGN_REFERENCE_SIZE, scale_campaign_bounds
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import PreparedFrame

from .constants import _PATH_HOUGH, _CircleCandidate
from .geometry import _circle_candidates, _clip_bounds, _deduplicate_marked, _disc_bounds, _edge_clipped, _is_badge_core, _is_lock_core, _node_features
from .ocr import _chapter_identity, _read_disc_number
from .rows import _node_entry

def _chapter_rows(
    *,
    image: Image.Image,
    frame: PreparedFrame,
    ocr_context: ObservationOcrContext,
) -> tuple[tuple[DetectedListEntry, ...], CampaignChapterIdentity | None]:
    """Stage rows plus the typed chapter identity read from the path title."""

    chapter = _chapter_identity(image=image, ocr_context=ocr_context)
    marked: list[tuple[Bounds, DetectedListEntry]] = []
    for candidate in _circle_candidates(frame, _PATH_HOUGH):
        marked_row = _path_node_row(
            image=image,
            pixels=frame.pixels,
            candidate=candidate,
            chapter_number=chapter.chapter_number if chapter else None,
            ocr_context=ocr_context,
        )
        if marked_row is not None:
            marked.append(marked_row)
    marked.sort(key=lambda item: (item[1].bounds.y, item[1].bounds.x))
    return _deduplicate_marked(marked), chapter

def _path_node_row(
    *,
    image: Image.Image,
    pixels: np.ndarray,
    candidate: _CircleCandidate,
    chapter_number: int | None,
    ocr_context: ObservationOcrContext,
) -> tuple[Bounds, DetectedListEntry] | None:
    """One stage row for a numbered badge or a locked circle on the path.

    The returned marker bounds are the measured disc itself so duplicate
    ownership never depends on later text envelopes.
    """

    disc = _disc_bounds(candidate)
    features = _node_features(pixels, disc)
    if _edge_clipped(disc, CAMPAIGN_REFERENCE_SIZE):
        clipped = _clip_bounds(disc, CAMPAIGN_REFERENCE_SIZE)
        if clipped is None or not (_is_badge_core(features) or _is_lock_core(features)):
            return None
        return clipped, _node_entry(
            kind=ListEntryKind.CAMPAIGN_STAGE,
            bounds=scale_campaign_bounds(clipped, image.size),
            campaign_node=CampaignNodeFacts(chapter_number=chapter_number),
            row_status=RowRecognitionStatus.CLIPPED,
        )
    if _is_lock_core(features):
        return disc, _node_entry(
            kind=ListEntryKind.CAMPAIGN_STAGE,
            bounds=scale_campaign_bounds(disc, image.size),
            campaign_node=CampaignNodeFacts(chapter_number=chapter_number, locked=True),
            row_status=RowRecognitionStatus.NO_ACTION,
        )
    if not _is_badge_core(features):
        return None
    number = _read_disc_number(
        image=image, disc_ref=disc, ocr_context=ocr_context,
        required_fact="campaign_stage_number",
    )
    disc_native = scale_campaign_bounds(disc, image.size)
    if number is None:
        return disc, _node_entry(
            kind=ListEntryKind.CAMPAIGN_STAGE,
            bounds=disc_native,
            campaign_node=CampaignNodeFacts(chapter_number=chapter_number, locked=False),
            row_status=RowRecognitionStatus.UNREADABLE,
        )
    return disc, _node_entry(
        kind=ListEntryKind.CAMPAIGN_STAGE,
        bounds=disc_native,
        title_text=str(number),
        campaign_node=CampaignNodeFacts(
            chapter_number=chapter_number, stage_number=number, locked=False,
        ),
        metadata={
            **({"chapter_number": chapter_number} if chapter_number is not None else {}),
            "stage_number": number,
        },
        row_status=RowRecognitionStatus.COMPLETE,
        action_bounds=disc_native,
        action_point=disc_native.center(),
    )
