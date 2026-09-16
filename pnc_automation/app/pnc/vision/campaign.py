"""Evidence-backed Campaign map and chapter-path content producer.

Numbered chapter and stage nodes are discovered by bounded circle geometry,
then validated against measured badge interiors, rims, and (on the map) their
attached horizontal nameplate before any OCR runs. Map locks are located by
bounded repeated glyph matching against the two observed padlock art variants.
All reads are candidate-local and never establish screen identity.

Digits that the OCR backend cannot see stay unreadable: a recognized node with
no observed ordinal publishes as UNREADABLE (or NO_ACTION when locked) rather
than an invented chapter or stage number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from pnc_automation.app.pnc.domain.campaign import CampaignChapterIdentity, CampaignNodeFacts
from pnc_automation.app.pnc.domain.observation import (
    DetectedListEntry,
    ListEntryKind,
    RowRecognitionStatus,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_CHAPTER_TITLE_REGION,
    CAMPAIGN_REFERENCE_SIZE,
    scale_campaign_bounds,
)
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrReadPurpose
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

_DATA_ROOT = Path(__file__).resolve().parent / "data"

# Bounded circle discovery measured on the lead's Hough probe for both
# observed frontier surfaces (540x960 reference space).
_MAP_HOUGH = (32, 18, 14, 25)  # min_dist, param2, min_radius, max_radius
_PATH_HOUGH = (38, 25, 18, 33)
_HOUGH_PARAM1 = 100
_MAX_CIRCLE_CANDIDATES = 48

# Map padlock glyph enumeration through the shared matcher. Two qualified art
# variants exist (gold body and whitened face); the negative margin reaches
# 0.78 on stage dialogs and 0.68 on foreign surfaces.
_MAP_PADLOCK_TEMPLATES = (
    "screen_anchors/campaign_map_padlock.png",
    "screen_anchors/campaign_map_padlock_alt.png",
)
_MAP_PADLOCK_THRESHOLD = 0.85
_MAP_PADLOCK_SEARCH = Bounds(x=0, y=0, width=540, height=800)
_MAP_MAX_PADLOCKS = 8

# Measured attachment windows in reference units. The locked-label text sits
# centered under the glyph; the unlocked nameplate extends right of the disc.
_MAP_LOCK_LABEL_OFFSET = (-60, 6, 120, 42)
_MAP_PLATE_OFFSET = (12, -24, 150, 48)
_MAP_DISC_DIGIT_MARGIN = 2

# A numeral counts only at the measured backend floor (the lowest accepted
# positive badge read on the map is 0.837). One narrower inner-core retry is
# allowed when the ordinary read resolves nothing, because observed ring
# decoration can leak punctuation into the raw disc read; the inset derives
# from the current disc size, never from a fixed node position.
_NUMERIC_CONFIDENCE_MIN = 0.80
_DISC_CORE_INSET_FRACTION = 0.10

# The two padlock art variants each match every observed glyph, so a single
# lock produces one hit per template at slightly shifted positions. Hits whose
# centers sit inside one glyph width belong to the same lock.
_MAP_PADLOCK_CLUSTER_RADIUS = 45.0

# Interior and rim-band thresholds measured on true positive cores and the
# probe's terrain/HUD false candidates with widened (non-uint8) arithmetic.
# Observed blue interiors measure 0.148-0.33; every false candidate in the
# captured evidence still fails the dark-core or white-numeral conjunction.
_BADGE_DARK_MIN = 0.30
_BADGE_WHITE_MIN = 0.08
_BADGE_GOLD_BAND_MIN = 0.15
_BADGE_BLUE_INTERIOR_MIN = 0.12
_LOCK_BLUE_INTERIOR_MIN = 0.50
_LOCK_WHITE_MAX = 0.08
_LOCK_GLYPH_MIN = 0.18

# Nameplate trim signatures: gold badges carry a gold-trimmed plate, unlocked
# prior chapters a navy-trimmed plate over a dark band.
_PLATE_GOLD_MIN = 0.30
_PLATE_NAVY_MIN = 0.10
_PLATE_NAVY_DARK_MIN = 0.20

# Title parsing for the accepted chapter-path header.
_CHAPTER_TITLE_PATTERN = re.compile(r"ch\.?\s*(\d{1,2})", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(r"^(\d{1,2})$")
_LOCK_LABEL_PATTERN = re.compile(r"^(\d{1,2})\s*([A-Za-z].*)?$")


@dataclass(frozen=True, slots=True)
class _CircleCandidate:
    """One bounded Hough circle in reference coordinates."""

    cx: float
    cy: float
    radius: float


def build_campaign_additions(
    *,
    image: Image.Image,
    screen_type: ScreenType,
    ocr_context: ObservationOcrContext,
    template_matcher: OpenCvTemplateMatcher | None,
) -> ObservationAdditions:
    """Publish typed Campaign rows and chapter identity for the accepted screen."""

    if screen_type not in {ScreenType.PNC_CAMPAIGN_MAP, ScreenType.PNC_CAMPAIGN_CHAPTER}:
        return ObservationAdditions()
    if template_matcher is None:
        return ObservationAdditions()
    frame = template_matcher.prepare_frame(image, reference_size=CAMPAIGN_REFERENCE_SIZE)
    if frame is None:
        return ObservationAdditions()
    if screen_type == ScreenType.PNC_CAMPAIGN_MAP:
        rows = _map_rows(image=image, frame=frame, ocr_context=ocr_context, matcher=template_matcher)
        return ObservationAdditions(list_entries=rows)
    rows, chapter = _chapter_rows(
        image=image, frame=frame, ocr_context=ocr_context,
    )
    return ObservationAdditions(list_entries=rows, campaign_chapter=chapter)


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


def _circle_candidates(frame: PreparedFrame, params: tuple[int, int, int, int]) -> tuple[_CircleCandidate, ...]:
    """Bounded gray-frame Hough candidates; raw detections are not yet facts."""

    min_dist, param2, min_radius, max_radius = params
    gray = cv2.cvtColor(frame.pixels, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=min_dist,
        param1=_HOUGH_PARAM1,
        param2=param2,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return ()
    detected = np.round(circles[0], 1)
    return tuple(
        _CircleCandidate(cx=float(cx), cy=float(cy), radius=float(radius))
        for cx, cy, radius in detected[:_MAX_CIRCLE_CANDIDATES]
    )


def _map_padlock_matches(
    frame: PreparedFrame,
    matcher: OpenCvTemplateMatcher,
) -> tuple[Bounds, ...]:
    """Repeated glyph hits for the two observed map padlock art variants.

    Both templates hit every observed glyph at slightly shifted positions, so
    hits are clustered by center distance and the strongest hit in each
    cluster represents the lock.
    """

    hits: list[tuple[Bounds, float]] = []
    for template_name in _MAP_PADLOCK_TEMPLATES:
        for match in matcher.find_matches(
            frame,
            _DATA_ROOT / template_name,
            threshold=_MAP_PADLOCK_THRESHOLD,
            search_region=_MAP_PADLOCK_SEARCH,
            max_matches=_MAP_MAX_PADLOCKS,
        ):
            hits.append((_to_reference_bounds(match.bounds, frame), match.confidence))
    hits.sort(key=lambda item: item[1], reverse=True)
    kept: list[Bounds] = []
    for bounds, _confidence in hits:
        center = bounds.center()
        if any(
            (center[0] - other.center()[0]) ** 2 + (center[1] - other.center()[1]) ** 2
            <= _MAP_PADLOCK_CLUSTER_RADIUS**2
            for other in kept
        ):
            continue
        kept.append(bounds)
    kept.sort(key=lambda bounds: (bounds.y, bounds.x))
    return tuple(kept)


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


def _chapter_identity(*, image: Image.Image, ocr_context: ObservationOcrContext) -> CampaignChapterIdentity | None:
    """The observed ``Ch.N`` title for the accepted chapter-path surface."""

    region = scale_campaign_bounds(CAMPAIGN_CHAPTER_TITLE_REGION, image.size)
    result = ocr_context.read_result(
        image,
        region,
        purpose=OcrReadPurpose.CONTENT,
        detail="campaign_chapter_title",
        required_fact="campaign_chapter_identity",
    )
    lines = sorted(result.lines, key=lambda line: (line.bounds.y, line.bounds.x))
    joined = " ".join(line.text for line in lines).strip()
    match = _CHAPTER_TITLE_PATTERN.search(joined)
    if match is None:
        return None
    chapter_number = int(match.group(1))
    name = _CHAPTER_TITLE_PATTERN.sub("", joined, count=1).strip(" .-")
    if name.startswith(str(chapter_number)) and (
        len(name) == len(str(chapter_number)) or name[len(str(chapter_number))] in " .-"
    ):
        name = name[len(str(chapter_number)):].strip(" .-")
    return CampaignChapterIdentity(
        chapter_number=chapter_number,
        name=name or None,
    )


def _to_reference_bounds(bounds: Bounds, frame: PreparedFrame) -> Bounds:
    """Project matcher output back into the frame's reference coordinate space."""

    original_width, original_height = frame.original_size
    reference_width, reference_height = frame.reference_size
    if (original_width, original_height) == (reference_width, reference_height):
        return bounds
    x = round(bounds.x * reference_width / original_width)
    y = round(bounds.y * reference_height / original_height)
    right = round((bounds.x + bounds.width) * reference_width / original_width)
    bottom = round((bounds.y + bounds.height) * reference_height / original_height)
    return Bounds(x=x, y=y, width=max(1, right - x), height=max(1, bottom - y))


def _disc_bounds(candidate: _CircleCandidate) -> Bounds:
    """Reference-space disc bounding box for one circle candidate."""

    diameter = int(round(candidate.radius * 2))
    return Bounds(
        x=int(round(candidate.cx - candidate.radius)),
        y=int(round(candidate.cy - candidate.radius)),
        width=max(1, diameter),
        height=max(1, diameter),
    )


def _edge_clipped(bounds: Bounds, size: tuple[int, int]) -> bool:
    """Whether a reference-space disc is cut by the frame edge."""

    return (
        bounds.x < 0
        or bounds.y < 0
        or bounds.x + bounds.width > size[0]
        or bounds.y + bounds.height > size[1]
    )


def _clip_bounds(bounds: Bounds, size: tuple[int, int]) -> Bounds | None:
    """Clamp reference-space bounds to the frame; ``None`` when nothing remains."""

    x = max(0, bounds.x)
    y = max(0, bounds.y)
    right = min(size[0], bounds.x + bounds.width)
    bottom = min(size[1], bounds.y + bounds.height)
    if right - x <= 0 or bottom - y <= 0:
        return None
    return Bounds(x=x, y=y, width=right - x, height=bottom - y)


def _node_features(pixels: np.ndarray, disc: Bounds) -> dict[str, float]:
    """Interior and rim-band color fractions for one circle candidate."""

    cx = disc.x + disc.width / 2.0
    cy = disc.y + disc.height / 2.0
    radius = min(disc.width, disc.height) / 2.0
    inner = _disc_mask(pixels.shape[:2], cx, cy, radius * 0.55)
    band = _disc_mask(pixels.shape[:2], cx, cy, radius) & ~_disc_mask(
        pixels.shape[:2], cx, cy, radius * 0.72
    )

    def _fraction(mask: np.ndarray, predicate) -> float:
        region = pixels[mask]
        if not np.any(mask):
            return 0.0
        return float(np.mean(predicate(region)))

    def _navy(region: np.ndarray) -> np.ndarray:
        blue = region[:, 2].astype(np.int16)
        return (blue - region[:, 0].astype(np.int16) > 30) & (blue > 80)

    return {
        "dark": _fraction(inner, lambda region: np.max(region, axis=1) < 80),
        "white": _fraction(inner, lambda region: np.min(region, axis=1) > 200),
        "blue": _fraction(inner, _navy),
        "grey": _fraction(
            inner,
            lambda region: (np.max(region, axis=1) - np.min(region, axis=1) < 40)
            & (region[:, 0] > 70)
            & (region[:, 0] < 200),
        ),
        "gold_band": _fraction(
            band,
            lambda region: (region[:, 0] > 140) & (region[:, 1] > 90) & (region[:, 2] < 110),
        ),
        "navy_band": _fraction(band, _navy),
    }


def _is_badge_core(features: dict[str, float]) -> bool:
    """A numbered badge: dark core, white numeral, gold rim or navy interior."""

    return (
        features["dark"] >= _BADGE_DARK_MIN
        and features["white"] >= _BADGE_WHITE_MIN
        and (
            features["gold_band"] >= _BADGE_GOLD_BAND_MIN
            or features["blue"] >= _BADGE_BLUE_INTERIOR_MIN
        )
    )


def _is_lock_core(features: dict[str, float]) -> bool:
    """A path lock circle: blue interior with a dark or grey padlock glyph."""

    return (
        features["blue"] >= _LOCK_BLUE_INTERIOR_MIN
        and features["white"] <= _LOCK_WHITE_MAX
        and features["grey"] + features["dark"] >= _LOCK_GLYPH_MIN
    )


def _disc_mask(shape: tuple[int, int], cx: float, cy: float, radius: float) -> np.ndarray:
    """Boolean mask for one circle inside a reference-space frame."""

    grid_y, grid_x = np.ogrid[: shape[0], : shape[1]]
    return (grid_x - cx) ** 2 + (grid_y - cy) ** 2 <= radius**2


def _nameplate_supported(pixels: np.ndarray, plate_ref: Bounds, *, gold: bool) -> bool:
    """Require the horizontal plate's measured trim color next to a badge disc."""

    clipped = _clip_bounds(plate_ref, (pixels.shape[1], pixels.shape[0]))
    if clipped is None:
        return False
    region = pixels[clipped.y : clipped.y + clipped.height, clipped.x : clipped.x + clipped.width]
    if region.size == 0:
        return False
    red, green, blue = region[..., 0], region[..., 1], region[..., 2]
    gold_fraction = np.mean((red > 140) & (green > 90) & (blue < 110))
    if gold:
        return bool(gold_fraction >= _PLATE_GOLD_MIN)
    blue_minus_red = blue.astype(np.int16) - red.astype(np.int16)
    navy = np.mean((blue_minus_red > 30) & (blue > 80))
    dark = np.mean(np.max(region, axis=2) < 80)
    return bool(navy >= _PLATE_NAVY_MIN and dark >= _PLATE_NAVY_DARK_MIN)


def _read_disc_number(
    *,
    image: Image.Image,
    disc_ref: Bounds,
    ocr_context: ObservationOcrContext,
    required_fact: str,
) -> int | None:
    """A badge numeral only when bounded reads prove exactly one positive value.

    The ordinary inset read runs first; the first credible singleton
    returns immediately, while conflicting values within one read abstain.
    One narrower inner-core retry runs only when the ordinary read resolves
    no credible numeral, because ring decoration can leak punctuation into
    the raw disc read.
    """

    candidates = _disc_number_candidates(
        image=image,
        ocr_context=ocr_context,
        required_fact=required_fact,
        detail="campaign_badge_number",
        region=_inset_bounds(disc_ref, _MAP_DISC_DIGIT_MARGIN),
    )
    if len(candidates) > 1:
        return None
    if not candidates:
        inset = max(
            1,
            round(min(disc_ref.width, disc_ref.height) * _DISC_CORE_INSET_FRACTION),
        )
        candidates = _disc_number_candidates(
            image=image,
            ocr_context=ocr_context,
            required_fact=required_fact,
            detail="campaign_badge_number_core",
            region=_inset_bounds(disc_ref, inset),
        )
    if len(candidates) != 1:
        return None
    return next(iter(candidates))


def _disc_number_candidates(
    *,
    image: Image.Image,
    ocr_context: ObservationOcrContext,
    required_fact: str,
    detail: str,
    region: Bounds,
) -> set[int]:
    """Credible positive numerals read inside one bounded disc region."""

    result = ocr_context.read_result(
        image,
        scale_campaign_bounds(region, image.size),
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
        required_fact=required_fact,
    )
    values: set[int] = set()
    for line in result.lines:
        match = _NUMBER_PATTERN.match(line.text.strip())
        if match is None or line.confidence < _NUMERIC_CONFIDENCE_MIN:
            continue
        value = int(match.group(1))
        if value > 0:
            values.add(value)
    return values


def _inset_bounds(bounds: Bounds, inset: int) -> Bounds:
    """Shrink bounds by ``inset`` reference units on each side."""

    return Bounds(
        x=bounds.x + inset,
        y=bounds.y + inset,
        width=max(1, bounds.width - 2 * inset),
        height=max(1, bounds.height - 2 * inset),
    )


def _read_region_text(
    *,
    image: Image.Image,
    region: Bounds,
    ocr_context: ObservationOcrContext,
    detail: str,
) -> str | None:
    """One bounded text read; empty results stay ``None`` rather than guessed."""

    result = ocr_context.read_result(
        image,
        region,
        purpose=OcrReadPurpose.CONTENT,
        detail=detail,
    )
    text = " ".join(
        line.text.strip()
        for line in sorted(result.lines, key=lambda line: (line.bounds.y, line.bounds.x))
        if line.text.strip()
    )
    return text or None


def _parse_lock_label(text: str | None) -> tuple[int | None, str | None]:
    """``7 Mt. Blade`` or ``8Otto Icefield`` into an observed number and name."""

    if text is None:
        return None, None
    match = _LOCK_LABEL_PATTERN.match(text.strip())
    if match is None:
        return None, text.strip() or None
    return int(match.group(1)), (match.group(2) or None)


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
    """One typed Campaign row; geometry and facts only, no inferred fields."""

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


def _union_bounds(left: Bounds, right: Bounds) -> Bounds:
    """Smallest rectangle covering two bounds."""

    x = min(left.x, right.x)
    y = min(left.y, right.y)
    return Bounds(
        x=x,
        y=y,
        width=max(left.x + left.width, right.x + right.width) - x,
        height=max(left.y + left.height, right.y + right.height) - y,
    )


def _bounds_overlap(left: Bounds, right: Bounds) -> bool:
    """Any-area overlap between two bounds."""

    return not (
        left.x + left.width <= right.x
        or right.x + right.width <= left.x
        or left.y + left.height <= right.y
        or right.y + right.height <= left.y
    )


def _deduplicate_marked(
    marked: list[tuple[Bounds, DetectedListEntry]],
) -> tuple[DetectedListEntry, ...]:
    """Drop a later row when its marker overlaps an earlier kept marker.

    Ownership is decided on the measured disc or glyph bounds, so an
    attached nameplate envelope overlapping a neighboring node cannot hide
    a distinct visible row.
    """

    kept_markers: list[Bounds] = []
    kept: list[DetectedListEntry] = []
    for marker, row in marked:
        if any(_bounds_overlap(marker, other) for other in kept_markers):
            continue
        kept_markers.append(marker)
        kept.append(row)
    return tuple(kept)
