"""Pet Workshop order cards, rewards, and detail segmentation."""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image

from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopOrder,
    WorkshopOrderReward,
    WorkshopOrderRewardCategory,
    WorkshopOrderView,
)
from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

from . import geometry, matching, ocr
from .constants import *  # noqa: F403 - measured constants are the data contract


def read_orders(
    *,
    image: Image.Image,
    prepared: PreparedFrame,
    matcher: OpenCvTemplateMatcher,
    ocr_context: ObservationOcrContext,
) -> tuple[tuple[WorkshopOrder, ...], tuple[WorkshopOrderView, ...], Bounds | None]:
    """Read measured order cards and their per-card view bounds."""

    cards = geometry.detect_card_extents(prepared.pixels)
    strip_bounds = geometry.order_strip_bounds(prepared.pixels)
    orders: list[WorkshopOrder] = []
    views: list[WorkshopOrderView] = []
    for index, card in enumerate(cards):
        order_ref = index + 1
        requirements, covered = read_card_requirements(matcher, prepared, card)
        rewards, orphan_reward = read_strip_rewards(
            matcher,
            image=image,
            prepared=prepared,
            ocr_context=ocr_context,
            card=card,
            order_ref=order_ref,
        )
        complete_search = geometry.clipped(
            Bounds(
                x=card.x0 + _CARD_COMPLETE_OFFSET.x,
                y=_CARD_COMPLETE_OFFSET.y,
                width=_CARD_COMPLETE_OFFSET.width,
                height=_CARD_COMPLETE_OFFSET.height,
            )
        )
        submit_bounds: Bounds | None = None
        if complete_search is None or not geometry.fits(
            complete_search, _COMPLETE_TEMPLATE_SIZE
        ):
            ready = None
        else:
            best = matching.best(matcher,
                prepared,
                _COMPLETE_TEMPLATES,
                complete_search,
                _CONTROL_THRESHOLD,
            )
            submit_bounds = best[0].bounds if best is not None else None
            ready = submit_bounds is not None
        if card.clipped:
            completeness = RowRecognitionStatus.CLIPPED
        elif covered and not orphan_reward:
            completeness = RowRecognitionStatus.COMPLETE
        else:
            completeness = RowRecognitionStatus.UNREADABLE
        orders.append(
            WorkshopOrder(
                order_ref=order_ref,
                requirements=requirements,
                rewards=rewards,
                completeness=completeness,
                ready=ready,
                source="order_strip",
            )
        )
        views.append(
            WorkshopOrderView(
                order_ref=order_ref,
                portrait_bounds=geometry.scaled_region(
                    Bounds(
                        x=card.x0,
                        y=card.top,
                        width=card.x1 - card.x0,
                        height=card.bottom - card.top,
                    ),
                    image,
                ),
                submit_bounds=submit_bounds,
            )
        )
    return tuple(orders), tuple(views), strip_bounds


def read_card_requirements(
    matcher: OpenCvTemplateMatcher,
    prepared: PreparedFrame,
    card: geometry.CardExtent,
) -> tuple[dict[int, int], bool]:
    """Match requirement icons and prove one-to-one tile coverage."""

    icon_region = geometry.clipped(
        Bounds(
            x=card.x0,
            y=_CARD_REQ_ICON_BAND[0],
            width=card.x1 - card.x0,
            height=_CARD_REQ_ICON_BAND[1],
        )
    )
    icons = (
        matching.icons(matcher,
            prepared,
            templates=_STRIP_REQUIREMENT_TEMPLATES,
            region=icon_region,
            threshold=_STRIP_ICON_THRESHOLD,
        )
        if icon_region is not None
        else []
    )
    return geometry.counted_icons(icons), geometry.tile_coverage(
        geometry.tile_runs(prepared.pixels, card), icons, prepared
    )


def read_strip_rewards(
    matcher: OpenCvTemplateMatcher,
    *,
    image: Image.Image,
    prepared: PreparedFrame,
    ocr_context: ObservationOcrContext,
    card: geometry.CardExtent,
    order_ref: int,
) -> tuple[tuple[WorkshopOrderReward, ...], bool]:
    """Read each independently segmented reward group and bounded count."""

    band = geometry.clipped(
        Bounds(
            x=card.x0 - 8,
            y=_CARD_REWARD_BAND[0],
            width=card.x1 - card.x0 + 16,
            height=_CARD_REWARD_BAND[1],
        )
    )
    if band is None:
        return (), False
    icons = matching.icons(matcher,
        prepared,
        templates=_STRIP_REWARD_TEMPLATES,
        region=band,
        threshold=_STRIP_ICON_THRESHOLD,
    )
    icon_refs = sorted(
        (
            (category, geometry.ref_region(match.bounds, prepared))
            for category, match in icons
        ),
        key=lambda item: item[1].x,
    )
    groups = geometry.reward_groups(prepared.pixels, card)
    entries: list[WorkshopOrderReward] = []
    covered_icons: set[int] = set()
    orphan = not groups
    for index, (x0, x1) in enumerate(groups):
        members = [
            (i, category, bounds)
            for i, (category, bounds) in enumerate(icon_refs)
            if x0 <= bounds.center()[0] <= x1
        ]
        if len(members) != 1:
            orphan = True
            label = ocr.read_region_text(
                image=image,
                ocr_context=ocr_context,
                region=Bounds(x=x0, y=band.y, width=x1 - x0 + 1, height=band.height),
                detail=f"workshop_order_{order_ref}_unknown_reward_{index}",
            )
            entries.append(
                WorkshopOrderReward(
                    category=WorkshopOrderRewardCategory.UNKNOWN,
                    label=label or None,
                )
            )
            continue
        icon_index, category, bounds = members[0]
        covered_icons.add(icon_index)
        right_edge = (
            groups[index + 1][0] - 2
            if index + 1 < len(groups)
            else min(card.x1 + 8, _REFERENCE_SIZE[0])
        )
        zone = geometry.clipped(
            Bounds(
                x=bounds.x + bounds.width,
                y=max(0, bounds.y - 4),
                width=max(0, right_edge - (bounds.x + bounds.width)),
                height=bounds.height + 14,
            )
        )
        entries.append(
            WorkshopOrderReward(
                category=category,
                quantity=ocr.zone_quantity(
                    image=image,
                    ocr_context=ocr_context,
                    region=zone,
                    detail=f"workshop_order_{order_ref}_reward_{index}_count",
                ),
            )
        )
    if len(covered_icons) != len(icon_refs):
        orphan = True
    return tuple(entries), orphan


def read_detail_rewards(
    matcher: OpenCvTemplateMatcher,
    *,
    image: Image.Image,
    prepared: PreparedFrame,
    ocr_context: ObservationOcrContext,
    icons: Sequence[tuple[object, TemplateMatch]],
    pedestals: Sequence[tuple[int, int]],
) -> tuple[tuple[WorkshopOrderReward, ...], bool]:
    """Read detail reward counts while retaining unmatched art as unknown."""

    icon_refs = sorted(
        (
            (category, geometry.ref_region(match.bounds, prepared))
            for category, match in icons
        ),
        key=lambda item: item[1].x,
    )
    ped_spans = [
        (x0 - _OD_PEDESTAL_PAD_X, x1 + _OD_PEDESTAL_PAD_X)
        for x0, x1 in pedestals
    ]
    entries: list[tuple[int, WorkshopOrderReward]] = []
    consumed: list[Bounds] = []
    for index, (category, bounds) in enumerate(icon_refs):
        right_edge = (
            icon_refs[index + 1][1].x - 2
            if index + 1 < len(icon_refs)
            else bounds.x + bounds.width + _OD_COUNT_ZONE_RIGHT_PAD
        )
        zone = geometry.clipped(
            Bounds(
                x=bounds.x - 2,
                y=bounds.y + _OD_COUNT_ZONE_Y[0],
                width=max(
                    0,
                    min(
                        right_edge,
                        bounds.x + bounds.width + _OD_COUNT_ZONE_RIGHT_PAD,
                    )
                    - (bounds.x - 2),
                ),
                height=_OD_COUNT_ZONE_Y[1]
                - _OD_COUNT_ZONE_Y[0],
            )
        )
        entries.append(
            (
                bounds.x,
                WorkshopOrderReward(
                    category=category,
                    quantity=ocr.zone_quantity(
                        image=image,
                        ocr_context=ocr_context,
                        region=zone,
                        detail=f"workshop_order_detail_reward_{index}_count",
                    ),
                ),
            )
        )
        consumed.append(bounds)
        if zone is not None:
            consumed.append(zone)
    orphan = False
    for value, token_bounds, text in ocr.numeric_tokens(
        ocr.read_lines(
            image=image,
            ocr_context=ocr_context,
            region=_OD_REWARD_TOKEN_BAND,
            detail="workshop_order_detail_rewards",
        )
    ):
        token_ref = geometry.ref_region(token_bounds, prepared)
        if any(geometry.intersects(token_ref, region) for region in consumed):
            continue
        orphan = True
        entries.append(
            (
                token_ref.x,
                WorkshopOrderReward(
                    category=WorkshopOrderRewardCategory.UNKNOWN,
                    quantity=value,
                    label=text,
                ),
            )
        )
    for x0, x1 in ped_spans:
        if any(
            x0 <= geometry.ref_region(match.bounds, prepared).center()[0] <= x1
            for _category, match in icons
        ):
            continue
        orphan = True
        entries.append((x0, WorkshopOrderReward(category=WorkshopOrderRewardCategory.UNKNOWN)))
    entries.sort(key=lambda item: item[0])
    return tuple(reward for _x, reward in entries), orphan
