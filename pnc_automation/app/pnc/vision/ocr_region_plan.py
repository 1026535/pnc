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
from pnc_automation.app.pnc.vision.bag_layout import bag_body_bounds_for_size
from pnc_automation.app.pnc.vision.campaign_ocr_regions import (
    CAMPAIGN_CHAPTER_TITLE_REGION,
    CAMPAIGN_MAP_CHAPTER_ROW,
    scale_campaign_bounds,
)
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
    MODAL_CONTENT = "modal_content"
    LOADING_STATUS = "loading_status"
    HEADER = "header"
    SCREEN_FIELDS = "screen_fields"
    BUILDING_LEVEL = "building_level"


class OcrRegionFailurePolicy(StrEnum):
    """States how a missing optional region fact is represented."""

    OMIT = "omit"
    ABSTAIN = "abstain"


class OcrRegionPreprocessing(StrEnum):
    """Named preprocessing variants owned by frame-local OCR plans."""

    RAW = "raw"
    RGB = "rgb"
    RGB_3X = "rgb_3x"


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


def compile_guard_ocr_region_plans(
    image_size: tuple[int, int],
) -> tuple[OcrRegionPlan, ...]:
    """Read the centered modal message/action surface from saved dialog captures.

    This region is independent of the requested background screen. Its
    surface includes the tall owned Research/Compose dialogs as well as
    centered update/reconnect messages. Startup identity is visual; ordinary
    headers and the bottom HUD are never scanned as hypothetical loading text.
    """

    if not is_reviewed_viewport(image_size):
        return ()
    width, height = image_size
    regions = (
        (OcrRegionPurpose.MODAL_CONTENT, "foreground_modal", (0.03, 0.25, 0.94, 0.50)),
    )
    return tuple(
        OcrRegionPlan(
            family=ScreenType.PNC_POPUP,
            purpose=purpose,
            bounds=Bounds(round(x * width), round(y * height), round(w * width), round(h * height)),
            required_fact=fact,
            failure_policy=OcrRegionFailurePolicy.OMIT,
            read_purpose=OcrReadPurpose.GUARD,
        )
        for purpose, fact, (x, y, w, h) in regions
    )


# Semantic owners on the frozen reference captures. Header OCR validates/reads
# text on an already identified layout; it never discovers another screen.
# Row bodies intentionally retain their complete scroll viewport and clipping.
_SCREEN_CONTENT_REGIONS = {
    ScreenType.PNC_HERO_HALL: (("recruit_labels", 0.02, 0.04, 0.96, 0.10), ("recruit_actions", 0.04, 0.65, 0.92, 0.26)),
    ScreenType.PNC_INSTITUTE: (("building_level_and_actions", 0.02, 0.20, 0.96, 0.12), ("research_categories", 0.02, 0.32, 0.96, 0.50), ("research_queue", 0.02, 0.84, 0.96, 0.15)),
    ScreenType.PNC_BUILDING_DETAILS: (
        ("building_level_and_actions", 0.02, 0.24, 0.96, 0.075),
        ("building_requirements", 0.04, 0.32, 0.92, 0.32),
    ),
    ScreenType.PNC_RESEARCH_TREE: (("research_nodes_and_detail", 0.025, 0.07, 0.95, 0.93),),
    ScreenType.PNC_RESEARCH_QUEUE: (("research_queue_rows", 0.03, 0.25, 0.94, 0.29),),
    # The small Castle fraction needs native field enlargement to preserve its
    # slash. The action buttons to its right have independent visual ownership.
    ScreenType.PNC_CASTLE: (("building_level", 97 / 540, 235 / 960, 97 / 540, 40 / 960),),
    ScreenType.PNC_WAREHOUSE: (("building_level_and_actions", 0.02, 0.20, 0.96, 0.14),),
    ScreenType.PNC_GODDESS_STATUE: (("building_level_and_actions", 0.02, 0.20, 0.96, 0.14),),
    ScreenType.PNC_EVENT_CENTER: (("event_rows", 0.02, 0.07, 0.96, 0.85),),
    ScreenType.PNC_SETTINGS: (),
    ScreenType.PNC_MORE_MENU: (),
    # Complete roster cards can extend to the bottom edge on the captured
    # eight-row layout. Keep the text column, including its last name/level.
    ScreenType.PNC_CASTLE_SELECTION: (("castle_roster", 0.20, 0.07, 0.62, 0.92),),
    ScreenType.PNC_HOME_CITY: (
        ("home_queue_status", 0.0, 0.19, 0.17, 0.22),
        # Building labels are the canonical input to the Home spatial surface.
        # Keep this bounded above the task/banner and bottom-navigation chrome;
        # labels below this region cannot authorize a safe building tap.
        ("home_city_objects", 0.0, 0.12, 1.0, 0.70),
        ("home_navigation", 0.0, 0.925, 1.0, 0.075),
    ),
    ScreenType.PNC_LORD_INFO: (("lord_header", 0.02, 0.02, 0.96, 0.16), ("lord_profile", 0.02, 0.18, 0.96, 0.72)),
    ScreenType.PNC_PLAYER_TERRITORY: (("territory_header", 0.02, 0.02, 0.96, 0.16), ("territory_profile", 0.02, 0.18, 0.96, 0.72)),
    ScreenType.PNC_PLAYER_PROFILE: (("profile_name", 0.18, 0.0, 0.70, 0.055),),
    # The coordinate field owns its prepared crop; rejection toasts are a
    # separate existing consumer fact immediately below the top HUD.
    ScreenType.PNC_WORLD_MAP: (("coordinate_rejection_status", 0.10, 0.10, 0.80, 0.10),),
    ScreenType.PNC_WORLD_COORDINATE_DIALOG: (),  # Requested field interiors come from the selector registry.
    ScreenType.PNC_WORLD_MAP_OVERVIEW: (("overview_ruler", 0.03, 0.06, 0.94, 0.16), ("overview_legend", 0.01, 0.70, 0.98, 0.26)),
    ScreenType.PNC_WORLD_KINGDOM_LIST: (("kingdom_rows", 0.04, 0.14, 0.92, 0.78),),
    ScreenType.PNC_MAIL_HUB: (("mail_categories", 0.02, 0.08, 0.96, 0.62),),
    ScreenType.PNC_MAILBOX_LIST: (("mailbox_rows", 0.02, 0.12, 0.96, 0.77), ("mailbox_actions", 0.02, 0.91, 0.96, 0.09)),
    ScreenType.PNC_MAIL_THREAD: (("mail_thread", 0.02, 0.08, 0.96, 0.82),),
    ScreenType.PNC_MAIL_COMPOSE_POPUP: (),  # Only the three requested field interiors need OCR.
    ScreenType.PNC_ALLIANCE_HOME: (("alliance_status_banner", 0.04, 0.20, 0.92, 0.18),),
    # Member rows own measured name/action crops; static Manage controls are visual.
    ScreenType.PNC_ALLIANCE_MEMBER_LIST: (),
    ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP: (),
    ScreenType.PNC_ALLIANCE_HALL: (
        ("building_level_and_actions", 0.18, 0.25, 0.78, 0.065),
    ),
    ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE: (),
    ScreenType.PNC_ALLIANCE_MEMBER_TRANSPORT: (("transport_rows", 0.02, 0.12, 0.96, 0.76),),
    ScreenType.PNC_CAMPAIGN_MAP: (),
    ScreenType.PNC_CAMPAIGN_CHAPTER: (),
    # The accepted stage publishes visual Challenge/Close only. There is no
    # stage-detail content contract that consumes a body OCR scan.
    ScreenType.PNC_CAMPAIGN_STAGE: (),
    ScreenType.PNC_HERO_FORMATION: (("formation_heroes", 0.02, 0.10, 0.96, 0.70), ("formation_actions", 0.02, 0.82, 0.96, 0.14)),
    ScreenType.PNC_BATTLE_PREP: (("battle_units", 0.02, 0.08, 0.96, 0.76),),
    ScreenType.PNC_GATHER_NODE: (("selected_resource_panel", 0.02, 0.36, 0.96, 0.55),),
    ScreenType.PNC_MARCH_CONFIRM: (("formation_fields", 0.02, 0.08, 0.96, 0.20), ("formation_troop_rows", 0.02, 0.37, 0.96, 0.46), ("formation_dispatch", 0.15, 0.85, 0.70, 0.14)),
}


def compile_screen_content_ocr_region_plans(
    *, resolved_screen: ScreenType, request: ObservationRequest,
    image_size: tuple[int, int],
    layout_id: str | None = None,
) -> tuple[OcrRegionPlan, ...]:
    """Compile semantic text regions only for an independently accepted screen."""

    if not is_reviewed_viewport(image_size) or resolved_screen == ScreenType.UNKNOWN:
        return ()
    width, height = image_size
    if resolved_screen == ScreenType.PNC_BUILDING_CONSTRUCTION:
        # Construction owns its title, level/actions row, and resource panel.
        # These crops deliberately exclude the surrounding city and modal
        # chrome so a missing action cannot trigger a second discovery read.
        return (
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.HEADER,
                bounds=Bounds(
                    round(width * 0.18), 0, round(width * 0.72), round(height * 0.055)
                ),
                required_fact="construction_target_name",
                failure_policy=OcrRegionFailurePolicy.OMIT,
                selector_id=UiElementId.PNC_BUILDING_CONSTRUCTION_HEADER,
            ),
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.BUILDING_LEVEL,
                bounds=Bounds(
                    round(width * 0.02), round(height * 0.24),
                    round(width * 0.96), round(height * 0.075),
                ),
                required_fact="building_level",
                failure_policy=OcrRegionFailurePolicy.OMIT,
            ),
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.SCREEN_FIELDS,
                bounds=Bounds(
                    round(width * 0.04), round(height * 0.32),
                    round(width * 0.92), round(height * 0.32),
                ),
                required_fact="construction_requirements",
                failure_policy=OcrRegionFailurePolicy.OMIT,
            ),
        )
    if resolved_screen == ScreenType.PNC_BUILD_QUEUE:
        # The queue is a centered modal. Keep its title and each queue row as
        # separate owned regions so row OCR retains current-frame provenance.
        return (
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.HEADER,
                bounds=Bounds(
                    round(width * 0.22), round(height * 0.25),
                    round(width * 0.56), round(height * 0.07),
                ),
                required_fact="build_queue_header",
                failure_policy=OcrRegionFailurePolicy.OMIT,
            ),
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.ROW_BODY,
                bounds=Bounds(
                    round(width * 0.04), round(height * 0.32),
                    round(width * 0.92), round(height * 0.10),
                ),
                required_fact="build_queue_first_row",
                failure_policy=OcrRegionFailurePolicy.OMIT,
            ),
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.ROW_BODY,
                bounds=Bounds(
                    round(width * 0.04), round(height * 0.42),
                    round(width * 0.92), round(height * 0.10),
                ),
                required_fact="build_queue_second_row",
                failure_policy=OcrRegionFailurePolicy.OMIT,
            ),
        )
    regions = _SCREEN_CONTENT_REGIONS.get(resolved_screen, ())
    if resolved_screen == ScreenType.PNC_INSTITUTE and layout_id == "institute_upgrade_detail":
        regions = (
            ("building_level_and_actions", 0.18, 0.24, 0.76, 0.075),
            ("building_upgrade_times", 0.06, 0.34, 0.64, 0.075),
            ("unmet_building_prerequisite", 0.04, 0.44, 0.92, 0.085),
            ("building_upgrade_materials", 0.055, 0.612, 0.47, 0.235),
        )
    if resolved_screen == ScreenType.PNC_RESEARCH_TREE:
        if layout_id == "research_tree_node_detail":
            # The detail panel spans the measured popup from its title band
            # through the resource cost rows; nothing below the panel is owned.
            regions = (("research_detail", 0.04, 0.24, 0.92, 0.58),)
        elif layout_id == "research_tree_node_detail_max":
            # The completed-node panel is lower and contains no action/cost area.
            regions = (("research_detail", 0.10, 0.37, 0.84, 0.32),)
        elif layout_id == "research_tree_development":
            # Node discovery is geometry-owned; OCR reads only the fixed
            # category header plus each measured label/level region owned by
            # the producer.
            return (
                OcrRegionPlan(
                    family=resolved_screen,
                    purpose=OcrRegionPurpose.HEADER,
                    bounds=Bounds(0, 0, width, round(height * 0.065)),
                    required_fact="screen_header",
                    failure_policy=OcrRegionFailurePolicy.OMIT,
                ),
            )
        else:
            return ()
    if resolved_screen == ScreenType.PNC_CAMPAIGN_MAP:
        campaign_region = CAMPAIGN_MAP_CHAPTER_ROW
        campaign_fact = "campaign_chapter_row"
    elif resolved_screen == ScreenType.PNC_CAMPAIGN_CHAPTER:
        campaign_region = CAMPAIGN_CHAPTER_TITLE_REGION
        campaign_fact = "campaign_chapter_title"
    else:
        campaign_region = None
    if campaign_region is not None:
        # Stage ownership is already proved by its template; only its chapter
        # title is an OCR input to the existing Campaign row parser.
        return (OcrRegionPlan(
            family=resolved_screen,
            purpose=OcrRegionPurpose.SCREEN_FIELDS,
            bounds=scale_campaign_bounds(campaign_region, image_size),
            required_fact=campaign_fact,
            failure_policy=OcrRegionFailurePolicy.ABSTAIN,
        ),)
    if resolved_screen in {ScreenType.PNC_QUEST_MAIN, ScreenType.PNC_QUEST_DAILY}:
        # Their canonical parsers own the body and per-row resegmentation.
        regions = (("selected_tab_labels", 0.0, 0.055, 1.0, 0.10),)
    elif resolved_screen == ScreenType.PNC_CHAT:
        # The independent profile already proves the title and tab controls.
        # Selection comes from their measured appearance, not redundant OCR.
        return () if not request.include_chat_entries else (OcrRegionPlan(
            family=resolved_screen, purpose=OcrRegionPurpose.ROW_BODY,
            bounds=Bounds(0, round(height * 0.13), width, round(height * 0.77)),
            required_fact="chat_message_rows", failure_policy=OcrRegionFailurePolicy.OMIT,
        ),)
    if not regions:
        return ()
    if resolved_screen == ScreenType.PNC_PLAYER_PROFILE:
        return (OcrRegionPlan(
            family=resolved_screen, purpose=OcrRegionPurpose.HEADER,
            bounds=Bounds(round(width * 0.18), 0, round(width * 0.70), round(height * 0.055)),
            required_fact="profile_player_name", failure_policy=OcrRegionFailurePolicy.ABSTAIN,
        ),) if layout_id == "remote_player_profile_gear" else ()
    header_bounds = Bounds(0, 0, width, round(height * 0.065))
    if resolved_screen == ScreenType.PNC_MAILBOX_LIST:
        # Padding below the title keeps Player Mail together in captured OCR;
        # Back and Info artwork remain outside its horizontal crop.
        header_bounds = Bounds(round(width * 0.18), 0, round(width * 0.72), round(height * 0.078125))
    if resolved_screen in {
        ScreenType.PNC_INSTITUTE,
        ScreenType.PNC_CASTLE,
        ScreenType.PNC_WAREHOUSE,
        ScreenType.PNC_BUILDING_DETAILS,
    }:
        # The captured building title sits between Back and Info. Including
        # either icon merges it into the title in real OCR (for example Farm0).
        header_bounds = Bounds(round(width * 0.18), 0, round(width * 0.72), round(height * 0.055))
    header = OcrRegionPlan(
        family=resolved_screen, purpose=OcrRegionPurpose.HEADER,
        bounds=header_bounds,
        required_fact="screen_header", failure_policy=OcrRegionFailurePolicy.OMIT,
    )
    include_header = not (
        resolved_screen in {ScreenType.PNC_ALLIANCE_HOME, ScreenType.PNC_WORLD_MAP}
        or (resolved_screen == ScreenType.PNC_RESEARCH_TREE
            and layout_id in {"research_tree_node_detail", "research_tree_node_detail_max"})
        or resolved_screen == ScreenType.PNC_RESEARCH_QUEUE
    )
    return (*((header,) if include_header else ()), *(
        OcrRegionPlan(
            family=resolved_screen,
            purpose=(
                OcrRegionPurpose.BUILDING_LEVEL
                if fact in {"building_level", "building_level_and_actions"}
                else OcrRegionPurpose.SCREEN_FIELDS
            ),
            bounds=Bounds(round(x * width), round(y * height), round(w * width), round(h * height)),
            required_fact=fact, failure_policy=OcrRegionFailurePolicy.OMIT,
            preprocessing=(OcrRegionPreprocessing.RGB_3X
                           if resolved_screen == ScreenType.PNC_CASTLE
                           else OcrRegionPreprocessing.RAW),
        )
        for fact, x, y, w, h in regions
    ))
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
            if plan.preprocessing in {OcrRegionPreprocessing.RGB, OcrRegionPreprocessing.RGB_3X}:
                result = ocr_context.read_preprocessed_result(
                    image,
                    plan.bounds,
                    preprocessing_id=f"ocr_region_{plan.preprocessing.value}_v1",
                    prepare=(
                        _prepare_rgb_3x_region
                        if plan.preprocessing == OcrRegionPreprocessing.RGB_3X
                        else _prepare_rgb_region
                    ),
                    purpose=plan.read_purpose,
                    detail=detail,
                    required_fact=plan.required_fact,
                )
            else:
                result = ocr_context.read_result(
                    image,
                    plan.bounds,
                    purpose=plan.read_purpose,
                    detail=detail,
                    required_fact=plan.required_fact,
                )
        except ValueError:
            raise
        except ScreenClassificationError:
            ocr_context.record_diagnostic(
                purpose=plan.read_purpose,
                status=OcrReadStatus.MISSING,
                region=plan.bounds,
                # Keep one diagnostic key across a transient miss and its retry.
                detail=detail,
                required_fact=plan.required_fact,
            )
            reads.append(OcrRegionRead(plan, None, OcrRegionReadStatus.MISSING))
            continue
        status = OcrRegionReadStatus.PRESENT if result is not None and result.lines else OcrRegionReadStatus.MISSING
        if status == OcrRegionReadStatus.MISSING and plan.failure_policy != OcrRegionFailurePolicy.OMIT:
            ocr_context.record_diagnostic(
                purpose=plan.read_purpose,
                status=OcrReadStatus.MISSING,
                region=plan.bounds,
                detail=detail,
                required_fact=plan.required_fact,
            )
        reads.append(OcrRegionRead(plan, result, status))
    return tuple(reads)


def _prepare_rgb_region(image: Image.Image, region: Bounds) -> Image.Image:
    """Prepare one owned OCR region as RGB for the named frame-local variant."""

    return image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("RGB")


def _prepare_rgb_3x_region(image: Image.Image, region: Bounds) -> Image.Image:
    """Enlarge only the owned numeric field; the OCR context restores native bounds."""

    crop = _prepare_rgb_region(image, region)
    return crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)


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

    Unsupported viewports have no reviewed field geometry and receive no plan.
    """

    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("image_size must contain positive dimensions")
    coordinate_only_world = (
        request.world_map_coordinate_only
        and resolved_screen in {ScreenType.PNC_WORLD_MAP, ScreenType.PNC_WORLD_MAP_ROOT}
    )
    if resolved_screen in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
        return ()
    if not is_reviewed_viewport(image_size) and not coordinate_only_world:
        return ()

    plans: list[OcrRegionPlan] = []
    if include_body_rows and resolved_screen == ScreenType.PNC_BAG:
        plans.append(
            OcrRegionPlan(
                family=resolved_screen,
                purpose=OcrRegionPurpose.ROW_BODY,
                bounds=bag_body_bounds_for_size(image_size),
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
