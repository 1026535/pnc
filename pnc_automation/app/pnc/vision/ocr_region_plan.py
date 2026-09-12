"""Typed, frame-local OCR region plans for fixed fields and coordinates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from PIL import Image
from pnc_automation.core.errors import ScreenClassificationError
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.daily_quest_rows import daily_quest_body_bounds_for_size
from pnc_automation.app.pnc.domain.screen_decision import is_reviewed_viewport
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.pnc.vision.resource_inventory import resource_inventory_body_bounds_for_size
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.ocr.ocr_service import (
    ObservationOcrContext,
    OcrReadPurpose,
    OcrReadStatus,
    OcrResult,
)


class OcrRegionPurpose(StrEnum):
    """Names the fixed OCR capability that owns a planned region."""

    TEXT_FIELD = "text_field"
    WORLD_COORDINATE_BAR = "world_coordinate_bar"
    ROW_BODY = "row_body"
    ROW_ACTION = "row_action"
    FULL_FRAME_FALLBACK = "full_frame_fallback"


class OcrRegionFailurePolicy(StrEnum):
    """States how a missing optional region fact is represented."""

    OMIT = "omit"
    ABSTAIN = "abstain"
    FULL_FRAME_FALLBACK = "full_frame_fallback"


class OcrRegionPreprocessing(StrEnum):
    """Named preprocessing variants owned by frame-local OCR plans."""

    RAW = "raw"
    RGB = "rgb"


class OcrRegionReadStatus(StrEnum):
    """Outcome of one planned region read."""

    PRESENT = "present"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class OcrRegionPlan:
    """One immutable OCR region owned by a resolved screen family."""

    family: ScreenType
    purpose: OcrRegionPurpose
    bounds: Bounds
    required_fact: str
    failure_policy: OcrRegionFailurePolicy
    selector_id: UiElementId | None = None
    fallback_reason: str | None = None
    read_purpose: OcrReadPurpose = OcrReadPurpose.CONTENT
    preprocessing: OcrRegionPreprocessing = OcrRegionPreprocessing.RAW


@dataclass(frozen=True, slots=True)
class OcrRegionRead:
    """Typed result of one plan-owned OCR read."""

    plan: OcrRegionPlan
    result: OcrResult | None
    status: OcrRegionReadStatus


def execute_ocr_region_plans(
    *,
    image: Image.Image,
    plans: tuple[OcrRegionPlan, ...] | list[OcrRegionPlan],
    ocr_context: ObservationOcrContext,
) -> tuple[OcrRegionRead, ...]:
    """Execute canonical frame-local region plans and return typed reads.

    Missing OCR is represented as a typed ``MISSING`` result. Invalid plans and
    backend contract errors propagate so malformed configuration cannot be
    mistaken for an optional content miss.
    """

    reads: list[OcrRegionRead] = []
    for plan in plans:
        detail = f"plan:{plan.required_fact}"
        if plan.fallback_reason is not None:
            detail += f";fallback={plan.fallback_reason}"
        try:
            if plan.failure_policy == OcrRegionFailurePolicy.FULL_FRAME_FALLBACK:
                result = ocr_context.read_result(
                    image,
                    purpose=plan.read_purpose,
                    detail=detail,
                )
            elif plan.preprocessing == OcrRegionPreprocessing.RGB:
                result = ocr_context.read_preprocessed_result(
                    image,
                    plan.bounds,
                    preprocessing_id="ocr_region_rgb_v1",
                    prepare=_prepare_rgb_region,
                    purpose=plan.read_purpose,
                    detail=detail,
                )
            else:
                result = ocr_context.read_result(
                    image,
                    plan.bounds,
                    purpose=plan.read_purpose,
                    detail=detail,
                )
        except ValueError:
            raise
        except ScreenClassificationError:
            ocr_context.record_diagnostic(
                purpose=plan.read_purpose,
                status=OcrReadStatus.MISSING,
                region=(
                    None
                    if plan.failure_policy == OcrRegionFailurePolicy.FULL_FRAME_FALLBACK
                    else plan.bounds
                ),
                detail=f"plan_missing:{plan.required_fact}",
            )
            reads.append(OcrRegionRead(plan, None, OcrRegionReadStatus.MISSING))
            continue
        status = OcrRegionReadStatus.PRESENT if result is not None and result.lines else OcrRegionReadStatus.MISSING
        if status == OcrRegionReadStatus.MISSING:
            ocr_context.record_diagnostic(
                purpose=plan.read_purpose,
                status=OcrReadStatus.MISSING,
                region=(
                    None
                    if plan.failure_policy == OcrRegionFailurePolicy.FULL_FRAME_FALLBACK
                    else plan.bounds
                ),
                detail=f"plan_missing:{plan.required_fact}",
            )
        reads.append(OcrRegionRead(plan, result, status))
    return tuple(reads)


def _prepare_rgb_region(image: Image.Image, region: Bounds) -> Image.Image:
    """Prepare one owned OCR region as RGB for the named frame-local variant."""

    return image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("RGB")


def compile_ocr_region_plans(
    *,
    registry: SelectorRegistry,
    resolved_screen: ScreenType,
    request: ObservationRequest,
    image_size: tuple[int, int],
    read_purpose: OcrReadPurpose = OcrReadPurpose.CONTENT,
    include_body_rows: bool = False,
) -> tuple[OcrRegionPlan, ...]:
    """Compile fixed-field and coordinate plans from the canonical owners.

    Unsupported aspect ratios receive an explicit full-frame fallback plan so
    callers can report the policy instead of inventing geometry.
    """

    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image_size must contain positive dimensions")
    coordinate_only_world = (
        request.world_map_coordinate_only
        and resolved_screen in {ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_ROOT}
    )
    if not is_reviewed_viewport(image_size) and not coordinate_only_world:
        aspect_error = abs((width / height) / (9 / 16) - 1.0)
        return (
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.FULL_FRAME_FALLBACK,
                bounds=Bounds(0, 0, width, height),
                required_fact="screen_identity_and_guard",
                failure_policy=OcrRegionFailurePolicy.FULL_FRAME_FALLBACK,
                fallback_reason=(
                    "unsupported_aspect"
                    if aspect_error > 0.01
                    else "unsupported_resolution"
                ),
                read_purpose=read_purpose,
            ),
        )

    plans: list[OcrRegionPlan] = []
    if include_body_rows and resolved_screen == ScreenType.PNC_BAG:
        plans.append(
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.ROW_BODY,
                bounds=resource_inventory_body_bounds_for_size(image_size),
                required_fact="resource_inventory_rows",
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
                read_purpose=read_purpose,
            )
        )
    elif include_body_rows and resolved_screen in {ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}:
        plans.append(
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.ROW_BODY,
                bounds=daily_quest_body_bounds_for_size(image_size),
                required_fact="daily_quest_rows",
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
                read_purpose=read_purpose,
            )
        )
    for selector_id in sorted(request.text_field_selectors, key=lambda value: value.value):
        selector = next((item for item in registry.all() if item.id == selector_id), None)
        if selector is None:
            raise ValueError(
                f"OCR region selector '{selector_id.value}' is not registered for planned reads."
            )
        if resolved_screen not in selector.screens:
            continue
        if selector.relative_bounds is None:
            raise ValueError(
                f"OCR region selector '{selector_id.value}' has no reviewed relative bounds."
            )
        plans.append(
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.TEXT_FIELD,
                bounds=selector.relative_bounds.materialize_region(image_size=image_size),
                required_fact=selector_id.value,
                failure_policy=OcrRegionFailurePolicy.ABSTAIN,
                selector_id=selector_id,
                read_purpose=read_purpose,
            )
        )

    if (
        resolved_screen in {ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_ROOT}
        and (request.world_map_coordinate_only or request.expected_world_coordinate is not None)
    ):
        selector = next(
            (item for item in registry.all() if item.id == UiElementId.PNC_WORLD_COORDINATE_BAR),
            None,
        )
        if selector is None:
            raise ValueError("World coordinate bar is not registered for planned reads.")
        if resolved_screen not in selector.screens:
            return tuple(plans)
        if selector.relative_bounds is None:
            raise ValueError("World coordinate bar has no reviewed relative bounds.")
        else:
            plans.append(
                OcrRegionPlan(
                    family=resolved_screen,
                    purpose=OcrRegionPurpose.WORLD_COORDINATE_BAR,
                    bounds=selector.relative_bounds.materialize_region(image_size=image_size),
                    required_fact="world_coordinate_pair",
                    failure_policy=OcrRegionFailurePolicy.ABSTAIN,
                    selector_id=UiElementId.PNC_WORLD_COORDINATE_BAR,
                    read_purpose=read_purpose,
                )
            )
    return tuple(plans)
