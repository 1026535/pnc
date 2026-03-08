"""Canonical selector registry and selector metadata."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


class DetectionKind(StrEnum):
    """Supported selector detection mechanisms."""

    TEMPLATE = "template"
    OCR_REGION = "ocr_region"
    ANCHORED_REGION = "anchored_region"
    COLLECTION = "collection"
    PLANNED = "planned"


class SelectorStatus(StrEnum):
    """Tracks refinement maturity for selectors."""

    PLANNED = "planned"
    SCREENSHOT_SEEDED = "screenshot_seeded"
    CLICK_MAPPED = "click_mapped"
    INTERACTION_VALIDATED = "interaction_validated"
    TASK_VALIDATED = "task_validated"


@dataclass(frozen=True, slots=True)
class Region:
    """Defines one rectangular image region."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ClickDefinition:
    """Defines how a selector should be converted into a click target."""

    anchor: str = "center"


@dataclass(frozen=True, slots=True)
class SelectorDefinition:
    """Defines one selector in the canonical registry."""

    id: UiElementId
    screens: tuple[ScreenType, ...]
    detection_kind: DetectionKind
    status: SelectorStatus
    template_path: Path | None = None
    threshold: float = 0.98
    click: ClickDefinition | None = field(default_factory=ClickDefinition)
    ocr_region: Region | None = None


@dataclass(frozen=True, slots=True)
class SelectorRegistry:
    """Owns canonical selector lookup and validation."""

    selectors: tuple[SelectorDefinition, ...]

    def __post_init__(self) -> None:
        """Ensures selector identifiers remain unique."""

        selector_ids = [selector.id for selector in self.selectors]
        duplicates = {selector_id for selector_id in selector_ids if selector_ids.count(selector_id) > 1}
        if duplicates:
            raise SelectorResolutionError("Duplicate selector ids are not allowed.", duplicates=sorted(duplicates))

    def all(self) -> tuple[SelectorDefinition, ...]:
        """Returns all selector definitions."""

        return self.selectors

    def require(self, selector_id: UiElementId) -> SelectorDefinition:
        """Returns one selector definition or fails fast."""

        for selector in self.selectors:
            if selector.id == selector_id:
                return selector
        raise SelectorResolutionError(f"Unknown selector '{selector_id}'.", selector_id=selector_id)

    def for_screen(self, screen_type: ScreenType) -> tuple[SelectorDefinition, ...]:
        """Returns selectors that can appear on the requested screen."""

        return tuple(selector for selector in self.selectors if screen_type in selector.screens)


def build_default_selector_registry(template_root: Path | None = None) -> SelectorRegistry:
    """Builds the seeded selector registry described by the implementation plan."""

    root = template_root or (Path(__file__).resolve().parents[2] / "templates" / "pnc")
    collection_ids = {
        UiElementId.PNC_BAG_ITEM_ROW,
        UiElementId.PNC_QUEST_ROW,
        UiElementId.PNC_HERO_CARD,
        UiElementId.PNC_CASH_MALL_ENTRY_ROW,
        UiElementId.PNC_GIFT_CENTER_ENTRY_ROW,
        UiElementId.PNC_EVENT_CENTER_EVENT_ROW,
        UiElementId.PNC_CASTLE_LIST_ENTRY,
    }
    ocr_ids = {
        UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION,
        UiElementId.PNC_CASH_MALL_ENTRY_TIMER_REGION,
        UiElementId.PNC_GIFT_CENTER_ENTRY_TITLE_REGION,
        UiElementId.PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION,
        UiElementId.PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION,
        UiElementId.PNC_EVENT_CENTER_ENTRY_TITLE_REGION,
        UiElementId.PNC_EVENT_CENTER_ENTRY_TIMER_REGION,
    }

    seeded_by_screen: dict[ScreenType, list[UiElementId]] = {
        ScreenType.PNC_HOME_CITY: [
            UiElementId.PNC_BOTTOM_NAV_HOME,
            UiElementId.PNC_BOTTOM_NAV_HERO,
            UiElementId.PNC_BOTTOM_NAV_QUEST,
            UiElementId.PNC_BOTTOM_NAV_BAG,
            UiElementId.PNC_BOTTOM_NAV_MAIL,
            UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
            UiElementId.PNC_BOTTOM_NAV_MORE,
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            UiElementId.PNC_HOME_BUILD_BUTTON,
            UiElementId.PNC_HOME_RESEARCH_BUTTON,
            UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
            UiElementId.PNC_HOME_WORLD_SWITCH,
            UiElementId.PNC_HOME_CHARACTER_PANEL,
            UiElementId.PNC_HOME_TOP_RESOURCE_FOOD,
            UiElementId.PNC_HOME_TOP_RESOURCE_WOOD,
            UiElementId.PNC_HOME_TOP_RESOURCE_DIAMOND,
            UiElementId.PNC_HOME_RIGHT_RAIL_CASH_MALL_ICON,
            UiElementId.PNC_HOME_RIGHT_RAIL_GIFT_CENTER_ICON,
            UiElementId.PNC_HOME_RIGHT_RAIL_EVENT_CENTER_ICON,
        ],
        ScreenType.PNC_BAG: [
            UiElementId.PNC_BAG_MAIN_TAB_BAG,
            UiElementId.PNC_BAG_MAIN_TAB_DIAMOND_SHOP,
            UiElementId.PNC_BAG_SUBTAB_RESOURCE,
            UiElementId.PNC_BAG_SUBTAB_SPEEDUP,
            UiElementId.PNC_BAG_SUBTAB_MILITARY,
            UiElementId.PNC_BAG_SUBTAB_TREASURE,
            UiElementId.PNC_BAG_SUBTAB_MISC,
            UiElementId.PNC_BAG_ITEM_ROW,
            UiElementId.PNC_BAG_USE_BUTTON,
            UiElementId.PNC_BAG_USE_IN_BULK_BUTTON,
        ],
        ScreenType.PNC_QUEST_DAILY: [
            UiElementId.PNC_QUEST_TAB_MAIN,
            UiElementId.PNC_QUEST_TAB_DAILY,
            UiElementId.PNC_QUEST_TAB_ALLIANCE_ACTIVITY,
            UiElementId.PNC_QUEST_REWARD_CHEST,
            UiElementId.PNC_QUEST_ROW,
            UiElementId.PNC_QUEST_GO_BUTTON,
            UiElementId.PNC_QUEST_CLAIMED_LABEL,
            UiElementId.PNC_QUEST_RESET_TIMER,
        ],
        ScreenType.PNC_HERO_LIST: [
            UiElementId.PNC_HERO_TAB_HERO,
            UiElementId.PNC_HERO_TAB_UNOBTAINED,
            UiElementId.PNC_HERO_TAB_BAG,
            UiElementId.PNC_HERO_CARD,
            UiElementId.PNC_HERO_FILTER_BUTTON,
        ],
        ScreenType.PNC_HERO_DETAIL_UPGRADE: [
            UiElementId.PNC_HERO_DETAIL_TAB_UPGRADE,
            UiElementId.PNC_HERO_DETAIL_TAB_ENHANCE,
            UiElementId.PNC_HERO_DETAIL_TAB_TROOP_SKILL,
            UiElementId.PNC_HERO_DETAIL_TAB_HERO_SKILL,
            UiElementId.PNC_HERO_EVOLVE_BUTTON,
        ],
        ScreenType.PNC_HERO_DETAIL_ENHANCE: [
            UiElementId.PNC_HERO_DETAIL_TAB_UPGRADE,
            UiElementId.PNC_HERO_DETAIL_TAB_ENHANCE,
            UiElementId.PNC_HERO_DETAIL_TAB_TROOP_SKILL,
            UiElementId.PNC_HERO_DETAIL_TAB_HERO_SKILL,
            UiElementId.PNC_HERO_ENHANCE_BUTTON,
        ],
        ScreenType.PNC_MAIL_LIST: [
            UiElementId.PNC_MAIL_ROW_SYSTEM_MESSAGE,
            UiElementId.PNC_MAIL_ROW_PLAYER_MAIL,
            UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL,
            UiElementId.PNC_MAIL_ROW_BATTLELOG,
            UiElementId.PNC_MAIL_ROW_HUNT_REPORT,
            UiElementId.PNC_MAIL_ROW_HELL_FORTRESS,
            UiElementId.PNC_MAIL_ROW_GATHERING_REPORT,
            UiElementId.PNC_MAIL_ROW_TRANSPORT_REPORT,
        ],
        ScreenType.PNC_SYSTEM_MESSAGE: [
            UiElementId.PNC_SYSTEM_MESSAGE_MARK_AS_READ_BUTTON,
            UiElementId.PNC_SYSTEM_MESSAGE_MANAGE_BUTTON,
        ],
        ScreenType.PNC_ALLIANCE_HOME: [
            UiElementId.PNC_ALLIANCE_TILE_TERRITORY,
            UiElementId.PNC_ALLIANCE_TILE_GIFT_LEVEL,
            UiElementId.PNC_ALLIANCE_TILE_WAR,
            UiElementId.PNC_ALLIANCE_TILE_TECH,
            UiElementId.PNC_ALLIANCE_TILE_TREASURY,
            UiElementId.PNC_ALLIANCE_TILE_RANK,
            UiElementId.PNC_ALLIANCE_TILE_EVENT,
            UiElementId.PNC_ALLIANCE_TILE_MEMBER,
            UiElementId.PNC_ALLIANCE_BOTTOM_TAB_SHOP,
            UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL,
            UiElementId.PNC_ALLIANCE_BOTTOM_TAB_HELP,
            UiElementId.PNC_ALLIANCE_BOTTOM_TAB_OPERATIONS,
        ],
        ScreenType.PNC_CASH_MALL: [
            UiElementId.PNC_CASH_MALL_TAB_DAILY_SALE,
            UiElementId.PNC_CASH_MALL_TAB_MONTHLY_GIFT,
            UiElementId.PNC_CASH_MALL_TAB_TIME_LIMITED_SPECIAL_OFFER,
            UiElementId.PNC_CASH_MALL_TAB_HERO,
            UiElementId.PNC_CASH_MALL_ENTRY_ROW,
            UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION,
            UiElementId.PNC_CASH_MALL_ENTRY_TIMER_REGION,
            UiElementId.PNC_CASH_MALL_ENTRY_PRICE_BUTTON,
            UiElementId.PNC_CASH_MALL_ENTRY_HOT_BADGE,
        ],
        ScreenType.PNC_GIFT_CENTER: [
            UiElementId.PNC_GIFT_CENTER_ENTRY_ROW,
            UiElementId.PNC_GIFT_CENTER_ENTRY_TITLE_REGION,
            UiElementId.PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION,
            UiElementId.PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION,
            UiElementId.PNC_GIFT_CENTER_ENTRY_ALERT_BADGE,
        ],
        ScreenType.PNC_EVENT_CENTER: [
            UiElementId.PNC_EVENT_CENTER_TAB_REGULAR_EVENTS,
            UiElementId.PNC_EVENT_CENTER_TAB_HOLIDAY_EVENTS,
            UiElementId.PNC_EVENT_CENTER_TAB_ABOUT_TO_START,
            UiElementId.PNC_EVENT_CENTER_EVENT_ROW,
            UiElementId.PNC_EVENT_CENTER_ENTRY_TITLE_REGION,
            UiElementId.PNC_EVENT_CENTER_ENTRY_TIMER_REGION,
            UiElementId.PNC_EVENT_CENTER_ENTRY_ALERT_BADGE,
        ],
        ScreenType.PNC_WORLD_MAP: [
            UiElementId.PNC_WORLD_COORDINATE_BAR,
            UiElementId.PNC_WORLD_MY_TERRITORY_LABEL,
            UiElementId.PNC_WORLD_HOME_NAV,
            UiElementId.PNC_WORLD_SEARCH_BUTTON,
            UiElementId.PNC_WORLD_EXPAND_BUTTON,
            UiElementId.PNC_WORLD_TARGET_CASTLE,
        ],
    }

    planned_by_screen: dict[ScreenType, list[UiElementId]] = {
        ScreenType.ANDROID_HOME: [UiElementId.ANDROID_HOME_PNC_ICON],
        ScreenType.PNC_LOGIN: [
            UiElementId.PNC_LOGIN_USERNAME_FIELD,
            UiElementId.PNC_LOGIN_PASSWORD_FIELD,
            UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
        ],
        ScreenType.PNC_CASTLE_SELECTION: [
            UiElementId.PNC_CASTLE_LIST_ENTRY,
            UiElementId.PNC_CASTLE_SELECTED_CHECKMARK,
        ],
        ScreenType.PNC_HOME_CITY: [
            UiElementId.PNC_HOME_BUILDING_UPGRADE_BADGE,
            UiElementId.PNC_HOME_ACADEMY_BUILDING,
        ],
        ScreenType.PNC_BUILDING_DETAILS: [UiElementId.PNC_BUILDING_UPGRADE_BUTTON],
        ScreenType.PNC_ACADEMY: [UiElementId.PNC_RESEARCH_AVAILABLE_BADGE],
        ScreenType.PNC_RESEARCH_TREE: [UiElementId.PNC_RESEARCH_START_BUTTON],
        ScreenType.PNC_GATHER_NODE: [UiElementId.PNC_GATHER_BUTTON],
        ScreenType.PNC_MARCH_CONFIRM: [UiElementId.PNC_MARCH_CONFIRM_BUTTON],
        ScreenType.PNC_CAMPAIGN: [UiElementId.PNC_CAMPAIGN_ENTRY_BUTTON],
        ScreenType.PNC_CAMPAIGN_STAGE: [UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON],
        ScreenType.PNC_POPUP: [UiElementId.PNC_POPUP_CLOSE_BUTTON],
    }

    selectors_by_id: dict[UiElementId, SelectorDefinition] = {}
    for screen, selector_ids in seeded_by_screen.items():
        for selector_id in selector_ids:
            _register_selector(
                selectors_by_id,
                _create_selector(
                    selector_id=selector_id,
                    screen=screen,
                    root=root,
                    collection_ids=collection_ids,
                    ocr_ids=ocr_ids,
                    status=SelectorStatus.SCREENSHOT_SEEDED,
                ),
            )
    for screen, selector_ids in planned_by_screen.items():
        for selector_id in selector_ids:
            _register_selector(
                selectors_by_id,
                _create_selector(
                    selector_id=selector_id,
                    screen=screen,
                    root=root,
                    collection_ids=collection_ids,
                    ocr_ids=ocr_ids,
                    status=SelectorStatus.PLANNED,
                ),
            )
    return SelectorRegistry(selectors=tuple(selectors_by_id.values()))


def _create_selector(
    *,
    selector_id: UiElementId,
    screen: ScreenType,
    root: Path,
    collection_ids: set[UiElementId],
    ocr_ids: set[UiElementId],
    status: SelectorStatus,
) -> SelectorDefinition:
    """Creates one default selector definition with canonical metadata defaults."""

    if status == SelectorStatus.PLANNED:
        return SelectorDefinition(
            id=selector_id,
            screens=(screen,),
            detection_kind=DetectionKind.PLANNED,
            status=status,
            template_path=None,
            click=ClickDefinition() if selector_id not in ocr_ids else None,
        )

    if selector_id in ocr_ids:
        return SelectorDefinition(
            id=selector_id,
            screens=(screen,),
            detection_kind=DetectionKind.OCR_REGION,
            status=status,
            template_path=None,
            click=None,
        )

    detection_kind = DetectionKind.COLLECTION if selector_id in collection_ids else DetectionKind.TEMPLATE
    return SelectorDefinition(
        id=selector_id,
        screens=(screen,),
        detection_kind=detection_kind,
        status=status,
        template_path=root / f"{selector_id.value.lower()}.png",
    )


def _register_selector(
    selectors_by_id: dict[UiElementId, SelectorDefinition],
    selector: SelectorDefinition,
) -> None:
    """Registers one selector or merges it with an existing shared-screen definition."""

    existing = selectors_by_id.get(selector.id)
    if existing is None:
        selectors_by_id[selector.id] = selector
        return
    if (
        existing.detection_kind != selector.detection_kind
        or existing.status != selector.status
        or existing.template_path != selector.template_path
        or existing.threshold != selector.threshold
        or existing.click != selector.click
        or existing.ocr_region != selector.ocr_region
    ):
        raise SelectorResolutionError(
            "Selector ids reused across screens must keep identical metadata.",
            selector_id=selector.id,
        )
    selectors_by_id[selector.id] = SelectorDefinition(
        id=existing.id,
        screens=tuple(dict.fromkeys((*existing.screens, *selector.screens))),
        detection_kind=existing.detection_kind,
        status=existing.status,
        template_path=existing.template_path,
        threshold=existing.threshold,
        click=existing.click,
        ocr_region=existing.ocr_region,
    )
