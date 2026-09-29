"""Campaign map badge and lock readers."""

from __future__ import annotations

from PIL import Image
import numpy as np

from pnc_automation.app.pnc.domain.campaign import CampaignNodeFacts
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, RowRecognitionStatus
from pnc_automation.app.pnc.vision.campaign_ocr_regions import CAMPAIGN_REFERENCE_SIZE, scale_campaign_bounds
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher, PreparedFrame

from .constants import _BADGE_BLUE_INTERIOR_MIN, _MAP_HOUGH, _MAP_LOCK_LABEL_OFFSET, _MAP_PLATE_OFFSET, _CircleCandidate
from .geometry import _circle_candidates, _clip_bounds, _deduplicate_marked, _disc_bounds, _edge_clipped, _is_badge_core, _nameplate_supported, _node_features, _union_bounds
from .matching import _map_padlock_matches
from .ocr import _parse_lock_label, _read_disc_number, _read_region_text
from .rows import _node_entry

def _map_rows(
    *,
    image: Image.Image,
    frame: PreparedFrame,
    ocr_context: ObservationOcrContext,
    matcher: OpenCvTemplateMatcher,
) -> tuple[DetectedListEntry, ...]:
    """Rows for unlocked badge nodes and standalone padlock nodes on the map."""

    marked: list[tuple[Bounds, DetectedListEntry]] = []
    for candidate in _circle_candidates(frame, _MAP_HOUGH):
        marked.extend(_map_badge_row(image=image, pixels=frame.pixels, candidate=candidate, ocr_context=ocr_context))
    for match in _map_padlock_matches(frame, matcher):
        row = _map_lock_row(image=image, match=match, ocr_context=ocr_context)
        if row is not None:
            marked.append((match, row))
    marked.sort(key=lambda item: (item[1].bounds.y, item[1].bounds.x))
    return _deduplicate_marked(marked)

def _map_badge_row(
    *,
    image: Image.Image,
    pixels: np.ndarray,
    candidate: _CircleCandidate,
    ocr_context: ObservationOcrContext,
) -> tuple[tuple[Bounds, DetectedListEntry], ...]:
    """One unlocked badge row when disc interior, rim, and nameplate agree.

    The marker bounds are the measured disc itself, not the row envelope
    that includes its attached nameplate.
    """

    disc = _disc_bounds(candidate)
    features = _node_features(pixels, disc)
    if _edge_clipped(disc, CAMPAIGN_REFERENCE_SIZE):
        clipped = _clip_bounds(disc, CAMPAIGN_REFERENCE_SIZE)
        if clipped is None or not _is_badge_core(features):
            return ()
        return (
            (
                clipped,
                _node_entry(
                    kind=ListEntryKind.CAMPAIGN_CHAPTER,
                    bounds=scale_campaign_bounds(clipped, image.size),
                    campaign_node=CampaignNodeFacts(locked=None),
                    row_status=RowRecognitionStatus.CLIPPED,
                ),
            ),
        )
    if not _is_badge_core(features):
        return ()
    plate_ref = Bounds(
        x=int(round(candidate.cx)) + _MAP_PLATE_OFFSET[0],
        y=int(round(candidate.cy)) + _MAP_PLATE_OFFSET[1],
        width=_MAP_PLATE_OFFSET[2],
        height=_MAP_PLATE_OFFSET[3],
    )
    plate_clipped = _clip_bounds(plate_ref, CAMPAIGN_REFERENCE_SIZE)
    if plate_clipped is None:
        return ()
    plate_bounds = scale_campaign_bounds(plate_clipped, image.size)
    if not _nameplate_supported(
        pixels, plate_clipped, gold=features["blue"] < _BADGE_BLUE_INTERIOR_MIN
    ):
        return ()
    number = _read_disc_number(
        image=image, disc_ref=disc, ocr_context=ocr_context,
        required_fact="campaign_chapter_number",
    )
    name = _read_region_text(
        image=image,
        region=plate_bounds,
        ocr_context=ocr_context,
        detail="campaign_chapter_nameplate",
    )
    disc_native = scale_campaign_bounds(disc, image.size)
    row_bounds = _union_bounds(disc_native, plate_bounds)
    title = " ".join(part for part in ((str(number) if number is not None else None), name) if part)
    metadata = {} if number is None else {"chapter_number": number}
    if number is None:
        return (
            (
                disc,
                _node_entry(
                    kind=ListEntryKind.CAMPAIGN_CHAPTER,
                    bounds=row_bounds,
                    title_text=title or None,
                    campaign_node=CampaignNodeFacts(name=name, locked=False),
                    row_status=RowRecognitionStatus.UNREADABLE,
                ),
            ),
        )
    return (
        (
            disc,
            _node_entry(
                kind=ListEntryKind.CAMPAIGN_CHAPTER,
                bounds=row_bounds,
                title_text=title or None,
                campaign_node=CampaignNodeFacts(chapter_number=number, name=name, locked=False),
                metadata=metadata,
                row_status=RowRecognitionStatus.COMPLETE,
                action_bounds=disc_native,
                action_point=disc_native.center(),
            ),
        ),
    )

def _map_lock_row(
    *,
    image: Image.Image,
    match: Bounds,
    ocr_context: ObservationOcrContext,
) -> DetectedListEntry | None:
    """One locked map node row from a glyph hit and its bounded label read.

    ``match`` is the glyph bounds in reference coordinates.
    """

    label_ref = Bounds(
        x=max(0, match.x + _MAP_LOCK_LABEL_OFFSET[0]),
        y=match.y + match.height + _MAP_LOCK_LABEL_OFFSET[1],
        width=match.width + _MAP_LOCK_LABEL_OFFSET[2],
        height=_MAP_LOCK_LABEL_OFFSET[3],
    )
    if label_ref.y + label_ref.height > CAMPAIGN_REFERENCE_SIZE[1]:
        return None
    label_native = scale_campaign_bounds(label_ref, image.size)
    label_text = _read_region_text(
        image=image,
        region=label_native,
        ocr_context=ocr_context,
        detail="campaign_locked_chapter_label",
    )
    number, name = _parse_lock_label(label_text)
    glyph_native = scale_campaign_bounds(match, image.size)
    row_bounds = _union_bounds(glyph_native, label_native)
    return _node_entry(
        kind=ListEntryKind.CAMPAIGN_CHAPTER,
        bounds=row_bounds,
        title_text=label_text or None,
        campaign_node=CampaignNodeFacts(chapter_number=number, name=name, locked=True),
        metadata={} if number is None else {"chapter_number": number},
        row_status=RowRecognitionStatus.NO_ACTION,
    )
