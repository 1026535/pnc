"""P&C-specific OCR enrichment for dynamic screens without template anchors."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from PIL import Image

from pnc_automation.app.authoring.config.models import CastleIdentity
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.chat import ChatChannel, ChatEntryKind
from pnc_automation.app.pnc.domain.building_catalog import is_upgradeable_primary_screen
from pnc_automation.app.pnc.domain.mail import MailboxType, compose_text_field_selector_ids
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    ObservedTextFieldState,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_coordinate_domain import WorldMapCoordinateDomain
from pnc_automation.app.pnc.navigation.world_map_overview_projection import (
    project_world_coordinate_to_overview_point,
)
from pnc_automation.core.text.normalization import normalize_ocr_text
from pnc_automation.app.pnc.vision.observation_builder import ObservationAdditions
from pnc_automation.app.pnc.vision.observation_request import (
    ObservationRequest,
    world_map_coordinate_dialog_text_field_selector_ids,
)
from pnc_automation.core.vision.ocr.ocr_lines import merge_ocr_lines
from pnc_automation.core.vision.ocr.ocr_service import OcrLine, OcrService
from pnc_automation.app.pnc.vision.pnc_ocr_capabilities import can_attempt_screen_family_ocr
from pnc_automation.app.pnc.vision.screen_classifier import ScreenEvidence
from pnc_automation.app.pnc.vision.selectors import Region, SelectorRegistry
from pnc_automation.app.pnc.vision.spatial_surfaces import (
    build_home_city_spatial_surface,
    build_world_map_spatial_surface,
)
from pnc_automation.app.pnc.vision.text_anchors import (
    DetectedTextAnchor,
    TextAnchorDetector,
    TextAnchorId,
)
from pnc_automation.app.pnc.vision.world_map_coordinates import (
    ParsedWorldViewport,
    parse_world_viewport,
    read_world_coordinate_bar_viewport,
    world_coordinate_text_matches,
)

_HOME_NAV_SELECTOR_BY_TEXT_ANCHOR = {
    TextAnchorId.LABEL_HOME: UiElementId.PNC_BOTTOM_NAV_HOME,
    TextAnchorId.LABEL_HERO: UiElementId.PNC_BOTTOM_NAV_HERO,
    TextAnchorId.LABEL_QUEST: UiElementId.PNC_BOTTOM_NAV_QUEST,
    TextAnchorId.LABEL_BAG: UiElementId.PNC_BOTTOM_NAV_BAG,
    TextAnchorId.LABEL_MAIL: UiElementId.PNC_BOTTOM_NAV_MAIL,
    TextAnchorId.LABEL_ALLIANCE: UiElementId.PNC_BOTTOM_NAV_ALLIANCE,
    TextAnchorId.LABEL_MORE: UiElementId.PNC_BOTTOM_NAV_MORE,
}
_HOME_ACTION_SELECTOR_BY_TEXT_ANCHOR = {
    TextAnchorId.LABEL_BUILD: UiElementId.PNC_HOME_BUILD_BUTTON,
    TextAnchorId.LABEL_HELP: UiElementId.PNC_HOME_BUILD_BUTTON,
    TextAnchorId.LABEL_RESEARCH: UiElementId.PNC_HOME_RESEARCH_BUTTON,
    TextAnchorId.LABEL_CAMPAIGN: UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
}
_MORE_OVERLAY_SELECTOR_BY_TEXT = {
    "SETTINGS": UiElementId.PNC_MORE_SETTINGS,
}
_MORE_MENU_SELECTOR_BY_TEXT = {
    "MANAGECHAR": UiElementId.PNC_MORE_MANAGE_CHAR,
    "LORDINFO": UiElementId.PNC_MORE_LORD_INFO,
    "VIP": UiElementId.PNC_MORE_VIP,
    "IMPROVEMIGHT": UiElementId.PNC_MORE_IMPROVE_MIGHT,
}
_MORE_MENU_SUPPORT_TEXTS = frozenset(
    {
        "RANK",
        "FRIEND",
        "GUIDES",
        "SETTINGS",
    }
)
_MORE_SETTINGS_MENU_SUPPORT_TEXTS = frozenset(
    {
        "ACCOUNT",
        "MANAGECHAR",
        "SEARCH",
        "RANK",
        "SETTINGS",
        "BLACKLIST",
        "LANGUAGE",
        "NOTIFICATIONS",
        "FANPAGE",
        "HELP",
        "FANEVENT",
        "PACK",
    }
)
_LORD_INFO_TAB_TEXTS = frozenset(
    {
        "BOOSTINFO",
        "ALLIANCEINFO",
        "ACHIEVEMENTS",
    }
)
_LORD_INFO_EXCLUDED_NAME_TEXTS = frozenset(
    {
        "LORDINFO",
        "GEAR",
        "GEM",
        "SAURGEM",
        "WARSIGIL",
        "SAURGIL",
        "WARSET",
        "BUILDERSET",
        "TECHSET",
        "TRAINERGEAR",
        "TALENT",
        "BOOSTINFO",
        "ALLIANCEINFO",
        "ACHIEVEMENTS",
    }
)
_VIP_SUPPORT_TEXTS = frozenset(
    {
        "GETPTS",
        "CURRENT",
        "NEXTLEVEL",
        "VIP1",
        "VIP2",
    }
)
_VIP_DAILY_RESET_SUPPORT_TEXTS = frozenset(
    {
        "LOGINEVERYDAYTOGETVIPPTS",
        "GAINVIPPTS",
        "CONSECLOGINDAYS",
        "PTSTOGAINTOMORROW",
        "CLOSE",
    }
)
_HOME_CITY_EVIDENCE_SELECTOR_IDS = frozenset(
    {
        UiElementId.PNC_HOME_BUILD_BUTTON,
        UiElementId.PNC_HOME_RESEARCH_BUTTON,
        UiElementId.PNC_HOME_CAMPAIGN_ENTRY,
        UiElementId.PNC_HOME_WORLD_SWITCH,
        UiElementId.PNC_HOME_CHARACTER_PANEL,
        UiElementId.PNC_HOME_TOP_RESOURCE_FOOD,
        UiElementId.PNC_HOME_TOP_RESOURCE_WOOD,
        UiElementId.PNC_HOME_TOP_RESOURCE_DIAMOND,
    }
)
_WORLD_ROOT_DISTANCE_PATTERN = re.compile(r"\b\d{1,4}\s*KM\b", re.IGNORECASE)
_WORLD_MAP_INVALID_COORDINATE_STATUS_REQUIRED_TEXT = "COORDINATE"
_WORLD_MAP_INVALID_COORDINATE_STATUS_REJECTION_TEXTS = frozenset({"INCORRECT", "INVALID", "WRONG"})
_WORLD_MAP_INVALID_COORDINATE_STATUS_PROMPT_TEXTS = frozenset({"PLEASEENTER", "ENTER", "INPUT"})
_WORLD_MAP_INVALID_COORDINATE_STATUS_PROMPT_QUALIFIERS = frozenset({"CORRECT", "VALID"})
_WORLD_OVERVIEW_MARKER_COMPONENT_GAP_PX = 18
_WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX = 18
_WORLD_OVERVIEW_MARKER_HINT_MIN_CLUSTER_PIXELS = 40
_WORLD_OVERVIEW_MARKER_EDGE_MIN_CLUSTER_PIXELS = 120
_WORLD_OVERVIEW_MARKER_INTERIOR_MIN_CLUSTER_PIXELS = 220
_WORLD_OVERVIEW_COORDINATE_DOMAIN = WorldMapCoordinateDomain.puzzles_and_conquest()
_POPUP_PRIMARY_ACTION_ANCHOR_IDS = frozenset(
    {
        TextAnchorId.LABEL_CONFIRM,
        TextAnchorId.LABEL_JOIN_APPLY,
        TextAnchorId.LABEL_NEXT,
    }
)
_BUILDING_DETAIL_CONFLICT_ANCHOR_IDS = frozenset(
    {
        TextAnchorId.LABEL_ENHANCE,
        TextAnchorId.LABEL_EVOLVE,
        TextAnchorId.LABEL_HERO,
        TextAnchorId.LABEL_HERO_SKILL,
        TextAnchorId.LABEL_TROOP_SKILL,
    }
)
_BUILDING_DETAIL_TITLE_TEXTS = frozenset(
    {
        "ACADEMY",
        "BARRACKS",
        "CASTLE",
        "EMBASSY",
        "FARM",
        "HALLOFWAR",
        "HOSPITAL",
        "IRONMINE",
        "LUMBERMILL",
        "LUMBERYARD",
        "QUARRY",
        "SHOOTINGRANGE",
        "STABLE",
        "TRAININGGROUNDS",
        "WALL",
        "WAREHOUSE",
        "WATCHTOWER",
    }
)
_BUILDING_REQUIREMENT_HEADER_TEXTS = frozenset({"REQUIREMENT"})
_BUILDING_REQUIREMENT_SECTION_TERMINATORS = frozenset({"MATERIALSREQUIRED", "EFFECT"})
_BUILDING_UPGRADE_CONFIRMATION_REQUIRED_SECTION_TEXTS = frozenset({"TIME"})
_BUILDING_UPGRADE_CONFIRMATION_SUPPORT_SECTION_TEXTS = frozenset({"REQUIREMENT", "MATERIALSREQUIRED", "EFFECT"})
_BUILD_QUEUE_HEADER_TEXTS = frozenset({"BUILDQUEUE"})
_BUILD_QUEUE_SUPPORT_TEXTS = frozenset({"SPEEDUP", "GO", "IDLE", "EXPIRED"})
_RESEARCH_QUEUE_HEADER_TEXTS = frozenset({"RESEARCHQUEUE"})
_RESEARCH_QUEUE_SUPPORT_TEXTS = frozenset({"GO", "IDLE"})
_BUILD_QUEUE_ACTIVE_TITLE_PATTERN = re.compile(r"^\s*UPGRADING\s*[:.]?\s*(?P<title>.+?)\s*$", re.IGNORECASE)
_QUEUE_TIMER_PATTERN = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
_CURRENCY_TEXT_PATTERN = re.compile(r"\$\s*\d+(?:[.,]\d+)?")
_RESEARCH_TREE_HEADER_TEXTS = frozenset(
    {
        "MILITARY",
        "DEVELOPMENT",
        "ECONOMY",
        "COMBAT",
    }
)
_DAILY_TO_DO_SECTION_TEXTS = frozenset(
    {
        "CAMP",
        "DAILYQUEST",
    }
)
_CHAT_HEADER_TEXT = "CHAT"
_CHAT_KINGDOM_TEXT = "KINGDOM"
_CHAT_ALLIANCE_TEXT = "ALLIANCE"
_CHAT_EMPTY_INPUT_PLACEHOLDER_TEXT = "PLEASEENTERCONTENT"
_CHAT_ACTIVE_TAB_MIN_WARMTH = 120
_CHAT_ACTIVE_TAB_MIN_DELTA = 80
_CHAT_MAX_SENDER_LENGTH = 64
_CHAT_BOUNDARY_FRAGMENT_MARGIN = 40
_CHAT_ANNOUNCEMENT_MIN_WARM_RATIO = 0.28
_CHAT_NON_TEXT_FOREGROUND_BRIGHTNESS = 90
_CHAT_NON_TEXT_FOREGROUND_VARIANCE = 35
_CHAT_TEXT_BUBBLE_MAX_DENSITY = 0.82
_CHAT_STICKER_MIN_DIMENSION = 72
_CHAT_EMOJI_MAX_DIMENSION = 72
_CHAT_NON_TEXT_MIN_FOREGROUND_PIXELS = 90
_CHAT_ANNOUNCEMENT_TOKENS = frozenset(
    {
        "SYSTEM",
        "ANNOUNCEMENT",
        "NOTICE",
        "GOVERNOR",
        "KINGDOM",
        "SERVER",
        "EVENT",
    }
)
_CHAT_SYSTEM_SENDER_TEXTS = frozenset({"SYSTEMMESSAGE", "SYSTEMANNOUNCEMENT"})
_CHAT_TIMESTAMP_SEPARATOR_PATTERN = re.compile(
    r"^\s*(?:\d{4}[-./]\d{1,2}[-./]\d{1,2}\s*)?\d{1,2}:\d{2}(?::\d{2})?\s*$"
)
_MAIL_HUB_CATEGORY_TEXTS = frozenset(
    {
        "SYSTEMMESSAGE",
        "PLAYERMAIL",
        "ALLIANCEMAIL",
        "BATTLELOG",
        "HUNTREPORT",
        "GATHERINGREPORT",
    }
)
_MAILBOX_HEADER_TO_TYPE = {
    "PLAYERMAIL": MailboxType.PLAYER,
    "ALLIANCEMAIL": MailboxType.ALLIANCE,
}
_MAILBOX_EMPTY_TEXT = "NOREPORTYET"
_MAIL_COMPOSE_HEADER_TEXTS = frozenset({"EDITMAIL", "COMPOSEMAIL"})
_MAIL_COMPOSE_TARGET_PLACEHOLDERS = frozenset({"ENTERPLAYERNAME", "TO"})
_MAIL_COMPOSE_SUBJECT_PLACEHOLDERS = frozenset({"ENTERTITLE", "SUBJECT", "TITLE"})
_MAIL_COMPOSE_BODY_PLACEHOLDERS = frozenset({"ENTERCONTENT", "CONTENT", "MESSAGE", "CANENTERUPTO1000CHARACTERS"})
_PLAYER_TERRITORY_HEADER_TEXTS = frozenset({"PLAYERTERRITORY", "TERRITORY"})
_PLAYER_PROFILE_HEADER_TEXTS = frozenset({"PLAYERPROFILE", "PLAYERINFO", "PERSONALINFO"})
_PLAYER_PROFILE_LAYOUT_SUPPORT_TEXTS = frozenset(
    {
        "GEAR",
        "GEM",
        "SAURGEM",
        "WARSIGIL",
        "SAURGIL",
        "LORDINFO",
        "ALLIANCEINFO",
        "SETTINGS",
        "ACHIEVEMENTS",
    }
)
_ALLIANCE_HOME_HEADER_TEXTS = frozenset({"ALLIANCE"})
_ALLIANCE_HOME_TILE_SELECTOR_BY_TEXT = {
    "ALLIANCETERRITORY": UiElementId.PNC_ALLIANCE_TILE_TERRITORY,
    "ALLIANCEWAR": UiElementId.PNC_ALLIANCE_TILE_WAR,
    "ALLIANCETECH": UiElementId.PNC_ALLIANCE_TILE_TECH,
    "ALLIANCETREASURY": UiElementId.PNC_ALLIANCE_TILE_TREASURY,
    "RANK": UiElementId.PNC_ALLIANCE_TILE_RANK,
    "ALLIANCEEVENT": UiElementId.PNC_ALLIANCE_TILE_EVENT,
    "ALLIANCEMEMBER": UiElementId.PNC_ALLIANCE_TILE_MEMBER,
}
_ALLIANCE_HOME_BOTTOM_TAB_SELECTOR_BY_TEXT = {
    "ALLIANCESHOP": UiElementId.PNC_ALLIANCE_BOTTOM_TAB_SHOP,
    "ALLIANCEMAIL": UiElementId.PNC_ALLIANCE_BOTTOM_TAB_MAIL,
    "ALLIANCEHELP": UiElementId.PNC_ALLIANCE_BOTTOM_TAB_HELP,
    "OPERATIONS": UiElementId.PNC_ALLIANCE_BOTTOM_TAB_OPERATIONS,
}
_ALLIANCE_MEMBER_HEADER_TEXTS = frozenset({"MEMBER", "ALLIANCEMEMBER", "ALLIANCEMEMBERS"})
_ALLIANCE_MEMBER_MANAGE_HEADER_TEXTS = frozenset({"MANAGE", "MEMBERMANAGE"})
_ALLIANCE_MEMBER_ROW_ACTION_TEXTS = frozenset({"MANAGE", "APPOINT", "DEPOSE", "PENDING"})
_MIGHT_RANK_HEADER_TEXTS = frozenset({"MIGHTRANK", "RANK"})
_CHAT_PLAYER_ACTION_PROFILE_TEXTS = frozenset({"PROFILE", "PLAYERPROFILE"})
_PERSONAL_INFO_TEXTS = frozenset({"PERSONALINFO", "PLAYERINFO"})
_DELETE_TEXTS = frozenset({"DELETE", "REMOVE"})
_SEND_TEXTS = frozenset({"SEND"})
_PLAYER_INFO_BUTTON_TEXTS = frozenset({"PLAYERINFO", "INFO"})
_MAIL_BUTTON_TEXTS = frozenset({"MAIL"})
_RESEARCH_TREE_SUPPORT_TOKENS = frozenset(
    {
        "ATK",
        "DEF",
        "HP",
        "MARCHSPEED",
        "TROOPSIZE",
    }
)
_PROGRESS_COUNTER_PATTERN = re.compile(r"^\d+/\d+$")
_PERCENT_PROGRESS_PATTERN = re.compile(r"^\d{1,3}%$")
_ACCOUNT_IDENTIFIER_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LOADING_TEXTS = frozenset(
    {
        "LOADING",
        "CONNECTING",
        "PLEASEWAIT",
    }
)
_LOADING_SUPPORT_TOKENS = frozenset(
    {
        "CONNECT",
        "NETWORK",
        "RETRY",
        "FAILED",
        "WAIT",
    }
)
_LOGIN_USERNAME_LABEL_TEXTS = frozenset(
    {
        "EMAIL",
        "USERNAME",
    }
)
_LOGIN_SUBMIT_TEXTS = frozenset(
    {
        "LOGIN",
        "SIGNIN",
    }
)
_ACCOUNT_SWITCH_HEADER_TEXTS = frozenset(
    {
        "SWITCHACCOUNT",
        "CHOOSEACCOUNT",
        "SELECTACCOUNT",
    }
)


class _ChatViewportEdgeKind(StrEnum):
    """Identifies whether one grouped chat fragment touches the trusted viewport boundary."""

    TOP = "top"
    INTERIOR = "interior"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class _ChatTranscriptViewport:
    """Stores the trusted visible transcript window used for chat-row normalization."""

    top: int
    bottom: int
    content_left: int
    content_right: int


@dataclass(frozen=True, slots=True)
class _ChatRowCandidate:
    """Represents one normalized visible chat-row candidate before entry projection."""

    bounds: Bounds
    source_lines: tuple[OcrLine, ...]
    edge_kind: _ChatViewportEdgeKind
    kind: ChatEntryKind | None = None
    title_text: str | None = None
    message_text: str | None = None
    sender_evidence: str | None = None
    message_evidence: str | None = None
    unsupported_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _TextScreenControlSpec:
    """Describes one OCR-labeled selector expected on an exact building-owned screen."""

    selector_id: UiElementId
    texts: frozenset[str]
    required: bool = False
    min_x_ratio: float = 0.0
    max_x_ratio: float = 1.0
    min_y_ratio: float = 0.0
    max_y_ratio: float = 1.0
    contains_match: bool = False
    alias_selector_ids: tuple[UiElementId, ...] = ()


@dataclass(frozen=True, slots=True)
class _TextScreenDefinition:
    """Defines one exact OCR-classified building-owned or linked screen."""

    screen_type: ScreenType
    header_selector_id: UiElementId
    header_texts: frozenset[str]
    controls: tuple[_TextScreenControlSpec, ...] = ()
    minimum_control_matches: int = 0
    add_back_button: bool = True


@dataclass(frozen=True, slots=True)
class _WarmPixelCluster:
    """Stores one warm-color cluster candidate used by overview-marker detection."""

    bounds: Bounds
    pixel_count: int

    def center(self) -> tuple[int, int]:
        """Returns the integer center point of the cluster bounds."""

        return self.bounds.center()


_TEXT_SCREEN_DEFINITIONS = (
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_CASTLE,
        header_selector_id=UiElementId.PNC_CASTLE_HEADER,
        header_texts=frozenset({"CASTLE"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_CASTLE_TERRITORY_OVERVIEW_BUTTON,
                texts=frozenset({"TERRITORYOVERVIEW"}),
                required=True,
                min_y_ratio=0.06,
                max_y_ratio=0.45,
                contains_match=True,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_CASTLE_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.12,
                max_y_ratio=0.45,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_CASTLE_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,
                texts=frozenset({"SPEEDUP"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_TERRITORY_OVERVIEW,
        header_selector_id=UiElementId.PNC_TERRITORY_OVERVIEW_HEADER,
        header_texts=frozenset({"TERRITORYOVERVIEW"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_HALL_OF_WAR,
        header_selector_id=UiElementId.PNC_HALL_OF_WAR_HEADER,
        header_texts=frozenset({"HALLOFWAR"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_HALL_OF_WAR_PRIORITIZED_UNIT_TYPE_DROPDOWN,
                texts=frozenset({"PRIORITIZEDUNITTYPE"}),
                min_y_ratio=0.1,
                max_y_ratio=0.45,
                contains_match=True,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_HALL_OF_WAR_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.1,
                max_y_ratio=0.45,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_HALL_OF_WAR_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_HALL_OF_WAR_JOIN_RALLY_ATTACK_GO_BUTTON,
                texts=frozenset({"GO"}),
                min_x_ratio=0.62,
                min_y_ratio=0.3,
                max_y_ratio=0.75,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SACRED_TREE,
        header_selector_id=UiElementId.PNC_SACRED_TREE_HEADER,
        header_texts=frozenset({"SACREDTREE"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_SACRED_TREE_BLESSING_RECORD_BUTTON,
                texts=frozenset({"BLESSINGRECORD"}),
                min_y_ratio=0.1,
                max_y_ratio=0.45,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_SACRED_TREE_HARVEST_BUTTON,
                texts=frozenset({"HARVEST"}),
                min_y_ratio=0.65,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SACRED_TREE_BLESSING_RECORD,
        header_selector_id=UiElementId.PNC_SACRED_TREE_BLESSING_RECORD_HEADER,
        header_texts=frozenset({"BLESSINGRECORD"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_RARE_EARTH_FIELD,
        header_selector_id=UiElementId.PNC_RARE_EARTH_FIELD_HEADER,
        header_texts=frozenset({"RAREEARTHFIELD"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_RARE_EARTH_FIELD_EXCHANGE_BUTTON,
                texts=frozenset({"EXCHANGE"}),
                min_y_ratio=0.08,
                max_y_ratio=0.35,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_RARE_EARTH_FIELD_GOLD_PICKAXE_CONTROL,
                texts=frozenset({"GOLDPICKAXE", "GOLDPICKAXEINACTIVE"}),
                min_y_ratio=0.1,
                max_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_RARE_EARTH_FIELD_ENTER_FIELD_BUTTON,
                texts=frozenset({"ENTERFIELD"}),
                min_x_ratio=0.55,
                min_y_ratio=0.3,
                max_y_ratio=0.9,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_DISPATCH,
        header_selector_id=UiElementId.PNC_DISPATCH_HEADER,
        header_texts=frozenset({"DISPATCH"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_DISPATCH_CLEAR_HERO_BUTTON,
                texts=frozenset({"CLEARHERO"}),
                min_y_ratio=0.08,
                max_y_ratio=0.35,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_DISPATCH_BUTTON,
                texts=frozenset({"DISPATCH"}),
                min_y_ratio=0.65,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SANCTUM,
        header_selector_id=UiElementId.PNC_SANCTUM_HEADER,
        header_texts=frozenset({"SANCTUM"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_RELICS,
        header_selector_id=UiElementId.PNC_RELICS_HEADER,
        header_texts=frozenset({"RELICS"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_RELICS_TAB_SET_LIST, texts=frozenset({"SETLIST"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_RELICS_TAB_EVENT_RELIC, texts=frozenset({"EVENTRELIC"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_RELICS_TAB_PRIVATE_COLLECTION,
                texts=frozenset({"PRIVATECOLLECTION"}),
            ),
        ),
        minimum_control_matches=2,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_TRIAL_CHALLENGE,
        header_selector_id=UiElementId.PNC_TRIAL_CHALLENGE_HEADER,
        header_texts=frozenset({"TRIALCHALLENGE"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_TRIAL_CHALLENGE_EXCHANGE_BUTTON, texts=frozenset({"EXCHANGE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_TRIAL_CHALLENGE_PROGRESS_BUTTON, texts=frozenset({"PROGRESS"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRIAL_CHALLENGE_TOTAL_RANK_BUTTON,
                texts=frozenset({"TOTALRANK"}),
            ),
        ),
        minimum_control_matches=2,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_GODDESS_STATUE,
        header_selector_id=UiElementId.PNC_GODDESS_STATUE_HEADER,
        header_texts=frozenset({"GODDESSSTATUE"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_GODDESS_STATUE_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_GODDESS_STATUE_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_GODDESS_STATUE_SPEEDUP_BUTTON,
                texts=frozenset({"SPEEDUP"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_SPEEDUP_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_INSTITUTE,
        header_selector_id=UiElementId.PNC_INSTITUTE_HEADER,
        header_texts=frozenset({"INSTITUTE", "ACADEMY"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_INSTITUTE_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON, texts=frozenset({"DEVELOPMENT"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON, texts=frozenset({"ECONOMY"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_INSTITUTE_MILITARY_BUTTON, texts=frozenset({"MILITARY"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_INSTITUTE_FORTIFICATION_BUTTON,
                texts=frozenset({"FORTIFICATION"}),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_INSTITUTE_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=3,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_WAREHOUSE,
        header_selector_id=UiElementId.PNC_WAREHOUSE_HEADER,
        header_texts=frozenset({"WAREHOUSE"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_WAREHOUSE_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_WAREHOUSE_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_TRAP_WORKSHOP,
        header_selector_id=UiElementId.PNC_TRAP_WORKSHOP_HEADER,
        header_texts=frozenset({"TRAPWORKSHOP"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_UNIT_ADVANTAGE_BUTTON,
                texts=frozenset({"UNITADVANTAGE"}),
                min_y_ratio=0.12,
                max_y_ratio=0.6,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_CRAFT_NOW_BUTTON,
                texts=frozenset({"CRAFTNOW"}),
                min_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_CRAFT_BUTTON,
                texts=frozenset({"CRAFT"}),
                min_y_ratio=0.6,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_COLLECT_BUTTON,
                texts=frozenset({"COLLECT"}),
                min_y_ratio=0.6,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_SPEEDUP_BUTTON,
                texts=frozenset({"SPEEDUP"}),
                min_y_ratio=0.6,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_TRAP_WORKSHOP_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_HERO_HALL,
        header_selector_id=UiElementId.PNC_HERO_HALL_HEADER,
        header_texts=frozenset({"HEROHALL"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_HERO_HALL_RECRUIT_TAB, texts=frozenset({"RECRUIT"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_HERO_HALL_EXCHANGE_TAB, texts=frozenset({"EXCHANGE"})),
        ),
        minimum_control_matches=2,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_WATCHTOWER,
        header_selector_id=UiElementId.PNC_WATCHTOWER_HEADER,
        header_texts=frozenset({"WATCHTOWER"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_WATCHTOWER_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_WATCHTOWER_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_BLACKSMITH,
        header_selector_id=UiElementId.PNC_BLACKSMITH_HEADER,
        header_texts=frozenset({"BLACKSMITH"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BLACKSMITH_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BLACKSMITH_GEAR_ROW, texts=frozenset({"GEAR"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BLACKSMITH_GEM_ROW, texts=frozenset({"GEM"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BLACKSMITH_SAURGEM_ROW, texts=frozenset({"SAURGEM"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BLACKSMITH_HERO_CURIO_ROW,
                texts=frozenset({"HEROCURIO"}),
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BLACKSMITH_WARSIGIL_ROW, texts=frozenset({"WARSIGIL"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BLACKSMITH_ASCEND_ROW, texts=frozenset({"ASCEND"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BLACKSMITH_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_GEAR,
        header_selector_id=UiElementId.PNC_GEAR_HEADER,
        header_texts=frozenset({"GEAR"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_GEM,
        header_selector_id=UiElementId.PNC_GEM_HEADER,
        header_texts=frozenset({"GEM"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SAURGEM,
        header_selector_id=UiElementId.PNC_SAURGEM_HEADER,
        header_texts=frozenset({"SAURGEM"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_SAURGEM_GET_BUTTON,
                texts=frozenset({"GETSAURGEM"}),
                min_y_ratio=0.65,
                contains_match=True,
            ),
        ),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_WARSIGIL,
        header_selector_id=UiElementId.PNC_WARSIGIL_HEADER,
        header_texts=frozenset({"WARSIGIL"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_HERO_CURIO,
        header_selector_id=UiElementId.PNC_HERO_CURIO_HEADER,
        header_texts=frozenset({"HEROCURIO"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_ASCEND,
        header_selector_id=UiElementId.PNC_ASCEND_HEADER,
        header_texts=frozenset({"ASCEND"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_ASCEND_BUTTON, texts=frozenset({"ASCEND"}), min_y_ratio=0.65),
        ),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_ALLIANCE_HALL,
        header_selector_id=UiElementId.PNC_ALLIANCE_HALL_HEADER,
        header_texts=frozenset({"ALLIANCEHALL"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_ALLIANCE_HALL_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_ALLIANCE_HALL_SEND_BACK_BUTTON, texts=frozenset({"SENDBACK"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_ALLIANCE_HALL_REINFORCE_BUTTON, texts=frozenset({"REINFORCE"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_ALLIANCE_HALL_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_MARKET,
        header_selector_id=UiElementId.PNC_MARKET_HEADER,
        header_texts=frozenset({"MARKET"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_MARKET_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_MARKET_RESOURCE_TRANSPORT_BUTTON,
                texts=frozenset({"RESOURCETRANSPORT"}),
                contains_match=True,
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_MARKET_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
        header_selector_id=UiElementId.PNC_ALLIANCE_MEMBER_HEADER,
        header_texts=frozenset({"ALLIANCEMEMBER"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_ALLIANCE_MEMBER_REINFORCE_BUTTON,
                texts=frozenset({"REINFORCE"}),
                required=True,
                min_x_ratio=0.6,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_ALLIANCE_MEMBER_TRANSPORT,
        header_selector_id=UiElementId.PNC_ALLIANCE_MEMBER_HEADER,
        header_texts=frozenset({"ALLIANCEMEMBER"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON,
                texts=frozenset({"TRANSPORT"}),
                required=True,
                min_x_ratio=0.6,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_INFANTRY_BARRACKS,
        header_selector_id=UiElementId.PNC_INFANTRY_BARRACKS_HEADER,
        header_texts=frozenset({"INFANTRYBARRACKS"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON, texts=frozenset({"UNITADVANTAGE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_TRAIN_BUTTON, texts=frozenset({"TRAIN"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_TRAIN_NOW_BUTTON,
                texts=frozenset({"TRAINNOW"}),
                min_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_SPEEDUP_BUTTON, texts=frozenset({"SPEEDUP"}), min_y_ratio=0.6),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_COLLECT_BUTTON, texts=frozenset({"COLLECT"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_CAVALRY_BARRACKS,
        header_selector_id=UiElementId.PNC_CAVALRY_BARRACKS_HEADER,
        header_texts=frozenset({"CAVALRYBARRACKS"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON, texts=frozenset({"UNITADVANTAGE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_TRAIN_BUTTON, texts=frozenset({"TRAIN"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_TRAIN_NOW_BUTTON,
                texts=frozenset({"TRAINNOW"}),
                min_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_SPEEDUP_BUTTON, texts=frozenset({"SPEEDUP"}), min_y_ratio=0.6),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_COLLECT_BUTTON, texts=frozenset({"COLLECT"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_RANGED_BARRACKS,
        header_selector_id=UiElementId.PNC_RANGED_BARRACKS_HEADER,
        header_texts=frozenset({"RANGEDBARRACKS"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON, texts=frozenset({"UNITADVANTAGE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_TRAIN_BUTTON, texts=frozenset({"TRAIN"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_TRAIN_NOW_BUTTON,
                texts=frozenset({"TRAINNOW"}),
                min_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_SPEEDUP_BUTTON, texts=frozenset({"SPEEDUP"}), min_y_ratio=0.6),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_COLLECT_BUTTON, texts=frozenset({"COLLECT"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SIEGE_FACTORY,
        header_selector_id=UiElementId.PNC_SIEGE_FACTORY_HEADER,
        header_texts=frozenset({"SIEGEFACTORY"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_GLORY_LEVEL_BUTTON,
                texts=frozenset({"GLORYLEVEL"}),
                min_y_ratio=0.08,
                max_y_ratio=0.4,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_UNIT_ADVANTAGE_BUTTON, texts=frozenset({"UNITADVANTAGE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_TRAIN_BUTTON, texts=frozenset({"TRAIN"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_TRAIN_NOW_BUTTON,
                texts=frozenset({"TRAINNOW"}),
                min_y_ratio=0.6,
                contains_match=True,
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_SPEEDUP_BUTTON, texts=frozenset({"SPEEDUP"}), min_y_ratio=0.6),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BARRACKS_COLLECT_BUTTON, texts=frozenset({"COLLECT"}), min_y_ratio=0.6),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BARRACKS_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SAUROI_LAIR,
        header_selector_id=UiElementId.PNC_SAUROI_LAIR_HEADER,
        header_texts=frozenset({"SAUROILAIR"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_SAUROI_LAIR_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_SAUREGG,
        header_selector_id=UiElementId.PNC_SAUREGG_HEADER,
        header_texts=frozenset({"SAUREGG"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_SAUREGG_OBTAIN_BUTTON, texts=frozenset({"OBTAIN"}), min_y_ratio=0.65),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_VERSUS_CENTER,
        header_selector_id=UiElementId.PNC_VERSUS_CENTER_HEADER,
        header_texts=frozenset({"VERSUSCENTER"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_VERSUS_CENTER_TAB_ARENA, texts=frozenset({"ARENA"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_VERSUS_CENTER_TAB_EXCHANGE_SHOP,
                texts=frozenset({"EXCHANGESHOP"}),
            ),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_VERSUS_CENTER_HERO_SHOWDOWN_ENTRY,
                texts=frozenset({"HEROSHOWDOWN"}),
                contains_match=True,
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_WALL,
        header_selector_id=UiElementId.PNC_WALL_HEADER,
        header_texts=frozenset({"WALL"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_WALL_DEFENSE_INFO_TILE, texts=frozenset({"DEFENSEINFO"}), required=True),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_WALL_REPAIR_WALL_TILE, texts=frozenset({"REPAIRWALL"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_WALL_UPGRADE_BUTTON,
                texts=frozenset({"UPGRADE"}),
                min_x_ratio=0.55,
                max_y_ratio=0.45,
                alias_selector_ids=(UiElementId.PNC_BUILDING_UPGRADE_BUTTON,),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_DEFENSE_INFO,
        header_selector_id=UiElementId.PNC_DEFENSE_INFO_HEADER,
        header_texts=frozenset({"DEFENSEINFO"}),
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_BUILD_MENU_FIXED_SLOT,
        header_selector_id=UiElementId.PNC_BUILD_HEADER,
        header_texts=frozenset({"BUILD"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_INSTITUTE_OPTION, texts=frozenset({"INSTITUTE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_WAREHOUSE_OPTION, texts=frozenset({"WAREHOUSE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_TRAP_WORKSHOP_OPTION, texts=frozenset({"TRAPWORKSHOP"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BUILD_GODDESS_STATUE_OPTION,
                texts=frozenset({"GODDESSSTATUE"}),
            ),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_BUILD_MENU_LARGE_SLOT,
        header_selector_id=UiElementId.PNC_BUILD_HEADER,
        header_texts=frozenset({"BUILD"}),
        controls=(
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BUILD_ALLIANCE_HALL_OPTION,
                texts=frozenset({"ALLIANCEHALL"}),
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_BLACKSMITH_OPTION, texts=frozenset({"BLACKSMITH"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_MARKET_OPTION, texts=frozenset({"MARKET"})),
        ),
        minimum_control_matches=1,
    ),
    _TextScreenDefinition(
        screen_type=ScreenType.PNC_BUILD_MENU_SMALL_SLOT,
        header_selector_id=UiElementId.PNC_BUILD_HEADER,
        header_texts=frozenset({"BUILD"}),
        controls=(
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_FARM_OPTION, texts=frozenset({"FARM"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_LUMBER_CAMP_OPTION, texts=frozenset({"LUMBERCAMP"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_MOON_WELL_OPTION, texts=frozenset({"MOONWELL"})),
            _TextScreenControlSpec(
                selector_id=UiElementId.PNC_BUILD_RECRUITING_CENTER_OPTION,
                texts=frozenset({"RECRUITINGCENTER"}),
            ),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_INFIRMARY_OPTION, texts=frozenset({"INFIRMARY"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_IRON_MINE_OPTION, texts=frozenset({"IRONMINE"})),
            _TextScreenControlSpec(selector_id=UiElementId.PNC_BUILD_GOLD_MINE_OPTION, texts=frozenset({"GOLDMINE"})),
        ),
        minimum_control_matches=1,
    ),
)


def _build_matching_text_screen_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    request: ObservationRequest,
    observed_screen: ScreenType,
) -> ObservationAdditions | None:
    """Returns the first exact text-screen observation allowed by the current OCR request."""

    for definition in _TEXT_SCREEN_DEFINITIONS:
        if not request.allows_screen(definition.screen_type):
            continue
        if not can_attempt_screen_family_ocr(
            request_screen=definition.screen_type,
            observed_screen=observed_screen,
        ):
            continue
        additions = _build_text_screen_additions(
            image=image,
            lines=lines,
            definition=definition,
        )
        if additions is not None:
            return additions
    return None


def _build_text_screen_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    definition: _TextScreenDefinition,
) -> ObservationAdditions | None:
    """Builds one exact building-owned screen observation from a shared header-and-controls definition."""

    header = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in definition.header_texts,
        max_y=int(image.height * 0.15),
    )
    if header is None:
        return None
    base_visible_elements = _build_text_screen_visible_elements(
        image=image,
        lines=lines,
        definition=definition,
        header=header,
    )
    if base_visible_elements is None:
        if not is_upgradeable_primary_screen(definition.screen_type):
            return None
        confirmation_visible_elements = _build_upgrade_confirmation_visible_elements(
            image=image,
            lines=lines,
            definition=definition,
            header=header,
        )
        if confirmation_visible_elements is None:
            return None
        visible_elements = confirmation_visible_elements
    else:
        visible_elements = base_visible_elements
    _add_upgrade_requirement_controls(
        image=image,
        lines=lines,
        screen_type=definition.screen_type,
        visible_elements=visible_elements,
    )
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(
            ScreenEvidence(
                definition.screen_type,
                f"ocr_text_screen_{definition.screen_type.value}",
            ),
        ),
    )


def _build_text_screen_visible_elements(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    definition: _TextScreenDefinition,
    header: OcrLine,
) -> dict[UiElementId, VisibleElement] | None:
    """Returns the canonical exact-screen controls when the base building-owned layout is present."""

    visible_elements = _make_text_screen_visible_element_seed(
        image=image,
        definition=definition,
        header=header,
    )
    control_matches = 0
    for control in definition.controls:
        line = _find_text_screen_control_line(
            image=image,
            lines=lines,
            control=control,
        )
        if line is None:
            if control.required:
                return None
            continue
        control_matches += 1
        _add_text_screen_control_visible_elements(
            visible_elements=visible_elements,
            control=control,
            line=line,
        )
    if control_matches < definition.minimum_control_matches:
        return None
    return visible_elements


def _build_upgrade_confirmation_visible_elements(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    definition: _TextScreenDefinition,
    header: OcrLine,
) -> dict[UiElementId, VisibleElement] | None:
    """Returns the exact building-owned confirmation layout when upgrade details replace the base controls."""

    upgrade_control = _find_shared_upgrade_control(definition)
    if upgrade_control is None:
        return None
    upgrade_line = _find_text_screen_control_line(
        image=image,
        lines=lines,
        control=upgrade_control,
    )
    if upgrade_line is None:
        return None
    required_section_lines = _find_text_lines_in_texts(
        lines=lines,
        texts=_BUILDING_UPGRADE_CONFIRMATION_REQUIRED_SECTION_TEXTS,
        min_y=int(image.height * 0.3),
    )
    if not required_section_lines:
        return None
    support_section_lines = _find_text_lines_in_texts(
        lines=lines,
        texts=_BUILDING_UPGRADE_CONFIRMATION_SUPPORT_SECTION_TEXTS,
        min_y=int(image.height * 0.35),
    )
    if not support_section_lines:
        return None
    visible_elements = _make_text_screen_visible_element_seed(
        image=image,
        definition=definition,
        header=header,
    )
    _add_text_screen_control_visible_elements(
        visible_elements=visible_elements,
        control=upgrade_control,
        line=upgrade_line,
    )
    panel_lines = [header, upgrade_line, *required_section_lines, *support_section_lines]
    confirm_line = _find_building_upgrade_confirm_line(image=image, lines=lines)
    if confirm_line is not None:
        panel_lines.append(confirm_line)
        visible_elements[UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON] = _make_visible_from_line(
            selector_id=UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
            line=confirm_line,
        )
    visible_elements[UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL] = _make_visible_from_lines(
        selector_id=UiElementId.PNC_BUILDING_UPGRADE_CONFIRMATION_PANEL,
        lines=tuple(panel_lines),
    )
    return visible_elements


def _make_text_screen_visible_element_seed(
    *,
    image: Image.Image,
    definition: _TextScreenDefinition,
    header: OcrLine,
) -> dict[UiElementId, VisibleElement]:
    """Builds the shared exact-screen header and back-button selectors."""

    visible_elements: dict[UiElementId, VisibleElement] = {
        definition.header_selector_id: _make_visible_from_line(
            selector_id=definition.header_selector_id,
            line=header,
        )
    }
    if definition.add_back_button:
        visible_elements[UiElementId.PNC_BACK_BUTTON_TOP_LEFT] = _make_visible(
            selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            x=0,
            y=0,
            width=max(1, int(image.width * 0.12)),
            height=max(1, int(image.height * 0.08)),
        )
    return visible_elements


def _add_text_screen_control_visible_elements(
    *,
    visible_elements: dict[UiElementId, VisibleElement],
    control: _TextScreenControlSpec,
    line: OcrLine,
) -> None:
    """Projects one matched text-screen control into its selector ids and shared aliases."""

    visible_elements[control.selector_id] = _make_visible_from_line(
        selector_id=control.selector_id,
        line=line,
    )
    for alias_selector_id in control.alias_selector_ids:
        visible_elements[alias_selector_id] = _make_visible_from_line(
            selector_id=alias_selector_id,
            line=line,
        )


def _find_shared_upgrade_control(definition: _TextScreenDefinition) -> _TextScreenControlSpec | None:
    """Returns the shared exact-screen control that aliases the canonical building upgrade button."""

    for control in definition.controls:
        if UiElementId.PNC_BUILDING_UPGRADE_BUTTON in control.alias_selector_ids:
            return control
    return None


def _find_text_screen_control_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    control: _TextScreenControlSpec,
) -> OcrLine | None:
    """Returns one OCR line that satisfies a shared exact-screen control specification."""

    min_x = int(image.width * control.min_x_ratio)
    max_x = int(image.width * control.max_x_ratio)
    min_y = int(image.height * control.min_y_ratio)
    max_y = int(image.height * control.max_y_ratio)
    candidate_lines = tuple(
        line
        for line in lines
        if line.bounds.x >= min_x and line.bounds.x <= max_x and line.bounds.y >= min_y and line.bounds.y <= max_y
    )
    for index, line in enumerate(candidate_lines):
        if _text_screen_control_matches(control=control, raw_text=line.text):
            return line
        merged_line = _merge_text_screen_control_candidate(candidate_lines=candidate_lines, index=index)
        if merged_line is not None and _text_screen_control_matches(control=control, raw_text=merged_line.text):
            return merged_line
    return None


def _text_screen_control_matches(*, control: _TextScreenControlSpec, raw_text: str) -> bool:
    """Returns whether one OCR text fragment satisfies the requested exact-screen control contract."""

    normalized_text = normalize_ocr_text(raw_text)
    if normalized_text == "":
        return False
    if control.contains_match:
        return any(text in normalized_text for text in control.texts)
    return normalized_text in control.texts


def _merge_text_screen_control_candidate(
    *,
    candidate_lines: tuple[OcrLine, ...],
    index: int,
) -> OcrLine | None:
    """Returns a merged stacked OCR fragment when one control phrase was split across two rows."""

    if index + 1 >= len(candidate_lines):
        return None
    upper_line = candidate_lines[index]
    lower_line = candidate_lines[index + 1]
    upper_bottom = upper_line.bounds.y + upper_line.bounds.height
    vertical_gap = lower_line.bounds.y - upper_bottom
    if vertical_gap < -max(upper_line.bounds.height, lower_line.bounds.height) * 0.35:
        return None
    if vertical_gap > max(upper_line.bounds.height, lower_line.bounds.height) * 1.2:
        return None
    upper_center_x = upper_line.bounds.x + (upper_line.bounds.width // 2)
    lower_center_x = lower_line.bounds.x + (lower_line.bounds.width // 2)
    allowed_center_delta = max(upper_line.bounds.width, lower_line.bounds.width) * 0.65
    if abs(upper_center_x - lower_center_x) > allowed_center_delta:
        return None
    return merge_ocr_lines(upper_line, lower_line)


def _add_upgrade_requirement_controls(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    screen_type: ScreenType,
    visible_elements: dict[UiElementId, VisibleElement],
) -> None:
    """Adds shared unmet-upgrade-requirement controls for upgradeable building-owned screens."""

    if not is_upgradeable_primary_screen(screen_type):
        return
    header = _find_building_requirement_header_line(image=image, lines=lines)
    if header is None:
        return
    requirement_line = _find_building_requirement_target_line(
        image=image,
        lines=lines,
        header=header,
    )
    go_line = _find_building_requirement_go_line(
        image=image,
        lines=lines,
        header=header,
        requirement_line=requirement_line,
    )
    if go_line is None:
        return
    visible_elements[UiElementId.PNC_BUILDING_REQUIREMENT_HEADER] = _make_visible_from_line(
        selector_id=UiElementId.PNC_BUILDING_REQUIREMENT_HEADER,
        line=header,
    )
    if requirement_line is not None:
        visible_elements[UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL] = _make_visible_from_line(
            selector_id=UiElementId.PNC_BUILDING_REQUIREMENT_TARGET_LABEL,
            line=requirement_line,
        )
    visible_elements[UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON] = _make_visible_from_line(
        selector_id=UiElementId.PNC_BUILDING_REQUIREMENT_GO_BUTTON,
        line=go_line,
    )


def _find_building_requirement_header_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the shared unmet-requirement section header when one upgrade gate is visible."""

    max_x = int(image.width * 0.35)
    return _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _BUILDING_REQUIREMENT_HEADER_TEXTS and line.bounds.x <= max_x,
        min_y=int(image.height * 0.35),
    )


def _find_building_requirement_target_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    header: OcrLine,
) -> OcrLine | None:
    """Returns the first visible prerequisite label listed under the unmet-requirement header."""

    header_bottom = header.bounds.y + header.bounds.height
    max_y = min(image.height, header_bottom + int(image.height * 0.14))
    max_x = int(image.width * 0.65)
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text in {"", "GO"} or normalized_text in _BUILDING_REQUIREMENT_SECTION_TERMINATORS:
            continue
        if line.bounds.y <= header_bottom or line.bounds.y > max_y:
            continue
        if line.bounds.x > max_x:
            continue
        return line
    return None


def _find_building_requirement_go_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    header: OcrLine,
    requirement_line: OcrLine | None,
) -> OcrLine | None:
    """Returns the right-side `Go` affordance associated with one unmet-requirement row when visible."""

    min_y = header.bounds.y
    max_y = min(image.height, header.bounds.y + header.bounds.height + int(image.height * 0.14))
    if requirement_line is not None:
        min_y = max(min_y, requirement_line.bounds.y - requirement_line.bounds.height)
        max_y = min(max_y, requirement_line.bounds.y + requirement_line.bounds.height + int(image.height * 0.03))
    min_x = int(image.width * 0.6)
    for line in lines:
        if normalize_ocr_text(line.text) != "GO":
            continue
        if line.bounds.x < min_x:
            continue
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        return line
    return None


def _find_building_upgrade_confirm_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the shared `Upgrade Now` confirmation affordance shown after the first upgrade tap."""

    min_x = int(image.width * 0.4)
    min_y = int(image.height * 0.2)
    max_y = int(image.height * 0.55)
    for line in lines:
        if normalize_ocr_text(line.text) != "UPGRADENOW":
            continue
        if line.bounds.x < min_x:
            continue
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        return line
    return None


@dataclass(slots=True)
class PncObservationEnricher:
    """Derives P&C screen facts that are more reliable via OCR than selectors."""

    ocr_service: OcrService
    selector_registry: SelectorRegistry | None = None
    text_anchor_detector: TextAnchorDetector = field(default_factory=TextAnchorDetector)

    def enrich(
        self,
        image: Image.Image,
        screen_type: ScreenType,
        visible_elements: Mapping[UiElementId, VisibleElement],
        request: ObservationRequest,
    ) -> ObservationAdditions:
        """Builds OCR-backed bootstrap, fallback-classification, and castle-roster observations."""

        chat_geometry = self._build_chat_geometry_additions(
            image=image,
            screen_type=screen_type,
            request=request,
        )
        if (
            chat_geometry is not None
            and not request.include_popup_guard
            and not request.include_loading_guard
            and not request.include_chat_entries
        ):
            return chat_geometry
        if not request.requires_ocr(screen_type):
            return ObservationAdditions()
        ocr_result = self.ocr_service.read_result(image)
        lines = tuple(sorted(ocr_result.lines, key=lambda line: (line.bounds.y, line.bounds.x)))
        anchors = self.text_anchor_detector.detect(ocr_result)
        status_banner = _build_status_banner_additions(
            image=image,
            lines=lines,
            request=request,
        )
        if request.include_popup_guard:
            popup = _build_popup_additions(image=image, lines=lines, anchors=anchors)
            if popup is not None:
                return popup
        if request.include_loading_guard and screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            loading = _build_loading_additions(image=image, lines=lines)
            if loading is not None:
                return loading
        if request.allows_screen(ScreenType.PNC_WORLD_COORDINATE_DIALOG) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_WORLD_COORDINATE_DIALOG,
            observed_screen=screen_type,
        ):
            coordinate_dialog = self._build_world_map_coordinate_dialog_additions(
                image=image,
                lines=lines,
            )
            if coordinate_dialog is not None:
                return _with_status_banner(coordinate_dialog, status_banner)
        if request.allows_screen(ScreenType.PNC_WORLD_MAP_OVERVIEW) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_WORLD_MAP_OVERVIEW,
            observed_screen=screen_type,
        ):
            overview = self._build_world_map_overview_additions(
                image=image,
                lines=lines,
                request=request,
            )
            if overview is not None:
                return overview
        if request.allows_screen(ScreenType.PNC_WORLD_KINGDOM_LIST) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_WORLD_KINGDOM_LIST,
            observed_screen=screen_type,
        ):
            kingdom_list = _build_world_kingdom_list_additions(image=image, lines=lines)
            if kingdom_list is not None:
                return kingdom_list
        if request.allows_screen(ScreenType.PNC_LOGIN) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_LOGIN,
            observed_screen=screen_type,
        ):
            login = _build_login_additions(image=image, lines=lines)
            if login is not None:
                return login
        if request.allows_screen(ScreenType.PNC_ACCOUNT_SWITCH) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ACCOUNT_SWITCH,
            observed_screen=screen_type,
        ):
            account_switch = _build_account_switch_additions(image=image, lines=lines)
            if account_switch is not None:
                return account_switch
        if request.allows_screen(ScreenType.PNC_LORD_INFO) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_LORD_INFO,
            observed_screen=screen_type,
        ):
            lord_info = _build_lord_info_additions(image=image, lines=lines)
            if lord_info is not None:
                return lord_info
        if request.allows_screen(ScreenType.PNC_PLAYER_TERRITORY) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_PLAYER_TERRITORY,
            observed_screen=screen_type,
        ):
            player_territory = _build_player_territory_additions(image=image, lines=lines)
            if player_territory is not None:
                return player_territory
        if request.allows_screen(ScreenType.PNC_PLAYER_PROFILE) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_PLAYER_PROFILE,
            observed_screen=screen_type,
        ):
            player_profile = _build_player_profile_additions(image=image, lines=lines)
            if player_profile is not None:
                return player_profile
        if request.allows_screen(ScreenType.PNC_VIP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_VIP,
            observed_screen=screen_type,
        ):
            vip = _build_vip_additions(image=image, lines=lines)
            if vip is not None:
                return vip
        if request.allows_screen(ScreenType.PNC_IMPROVE_MIGHT) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_IMPROVE_MIGHT,
            observed_screen=screen_type,
        ):
            improve_might = _build_improve_might_additions(image=image, lines=lines)
            if improve_might is not None:
                return improve_might
        if request.allows_screen(ScreenType.PNC_MORE_MENU) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MORE_MENU,
            observed_screen=screen_type,
        ):
            more_settings_menu = _build_more_settings_menu_additions(image=image, lines=lines)
            if more_settings_menu is not None:
                return more_settings_menu
            more_menu = _build_more_menu_additions(image=image, lines=lines, anchors=anchors)
            if more_menu is not None:
                return more_menu
        text_screen = _build_matching_text_screen_additions(
            image=image,
            lines=lines,
            request=request,
            observed_screen=screen_type,
        )
        if text_screen is not None:
            return text_screen
        if request.allows_screen(ScreenType.PNC_BUILDING_DETAILS) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_BUILDING_DETAILS,
            observed_screen=screen_type,
        ):
            building_detail = _build_building_detail_additions(image=image, lines=lines, anchors=anchors)
            if building_detail is not None:
                return building_detail
        if request.allows_screen(ScreenType.PNC_BUILD_QUEUE) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_BUILD_QUEUE,
            observed_screen=screen_type,
        ):
            build_queue = _build_build_queue_additions(image=image, lines=lines)
            if build_queue is not None:
                return build_queue
        if request.allows_screen(ScreenType.PNC_POPUP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_POPUP,
            observed_screen=screen_type,
        ):
            research_queue_popup = _build_research_queue_popup_additions(image=image, lines=lines)
            if research_queue_popup is not None:
                return research_queue_popup
        if request.allows_screen(ScreenType.PNC_WORLD_MAP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_WORLD_MAP,
            observed_screen=screen_type,
        ):
            world_map = _build_world_map_additions(
                image=image,
                lines=lines,
                anchors=anchors,
                selector_registry=self.selector_registry,
                ocr_service=self.ocr_service,
            )
            if world_map is not None:
                return _with_status_banner(world_map, status_banner)
            world_map_root = _build_world_map_root_additions(
                image=image,
                lines=lines,
                anchors=anchors,
            )
            if world_map_root is not None:
                return _with_status_banner(world_map_root, status_banner)
        if request.allows_screen(ScreenType.PNC_HOME_CITY) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_HOME_CITY,
            observed_screen=screen_type,
        ):
            home_city = _build_home_city_additions(
                image=image,
                lines=lines,
                anchors=anchors,
                visible_elements=visible_elements,
                selector_registry=self.selector_registry,
            )
            if home_city is not None:
                return home_city
            home_city_root = _build_home_city_root_additions(
                image=image,
                anchors=anchors,
                visible_elements=visible_elements,
            )
            if home_city_root is not None:
                return home_city_root
        if request.allows_screen(ScreenType.PNC_BAG) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_BAG,
            observed_screen=screen_type,
        ):
            bag = _build_bag_additions(image=image, lines=lines, anchors=anchors)
            if bag is not None:
                return bag
        if request.allows_screen(ScreenType.PNC_ALLIANCE_JOIN) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ALLIANCE_JOIN,
            observed_screen=screen_type,
        ):
            alliance_join = _build_alliance_join_additions(image=image, lines=lines)
            if alliance_join is not None:
                return alliance_join
        if request.allows_screen(ScreenType.PNC_MAIL_COMPOSE_POPUP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MAIL_COMPOSE_POPUP,
            observed_screen=screen_type,
        ):
            mail_compose = self._build_mail_compose_additions(
                image=image,
                lines=lines,
                request=request,
            )
            if mail_compose is not None:
                return mail_compose
        if request.allows_screen(ScreenType.PNC_MAIL_THREAD) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MAIL_THREAD,
            observed_screen=screen_type,
        ):
            mail_thread = _build_mail_thread_additions(image=image, lines=lines)
            if mail_thread is not None:
                return mail_thread
        if request.allows_screen(ScreenType.PNC_MAILBOX_LIST) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MAILBOX_LIST,
            observed_screen=screen_type,
        ):
            mailbox = _build_mailbox_additions(image=image, lines=lines, request=request)
            if mailbox is not None:
                return mailbox
        if request.allows_screen(ScreenType.PNC_ALLIANCE_HOME) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ALLIANCE_HOME,
            observed_screen=screen_type,
        ):
            alliance_home = _build_alliance_home_additions(image=image, lines=lines)
            if alliance_home is not None:
                return alliance_home
        if request.allows_screen(ScreenType.PNC_MAIL_HUB) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MAIL_HUB,
            observed_screen=screen_type,
        ):
            mail_hub = _build_mail_hub_additions(image=image, lines=lines)
            if mail_hub is not None:
                return mail_hub
        if request.allows_screen(ScreenType.PNC_CHAT) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_CHAT,
            observed_screen=screen_type,
        ):
            chat = self._build_chat_additions(
                image=image,
                lines=lines,
                request=request,
            )
            if chat is not None:
                return chat
        if request.allows_screen(ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
            observed_screen=screen_type,
        ):
            chat_player_actions = _build_chat_player_action_popup_additions(image=image, lines=lines)
            if chat_player_actions is not None:
                return chat_player_actions
        if request.allows_screen(ScreenType.PNC_ALLIANCE_MEMBER_LIST) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
            observed_screen=screen_type,
        ):
            alliance_members = _build_alliance_member_list_additions(image=image, lines=lines)
            if alliance_members is not None:
                return alliance_members
        if request.allows_screen(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
            observed_screen=screen_type,
        ):
            alliance_member_manage = _build_alliance_member_manage_popup_additions(image=image, lines=lines)
            if alliance_member_manage is not None:
                return alliance_member_manage
        if request.allows_screen(ScreenType.PNC_DAILY_TO_DO) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_DAILY_TO_DO,
            observed_screen=screen_type,
        ):
            daily_to_do = _build_daily_to_do_additions(image=image, lines=lines)
            if daily_to_do is not None:
                return daily_to_do
        if request.allows_screen(ScreenType.PNC_MIGHT_RANK) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_MIGHT_RANK,
            observed_screen=screen_type,
        ):
            might_rank = _build_might_rank_additions(image=image, lines=lines)
            if might_rank is not None:
                return might_rank
        if request.allows_screen(ScreenType.PNC_RESEARCH_TREE) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_RESEARCH_TREE,
            observed_screen=screen_type,
        ):
            research_tree = _build_research_tree_additions(image=image, lines=lines)
            if research_tree is not None:
                return research_tree
        if not request.allows_screen(ScreenType.PNC_CASTLE_SELECTION) or not can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_CASTLE_SELECTION,
            observed_screen=screen_type,
        ):
            return ObservationAdditions() if status_banner is None else status_banner
        entries = _extract_castle_entries(image=image, lines=lines, anchors=anchors)
        if not _looks_like_castle_selection(anchors, entries):
            return ObservationAdditions() if status_banner is None else status_banner

        visible_elements_by_id: dict[UiElementId, VisibleElement] = {}
        if entries:
            visible_elements_by_id[UiElementId.PNC_CASTLE_LIST_ENTRY] = _make_visible_from_entry(
                selector_id=UiElementId.PNC_CASTLE_LIST_ENTRY,
                entry=entries[0],
            )
        selected_entry = next((entry for entry in entries if entry.selected), None)
        if selected_entry is not None:
            visible_elements_by_id[UiElementId.PNC_CASTLE_SELECTED_CHECKMARK] = _make_visible(
                selector_id=UiElementId.PNC_CASTLE_SELECTED_CHECKMARK,
                x=max(0, selected_entry.bounds.x + int(selected_entry.bounds.width * 0.82)),
                y=selected_entry.bounds.y,
                width=max(1, int(selected_entry.bounds.width * 0.18)),
                height=selected_entry.bounds.height,
            )
        return ObservationAdditions(
            visible_elements=visible_elements_by_id,
            list_entries=entries,
            screen_evidence=(ScreenEvidence(ScreenType.PNC_CASTLE_SELECTION, "manage_char_roster"),),
            current_castle=_entry_to_current_castle(selected_entry),
            current_castle_evidence=None if selected_entry is None else CurrentCastleEvidenceKind.EXACT,
        )

    def _build_chat_geometry_additions(
        self,
        *,
        image: Image.Image,
        screen_type: ScreenType,
        request: ObservationRequest,
    ) -> ObservationAdditions | None:
        """Returns geometry-first chat evidence when the shared tab and footer chrome is visible."""

        if not request.allows_candidate_screen(ScreenType.PNC_CHAT) and not request.allows_screen(ScreenType.PNC_CHAT):
            return None
        if screen_type not in {ScreenType.UNKNOWN, ScreenType.PNC_CHAT, ScreenType.PNC_HOME_CITY, ScreenType.PNC_WORLD_MAP}:
            return None
        if self.selector_registry is None:
            return None
        input_region = self._require_chat_region(UiElementId.PNC_CHAT_INPUT_FIELD, image=image)
        if _region_brightness(image, input_region) > 60:
            return None
        kingdom_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_KINGDOM, image=image)
        alliance_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_ALLIANCE, image=image)
        active_chat_channel = _resolve_active_chat_channel(
            image=image,
            kingdom_region=kingdom_region,
            alliance_region=alliance_region,
        )
        if active_chat_channel is None:
            return None
        chat_state = self._build_proven_chat_state_additions(
            image=image,
            request=request,
            active_chat_channel=active_chat_channel,
        )
        return ObservationAdditions(
            screen_evidence=(ScreenEvidence(ScreenType.PNC_CHAT, "geometry_chat_overlay"),),
            active_chat_channel=chat_state.active_chat_channel,
            text_field_states=chat_state.text_field_states,
            chat_draft_empty=chat_state.chat_draft_empty,
            chat_draft_text=chat_state.chat_draft_text,
        )

    def _build_chat_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        request: ObservationRequest,
    ) -> ObservationAdditions | None:
        """Returns OCR-proven chat evidence plus shared chat state when the request requires it."""

        chat = _build_chat_overlay_additions(image=image, lines=lines)
        if chat is None:
            return None
        chat_state = self._build_proven_chat_state_additions(image=image, request=request)
        return ObservationAdditions(
            visible_elements=chat.visible_elements,
            list_entries=self._extract_chat_message_entries(image=image, lines=lines),
            screen_evidence=chat.screen_evidence,
            active_chat_channel=chat_state.active_chat_channel,
            text_field_states=chat_state.text_field_states,
            chat_draft_empty=chat_state.chat_draft_empty,
            chat_draft_text=chat_state.chat_draft_text,
        )

    def _extract_chat_message_entries(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> tuple[DetectedListEntry, ...]:
        """Extracts normalized chat rows using the trusted chat viewport and one canonical candidate pipeline."""

        viewport = self._resolve_chat_transcript_viewport(image=image)
        candidate_lines = [line for line in lines if _is_chat_message_candidate_line(line=line, viewport=viewport)]
        grouped_rows: list[_ChatRowCandidate] = []
        for row_lines in _group_lines_by_vertical_gap(candidate_lines, gap=max(24, image.height // 36)):
            if not row_lines:
                continue
            bounds = _entry_bounds_from_lines(image=image, row_lines=row_lines)
            grouped_rows.append(
                _ChatRowCandidate(
                    bounds=bounds,
                    source_lines=tuple(row_lines),
                    edge_kind=_chat_row_edge_kind(bounds=bounds, viewport=viewport),
                )
            )
        normalized_rows = _normalize_chat_row_candidates(image=image, raw_candidates=tuple(grouped_rows), viewport=viewport)
        return tuple(
            _chat_row_entry_from_candidate(candidate=candidate, visible_order=visible_order)
            for visible_order, candidate in enumerate(candidate for candidate in normalized_rows if candidate.kind is not None)
        )

    def _resolve_chat_transcript_viewport(self, *, image: Image.Image) -> _ChatTranscriptViewport:
        """Returns the shared trusted transcript viewport bounded by the chat tabs and input field."""

        input_region = self._require_chat_region(UiElementId.PNC_CHAT_INPUT_FIELD, image=image)
        kingdom_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_KINGDOM, image=image)
        alliance_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_ALLIANCE, image=image)
        return _ChatTranscriptViewport(
            top=max(int(image.height * 0.14), max(kingdom_region.y + kingdom_region.height, alliance_region.y + alliance_region.height) + 12),
            bottom=max(1, input_region.y - 12),
            content_left=max(0, int(image.width * 0.14)),
            content_right=min(image.width, int(image.width * 0.78)),
        )

    def _build_proven_chat_state_additions(
        self,
        *,
        image: Image.Image,
        request: ObservationRequest,
        active_chat_channel: ChatChannel | None = None,
    ) -> ObservationAdditions:
        """Returns active-channel and draft facts for one observation that has already proven chat."""

        if not request.include_chat_state:
            return ObservationAdditions()
        input_region = self._require_chat_region(UiElementId.PNC_CHAT_INPUT_FIELD, image=image)
        if active_chat_channel is None:
            kingdom_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_KINGDOM, image=image)
            alliance_region = self._require_chat_region(UiElementId.PNC_CHAT_TAB_ALLIANCE, image=image)
            active_chat_channel = _resolve_active_chat_channel(
                image=image,
                kingdom_region=kingdom_region,
                alliance_region=alliance_region,
            )
        chat_draft_state = self._read_text_field_state(
            image=image,
            selector_id=UiElementId.PNC_CHAT_INPUT_FIELD,
            region=input_region,
            empty_placeholders=frozenset({_CHAT_EMPTY_INPUT_PLACEHOLDER_TEXT}),
        )
        return ObservationAdditions(
            active_chat_channel=active_chat_channel,
            text_field_states={UiElementId.PNC_CHAT_INPUT_FIELD: chat_draft_state},
            chat_draft_empty=chat_draft_state.empty,
            chat_draft_text=chat_draft_state.text,
        )

    def _build_mail_compose_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        request: ObservationRequest,
    ) -> ObservationAdditions | None:
        """Returns OCR-backed compose-popup evidence plus shared text-field state."""

        del request
        if self.selector_registry is None:
            return None
        header_line = _find_header_line(lines=lines, header_texts=_MAIL_COMPOSE_HEADER_TEXTS, max_y=int(image.height * 0.35))
        send_line = _find_first_line_in_texts(lines=lines, texts=_SEND_TEXTS, min_y=int(image.height * 0.6))
        if header_line is None:
            return None
        visible_elements: dict[UiElementId, VisibleElement] = {}
        text_field_states: dict[UiElementId, ObservedTextFieldState] = {}
        for selector_id in compose_text_field_selector_ids():
            text_field_states[selector_id] = self._build_observed_text_field_state(
                image=image,
                selector_id=selector_id,
            )
            visible_elements[selector_id] = self._materialize_selector_visible(selector_id=selector_id, image=image)
        for selector_id in (
            UiElementId.PNC_MAIL_COMPOSE_CLOSE_BUTTON,
            UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
        ):
            try:
                visible_elements[selector_id] = self._materialize_selector_visible(selector_id=selector_id, image=image)
            except SelectorResolutionError:
                continue
        if header_line is not None:
            visible_elements[UiElementId.PNC_MAIL_COMPOSE_HEADER] = _make_visible_from_line(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_HEADER,
                line=header_line,
            )
        if send_line is not None:
            visible_elements[UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON] = _make_visible_from_line(
                selector_id=UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
                line=send_line,
            )
        return ObservationAdditions(
            visible_elements=visible_elements,
            screen_evidence=(ScreenEvidence(ScreenType.PNC_MAIL_COMPOSE_POPUP, "ocr_mail_compose_popup"),),
            text_field_states=text_field_states,
        )

    def _build_observed_text_field_state(
        self,
        *,
        image: Image.Image,
        selector_id: UiElementId,
    ) -> ObservedTextFieldState:
        """Builds the shared text-field state for one selector-backed OCR region."""

        region = self._require_selector_region(selector_id, image=image)
        return self._read_text_field_state(
            image=image,
            selector_id=selector_id,
            region=region,
            empty_placeholders=_empty_text_placeholders(selector_id),
        )

    def _read_text_field_state(
        self,
        *,
        image: Image.Image,
        selector_id: UiElementId,
        region: object,
        empty_placeholders: frozenset[str],
    ) -> ObservedTextFieldState:
        """Reads one selector-backed text region into the shared observed field-state model."""

        raw_text = self.ocr_service.read_text(image, region).strip()
        normalized_text = normalize_ocr_text(raw_text)
        if normalized_text == "" or normalized_text in empty_placeholders or _is_empty_chat_draft_text(normalized_text):
            return ObservedTextFieldState(selector_id=selector_id, text=None, empty=True)
        return ObservedTextFieldState(selector_id=selector_id, text=raw_text, empty=False)

    def _materialize_selector_visible(self, *, selector_id: UiElementId, image: Image.Image) -> VisibleElement:
        """Materializes one geometry-backed visible selector from the shared registry."""

        if self.selector_registry is None:
            raise SelectorResolutionError(
                "Selector materialization requires the shared selector registry.",
                selector_id=selector_id,
            )
        selector = self.selector_registry.require(selector_id)
        if selector.relative_bounds is None:
            raise SelectorResolutionError(
                "Selector materialization requires normalized relative bounds.",
                selector_id=selector_id,
            )
        return selector.relative_bounds.materialize(selector_id=selector_id, image_size=image.size)

    def _require_chat_region(self, selector_id: UiElementId, *, image: Image.Image) -> object:
        """Materializes one shared chat selector region from the canonical registry."""

        return self._require_selector_region(selector_id, image=image)

    def _require_selector_region(self, selector_id: UiElementId, *, image: Image.Image) -> object:
        """Materializes one shared selector OCR region from the canonical registry."""

        if self.selector_registry is None:
            raise SelectorResolutionError(
                "Shared OCR region extraction requires the selector registry.",
                selector_id=selector_id,
            )
        selector = self.selector_registry.require(selector_id)
        if selector.relative_bounds is None:
            raise SelectorResolutionError(
                "Shared OCR region extraction requires normalized selector bounds.",
                selector_id=selector_id,
            )
        return selector.relative_bounds.materialize_region(image_size=image.size)

    def _build_world_map_coordinate_dialog_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
    ) -> ObservationAdditions | None:
        """Returns OCR-backed coordinate-dialog evidence plus committed field state."""

        if self.selector_registry is None:
            return None
        label_min_y = int(image.height * 0.32)
        label_max_y = int(image.height * 0.55)
        if (
            _find_line_with_normalized_text(lines=lines, normalized_text="K", min_y=label_min_y, max_y=label_max_y) is None
            or _find_line_with_normalized_text(lines=lines, normalized_text="X", min_y=label_min_y, max_y=label_max_y) is None
            or _find_line_with_normalized_text(lines=lines, normalized_text="Y", min_y=label_min_y, max_y=label_max_y) is None
        ):
            return None
        go_line = _find_line_with_normalized_text(
            lines=lines,
            normalized_text="GO",
            min_y=int(image.height * 0.45),
            max_y=int(image.height * 0.7),
        )
        if go_line is None:
            return None
        visible_elements: dict[UiElementId, VisibleElement] = {}
        text_field_states: dict[UiElementId, ObservedTextFieldState] = {}
        parsed_fields: dict[UiElementId, int] = {}
        for selector_id in world_map_coordinate_dialog_text_field_selector_ids():
            state = self._build_observed_text_field_state(image=image, selector_id=selector_id)
            parsed_value = _parse_world_coordinate_dialog_field_text(selector_id=selector_id, text=state.text)
            if parsed_value is None:
                return None
            parsed_fields[selector_id] = parsed_value
            text_field_states[selector_id] = state
            visible_elements[selector_id] = self._materialize_selector_visible(selector_id=selector_id, image=image)
        if parsed_fields[UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD] <= 0:
            return None
        for selector_id in (
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
            UiElementId.PNC_WORLD_COORDINATE_DIALOG_KEYBOARD_OK_BUTTON,
        ):
            visible_elements[selector_id] = self._materialize_selector_visible(selector_id=selector_id, image=image)
        visible_elements[UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON] = _make_visible_from_line(
            selector_id=UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
            line=go_line,
        )
        return ObservationAdditions(
            visible_elements=visible_elements,
            screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_COORDINATE_DIALOG, "ocr_world_coordinate_dialog"),),
            text_field_states=text_field_states,
        )

    def _build_world_map_overview_additions(
        self,
        *,
        image: Image.Image,
        lines: tuple[OcrLine, ...],
        request: ObservationRequest,
    ) -> ObservationAdditions | None:
        """Returns OCR-backed world-map overview chrome plus fixed control geometry."""

        if self.selector_registry is None:
            return None
        header_line = _find_world_map_overview_header_line(image=image, lines=lines)
        if header_line is None:
            return None
        visible_elements: dict[UiElementId, VisibleElement] = {
            UiElementId.PNC_WORLD_OVERVIEW_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_WORLD_OVERVIEW_HEADER,
                line=header_line,
            ),
        }
        map_region_element = self._materialize_selector_visible(
            selector_id=UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
            image=image,
        )
        visible_elements[UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION] = map_region_element
        for selector_id in (
            UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
            UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
            UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON,
            UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON,
            UiElementId.PNC_WORLD_OVERVIEW_RECENTER_REGION,
        ):
            visible_elements[selector_id] = self._materialize_selector_visible(selector_id=selector_id, image=image)
        marker_element = _build_world_map_overview_viewport_marker(
            image=image,
            map_region_bounds=map_region_element.bounds,
            expected_coordinate=request.expected_world_coordinate,
        )
        if marker_element is not None:
            visible_elements[UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER] = marker_element
        return ObservationAdditions(
            visible_elements=visible_elements,
            screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_OVERVIEW, "ocr_world_map_overview"),),
        )


def _build_player_territory_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the Player Territory screen when OCR exposes its header and Player Info action."""

    header = _find_header_line(lines=lines, header_texts=_PLAYER_TERRITORY_HEADER_TEXTS, max_y=int(image.height * 0.18))
    player_info = _find_first_line_in_texts(lines=lines, texts=_PLAYER_INFO_BUTTON_TEXTS, min_y=int(image.height * 0.18))
    if header is None or player_info is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_PLAYER_TERRITORY_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                line=header,
            ),
            UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON: _make_visible_from_line(
                selector_id=UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                line=player_info,
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_PLAYER_TERRITORY, "ocr_player_territory"),),
    )


def _build_player_profile_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the remote player-profile screen and visible profile name when OCR matches the layout."""

    header = _find_header_line(lines=lines, header_texts=_PLAYER_PROFILE_HEADER_TEXTS, max_y=int(image.height * 0.18))
    if header is None and not _has_remote_profile_layout_support(lines):
        return None
    name_line = (
        _find_profile_name_line(
            image=image,
            lines=lines,
            excluded_texts=_PLAYER_PROFILE_HEADER_TEXTS | _MAIL_BUTTON_TEXTS | _PERSONAL_INFO_TEXTS,
        )
        if header is not None
        else _find_profile_name_line(
            image=image,
            lines=lines,
            excluded_texts=_PLAYER_PROFILE_LAYOUT_SUPPORT_TEXTS | _MAIL_BUTTON_TEXTS,
            min_y_ratio=0.0,
            max_y_ratio=0.18,
        )
    )
    if name_line is None:
        return None
    visible_elements = {
        UiElementId.PNC_PLAYER_PROFILE_HEADER: (
            _make_visible_from_line(
                selector_id=UiElementId.PNC_PLAYER_PROFILE_HEADER,
                line=header,
            )
            if header is not None
            else _make_visible(
                selector_id=UiElementId.PNC_PLAYER_PROFILE_HEADER,
                x=0,
                y=0,
                width=image.width,
                height=max(1, int(image.height * 0.14)),
                extracted_text=name_line.text.strip(),
            )
        ),
        UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL: _make_visible_from_line(
            selector_id=UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL,
            line=name_line,
        ),
    }
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_PLAYER_PROFILE, "ocr_player_profile"),),
        profile_player_name=name_line.text.strip(),
    )


def _build_mail_hub_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the shared mail hub when OCR exposes mailbox category rows."""

    category_max_y = int(image.height * 0.93)
    visible_elements: dict[UiElementId, VisibleElement] = {}
    for line in lines:
        if line.bounds.y > category_max_y:
            continue
        normalized_text = normalize_ocr_text(line.text)
        selector_id = _mail_hub_selector_id(normalized_text)
        if selector_id is None or selector_id in visible_elements:
            continue
        visible_elements[selector_id] = _make_visible_from_mail_hub_row(
            image=image,
            selector_id=selector_id,
            line=line,
        )
    if UiElementId.PNC_MAIL_ROW_PLAYER_MAIL not in visible_elements and UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL not in visible_elements:
        return None
    header = _find_first_line_in_texts(lines=lines, texts=frozenset({"MAIL"}), max_y=120)
    if len(visible_elements) == 1 and header is None:
        return None
    if header is not None:
        visible_elements[UiElementId.PNC_MAIL_HEADER] = _make_visible_from_line(
            selector_id=UiElementId.PNC_MAIL_HEADER,
            line=header,
        )
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MAIL_HUB, "ocr_mail_hub"),),
    )


def _build_alliance_home_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns alliance-home selectors when OCR exposes alliance tiles plus the lower tab bar."""

    header = _find_header_line(lines=lines, header_texts=_ALLIANCE_HOME_HEADER_TEXTS, max_y=int(image.height * 0.12))
    if header is None:
        return None
    visible_elements: dict[UiElementId, VisibleElement] = {}
    tile_min_y = int(image.height * 0.45)
    tile_max_y = int(image.height * 0.86)
    bottom_tab_min_y = int(image.height * 0.88)
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        selector_id = _ALLIANCE_HOME_TILE_SELECTOR_BY_TEXT.get(normalized_text)
        if selector_id is not None and tile_min_y <= line.bounds.y <= tile_max_y and selector_id not in visible_elements:
            visible_elements[selector_id] = _make_visible_from_line(selector_id=selector_id, line=line)
            continue
        if line.bounds.y >= bottom_tab_min_y:
            for bottom_tab_text, selector_id in _ALLIANCE_HOME_BOTTOM_TAB_SELECTOR_BY_TEXT.items():
                if selector_id in visible_elements or not _matches_alliance_home_bottom_tab_text(
                    normalized_text=normalized_text,
                    expected_text=bottom_tab_text,
                ):
                    continue
                visible_elements[selector_id] = _make_visible_from_bottom_nav_line_segment(
                    image=image,
                    selector_id=selector_id,
                    line=line,
                    normalized_text_segment=bottom_tab_text,
                )
    if not any(selector_id in _ALLIANCE_HOME_TILE_SELECTOR_BY_TEXT.values() for selector_id in visible_elements):
        return None
    if not any(selector_id in _ALLIANCE_HOME_BOTTOM_TAB_SELECTOR_BY_TEXT.values() for selector_id in visible_elements):
        return None
    status_banner = _find_alliance_home_status_banner_line(image=image, lines=lines)
    if status_banner is not None:
        visible_elements[UiElementId.PNC_STATUS_BANNER] = _make_status_banner_visible_element(status_banner)
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ALLIANCE_HOME, "ocr_alliance_home"),),
    )


def _build_status_banner_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    request: ObservationRequest,
) -> ObservationAdditions | None:
    """Returns transient in-game status banners that task follow-up handling must preserve."""

    if request.allows_screen(ScreenType.PNC_ALLIANCE_HOME):
        alliance_status_banner = _find_alliance_home_status_banner_line(image=image, lines=lines)
        if alliance_status_banner is not None:
            return _build_status_banner_additions_from_line(alliance_status_banner)
    if request.allows_screen(ScreenType.PNC_WORLD_MAP):
        world_map_status_banner = _find_world_map_invalid_coordinate_status_banner_line(image=image, lines=lines)
        if world_map_status_banner is not None:
            return _build_status_banner_additions_from_line(world_map_status_banner)
    return None


def _build_status_banner_additions_from_line(status_banner: OcrLine | None) -> ObservationAdditions | None:
    """Builds the canonical visible status-banner addition from one OCR line when present."""

    if status_banner is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_STATUS_BANNER: _make_status_banner_visible_element(status_banner)
        }
    )


def _make_status_banner_visible_element(status_banner: OcrLine) -> VisibleElement:
    """Builds the canonical visible selector for one transient in-game status banner."""

    return _make_visible_from_line(
        selector_id=UiElementId.PNC_STATUS_BANNER,
        line=status_banner,
    )


def _with_status_banner(
    additions: ObservationAdditions,
    status_banner: ObservationAdditions | None,
) -> ObservationAdditions:
    """Carries transient status-banner OCR alongside a stronger screen-specific enrichment result."""

    if status_banner is None:
        return additions
    return replace(
        additions,
        visible_elements={
            **additions.visible_elements,
            **status_banner.visible_elements,
        },
    )


def _build_mailbox_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    request: ObservationRequest,
) -> ObservationAdditions | None:
    """Returns one mailbox list plus visible thread rows and empty-state facts."""

    header = _find_mailbox_header_line(image=image, lines=lines)
    if header is None:
        return None
    mailbox_type = _MAILBOX_HEADER_TO_TYPE.get(normalize_ocr_text(header.text))
    if mailbox_type is None:
        return None
    if request.expected_mailbox is not None and mailbox_type != request.expected_mailbox:
        return None
    empty_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text=_MAILBOX_EMPTY_TEXT,
        min_y=int(image.height * 0.18),
    )
    thread_entries = () if empty_line is not None else _extract_mail_thread_entries(image=image, lines=lines)
    visible_elements: dict[UiElementId, VisibleElement] = {
        UiElementId.PNC_MAIL_HEADER: _make_visible_from_line(selector_id=UiElementId.PNC_MAIL_HEADER, line=header),
    }
    manage_line = _find_first_line_in_texts(lines=lines, texts=frozenset({"MANAGE"}), max_y=int(image.height * 0.18))
    if manage_line is not None:
        visible_elements[UiElementId.PNC_MAILBOX_MANAGE_BUTTON] = _make_visible_from_line(
            selector_id=UiElementId.PNC_MAILBOX_MANAGE_BUTTON,
            line=manage_line,
        )
    read_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: "READ" in normalize_ocr_text(line.text),
        max_y=int(image.height * 0.18),
    )
    if read_line is not None:
        visible_elements[UiElementId.PNC_MAILBOX_MARK_ALL_AS_READ_BUTTON] = _make_visible_from_line(
            selector_id=UiElementId.PNC_MAILBOX_MARK_ALL_AS_READ_BUTTON,
            line=read_line,
        )
    if empty_line is not None:
        visible_elements[UiElementId.PNC_MAILBOX_EMPTY_LABEL] = _make_visible_from_line(
            selector_id=UiElementId.PNC_MAILBOX_EMPTY_LABEL,
            line=empty_line,
        )
    elif thread_entries:
        visible_elements[UiElementId.PNC_MAIL_THREAD_ROW] = _make_visible_from_entry(
            selector_id=UiElementId.PNC_MAIL_THREAD_ROW,
            entry=thread_entries[0],
        )
    return ObservationAdditions(
        visible_elements=visible_elements,
        list_entries=thread_entries,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MAILBOX_LIST, "ocr_mailbox_list"),),
        mailbox_type=mailbox_type,
        mailbox_empty=empty_line is not None,
    )


def _build_mail_thread_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns one opened mail thread plus visible message lines."""

    header = _find_mailbox_header_line(image=image, lines=lines)
    if header is None:
        return None
    mailbox_type = _MAILBOX_HEADER_TO_TYPE.get(normalize_ocr_text(header.text))
    if mailbox_type is None:
        return None
    message_entries = _extract_mail_message_entries(image=image, lines=lines)
    delete_line = _find_first_line_in_texts(lines=lines, texts=_DELETE_TEXTS, min_y=int(image.height * 0.78))
    visible_elements = {
        UiElementId.PNC_MAIL_HEADER: _make_visible_from_line(selector_id=UiElementId.PNC_MAIL_HEADER, line=header),
    }
    if delete_line is not None:
        visible_elements[UiElementId.PNC_MAIL_THREAD_DELETE_BUTTON] = _make_visible_from_line(
            selector_id=UiElementId.PNC_MAIL_THREAD_DELETE_BUTTON,
            line=delete_line,
        )
    if not message_entries and delete_line is None:
        return None
    return ObservationAdditions(
        visible_elements=visible_elements,
        list_entries=message_entries,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MAIL_THREAD, "ocr_mail_thread"),),
        mailbox_type=mailbox_type,
    )


def _build_chat_player_action_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the chat player-action popup when OCR exposes the Profile action."""

    del image
    profile_line = _find_first_line_in_texts(lines=lines, texts=_CHAT_PLAYER_ACTION_PROFILE_TEXTS)
    if profile_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON: _make_visible_from_line(
                selector_id=UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON,
                line=profile_line,
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP, "ocr_chat_player_actions"),),
    )


def _build_alliance_member_list_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the alliance-member list and visible member rows."""

    header = _find_header_line(lines=lines, header_texts=_ALLIANCE_MEMBER_HEADER_TEXTS, max_y=int(image.height * 0.18))
    if header is None:
        return None
    entries = _extract_grouped_named_rows(
        image=image,
        lines=lines,
        kind=ListEntryKind.ALLIANCE_MEMBER,
        min_y=int(image.height * 0.18),
        excluded_texts=_ALLIANCE_MEMBER_HEADER_TEXTS | _PERSONAL_INFO_TEXTS | _MAIL_BUTTON_TEXTS,
        ignored_title_texts=_ALLIANCE_MEMBER_ROW_ACTION_TEXTS,
        action_texts=_ALLIANCE_MEMBER_ROW_ACTION_TEXTS,
        action_x_ratio=0.88,
    )
    if not entries:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_ALLIANCE_MEMBER_ROW: _make_visible_from_entry(
                selector_id=UiElementId.PNC_ALLIANCE_MEMBER_ROW,
                entry=entries[0],
            )
        },
        list_entries=entries,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ALLIANCE_MEMBER_LIST, "ocr_alliance_member_list"),),
    )


def _build_alliance_member_manage_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the alliance-member manage popup when OCR exposes Personal Info."""

    header = _find_header_line(lines=lines, header_texts=_ALLIANCE_MEMBER_MANAGE_HEADER_TEXTS, max_y=int(image.height * 0.4))
    personal_info = _find_first_line_in_texts(lines=lines, texts=_PERSONAL_INFO_TEXTS)
    if header is None or personal_info is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON: _make_visible_from_line(
                selector_id=UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON,
                line=personal_info,
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP, "ocr_alliance_member_manage"),),
    )


def _build_might_rank_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the Might Rank screen and visible ranked-player rows."""

    header = _find_header_line(lines=lines, header_texts=_MIGHT_RANK_HEADER_TEXTS, max_y=int(image.height * 0.18))
    if header is None:
        return None
    entries = _extract_grouped_named_rows(
        image=image,
        lines=lines,
        kind=ListEntryKind.RANKED_PLAYER,
        min_y=int(image.height * 0.18),
        excluded_texts=_MIGHT_RANK_HEADER_TEXTS | _PERSONAL_INFO_TEXTS | _MAIL_BUTTON_TEXTS,
        action_x_ratio=0.9,
        normalize_title=_normalize_ranked_player_title,
    )
    if not entries:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_MIGHT_RANK_ROW: _make_visible_from_entry(
                selector_id=UiElementId.PNC_MIGHT_RANK_ROW,
                entry=entries[0],
            )
        },
        list_entries=entries,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MIGHT_RANK, "ocr_might_rank"),),
    )


def _empty_text_placeholders(selector_id: UiElementId) -> frozenset[str]:
    """Returns the known placeholder texts that imply one empty selector-backed field."""

    if selector_id == UiElementId.PNC_MAIL_COMPOSE_TARGET_FIELD:
        return _MAIL_COMPOSE_TARGET_PLACEHOLDERS
    if selector_id == UiElementId.PNC_MAIL_COMPOSE_SUBJECT_FIELD:
        return _MAIL_COMPOSE_SUBJECT_PLACEHOLDERS
    if selector_id == UiElementId.PNC_MAIL_COMPOSE_BODY_FIELD:
        return _MAIL_COMPOSE_BODY_PLACEHOLDERS
    return frozenset()


def _parse_world_coordinate_dialog_field_text(*, selector_id: UiElementId, text: str | None) -> int | None:
    """Returns one committed coordinate-dialog field value from OCR text when it is parseable."""

    if text is None:
        return None
    stripped = text.strip()
    if stripped == "":
        return None
    match = re.search(r"\d+", stripped)
    if match is None:
        return None
    value = int(match.group(0))
    if selector_id == UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD and value <= 0:
        return None
    return value


def _find_world_map_overview_header_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the overview header line that names the current kingdom when it is visible."""

    max_y = int(image.height * 0.2)
    for line in lines:
        if line.bounds.y > max_y:
            continue
        normalized_text = normalize_ocr_text(line.text)
        if re.search(r"K[:：]?\d+", normalized_text) is None:
            continue
        return line
    return None


def _build_world_map_overview_viewport_marker(
    *,
    image: Image.Image,
    map_region_bounds: Bounds,
    expected_coordinate: tuple[int, int] | None,
) -> VisibleElement | None:
    """Returns the current overview viewport marker when one warm marker cluster is visible inside the calibrated map region."""

    local_map_region = Bounds(x=0, y=0, width=map_region_bounds.width, height=map_region_bounds.height)
    crop = image.crop(
        (
            map_region_bounds.x,
            map_region_bounds.y,
            map_region_bounds.x + map_region_bounds.width,
            map_region_bounds.y + map_region_bounds.height,
        )
    ).convert("RGB")
    clusters = _merge_world_map_overview_marker_clusters(_find_world_map_overview_marker_components(crop))
    if not clusters:
        return None
    expected_local_point = (
        project_world_coordinate_to_overview_point(
            coordinate=expected_coordinate,
            bounds=_WORLD_OVERVIEW_COORDINATE_DOMAIN.bounds,
            map_region_bounds=local_map_region,
        )
        if expected_coordinate is not None
        else None
    )
    candidate = _select_world_map_overview_marker_cluster(
        clusters=clusters,
        local_map_region=local_map_region,
        expected_local_point=expected_local_point,
    )
    if candidate is None:
        return None
    candidate_bounds = Bounds(
        x=map_region_bounds.x + candidate.bounds.x,
        y=map_region_bounds.y + candidate.bounds.y,
        width=candidate.bounds.width,
        height=candidate.bounds.height,
    )
    local_action_point = _resolve_world_map_overview_marker_action_point(
        cluster_bounds=candidate.bounds,
        local_map_region=local_map_region,
    )
    if expected_local_point is not None and _bounds_contains_point_with_padding(
        candidate.bounds,
        expected_local_point,
        padding=max(8, _WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX // 2),
    ):
        local_action_point = expected_local_point
    action_point = (
        map_region_bounds.x + local_action_point[0],
        map_region_bounds.y + local_action_point[1],
    )
    return VisibleElement(
        selector_id=UiElementId.PNC_WORLD_OVERVIEW_VIEWPORT_MARKER,
        bounds=candidate_bounds,
        confidence=1.0,
        source_kind=VisibleElementSourceKind.GEOMETRY,
        action_point=action_point,
    )


def _select_world_map_overview_marker_cluster(
    *,
    clusters: tuple[_WarmPixelCluster, ...],
    local_map_region: Bounds,
    expected_local_point: tuple[int, int] | None,
) -> _WarmPixelCluster | None:
    """Returns the best warm marker cluster using the expected-point hint when available, otherwise one conservative live heuristic."""

    if expected_local_point is not None:
        hinted_clusters = tuple(
            cluster for cluster in clusters if cluster.pixel_count >= _WORLD_OVERVIEW_MARKER_HINT_MIN_CLUSTER_PIXELS
        )
        if not hinted_clusters:
            return None
        return min(hinted_clusters, key=lambda cluster: _distance_squared(cluster.center(), expected_local_point))
    edge_clusters = tuple(
        cluster
        for cluster in clusters
        if cluster.pixel_count >= _WORLD_OVERVIEW_MARKER_EDGE_MIN_CLUSTER_PIXELS
        and _cluster_touches_map_edge(cluster.bounds, local_map_region, margin=_WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX)
    )
    if edge_clusters:
        return max(edge_clusters, key=lambda cluster: cluster.pixel_count)
    interior_clusters = tuple(
        cluster for cluster in clusters if cluster.pixel_count >= _WORLD_OVERVIEW_MARKER_INTERIOR_MIN_CLUSTER_PIXELS
    )
    if not interior_clusters:
        return None
    return max(interior_clusters, key=lambda cluster: cluster.pixel_count)


def _find_world_map_overview_marker_components(image: Image.Image) -> tuple[_WarmPixelCluster, ...]:
    """Returns contiguous warm-color components inside one overview-map crop."""

    pixels = image.load()
    width = image.width
    height = image.height
    warm_mask = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            warm_mask[y][x] = _is_world_map_overview_marker_pixel(pixels[x, y])
    visited = [[False] * width for _ in range(height)]
    components: list[_WarmPixelCluster] = []
    for y in range(height):
        for x in range(width):
            if not warm_mask[y][x] or visited[y][x]:
                continue
            queue: deque[tuple[int, int]] = deque(((x, y),))
            visited[y][x] = True
            left = right = x
            top = bottom = y
            pixel_count = 0
            while queue:
                current_x, current_y = queue.popleft()
                pixel_count += 1
                left = min(left, current_x)
                right = max(right, current_x)
                top = min(top, current_y)
                bottom = max(bottom, current_y)
                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if not (0 <= next_x < width and 0 <= next_y < height):
                        continue
                    if not warm_mask[next_y][next_x] or visited[next_y][next_x]:
                        continue
                    visited[next_y][next_x] = True
                    queue.append((next_x, next_y))
            if pixel_count < 6:
                continue
            components.append(
                _WarmPixelCluster(
                    bounds=Bounds(
                        x=left,
                        y=top,
                        width=(right - left) + 1,
                        height=(bottom - top) + 1,
                    ),
                    pixel_count=pixel_count,
                )
            )
    return tuple(components)


def _merge_world_map_overview_marker_clusters(
    clusters: tuple[_WarmPixelCluster, ...],
) -> tuple[_WarmPixelCluster, ...]:
    """Returns warm-color clusters after merging nearby fragments from the same live marker glow."""

    merged: list[_WarmPixelCluster] = []
    for cluster in sorted(clusters, key=lambda current: current.pixel_count, reverse=True):
        for index, current in enumerate(merged):
            if _bounds_overlap_with_gap(current.bounds, cluster.bounds, gap=_WORLD_OVERVIEW_MARKER_COMPONENT_GAP_PX):
                merged[index] = _WarmPixelCluster(
                    bounds=_union_bounds(current.bounds, cluster.bounds),
                    pixel_count=current.pixel_count + cluster.pixel_count,
                )
                break
        else:
            merged.append(cluster)
    return tuple(sorted(merged, key=lambda cluster: cluster.pixel_count, reverse=True))


def _is_world_map_overview_marker_pixel(rgb: tuple[int, int, int]) -> bool:
    """Returns whether one RGB pixel belongs to the warm orange viewport-marker family seen in live overview captures."""

    red, green, blue = rgb
    return red >= 175 and 45 <= green <= 220 and blue <= 125 and red - blue >= 105


def _cluster_touches_map_edge(bounds: Bounds, map_region_bounds: Bounds, *, margin: int) -> bool:
    """Returns whether one candidate cluster hugs a calibrated overview-map edge within the requested margin."""

    right = bounds.x + bounds.width
    bottom = bounds.y + bounds.height
    map_right = map_region_bounds.x + map_region_bounds.width
    map_bottom = map_region_bounds.y + map_region_bounds.height
    return (
        bounds.x <= map_region_bounds.x + margin
        or bounds.y <= map_region_bounds.y + margin
        or right >= map_right - margin
        or bottom >= map_bottom - margin
    )


def _resolve_world_map_overview_marker_action_point(
    *,
    cluster_bounds: Bounds,
    local_map_region: Bounds,
) -> tuple[int, int]:
    """Returns the best marker action point from one selected cluster, compensating for the clipped edge-marker shape when needed."""

    left_touched = cluster_bounds.x <= local_map_region.x + _WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX
    top_touched = cluster_bounds.y <= local_map_region.y + _WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX
    right_touched = (
        cluster_bounds.x + cluster_bounds.width
        >= local_map_region.x + local_map_region.width - _WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX
    )
    bottom_touched = (
        cluster_bounds.y + cluster_bounds.height
        >= local_map_region.y + local_map_region.height - _WORLD_OVERVIEW_MARKER_EDGE_MARGIN_PX
    )
    if not any((left_touched, top_touched, right_touched, bottom_touched)):
        return cluster_bounds.center()
    if left_touched and not right_touched:
        action_x = min(
            cluster_bounds.x + cluster_bounds.width - 1,
            cluster_bounds.x + max(8, int(round(cluster_bounds.width * 0.4))),
        )
    elif right_touched and not left_touched:
        action_x = cluster_bounds.x + cluster_bounds.width - 1
    else:
        action_x = cluster_bounds.center()[0]
    if top_touched and not bottom_touched:
        action_y = min(
            cluster_bounds.y + cluster_bounds.height - 1,
            cluster_bounds.y + max(6, int(round(cluster_bounds.height * 0.38))),
        )
    elif bottom_touched and not top_touched:
        action_y = cluster_bounds.y + cluster_bounds.height - 1
    else:
        action_y = cluster_bounds.center()[1]
    return (action_x, action_y)


def _bounds_contains_point_with_padding(bounds: Bounds, point: tuple[int, int], *, padding: int) -> bool:
    """Returns whether one point lies inside or immediately adjacent to the provided bounds."""

    return (
        bounds.x - padding <= point[0] <= bounds.x + bounds.width + padding
        and bounds.y - padding <= point[1] <= bounds.y + bounds.height + padding
    )


def _bounds_overlap_with_gap(first: Bounds, second: Bounds, *, gap: int) -> bool:
    """Returns whether two bounds overlap or nearly touch once the requested gap margin is applied."""

    return not (
        second.x + second.width < first.x - gap
        or second.x > first.x + first.width + gap
        or second.y + second.height < first.y - gap
        or second.y > first.y + first.height + gap
    )


def _union_bounds(first: Bounds, second: Bounds) -> Bounds:
    """Returns one bounding box that spans both input bounds."""

    left = min(first.x, second.x)
    top = min(first.y, second.y)
    right = max(first.x + first.width, second.x + second.width)
    bottom = max(first.y + first.height, second.y + second.height)
    return Bounds(x=left, y=top, width=right - left, height=bottom - top)


def _distance_squared(first: tuple[int, int], second: tuple[int, int]) -> int:
    """Returns one squared pixel distance used to compare expected-point proximity without float overhead."""

    delta_x = first[0] - second[0]
    delta_y = first[1] - second[1]
    return (delta_x * delta_x) + (delta_y * delta_y)


def _build_world_kingdom_list_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns OCR-backed evidence for the kingdom-list screen opened from overview."""

    del image
    for line in lines:
        if normalize_ocr_text(line.text) != "KINGDOMLIST":
            continue
        return ObservationAdditions(
            visible_elements={
                UiElementId.PNC_WORLD_KINGDOM_LIST_HEADER: _make_visible_from_line(
                    selector_id=UiElementId.PNC_WORLD_KINGDOM_LIST_HEADER,
                    line=line,
                ),
            },
            screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_KINGDOM_LIST, "ocr_world_kingdom_list"),),
        )
    return None


def _mail_hub_selector_id(normalized_text: str) -> UiElementId | None:
    """Returns the mail-hub selector that matches one normalized category label."""

    if normalized_text == "SYSTEMMESSAGE":
        return UiElementId.PNC_MAIL_ROW_SYSTEM_MESSAGE
    if normalized_text == "PLAYERMAIL":
        return UiElementId.PNC_MAIL_ROW_PLAYER_MAIL
    if normalized_text == "ALLIANCEMAIL":
        return UiElementId.PNC_MAIL_ROW_ALLIANCE_MAIL
    if normalized_text == "BATTLELOG":
        return UiElementId.PNC_MAIL_ROW_BATTLELOG
    if normalized_text == "HUNTREPORT":
        return UiElementId.PNC_MAIL_ROW_HUNT_REPORT
    if normalized_text == "HELLFORTRESS":
        return UiElementId.PNC_MAIL_ROW_HELL_FORTRESS
    if normalized_text == "GATHERINGREPORT":
        return UiElementId.PNC_MAIL_ROW_GATHERING_REPORT
    if normalized_text == "TRANSPORTREPORT":
        return UiElementId.PNC_MAIL_ROW_TRANSPORT_REPORT
    return None


def _matches_alliance_home_bottom_tab_text(*, normalized_text: str, expected_text: str) -> bool:
    """Returns whether one OCR line matches the requested alliance-home bottom-tab label."""

    if expected_text in normalized_text:
        return True
    if abs(len(normalized_text) - len(expected_text)) > 2:
        return False
    return _bounded_edit_distance(left=normalized_text, right=expected_text, max_distance=2) <= 2


def _find_alliance_home_status_banner_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the transient alliance-home status banner when the mail tab is gameplay-gated."""

    return _find_line_matching(
        lines=lines,
        predicate=lambda line: "PLEASECLEAR" in normalize_ocr_text(line.text) and "FIRST" in normalize_ocr_text(line.text),
        min_y=int(image.height * 0.2),
        max_y=int(image.height * 0.38),
    )


def _find_world_map_invalid_coordinate_status_banner_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the transient world-map coordinate-jump rejection banner after an invalid magnifier search."""

    return _find_line_matching(
        lines=lines,
        predicate=lambda line: _matches_world_map_invalid_coordinate_status_text(normalize_ocr_text(line.text)),
        max_y=int(image.height * 0.45),
    )


def _matches_world_map_invalid_coordinate_status_text(normalized_text: str) -> bool:
    """Returns whether normalized OCR text describes the world-map invalid-coordinate rejection."""

    if _WORLD_MAP_INVALID_COORDINATE_STATUS_REQUIRED_TEXT not in normalized_text:
        return False
    if any(text in normalized_text for text in _WORLD_MAP_INVALID_COORDINATE_STATUS_REJECTION_TEXTS):
        return True
    return (
        any(text in normalized_text for text in _WORLD_MAP_INVALID_COORDINATE_STATUS_PROMPT_QUALIFIERS)
        and any(text in normalized_text for text in _WORLD_MAP_INVALID_COORDINATE_STATUS_PROMPT_TEXTS)
    )


def _find_mailbox_header_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the mailbox header line when OCR exposes a supported mailbox title."""

    return _find_header_line(
        lines=lines,
        header_texts=frozenset(_MAILBOX_HEADER_TO_TYPE),
        max_y=int(image.height * 0.18),
    )


def _find_header_line(
    *,
    lines: tuple[OcrLine, ...],
    header_texts: frozenset[str],
    max_y: int,
) -> OcrLine | None:
    """Returns the first OCR line that matches one supported screen header."""

    return _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in header_texts,
        max_y=max_y,
    )


def _find_first_line_in_texts(
    *,
    lines: tuple[OcrLine, ...],
    texts: frozenset[str],
    min_y: int = 0,
    max_y: int | None = None,
) -> OcrLine | None:
    """Returns the first OCR line whose normalized text matches one supported label set."""

    return _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in texts,
        min_y=min_y,
        max_y=max_y,
    )


def _find_text_lines_in_texts(
    *,
    lines: tuple[OcrLine, ...],
    texts: frozenset[str],
    min_y: int = 0,
    max_y: int | None = None,
) -> tuple[OcrLine, ...]:
    """Returns all OCR lines whose normalized text matches one supported label set."""

    return tuple(
        line
        for line in lines
        if line.bounds.y >= min_y
        and (max_y is None or line.bounds.y <= max_y)
        and normalize_ocr_text(line.text) in texts
    )


def _extract_mail_thread_entries(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> tuple[DetectedListEntry, ...]:
    """Extracts visible mailbox thread rows from OCR lines."""

    candidate_lines = [
        line
        for line in lines
        if line.bounds.y >= int(image.height * 0.08)
        and line.bounds.y <= int(image.height * 0.9)
        and normalize_ocr_text(line.text) not in _MAIL_HUB_CATEGORY_TEXTS
        and normalize_ocr_text(line.text) not in _MAIL_COMPOSE_HEADER_TEXTS
        and normalize_ocr_text(line.text) not in _DELETE_TEXTS
    ]
    grouped_rows = _group_lines_by_vertical_gap(candidate_lines, gap=max(28, image.height // 32))
    entries: list[DetectedListEntry] = []
    for row_lines in grouped_rows:
        if not row_lines:
            continue
        date_line = next((line for line in row_lines if _looks_like_mail_date_text(line.text)), None)
        content_lines = [line for line in row_lines if not _looks_like_mail_date_text(line.text)]
        if not content_lines:
            continue
        sender_line = content_lines[0]
        sender_name = sender_line.text.strip()
        if sender_name == "":
            continue
        preview_lines = content_lines[1:]
        preview_text = " ".join(line.text.strip() for line in preview_lines if line.text.strip() != "") or None
        date_text = None if date_line is None else date_line.text.strip()
        bounds = _entry_bounds_from_lines(image=image, row_lines=row_lines)
        entries.append(
            DetectedListEntry(
                kind=ListEntryKind.MAIL_THREAD,
                bounds=bounds,
                title_text=sender_name,
                subtitle_text=preview_text,
                action_point=(bounds.x + bounds.width // 2, bounds.y + bounds.height // 2),
                metadata={
                    "sender_name": sender_name,
                    "preview_text": preview_text,
                    "date_text": date_text,
                },
            )
        )
    return tuple(entries)


def _extract_mail_message_entries(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> tuple[DetectedListEntry, ...]:
    """Extracts visible mail-thread message lines from OCR text."""

    entries: list[DetectedListEntry] = []
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if line.bounds.y < int(image.height * 0.18):
            continue
        if normalized_text in _DELETE_TEXTS or normalized_text in _MAILBOX_HEADER_TO_TYPE:
            continue
        if normalized_text == "":
            continue
        entries.append(
            DetectedListEntry(
                kind=ListEntryKind.MAIL_MESSAGE,
                bounds=Bounds(x=0, y=line.bounds.y, width=image.width, height=max(line.bounds.height + 8, 18)),
                title_text=line.text.strip(),
                action_point=(image.width // 2, line.bounds.y + max(line.bounds.height // 2, 1)),
                metadata={"timestamp_text": line.text.strip() if _looks_like_mail_date_text(line.text) else None},
            )
        )
    return tuple(entries)


def _normalize_chat_row_candidates(
    *,
    image: Image.Image,
    raw_candidates: tuple[_ChatRowCandidate, ...],
    viewport: _ChatTranscriptViewport,
) -> tuple[_ChatRowCandidate, ...]:
    """Normalizes grouped OCR fragments into one canonical stream of supported or unsupported chat rows."""

    normalized: list[_ChatRowCandidate] = []
    index = 0
    while index < len(raw_candidates):
        candidate = raw_candidates[index]
        next_candidate = None if index + 1 >= len(raw_candidates) else raw_candidates[index + 1]
        if _looks_like_chat_timestamp_separator_text(_chat_row_combined_text(candidate)):
            index += 1
            continue
        inline_player = _try_build_inline_player_chat_candidate(candidate)
        if inline_player is not None:
            normalized.append(inline_player)
            index += 1
            continue
        announcement = _try_build_announcement_chat_candidate(image=image, candidate=candidate)
        if announcement is not None:
            normalized.append(announcement)
            index += 1
            continue
        grouped_player = _try_build_grouped_player_chat_candidate(candidate)
        if grouped_player is not None:
            normalized.append(grouped_player)
            index += 1
            continue
        split_player = _try_build_split_player_chat_candidate(image=image, sender_candidate=candidate, message_candidate=next_candidate)
        if split_player is not None:
            normalized.append(split_player)
            index += 2
            continue
        if _is_absorbed_duplicate_sender_fragment(candidate=candidate, following_candidate=next_candidate):
            index += 1
            continue
        image_only_player = _try_build_image_only_player_chat_candidate(
            image=image,
            candidate=candidate,
            next_candidate=next_candidate,
            viewport=viewport,
        )
        if image_only_player is not None:
            normalized.append(image_only_player)
            index += 1
            continue
        if _is_chat_boundary_fragment(candidate):
            index += 1
            continue
        unsupported_reason = "sender_only" if _looks_like_sender_only_chat_candidate(candidate) else "message_only" if _looks_like_message_only_chat_candidate(candidate) else "ambiguous_merge"
        normalized.append(_build_unsupported_chat_candidate(candidate=candidate, reason=unsupported_reason))
        index += 1
    return tuple(normalized)


def _chat_row_entry_from_candidate(*, candidate: _ChatRowCandidate, visible_order: int) -> DetectedListEntry:
    """Projects one normalized chat-row candidate into the shared detected-list entry model."""

    if candidate.kind is None:
        raise SelectorResolutionError("Only classified chat-row candidates can be projected as entries.")
    message_text = candidate.message_text if isinstance(candidate.message_text, str) and candidate.message_text != "" else candidate.title_text or ""
    subtitle_text = None if candidate.title_text is None or message_text == candidate.title_text else message_text
    metadata: dict[str, object] = {
        "chat_entry_kind": candidate.kind.value,
        "message_text": message_text,
        "message_preview": message_text,
        "visible_order": visible_order,
    }
    if candidate.sender_evidence is not None:
        metadata["sender_evidence"] = candidate.sender_evidence
    if candidate.message_evidence is not None:
        metadata["message_evidence"] = candidate.message_evidence
    if candidate.unsupported_reason is not None:
        metadata["unsupported_reason"] = candidate.unsupported_reason
    return DetectedListEntry(
        kind=ListEntryKind.CHAT_MESSAGE,
        bounds=candidate.bounds,
        title_text=candidate.title_text,
        subtitle_text=subtitle_text,
        action_point=candidate.bounds.center() if candidate.kind == ChatEntryKind.PLAYER else None,
        metadata=metadata,
    )


def _try_build_inline_player_chat_candidate(candidate: _ChatRowCandidate) -> _ChatRowCandidate | None:
    """Parses the OCR-merged single-line `Sender: message` shape when it remains trustworthy."""

    if len(candidate.source_lines) != 1:
        return None
    match = re.match(r"^\s*([^:]{2,64})\s*:\s*(.+?)\s*$", candidate.source_lines[0].text)
    if match is None:
        return None
    sender_name = match.group(1).strip()
    message_text = match.group(2).strip()
    if sender_name == "" or message_text == "" or not _looks_like_player_chat_sender_text(sender_name):
        return None
    return _build_player_chat_candidate(candidate=candidate, sender_name=sender_name, message_text=message_text)


def _try_build_grouped_player_chat_candidate(candidate: _ChatRowCandidate) -> _ChatRowCandidate | None:
    """Parses one grouped sender-plus-message cluster into a supported player row when exact."""

    if not candidate.source_lines:
        return None
    sender_line = candidate.source_lines[0]
    if not _looks_like_player_chat_sender_line(sender_line):
        return None
    message_text = _chat_message_text_from_lines(candidate.source_lines[1:])
    if message_text == "":
        return None
    return _build_player_chat_candidate(candidate=candidate, sender_name=sender_line.text.strip(), message_text=message_text)


def _try_build_split_player_chat_candidate(
    *,
    image: Image.Image,
    sender_candidate: _ChatRowCandidate,
    message_candidate: _ChatRowCandidate | None,
) -> _ChatRowCandidate | None:
    """Merges an isolated sender fragment with exactly one neighboring message block when geometry is decisive."""

    if message_candidate is None or not _looks_like_sender_only_chat_candidate(sender_candidate):
        return None
    if not _looks_like_message_only_chat_candidate(message_candidate):
        return None
    gap = message_candidate.bounds.y - (sender_candidate.bounds.y + sender_candidate.bounds.height)
    if gap < 0 or gap > max(56, image.height // 20):
        return None
    sender_line = sender_candidate.source_lines[0]
    first_message_line = message_candidate.source_lines[0]
    if first_message_line.bounds.x < sender_line.bounds.x - 28:
        return None
    merged_candidate = _merge_chat_row_candidates(sender_candidate, message_candidate)
    return _build_player_chat_candidate(
        candidate=merged_candidate,
        sender_name=sender_line.text.strip(),
        message_text=_chat_message_text_from_lines(message_candidate.source_lines),
    )


def _try_build_image_only_player_chat_candidate(
    *,
    image: Image.Image,
    candidate: _ChatRowCandidate,
    next_candidate: _ChatRowCandidate | None,
    viewport: _ChatTranscriptViewport,
) -> _ChatRowCandidate | None:
    """Builds a placeholder-backed player row when the sender is visible and the bubble is confidently non-text."""

    if not _looks_like_sender_only_chat_candidate(candidate):
        return None
    sender_line = candidate.source_lines[0]
    search_top = sender_line.bounds.y + sender_line.bounds.height + 4
    search_bottom = viewport.bottom if next_candidate is None else min(viewport.bottom, next_candidate.bounds.y - 4)
    placeholder = _classify_non_text_chat_placeholder(
        image=image,
        search_bounds=Bounds(
            x=viewport.content_left,
            y=search_top,
            width=max(1, viewport.content_right - viewport.content_left),
            height=max(1, search_bottom - search_top),
        ),
    )
    if placeholder is None:
        return None
    return _build_player_chat_candidate(candidate=candidate, sender_name=sender_line.text.strip(), message_text=placeholder)


def _try_build_announcement_chat_candidate(
    *,
    image: Image.Image,
    candidate: _ChatRowCandidate,
) -> _ChatRowCandidate | None:
    """Returns one strict announcement candidate only for the supported brown system-message family."""

    if not candidate.source_lines:
        return None
    first_line = candidate.source_lines[0]
    if _is_explicit_system_message_sender_text(first_line.text):
        announcement_body = _chat_message_text_from_lines(candidate.source_lines[1:])
        return _build_announcement_chat_candidate(
            candidate=candidate,
            title_text=first_line.text.strip(),
            message_text=announcement_body if announcement_body != "" else first_line.text.strip(),
        )
    if _looks_like_player_chat_sender_line(first_line):
        return None
    if not _row_has_announcement_chrome(image=image, bounds=candidate.bounds):
        return None
    announcement_text = _chat_row_combined_text(candidate)
    if announcement_text == "":
        return None
    return _build_announcement_chat_candidate(
        candidate=candidate,
        title_text=announcement_text,
        message_text=announcement_text,
    )


def _build_player_chat_candidate(
    *,
    candidate: _ChatRowCandidate,
    sender_name: str,
    message_text: str,
) -> _ChatRowCandidate:
    """Returns one supported player candidate from normalized sender and message evidence."""

    return _ChatRowCandidate(
        bounds=candidate.bounds,
        source_lines=candidate.source_lines,
        edge_kind=candidate.edge_kind,
        kind=ChatEntryKind.PLAYER,
        title_text=sender_name,
        message_text=message_text,
        sender_evidence=sender_name,
        message_evidence=message_text,
    )


def _build_announcement_chat_candidate(
    *,
    candidate: _ChatRowCandidate,
    title_text: str,
    message_text: str,
) -> _ChatRowCandidate:
    """Returns one strict supported announcement candidate."""

    return _ChatRowCandidate(
        bounds=candidate.bounds,
        source_lines=candidate.source_lines,
        edge_kind=candidate.edge_kind,
        kind=ChatEntryKind.ANNOUNCEMENT,
        title_text=title_text,
        message_text=message_text,
        sender_evidence=title_text,
        message_evidence=message_text,
    )


def _build_unsupported_chat_candidate(
    *,
    candidate: _ChatRowCandidate,
    reason: str,
) -> _ChatRowCandidate:
    """Returns one fail-fast unsupported candidate with enough evidence for downstream diagnostics."""

    combined_text = _chat_row_combined_text(candidate)
    sender_evidence = None if not candidate.source_lines or not _looks_like_player_chat_sender_line(candidate.source_lines[0]) else candidate.source_lines[0].text.strip()
    message_evidence = _chat_message_text_from_lines(candidate.source_lines[1:]) if sender_evidence is not None else combined_text
    return _ChatRowCandidate(
        bounds=candidate.bounds,
        source_lines=candidate.source_lines,
        edge_kind=candidate.edge_kind,
        kind=ChatEntryKind.UNSUPPORTED,
        title_text=sender_evidence or combined_text or None,
        message_text=combined_text,
        sender_evidence=sender_evidence,
        message_evidence=None if message_evidence == "" else message_evidence,
        unsupported_reason=reason,
    )


def _merge_chat_row_candidates(first: _ChatRowCandidate, second: _ChatRowCandidate) -> _ChatRowCandidate:
    """Combines two adjacent OCR fragments into one normalized candidate shell."""

    merged_lines = tuple(sorted((*first.source_lines, *second.source_lines), key=lambda line: (line.bounds.y, line.bounds.x)))
    return _ChatRowCandidate(
        bounds=Bounds(
            x=min(first.bounds.x, second.bounds.x),
            y=min(first.bounds.y, second.bounds.y),
            width=max(first.bounds.width, second.bounds.width),
            height=max(first.bounds.y + first.bounds.height, second.bounds.y + second.bounds.height)
            - min(first.bounds.y, second.bounds.y),
        ),
        source_lines=merged_lines,
        edge_kind=first.edge_kind if first.edge_kind != _ChatViewportEdgeKind.INTERIOR else second.edge_kind,
    )


def _looks_like_sender_only_chat_candidate(candidate: _ChatRowCandidate) -> bool:
    """Returns whether one grouped fragment contains only trustworthy sender evidence."""

    return len(candidate.source_lines) == 1 and _looks_like_player_chat_sender_line(candidate.source_lines[0])


def _looks_like_message_only_chat_candidate(candidate: _ChatRowCandidate) -> bool:
    """Returns whether one grouped fragment contains message text without attributable sender evidence."""

    if not candidate.source_lines:
        return False
    if _looks_like_chat_timestamp_separator_text(_chat_row_combined_text(candidate)):
        return False
    if _is_explicit_system_message_sender_text(candidate.source_lines[0].text):
        return False
    return not _looks_like_player_chat_sender_line(candidate.source_lines[0])


def _is_absorbed_duplicate_sender_fragment(
    *,
    candidate: _ChatRowCandidate,
    following_candidate: _ChatRowCandidate | None,
) -> bool:
    """Returns whether one sender-only fragment is duplicated verbatim by the following complete player row."""

    if following_candidate is None or not _looks_like_sender_only_chat_candidate(candidate):
        return False
    following_player = _try_build_grouped_player_chat_candidate(following_candidate)
    if following_player is None:
        return False
    return following_player.title_text == candidate.source_lines[0].text.strip()


def _looks_like_player_chat_sender_line(line: OcrLine) -> bool:
    """Returns whether the first OCR line of a chat row looks like a player sender label."""

    return _looks_like_player_chat_sender_text(line.text)


def _looks_like_player_chat_sender_text(text: str) -> bool:
    """Returns whether one OCR string is conservative enough to trust as a player sender label."""

    normalized_text = normalize_ocr_text(text)
    if normalized_text == "":
        return False
    if normalized_text in {_CHAT_HEADER_TEXT, _CHAT_KINGDOM_TEXT, _CHAT_ALLIANCE_TEXT}:
        return False
    if normalized_text in _CHAT_SYSTEM_SENDER_TEXTS or _looks_like_chat_timestamp_separator_text(text):
        return False
    if len(normalized_text) < 3 or len(normalized_text) > _CHAT_MAX_SENDER_LENGTH:
        return False
    if len(re.findall(r"\S+", text.strip())) > 4:
        return False
    if ":" in text:
        return False
    letters = sum(character.isalpha() for character in normalized_text)
    digits = sum(character.isdigit() for character in normalized_text)
    if letters == 0 and digits > 0:
        return False
    if digits > max(4, letters * 2):
        return False
    return re.search(r"\w", text, flags=re.UNICODE) is not None


def _is_explicit_system_message_sender_text(text: str) -> bool:
    """Returns whether one OCR line names the strict system-message sender family."""

    return normalize_ocr_text(text) in _CHAT_SYSTEM_SENDER_TEXTS


def _looks_like_chat_timestamp_separator_text(text: str) -> bool:
    """Returns whether one OCR line is the centered transcript date separator rather than a chat row."""

    stripped = text.strip()
    if stripped == "":
        return False
    if _CHAT_TIMESTAMP_SEPARATOR_PATTERN.match(stripped) is not None:
        return True
    normalized_text = normalize_ocr_text(stripped)
    digit_count = sum(character.isdigit() for character in normalized_text)
    return digit_count >= 10 and (":" in stripped or normalized_text.endswith("AM") or normalized_text.endswith("PM"))


def _chat_row_edge_kind(*, bounds: Bounds, viewport: _ChatTranscriptViewport) -> _ChatViewportEdgeKind:
    """Returns whether one grouped row touches the top or bottom boundary of the trusted viewport."""

    if bounds.y <= viewport.top + _CHAT_BOUNDARY_FRAGMENT_MARGIN:
        return _ChatViewportEdgeKind.TOP
    if bounds.y + bounds.height >= viewport.bottom - _CHAT_BOUNDARY_FRAGMENT_MARGIN:
        return _ChatViewportEdgeKind.BOTTOM
    return _ChatViewportEdgeKind.INTERIOR


def _is_chat_boundary_fragment(candidate: _ChatRowCandidate) -> bool:
    """Returns whether one unresolved candidate should be dropped because it is clipped at the viewport edge."""

    return candidate.edge_kind != _ChatViewportEdgeKind.INTERIOR


def _chat_row_combined_text(candidate: _ChatRowCandidate) -> str:
    """Returns the joined OCR text carried by one grouped row candidate."""

    return " ".join(line.text.strip() for line in candidate.source_lines if line.text.strip() != "")


def _chat_message_text_from_lines(lines: tuple[OcrLine, ...]) -> str:
    """Returns one normalized multi-line message payload from the provided OCR lines."""

    return " ".join(line.text.strip() for line in lines if line.text.strip() != "")


def _row_has_announcement_chrome(*, image: Image.Image, bounds: Bounds) -> bool:
    """Returns whether one chat row crop is dominated by the warm brown system-message chrome."""

    crop = image.crop((max(0, int(image.width * 0.16)), bounds.y, image.width, bounds.y + bounds.height)).convert("RGB")
    warm_pixels = _count_pixels(
        crop,
        predicate=lambda red, green, blue: red >= 70 and red >= blue + 20 and green >= blue + 10,
    )
    return warm_pixels / max(1, crop.width * crop.height) >= _CHAT_ANNOUNCEMENT_MIN_WARM_RATIO


def _classify_non_text_chat_placeholder(
    *,
    image: Image.Image,
    search_bounds: Bounds,
) -> str | None:
    """Returns a deterministic placeholder for confidently image-only chat content when visible."""

    if search_bounds.height <= 0 or search_bounds.width <= 0:
        return None
    foreground_bounds = _find_non_text_chat_foreground_bounds(image=image, search_bounds=search_bounds)
    if foreground_bounds is None:
        return None
    crop = image.crop(
        (
            foreground_bounds.x,
            foreground_bounds.y,
            foreground_bounds.x + foreground_bounds.width,
            foreground_bounds.y + foreground_bounds.height,
        )
    ).convert("RGB")
    total_pixels = max(1, crop.width * crop.height)
    foreground_pixels = _count_pixels(crop, predicate=_is_non_text_chat_foreground_pixel)
    density = foreground_pixels / total_pixels
    if (
        foreground_bounds.width >= _CHAT_STICKER_MIN_DIMENSION
        and foreground_bounds.height >= _CHAT_STICKER_MIN_DIMENSION
        and density < _CHAT_TEXT_BUBBLE_MAX_DENSITY
    ):
        return "[sticker]"
    if foreground_bounds.width > _CHAT_EMOJI_MAX_DIMENSION or foreground_bounds.height > _CHAT_EMOJI_MAX_DIMENSION:
        return None
    if density >= _CHAT_TEXT_BUBBLE_MAX_DENSITY and foreground_bounds.width >= foreground_bounds.height * 2:
        return None
    return _classify_emoji_placeholder(crop)


def _find_non_text_chat_foreground_bounds(
    *,
    image: Image.Image,
    search_bounds: Bounds,
) -> Bounds | None:
    """Returns the bounding box of the visible non-background foreground inside one candidate message region."""

    crop = image.crop(
        (
            search_bounds.x,
            search_bounds.y,
            search_bounds.x + search_bounds.width,
            search_bounds.y + search_bounds.height,
        )
    ).convert("RGB")
    xs: list[int] = []
    ys: list[int] = []
    for y in range(crop.height):
        for x in range(crop.width):
            if not _is_non_text_chat_foreground_pixel(*crop.getpixel((x, y))):
                continue
            xs.append(x)
            ys.append(y)
    if len(xs) < _CHAT_NON_TEXT_MIN_FOREGROUND_PIXELS:
        return None
    left = min(xs)
    right = max(xs)
    top = min(ys)
    bottom = max(ys)
    return Bounds(
        x=search_bounds.x + left,
        y=search_bounds.y + top,
        width=max(1, right - left + 1),
        height=max(1, bottom - top + 1),
    )


def _classify_emoji_placeholder(crop: Image.Image) -> str:
    """Returns the most specific safe emoji placeholder supported by the coarse visual classifier."""

    white_pixels = _count_pixels(
        crop,
        predicate=lambda red, green, blue: red >= 210 and green >= 210 and blue >= 210,
    )
    yellow_pixels = _count_pixels(
        crop,
        predicate=lambda red, green, blue: red >= 170 and green >= 140 and blue <= 120,
    )
    lower_half = crop.crop((0, crop.height // 2, crop.width, crop.height))
    lower_dark_pixels = _count_pixels(
        lower_half,
        predicate=lambda red, green, blue: red <= 80 and green <= 80 and blue <= 80,
    )
    total_pixels = max(1, crop.width * crop.height)
    if white_pixels / total_pixels >= 0.14:
        return "[eyes emoji]"
    if yellow_pixels / total_pixels >= 0.2 and lower_dark_pixels / max(1, lower_half.width * lower_half.height) >= 0.03:
        return "[happy emoji]"
    return "[emoji]"


def _count_pixels(image: Image.Image, *, predicate: Callable[[int, int, int], bool]) -> int:
    """Counts pixels matching one RGB predicate inside the provided crop."""

    matches = 0
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            if predicate(*pixels[x, y]):
                matches += 1
    return matches


def _is_non_text_chat_foreground_pixel(red: int, green: int, blue: int) -> bool:
    """Returns whether one pixel belongs to visible chat content rather than the dark background."""

    brightest = max(red, green, blue)
    return brightest >= _CHAT_NON_TEXT_FOREGROUND_BRIGHTNESS or (
        brightest >= 80 and brightest - min(red, green, blue) >= _CHAT_NON_TEXT_FOREGROUND_VARIANCE
    )


def _extract_simple_named_rows(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    kind: ListEntryKind,
    min_y: int,
    excluded_texts: frozenset[str],
    action_x_ratio: float,
    normalize_title: Callable[[str], str | None] | None = None,
) -> tuple[DetectedListEntry, ...]:
    """Extracts simple single-line named rows used by profile-entry route screens."""

    entries: list[DetectedListEntry] = []
    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if line.bounds.y < min_y or normalized_text in excluded_texts or normalized_text == "":
            continue
        title_text = line.text.strip()
        if normalize_title is not None:
            normalized_title = normalize_title(title_text)
            if normalized_title is None:
                continue
            title_text = normalized_title
        if len(normalize_ocr_text(title_text)) < 3:
            continue
        bounds = Bounds(x=0, y=max(0, line.bounds.y - 6), width=image.width, height=max(20, line.bounds.height + 12))
        entries.append(
            DetectedListEntry(
                kind=kind,
                bounds=bounds,
                title_text=title_text,
                action_point=(int(image.width * action_x_ratio), bounds.y + bounds.height // 2),
            )
        )
    return tuple(entries)


def _extract_grouped_named_rows(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    kind: ListEntryKind,
    min_y: int,
    excluded_texts: frozenset[str],
    action_x_ratio: float,
    ignored_title_texts: frozenset[str] = frozenset(),
    action_texts: frozenset[str] = frozenset(),
    normalize_title: Callable[[str], str | None] | None = None,
) -> tuple[DetectedListEntry, ...]:
    """Extracts one named entry per grouped row for OCR-heavy list screens."""

    candidate_lines = [
        line
        for line in lines
        if line.bounds.y >= min_y and normalize_ocr_text(line.text) not in excluded_texts and normalize_ocr_text(line.text) != ""
    ]
    grouped_rows = _group_lines_by_vertical_gap(candidate_lines, gap=max(34, image.height // 28))
    entries: list[DetectedListEntry] = []
    for row_lines in grouped_rows:
        if not row_lines:
            continue
        title_line = _find_grouped_row_title_line(
            image=image,
            row_lines=row_lines,
            ignored_title_texts=ignored_title_texts,
        )
        if title_line is None:
            continue
        title_text = title_line.text.strip()
        if normalize_title is not None:
            normalized_title = normalize_title(title_text)
            if normalized_title is None:
                continue
            title_text = normalized_title
        if len(normalize_ocr_text(title_text)) < 3:
            continue
        bounds = _entry_bounds_from_lines(image=image, row_lines=row_lines)
        action_line = _find_line_matching(
            lines=tuple(row_lines),
            predicate=lambda line: normalize_ocr_text(line.text) in action_texts,
        )
        action_point = (
            (
                action_line.bounds.x + action_line.bounds.width // 2,
                action_line.bounds.y + action_line.bounds.height // 2,
            )
            if action_line is not None
            else (int(image.width * action_x_ratio), bounds.y + bounds.height // 2)
        )
        entries.append(
            DetectedListEntry(
                kind=kind,
                bounds=bounds,
                title_text=title_text,
                action_point=action_point,
            )
        )
    return tuple(entries)


def _normalize_ranked_player_title(title_text: str) -> str | None:
    """Normalizes a ranked-player OCR line into just the visible player name when possible."""

    cleaned = re.sub(r"^\s*\d+\s*[.)-]?\s*", "", title_text).strip()
    return None if cleaned == "" else cleaned


def _find_grouped_row_title_line(
    *,
    image: Image.Image,
    row_lines: list[OcrLine],
    ignored_title_texts: frozenset[str],
) -> OcrLine | None:
    """Returns the best title-bearing OCR line for one grouped named-row cluster."""

    title_candidates = [
        line
        for line in sorted(row_lines, key=lambda item: (item.bounds.x, item.bounds.y))
        if line.bounds.x <= int(image.width * 0.62)
        and _is_viable_grouped_row_title(line, ignored_title_texts=ignored_title_texts)
    ]
    if not title_candidates:
        return None
    return title_candidates[0]


def _is_viable_grouped_row_title(line: OcrLine, *, ignored_title_texts: frozenset[str]) -> bool:
    """Returns whether one OCR line looks like the left-side name label of a grouped row."""

    normalized_text = normalize_ocr_text(line.text)
    if normalized_text in ignored_title_texts or normalized_text == "":
        return False
    if len(normalized_text) < 3:
        return False
    if _looks_like_grouped_row_stat_text(normalized_text):
        return False
    return True


def _looks_like_grouped_row_stat_text(normalized_text: str) -> bool:
    """Returns whether one OCR token is more likely a stat/id line than a player-name line."""

    letters = sum(character.isalpha() for character in normalized_text)
    digits = sum(character.isdigit() for character in normalized_text)
    if letters == 0 and digits > 0:
        return True
    if digits > max(2, letters * 2):
        return True
    return False


def _entry_bounds_from_lines(*, image: Image.Image, row_lines: list[OcrLine]) -> Bounds:
    """Builds one row-sized bounds rectangle from the OCR lines assigned to that row."""

    top = max(0, row_lines[0].bounds.y - 6)
    bottom = min(image.height, row_lines[-1].bounds.y + row_lines[-1].bounds.height + 6)
    return Bounds(x=0, y=top, width=image.width, height=max(1, bottom - top))


def _group_lines_by_vertical_gap(lines: list[OcrLine], *, gap: int) -> list[list[OcrLine]]:
    """Groups sorted OCR lines into row-like clusters using one shared vertical-gap threshold."""

    grouped: list[list[OcrLine]] = []
    current_group: list[OcrLine] = []
    previous_bottom: int | None = None
    for line in sorted(lines, key=lambda item: (item.bounds.y, item.bounds.x)):
        if previous_bottom is None or line.bounds.y - previous_bottom <= gap:
            current_group.append(line)
        else:
            grouped.append(current_group)
            current_group = [line]
        previous_bottom = line.bounds.y + line.bounds.height
    if current_group:
        grouped.append(current_group)
    return grouped


def _looks_like_mail_date_text(text: str) -> bool:
    """Returns whether one OCR line looks like a compact mailbox date or thread timestamp."""

    normalized_text = normalize_ocr_text(text)
    if normalized_text == "":
        return False
    if re.search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", text) is not None:
        return True
    if re.search(r"\d{1,2}:\d{2}(:\d{2})?", text) is not None:
        return True
    return bool(re.search(r"\d", normalized_text) and any(token in normalized_text for token in ("AM", "PM", "AGO", "DAY", "HOUR", "MIN", "SEC")))


def _is_chat_message_candidate_line(*, line: OcrLine, viewport: _ChatTranscriptViewport) -> bool:
    """Returns whether one OCR line can belong to the visible chat-message list."""

    normalized_text = normalize_ocr_text(line.text)
    if normalized_text == "":
        return False
    if line.bounds.y < viewport.top or line.bounds.y > viewport.bottom:
        return False
    if normalized_text in {_CHAT_HEADER_TEXT, _CHAT_KINGDOM_TEXT, _CHAT_ALLIANCE_TEXT, *_SEND_TEXTS}:
        return False
    if _is_empty_chat_draft_text(normalized_text) or _looks_like_chat_timestamp_separator_text(line.text):
        return False
    return True


def _build_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns popup dismissal controls when OCR matches a blocking modal footer."""

    vip_daily_reset = _build_vip_daily_reset_popup_additions(image=image, lines=lines)
    if vip_daily_reset is not None:
        return vip_daily_reset
    dismiss_anchor = _find_popup_dismiss_anchor(image=image, anchors=anchors)
    if dismiss_anchor is not None:
        return ObservationAdditions(
            visible_elements={
                UiElementId.PNC_POPUP_CLOSE_BUTTON: _make_visible_from_anchor(
                    selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON,
                    anchor=dismiss_anchor,
                )
            },
            screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, "ocr_popup_cancel_button"),),
        )
    return _build_promotional_popup_additions(image=image, lines=lines)


def _build_vip_daily_reset_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the VIP daily-reset modal and its Close button when OCR matches the observed midnight-reset layout."""

    vip_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="VIP",
        min_y=int(image.height * 0.18),
        max_y=int(image.height * 0.5),
    )
    close_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="CLOSE",
        min_y=int(image.height * 0.48),
        max_y=int(image.height * 0.72),
    )
    if vip_line is None or close_line is None:
        return None
    support_texts = {
        support_text
        for line in lines
        for support_text in _VIP_DAILY_RESET_SUPPORT_TEXTS
        if normalize_ocr_text(line.text).startswith(support_text)
    }
    if len(support_texts) < 4:
        return None
    close_width_padding = max(30, close_line.bounds.width // 3)
    close_height_padding = max(18, close_line.bounds.height // 2)
    close_left = max(0, close_line.bounds.x - close_width_padding)
    close_top = max(0, close_line.bounds.y - close_height_padding)
    close_width = min(image.width - close_left, close_line.bounds.width + (close_width_padding * 2))
    close_height = min(image.height - close_top, close_line.bounds.height + (close_height_padding * 2))
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_VIP_DAILY_RESET_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_VIP_DAILY_RESET_HEADER,
                line=vip_line,
            ),
            UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON: _make_visible(
                selector_id=UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
                x=close_left,
                y=close_top,
                width=close_width,
                height=close_height,
                action_point=(close_line.bounds.x + (close_line.bounds.width // 2), close_line.bounds.y + (close_line.bounds.height // 2)),
                extracted_text=close_line.text,
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_VIP_DAILY_RESET, "ocr_vip_daily_reset_popup"),),
    )


def _build_promotional_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns a popup close target for the observed monetized offer modals."""

    title_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: "HERO" in normalize_ocr_text(line.text),
        max_y=int(image.height * 0.2),
    )
    one_time_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="ONETIME",
        min_y=int(image.height * 0.72),
    )
    price_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: _CURRENCY_TEXT_PATTERN.search(line.text) is not None,
        min_y=int(image.height * 0.65),
    )
    if title_line is None or one_time_line is None or price_line is None:
        top_up_button_line = _find_line_with_normalized_text(
            lines=lines,
            normalized_text="TOPUP",
            min_y=int(image.height * 0.72),
        )
        obtain_now_line = _find_line_with_normalized_text(
            lines=lines,
            normalized_text="OBTAINNOW",
            min_y=int(image.height * 0.35),
        )
        claim_next_day_line = _find_line_with_normalized_text(
            lines=lines,
            normalized_text="CLAIMNEXTDAY",
            min_y=int(image.height * 0.45),
        )
        if top_up_button_line is None or (obtain_now_line is None and claim_next_day_line is None):
            return None
        return _build_top_right_popup_close_additions(image=image, reason="ocr_top_up_offer_popup")

    return _build_top_right_popup_close_additions(image=image, reason="ocr_promotional_offer_popup")


def _build_top_right_popup_close_additions(*, image: Image.Image, reason: str) -> ObservationAdditions:
    """Builds the canonical close target for offer popups that dismiss from the top-right corner."""

    close_width = max(32, int(image.width * 0.12))
    close_height = max(32, int(image.height * 0.12))
    close_left = max(0, image.width - close_width - int(image.width * 0.05))
    close_top = max(0, int(image.height * 0.02))
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_POPUP_CLOSE_BUTTON: _make_visible(
                selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON,
                x=close_left,
                y=close_top,
                width=close_width,
                height=close_height,
                action_point=(close_left + (close_width // 2), close_top + (close_height // 2)),
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, reason),),
    )


def _find_popup_dismiss_anchor(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
) -> DetectedTextAnchor | None:
    """Returns the modal dismiss anchor when a popup action row is present."""

    for anchor in anchors:
        if anchor.id != TextAnchorId.LABEL_CANCEL:
            continue
        if not _is_popup_footer_anchor(image=image, anchor=anchor):
            continue
        if _has_popup_primary_action(image=image, anchors=anchors, dismiss_anchor=anchor):
            return anchor
    return None


def _has_popup_primary_action(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
    dismiss_anchor: DetectedTextAnchor,
) -> bool:
    """Returns whether the dismiss button is paired with a modal primary action."""

    row_tolerance = max(28, dismiss_anchor.bounds.height * 2)
    minimum_gap = max(40, int(image.width * 0.08))
    for anchor in anchors:
        if anchor.id not in _POPUP_PRIMARY_ACTION_ANCHOR_IDS:
            continue
        if not _is_popup_footer_anchor(image=image, anchor=anchor):
            continue
        if abs(anchor.bounds.y - dismiss_anchor.bounds.y) > row_tolerance:
            continue
        if anchor.bounds.x <= dismiss_anchor.bounds.x + minimum_gap:
            continue
        return True
    return False


def _is_popup_footer_anchor(
    *,
    image: Image.Image,
    anchor: DetectedTextAnchor,
) -> bool:
    """Returns whether one OCR anchor sits where modal footer actions normally appear, including bottom sheets."""

    return (
        anchor.bounds.y >= int(image.height * 0.45)
        and anchor.bounds.y <= int(image.height * 0.97)
        and anchor.bounds.x >= int(image.width * 0.04)
        and anchor.bounds.x <= int(image.width * 0.92)
    )


def _build_loading_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns loading or reconnect-state evidence when OCR matches bootstrap waits."""

    splash = _build_loading_splash_additions(image=image, lines=lines)
    if splash is not None:
        return splash
    loading_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _LOADING_TEXTS,
        max_y=int(image.height * 0.45),
    )
    reconnect_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="RECONNECT",
        min_y=int(image.height * 0.4),
    )
    if loading_line is None and reconnect_line is None:
        return None
    if reconnect_line is not None and not _has_loading_support(lines):
        return None
    visible_elements: dict[UiElementId, VisibleElement] = {}
    reason = "ocr_loading_state"
    if reconnect_line is not None:
        visible_elements[UiElementId.PNC_LOADING_RECONNECT_BUTTON] = _make_visible(
            selector_id=UiElementId.PNC_LOADING_RECONNECT_BUTTON,
            x=max(0, reconnect_line.bounds.x - max(20, reconnect_line.bounds.width // 2)),
            y=max(0, reconnect_line.bounds.y - max(16, reconnect_line.bounds.height // 2)),
            width=reconnect_line.bounds.width + max(40, reconnect_line.bounds.width),
            height=reconnect_line.bounds.height + max(24, reconnect_line.bounds.height),
            extracted_text=reconnect_line.text,
        )
        reason = "ocr_loading_reconnect"
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_LOADING, reason),),
    )


def _build_loading_splash_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns loading-state evidence when OCR matches the branded game splash screen."""

    conquest_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: "CONQUEST" in normalize_ocr_text(line.text),
        max_y=int(image.height * 0.18),
    )
    progress_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: _PERCENT_PROGRESS_PATTERN.match(line.text.strip()) is not None,
        min_y=int(image.height * 0.7),
    )
    if conquest_line is None or progress_line is None:
        return None
    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_LOADING, "ocr_loading_splash"),),
    )


def _build_login_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns login-screen evidence and the visible username when OCR matches the credential form."""

    username_label = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _LOGIN_USERNAME_LABEL_TEXTS,
        max_y=int(image.height * 0.65),
    )
    password_label = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="PASSWORD",
        max_y=int(image.height * 0.8),
    )
    submit_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _LOGIN_SUBMIT_TEXTS,
        min_y=int(image.height * 0.35),
    )
    if username_label is None or password_label is None or submit_line is None:
        return None
    if username_label.bounds.y >= password_label.bounds.y or password_label.bounds.y >= submit_line.bounds.y:
        return None

    username_field = _build_labeled_field(
        image=image,
        selector_id=UiElementId.PNC_LOGIN_USERNAME_FIELD,
        label_line=username_label,
        next_line=password_label,
    )
    current_pnc_account_id = _find_account_identifier(
        lines=lines,
        min_y=username_field.bounds.y,
        max_y=username_field.bounds.y + username_field.bounds.height,
    )
    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_LOGIN, "ocr_login_form"),),
        current_pnc_account_id=current_pnc_account_id,
    )


def _build_account_switch_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns account-switch evidence and the visible account identifier when OCR matches the chooser."""

    header = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _ACCOUNT_SWITCH_HEADER_TEXTS,
        max_y=int(image.height * 0.25),
    )
    if header is None:
        return None
    continue_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="CONTINUE",
        min_y=int(image.height * 0.4),
    )
    change_account_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="CHANGEACCOUNT",
        min_y=int(image.height * 0.4),
    )
    if continue_line is None and change_account_line is None:
        return None

    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ACCOUNT_SWITCH, "ocr_account_switch"),),
        current_pnc_account_id=_find_account_identifier(
            lines=lines,
            min_y=header.bounds.y + header.bounds.height,
            max_y=int(image.height * 0.78),
        ),
    )


def _build_building_detail_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns derived selectors when OCR matches a building-detail screen."""

    if _has_building_detail_conflicts(image=image, anchors=anchors):
        return None

    upgrade_anchor = next(
        (
            anchor
            for anchor in anchors
            if anchor.id == TextAnchorId.LABEL_UPGRADE
            and anchor.bounds.x >= int(image.width * 0.55)
            and anchor.bounds.y <= int(image.height * 0.42)
        ),
        None,
    )
    if upgrade_anchor is None:
        return None
    title_line = _find_building_title_line(image=image, lines=lines)
    if title_line is None:
        return None
    support_line = _find_building_detail_support_line(
        image=image,
        lines=lines,
        title_line=title_line,
    )
    if support_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT: _make_visible(
                selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                x=0,
                y=0,
                width=max(1, int(image.width * 0.12)),
                height=max(1, int(image.height * 0.08)),
            ),
            UiElementId.PNC_BUILDING_UPGRADE_BUTTON: _make_visible(
                selector_id=UiElementId.PNC_BUILDING_UPGRADE_BUTTON,
                x=max(0, upgrade_anchor.bounds.x - max(12, upgrade_anchor.bounds.width // 2)),
                y=max(0, upgrade_anchor.bounds.y - max(10, upgrade_anchor.bounds.height)),
                width=min(
                    image.width,
                    upgrade_anchor.bounds.width + max(40, upgrade_anchor.bounds.width),
                ),
                height=min(
                    image.height,
                    upgrade_anchor.bounds.height + max(20, upgrade_anchor.bounds.height),
                ),
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_BUILDING_DETAILS, "ocr_building_detail"),),
    )


def _build_build_queue_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the build-queue overlay when OCR exposes its header plus queue-row support."""

    header = _find_header_line(lines=lines, header_texts=_BUILD_QUEUE_HEADER_TEXTS, max_y=int(image.height * 0.18))
    if header is None:
        return None
    entries: list[DetectedListEntry] = []
    active_entry = _extract_build_queue_active_entry(image=image, lines=lines)
    if active_entry is not None:
        entries.append(active_entry)
    support_count = sum(
        1
        for line in lines
        if line.bounds.y >= header.bounds.y and normalize_ocr_text(line.text) in _BUILD_QUEUE_SUPPORT_TEXTS
    )
    if active_entry is None and support_count < 2:
        return None
    return ObservationAdditions(
        list_entries=tuple(entries),
        screen_evidence=(ScreenEvidence(ScreenType.PNC_BUILD_QUEUE, "ocr_build_queue"),),
    )


def _extract_build_queue_active_entry(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> DetectedListEntry | None:
    """Returns the visible active construction row from the build queue when OCR proves one exists."""

    title_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: _BUILD_QUEUE_ACTIVE_TITLE_PATTERN.match(line.text.strip()) is not None,
        min_y=int(image.height * 0.14),
        max_y=int(image.height * 0.55),
    )
    timer_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: _QUEUE_TIMER_PATTERN.match(line.text.strip()) is not None,
        min_y=int(image.height * 0.18),
        max_y=int(image.height * 0.65),
    )
    speedup_line = _find_first_line_in_texts(
        lines=lines,
        texts=frozenset({"SPEEDUP"}),
        min_y=int(image.height * 0.18),
        max_y=int(image.height * 0.65),
    )
    if title_line is None and timer_line is None:
        return None
    title_text: str | None = None
    if title_line is not None:
        title_match = _BUILD_QUEUE_ACTIVE_TITLE_PATTERN.match(title_line.text.strip())
        if title_match is not None:
            title_text = title_match.group("title").strip() or None
    row_lines = [line for line in (title_line, timer_line, speedup_line) if line is not None]
    top = max(0, min(line.bounds.y for line in row_lines) - 12)
    bottom = min(image.height, max(line.bounds.y + line.bounds.height for line in row_lines) + 12)
    return DetectedListEntry(
        kind=ListEntryKind.BUILDING,
        bounds=Bounds(x=0, y=top, width=image.width, height=max(1, bottom - top)),
        title_text=title_text,
        timer_text=None if timer_line is None else timer_line.text.strip(),
        metadata={"queue_state": "upgrading"},
    )


def _build_research_queue_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the in-game research-queue overlay as a blocking popup when OCR proves its header and idle row."""

    header = _find_header_line(lines=lines, header_texts=_RESEARCH_QUEUE_HEADER_TEXTS, max_y=int(image.height * 0.4))
    if header is None:
        return None
    support_count = sum(
        1
        for line in lines
        if line.bounds.y >= header.bounds.y and normalize_ocr_text(line.text) in _RESEARCH_QUEUE_SUPPORT_TEXTS
    )
    if support_count < 2:
        return None
    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_POPUP, "ocr_research_queue_popup"),),
    )


def _build_more_menu_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns the More overlay when OCR exposes multiple More-menu actions."""

    visible_elements: dict[UiElementId, VisibleElement] = {}
    for normalized_text, selector_id in _MORE_OVERLAY_SELECTOR_BY_TEXT.items():
        line = _find_line_with_normalized_text(
            lines=lines,
            normalized_text=normalized_text,
            min_y=int(image.height * 0.82),
        )
        if line is None:
            continue
        visible_elements[selector_id] = _make_visible_from_more_overlay_line(
            image=image,
            selector_id=selector_id,
            line=line,
        )
    for normalized_text, selector_id in _MORE_MENU_SELECTOR_BY_TEXT.items():
        line = _find_line_with_normalized_text(lines=lines, normalized_text=normalized_text)
        if line is None:
            continue
        visible_elements[selector_id] = _make_visible_from_line(selector_id=selector_id, line=line)
    more_anchor = next(
        (
            anchor
            for anchor in anchors
            if anchor.id == TextAnchorId.LABEL_MORE and anchor.bounds.y >= int(image.height * 0.86)
        ),
        None,
    )
    if more_anchor is not None:
        visible_elements[UiElementId.PNC_BOTTOM_NAV_MORE] = _make_visible_from_bottom_nav_anchor(
            image=image,
            selector_id=UiElementId.PNC_BOTTOM_NAV_MORE,
            anchor=more_anchor,
        )
    support_texts = {
        normalize_ocr_text(line.text)
        for line in lines
        if normalize_ocr_text(line.text) in _MORE_MENU_SUPPORT_TEXTS
    }
    if len(support_texts) + len(visible_elements) < 3:
        return None
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MORE_MENU, "ocr_more_menu_overlay"),),
    )


def _build_more_settings_menu_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the full-screen Settings submenu shown after opening More > Settings."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="SETTINGS",
        max_y=int(image.height * 0.1),
    )
    if header is None:
        return None
    support_count = sum(
        1
        for line in lines
        if normalize_ocr_text(line.text) in _MORE_SETTINGS_MENU_SUPPORT_TEXTS
    )
    if support_count < 4:
        return None
    visible_elements = {
        UiElementId.PNC_BACK_BUTTON_TOP_LEFT: _make_visible(
            selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
            x=0,
            y=0,
            width=max(1, int(image.width * 0.14)),
            height=max(1, int(image.height * 0.1)),
        )
    }
    for normalized_text, selector_id in _MORE_MENU_SELECTOR_BY_TEXT.items():
        line = _find_line_with_normalized_text(lines=lines, normalized_text=normalized_text)
        if line is None:
            continue
        visible_elements[selector_id] = _make_visible_from_line(selector_id=selector_id, line=line)
    return ObservationAdditions(
        visible_elements=visible_elements,
        suppress_geometry_selector_ids=frozenset({UiElementId.PNC_BOTTOM_NAV_MORE}),
        screen_evidence=(ScreenEvidence(ScreenType.PNC_MORE_MENU, "ocr_more_settings_menu"),),
    )


def _build_lord_info_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the Lord Info screen and the visible lord name label when OCR matches the profile layout."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="LORDINFO",
        max_y=int(image.height * 0.08),
    )
    if header is None:
        return None
    tab_count = sum(1 for line in lines if normalize_ocr_text(line.text) in _LORD_INFO_TAB_TEXTS)
    if tab_count < 2:
        return None
    name_line = _find_profile_name_line(
        image=image,
        lines=lines,
        excluded_texts=_LORD_INFO_EXCLUDED_NAME_TEXTS,
    )
    if name_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_LORD_INFO_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_LORD_INFO_HEADER,
                line=header,
            ),
            UiElementId.PNC_LORD_INFO_NAME_LABEL: _make_visible_from_line(
                selector_id=UiElementId.PNC_LORD_INFO_NAME_LABEL,
                line=name_line,
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_LORD_INFO, "ocr_lord_info"),),
        current_castle=_lord_info_name_to_current_castle(name_line.text),
        current_castle_evidence=CurrentCastleEvidenceKind.NAME_ONLY,
    )


def _build_vip_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the VIP screen when OCR matches the live VIP benefits layout."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="VIP",
        max_y=int(image.height * 0.08),
    )
    if header is None:
        return None
    support_count = sum(1 for line in lines if normalize_ocr_text(line.text) in _VIP_SUPPORT_TEXTS)
    if support_count < 3:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_VIP_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_VIP_HEADER,
                line=header,
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_VIP, "ocr_vip_screen"),),
    )


def _build_improve_might_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the Improve Might screen when OCR matches the guided-upgrade prompt."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="IMPROVEMIGHT",
        min_y=int(image.height * 0.12),
        max_y=int(image.height * 0.35),
    )
    if header is None:
        return None
    improve_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="IMPROVE",
        min_y=header.bounds.y,
        max_y=int(image.height * 0.45),
    )
    support_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: "IMPROVEMIGHT" in normalize_ocr_text(line.text),
        min_y=int(image.height * 0.6),
    )
    if improve_line is None or support_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_IMPROVE_MIGHT_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_IMPROVE_MIGHT_HEADER,
                line=header,
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_IMPROVE_MIGHT, "ocr_improve_might_screen"),),
    )


def _build_home_city_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
    visible_elements: Mapping[UiElementId, VisibleElement],
    selector_registry: SelectorRegistry | None,
) -> ObservationAdditions | None:
    """Returns home-city classification when bottom navigation OCR has supporting evidence."""

    visible_nav_elements, _ = _extract_bottom_nav_additions(image=image, anchors=anchors)
    if len(visible_nav_elements) < 2:
        return None
    if UiElementId.PNC_BOTTOM_NAV_MORE not in visible_nav_elements and UiElementId.PNC_BOTTOM_NAV_ALLIANCE not in visible_nav_elements:
        return None
    visible_home_action_elements = _build_home_action_additions(image=image, anchors=anchors)
    if not visible_home_action_elements and _HOME_CITY_EVIDENCE_SELECTOR_IDS.isdisjoint(visible_elements):
        return None
    return ObservationAdditions(
        visible_elements=visible_nav_elements | visible_home_action_elements,
        spatial_surface=build_home_city_spatial_surface(
            image=image,
            lines=lines,
            selector_registry=selector_registry,
        ),
        screen_evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "bottom_nav_and_home_actions"),),
    )


def _build_world_map_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
    selector_registry: SelectorRegistry | None,
    ocr_service: OcrService,
) -> ObservationAdditions | None:
    """Returns world-map additions once OCR proves the coordinate bar, optionally enriching fixed footer chrome."""

    visible_nav_elements, nav_anchors = _extract_bottom_nav_additions(image=image, anchors=anchors)
    parsed_viewport = _read_world_map_coordinate_viewport(
        image=image,
        lines=lines,
        selector_registry=selector_registry,
        ocr_service=ocr_service,
    )
    if parsed_viewport is None:
        return None
    visible_elements = dict(visible_nav_elements)
    visible_elements[UiElementId.PNC_WORLD_COORDINATE_BAR] = _make_visible(
        selector_id=UiElementId.PNC_WORLD_COORDINATE_BAR,
        x=parsed_viewport.coordinate_bounds.x,
        y=parsed_viewport.coordinate_bounds.y,
        width=parsed_viewport.coordinate_bounds.width,
        height=parsed_viewport.coordinate_bounds.height,
        extracted_text=parsed_viewport.coordinate_text,
    )
    visible_elements[UiElementId.PNC_WORLD_SEARCH_BUTTON] = _build_world_map_search_button_element(
        image=image,
        coordinate_bounds=parsed_viewport.coordinate_bounds,
    )
    home_anchor = nav_anchors.get(TextAnchorId.LABEL_HOME)
    if home_anchor is not None:
        visible_elements[UiElementId.PNC_WORLD_HOME_NAV] = _make_visible_from_bottom_nav_anchor(
            image=image,
            selector_id=UiElementId.PNC_WORLD_HOME_NAV,
            anchor=home_anchor,
        )
    return ObservationAdditions(
        visible_elements=visible_elements,
        spatial_surface=build_world_map_spatial_surface(
            image=image,
            lines=lines,
            selector_registry=selector_registry,
            parsed_viewport=parsed_viewport,
        ),
        screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP, "ocr_world_coordinates_and_bottom_nav"),),
    )


def _read_world_map_coordinate_viewport(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    selector_registry: SelectorRegistry | None,
    ocr_service: OcrService,
) -> ParsedWorldViewport | None:
    """Returns the canonical coordinate-bar viewport, preferring blue/cyan filtered selector OCR."""

    if selector_registry is not None:
        selector = selector_registry.require(UiElementId.PNC_WORLD_COORDINATE_BAR)
        if selector.relative_bounds is not None:
            parsed = read_world_coordinate_bar_viewport(
                image=image,
                bounds=selector.relative_bounds.materialize_region(image_size=image.size),
                ocr_service=ocr_service,
            )
            if parsed is not None:
                return parsed
    return parse_world_viewport(image=image, lines=lines)


def _build_world_map_search_button_element(
    *,
    image: Image.Image,
    coordinate_bounds: Bounds,
) -> VisibleElement:
    """Builds the world-map search tap target from the proven coordinate-bar HUD instead of a separate freehand screen region."""

    button_size = max(28, int(round(coordinate_bounds.height * 1.6)))
    horizontal_gap = max(8, int(round(coordinate_bounds.height * 0.5)))
    action_x = max(0, coordinate_bounds.x - horizontal_gap - (button_size // 2))
    action_y = max(0, min(image.height - 1, coordinate_bounds.y + (coordinate_bounds.height // 2)))
    left = max(0, action_x - (button_size // 2))
    top = max(0, action_y - (button_size // 2))
    width = min(button_size, image.width - left)
    height = min(button_size, image.height - top)
    return _make_visible(
        selector_id=UiElementId.PNC_WORLD_SEARCH_BUTTON,
        x=left,
        y=top,
        width=width,
        height=height,
        action_point=(action_x, action_y),
    )


def _build_world_map_root_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns coarse world-map-root evidence when map chrome is visible but strict viewport parsing still fails."""

    visible_nav_elements, nav_anchors = _extract_bottom_nav_additions(image=image, anchors=anchors)
    if len(visible_nav_elements) < 3:
        return None
    coordinate_line = _find_world_map_root_coordinate_line(image=image, lines=lines)
    if coordinate_line is None:
        return None
    if _find_world_map_root_label_line(image=image, lines=lines) is None:
        return None
    home_anchor = nav_anchors.get(TextAnchorId.LABEL_HOME)
    if home_anchor is None:
        return None
    visible_elements = dict(visible_nav_elements)
    visible_elements[UiElementId.PNC_BOTTOM_NAV_HOME] = _make_visible_from_bottom_nav_anchor(
        image=image,
        selector_id=UiElementId.PNC_BOTTOM_NAV_HOME,
        anchor=home_anchor,
    )
    visible_elements[UiElementId.PNC_WORLD_COORDINATE_BAR] = _make_visible(
        selector_id=UiElementId.PNC_WORLD_COORDINATE_BAR,
        x=coordinate_line.bounds.x,
        y=coordinate_line.bounds.y,
        width=coordinate_line.bounds.width,
        height=coordinate_line.bounds.height,
        extracted_text=coordinate_line.text.strip(),
    )
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP_ROOT, "ocr_world_map_root"),),
    )


def _build_home_city_root_additions(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
    visible_elements: Mapping[UiElementId, VisibleElement],
) -> ObservationAdditions | None:
    """Returns coarse home-city-root evidence when footer chrome proves the root but exact city support is incomplete."""

    visible_nav_elements, _ = _extract_bottom_nav_additions(image=image, anchors=anchors)
    if len(visible_nav_elements) < 3:
        return None
    if UiElementId.PNC_BOTTOM_NAV_MORE not in visible_nav_elements and UiElementId.PNC_BOTTOM_NAV_ALLIANCE not in visible_nav_elements:
        return None
    if UiElementId.PNC_HOME_WORLD_SWITCH not in visible_elements and UiElementId.PNC_HOME_CHARACTER_PANEL not in visible_elements:
        return None
    return ObservationAdditions(
        visible_elements=visible_nav_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY_ROOT, "partial_home_city_root"),),
    )


def _extract_bottom_nav_additions(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
) -> tuple[dict[UiElementId, VisibleElement], dict[TextAnchorId, DetectedTextAnchor]]:
    """Returns canonical bottom-nav selectors and their source anchors from the footer band."""

    visible_nav_elements: dict[UiElementId, VisibleElement] = {}
    nav_anchors: dict[TextAnchorId, DetectedTextAnchor] = {}
    for anchor in anchors:
        if anchor.bounds.y < int(image.height * 0.86):
            continue
        selector_id = _HOME_NAV_SELECTOR_BY_TEXT_ANCHOR.get(anchor.id)
        if selector_id is None or selector_id in visible_nav_elements:
            continue
        visible_nav_elements[selector_id] = _make_visible_from_bottom_nav_anchor(
            image=image,
            selector_id=selector_id,
            anchor=anchor,
        )
        nav_anchors[anchor.id] = anchor
    return visible_nav_elements, nav_anchors


def _find_world_map_root_coordinate_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> OcrLine | None:
    """Returns one coarse coordinate-bar OCR line when both world axes are visible in the top HUD band."""

    candidate_lines = tuple(
        line
        for line in lines
        if line.bounds.y <= int(image.height * 0.18) and line.bounds.x <= int(image.width * 0.72)
    )
    for line in candidate_lines:
        if world_coordinate_text_matches(line.text):
            return line
    return None


def _find_world_map_root_label_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> OcrLine | None:
    """Returns one OCR line that looks map-owned instead of root-footer or resource chrome."""

    min_y = int(image.height * 0.14)
    max_y = int(image.height * 0.82)
    for line in lines:
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        normalized = normalize_ocr_text(line.text)
        if normalized == "":
            continue
        if normalized.startswith("LFG") or normalized.startswith("K") and any(character.isdigit() for character in normalized):
            return line
        if _WORLD_ROOT_DISTANCE_PATTERN.search(normalized) is not None:
            return line
        if "GATHERING" in normalized or "ENCHANTED" in normalized:
            return line
    return None


def _build_bag_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns bag-screen selectors when OCR matches the live inventory layout."""

    bag_anchor = _find_bag_tab_anchor(image=image, anchors=anchors)
    if bag_anchor is None:
        return None
    use_line = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="USE",
        min_x=int(image.width * 0.7),
        min_y=int(image.height * 0.15),
        max_y=int(image.height * 0.85),
    )
    if use_line is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_BAG_MAIN_TAB_BAG: _make_visible_from_anchor(
                selector_id=UiElementId.PNC_BAG_MAIN_TAB_BAG,
                anchor=bag_anchor,
            ),
            UiElementId.PNC_BAG_USE_BUTTON: _make_visible(
                selector_id=UiElementId.PNC_BAG_USE_BUTTON,
                x=use_line.bounds.x,
                y=use_line.bounds.y,
                width=use_line.bounds.width,
                height=use_line.bounds.height,
                extracted_text=use_line.text,
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_BAG, "ocr_bag_layout"),),
    )


def _find_bag_tab_anchor(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
) -> DetectedTextAnchor | None:
    """Returns the bag-tab anchor from the header band when it is present."""

    candidates = tuple(
        anchor
        for anchor in anchors
        if anchor.id == TextAnchorId.LABEL_BAG and anchor.bounds.y <= int(image.height * 0.15)
    )
    if not candidates:
        return None
    return max(candidates, key=lambda anchor: anchor.bounds.y)


def _build_alliance_join_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the join-alliance landing screen when the account is not yet in an alliance."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="JOINALLIANCE",
        max_y=int(image.height * 0.5),
    )
    primary_join = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="JOIN",
        min_y=int(image.height * 0.65),
    )
    create_alliance = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="CREATEALLIANCE",
        min_y=int(image.height * 0.65),
    )
    if header is None or primary_join is None or create_alliance is None:
        return None
    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ALLIANCE_JOIN, "ocr_alliance_join_landing"),),
    )


def _build_daily_to_do_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the Daily To-Do overlay when OCR matches the live task checklist layout."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="DAILYTODO",
        max_y=int(image.height * 0.28),
    )
    if header is None:
        return None
    close_hint = _find_line_with_normalized_text(
        lines=lines,
        normalized_text="TAPTOCLOSE",
        min_y=int(image.height * 0.78),
    )
    if close_hint is None:
        return None
    section_count = sum(1 for line in lines if normalize_ocr_text(line.text) in _DAILY_TO_DO_SECTION_TEXTS)
    if section_count < 2:
        return None
    go_count = sum(
        1
        for line in lines
        if normalize_ocr_text(line.text) == "GO"
        and line.bounds.x >= int(image.width * 0.55)
    )
    if go_count < 2:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_DAILY_TO_DO_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_DAILY_TO_DO_HEADER,
                line=header,
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_DAILY_TO_DO, "ocr_daily_to_do_overlay"),),
    )


def _build_chat_overlay_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the chat overlay when OCR exposes the header and shared channel tabs."""

    header = _find_line_with_normalized_text(
        lines=lines,
        normalized_text=_CHAT_HEADER_TEXT,
        min_x=int(image.width * 0.12),
        max_y=int(image.height * 0.08),
    )
    kingdom = _find_line_with_normalized_text(
        lines=lines,
        normalized_text=_CHAT_KINGDOM_TEXT,
        min_x=int(image.width * 0.12),
        min_y=int(image.height * 0.05),
        max_y=int(image.height * 0.14),
    )
    alliance = _find_line_with_normalized_text(
        lines=lines,
        normalized_text=_CHAT_ALLIANCE_TEXT,
        min_x=int(image.width * 0.55),
        min_y=int(image.height * 0.05),
        max_y=int(image.height * 0.14),
    )
    if header is None or kingdom is None or alliance is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_CHAT_HEADER: _make_visible_from_line(
                selector_id=UiElementId.PNC_CHAT_HEADER,
                line=header,
            ),
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_CHAT, "ocr_chat_overlay"),),
    )


def _resolve_active_chat_channel(
    *,
    image: Image.Image,
    kingdom_region: object,
    alliance_region: object,
) -> ChatChannel | None:
    """Returns the highlighted chat tab when the shared color signal is strong enough to trust."""

    kingdom_warmth = _region_warmth(image, kingdom_region)
    alliance_warmth = _region_warmth(image, alliance_region)
    if max(kingdom_warmth, alliance_warmth) < _CHAT_ACTIVE_TAB_MIN_WARMTH:
        return None
    if abs(kingdom_warmth - alliance_warmth) < _CHAT_ACTIVE_TAB_MIN_DELTA:
        return None
    return ChatChannel.WORLD if kingdom_warmth > alliance_warmth else ChatChannel.ALLIANCE


def _is_empty_chat_draft_text(normalized_text: str) -> bool:
    """Returns whether one normalized chat-input OCR read matches the empty placeholder."""

    if normalized_text == "":
        return True
    if len(normalized_text) < 12 or len(normalized_text) > 24:
        return False
    return _bounded_edit_distance(
        left=normalized_text,
        right=_CHAT_EMPTY_INPUT_PLACEHOLDER_TEXT,
        max_distance=3,
    ) <= 3


def _bounded_edit_distance(*, left: str, right: str, max_distance: int) -> int:
    """Returns a bounded edit distance, stopping early once the requested limit is exceeded."""

    if max_distance < 0:
        raise ValueError("max_distance cannot be negative.")
    if left == right:
        return 0
    if abs(len(left) - len(right)) > max_distance:
        return max_distance + 1
    previous_row = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current_row = [left_index]
        row_minimum = current_row[0]
        for right_index, right_character in enumerate(right, start=1):
            substitution_cost = 0 if left_character == right_character else 1
            current_cost = min(
                previous_row[right_index] + 1,
                current_row[right_index - 1] + 1,
                previous_row[right_index - 1] + substitution_cost,
            )
            current_row.append(current_cost)
            row_minimum = min(row_minimum, current_cost)
        if row_minimum > max_distance:
            return max_distance + 1
        previous_row = current_row
    return previous_row[-1]


def _build_research_tree_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> ObservationAdditions | None:
    """Returns the research-tree screen when OCR matches a live research grid."""

    header = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _RESEARCH_TREE_HEADER_TEXTS,
        max_y=int(image.height * 0.12),
    )
    if header is None:
        return None
    support_count = sum(1 for line in lines if _is_research_tree_support_line(line))
    if support_count < 3:
        return None
    return ObservationAdditions(
        screen_evidence=(ScreenEvidence(ScreenType.PNC_RESEARCH_TREE, "ocr_research_tree"),),
    )
def _has_loading_support(lines: tuple[OcrLine, ...]) -> bool:
    """Returns whether OCR around a reconnect button also contains loading-related language."""

    return any(
        (normalized_text := normalize_ocr_text(line.text)) not in {"", "RECONNECT"}
        and (normalized_text in _LOADING_TEXTS or any(token in normalized_text for token in _LOADING_SUPPORT_TOKENS))
        for line in lines
    )


def _build_labeled_field(
    *,
    image: Image.Image,
    selector_id: UiElementId,
    label_line: OcrLine,
    next_line: OcrLine,
) -> VisibleElement:
    """Builds one large input target from a field label and the next stacked control."""

    left = max(0, min(label_line.bounds.x, next_line.bounds.x) - max(20, image.width // 30))
    right = min(image.width, max(label_line.bounds.x + label_line.bounds.width, next_line.bounds.x + next_line.bounds.width) + max(20, image.width // 20))
    top = max(0, label_line.bounds.y - max(12, label_line.bounds.height // 2))
    bottom = max(top + 1, next_line.bounds.y - max(10, next_line.bounds.height // 2))
    return _make_visible(
        selector_id=selector_id,
        x=left,
        y=top,
        width=max(1, right - left),
        height=max(1, bottom - top),
        extracted_text=label_line.text,
    )


def _find_account_identifier(
    *,
    lines: tuple[OcrLine, ...],
    min_y: int,
    max_y: int,
) -> str | None:
    """Returns a visible account identifier when OCR exposes an email-like username."""

    for line in lines:
        if line.bounds.y < min_y or line.bounds.y > max_y:
            continue
        candidate = line.text.strip()
        if _ACCOUNT_IDENTIFIER_PATTERN.fullmatch(candidate) is None:
            continue
        return candidate
    return None


def _find_line_with_normalized_text(
    *,
    lines: tuple[OcrLine, ...],
    normalized_text: str,
    min_x: int = 0,
    min_y: int = 0,
    max_y: int | None = None,
) -> OcrLine | None:
    """Returns the first OCR line whose normalized text and region match the requested filter."""

    return _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) == normalized_text,
        min_x=min_x,
        min_y=min_y,
        max_y=max_y,
    )


def _find_line_matching(
    *,
    lines: tuple[OcrLine, ...],
    predicate: Callable[[OcrLine], bool],
    min_x: int = 0,
    min_y: int = 0,
    max_y: int | None = None,
) -> OcrLine | None:
    """Returns the first OCR line that matches one shared text-and-region predicate."""

    for line in lines:
        if not predicate(line):
            continue
        if line.bounds.x < min_x or line.bounds.y < min_y:
            continue
        if max_y is not None and line.bounds.y > max_y:
            continue
        return line
    return None


def _find_lord_info_name_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns the displayed lord name from the Lord Info profile band."""

    return _find_profile_name_line(
        image=image,
        lines=lines,
        excluded_texts=_LORD_INFO_EXCLUDED_NAME_TEXTS,
    )


def _find_profile_name_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    excluded_texts: frozenset[str],
    min_y_ratio: float = 0.22,
    max_y_ratio: float = 0.72,
) -> OcrLine | None:
    """Returns the displayed profile name from the shared upper-screen profile band."""

    min_y = int(image.height * min_y_ratio)
    max_y = int(image.height * max_y_ratio)
    candidates = [
        line
        for line in lines
        if _looks_like_profile_name(line, excluded_texts=excluded_texts) and min_y <= line.bounds.y <= max_y
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda line: len(normalize_ocr_text(line.text)))


def _looks_like_lord_info_name(line: OcrLine) -> bool:
    """Returns whether one OCR line looks like the dynamic lord name in the profile view."""

    return _looks_like_profile_name(line, excluded_texts=_LORD_INFO_EXCLUDED_NAME_TEXTS)


def _looks_like_profile_name(line: OcrLine, *, excluded_texts: frozenset[str]) -> bool:
    """Returns whether one OCR line looks like a profile-name label instead of static UI chrome."""

    normalized_text = normalize_ocr_text(line.text)
    if normalized_text == "" or normalized_text in excluded_texts:
        return False
    if any(token in line.text for token in ("/", ":", "$")):
        return False
    return len(normalized_text) >= 5


def _has_remote_profile_layout_support(lines: tuple[OcrLine, ...]) -> bool:
    """Returns whether OCR exposes the gear-tab remote-profile layout used by live player profiles."""

    support_count = sum(1 for line in lines if normalize_ocr_text(line.text) in _PLAYER_PROFILE_LAYOUT_SUPPORT_TEXTS)
    return support_count >= 4


def _lord_info_name_to_current_castle(name_text: str) -> CastleIdentity:
    """Converts the displayed Lord Info name into the current-castle identity signal."""

    return CastleIdentity(
        kingdom="",
        castle_name=_normalize_lord_info_current_castle_name(name_text),
    )


def _normalize_lord_info_current_castle_name(name_text: str) -> str:
    """Returns the canonical castle name from the Lord Info display label.

    The live Lord Info header can prepend the alliance tag, for example
    ``[AAS] pine cobaye 1``, even though the configured castle identity and the
    Manage Char roster use the bare castle name. Current-castle matching should
    therefore strip one leading bracketed alliance tag while preserving the
    exact visible spelling of the castle name itself.
    """

    stripped = name_text.strip()
    normalized = re.sub(r"^\[[^\]]+\]\s*", "", stripped, count=1).strip()
    return stripped if normalized == "" else normalized


def _is_research_tree_support_line(line: OcrLine) -> bool:
    """Returns whether one OCR line looks like a research-node label or progress counter."""

    normalized_text = normalize_ocr_text(line.text)
    if normalized_text == "":
        return False
    if _PROGRESS_COUNTER_PATTERN.match(line.text.strip()) is not None:
        return True
    return any(token in normalized_text for token in _RESEARCH_TREE_SUPPORT_TOKENS)


def _looks_like_castle_selection(
    anchors: tuple[DetectedTextAnchor, ...],
    entries: tuple[DetectedListEntry, ...],
) -> bool:
    """Returns whether OCR output matches the Manage Char screen structure."""

    if any(anchor.id == TextAnchorId.LABEL_MANAGE_CHAR for anchor in anchors):
        return len(entries) >= 1
    if len(entries) < 2:
        return False
    leveled_entries = sum(1 for entry in entries if entry.metadata.get("castle_level") is not None)
    return leveled_entries >= 2


def _extract_castle_entries(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> tuple[DetectedListEntry, ...]:
    """Extracts typed castle rows from OCR lines on the Manage Char screen."""

    kingdom_line_indexes = [index for index, line in enumerate(lines) if _line_has_anchor(line, anchors, TextAnchorId.KINGDOM)]
    entries: list[DetectedListEntry] = []
    for index, start in enumerate(kingdom_line_indexes):
        end = kingdom_line_indexes[index + 1] if index + 1 < len(kingdom_line_indexes) else len(lines)
        entry = _build_castle_entry(
            image=image,
            row_lines=lines[start:end],
            row_anchors=tuple(anchor for anchor in anchors if _anchor_in_line_range(anchor, lines[start:end])),
            next_row_top=None if end >= len(lines) else lines[end].bounds.y,
        )
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def _build_castle_entry(
    *,
    image: Image.Image,
    row_lines: tuple[OcrLine, ...],
    row_anchors: tuple[DetectedTextAnchor, ...],
    next_row_top: int | None,
) -> DetectedListEntry | None:
    """Builds one detected castle entry from the OCR lines belonging to a row."""

    if not row_lines:
        return None
    kingdom_anchor = next((anchor for anchor in row_anchors if anchor.id == TextAnchorId.KINGDOM), None)
    if kingdom_anchor is None:
        return None
    kingdom = kingdom_anchor.metadata_value("kingdom")
    if not isinstance(kingdom, str) or kingdom == "":
        return None

    level_anchor = next((anchor for anchor in row_anchors if anchor.id == TextAnchorId.CASTLE_LEVEL), None)
    level_line = next((line for line in row_lines if level_anchor is not None and line.bounds == level_anchor.bounds), None)
    castle_name_line = _find_castle_name_line(row_lines, row_anchors=row_anchors, level_line=level_line)
    if castle_name_line is None:
        return None

    row_top = max(0, row_lines[0].bounds.y - 8)
    row_bottom = _resolve_row_bottom(row_lines, level_line=level_line, next_row_top=next_row_top, image_height=image.height)
    row_height = max(1, row_bottom - row_top)
    selected = _has_selected_checkmark(image, row_top=row_top, row_bottom=row_bottom)
    castle_level = level_anchor.metadata_value("castle_level") if level_anchor is not None else None
    if castle_level is not None and not isinstance(castle_level, int):
        castle_level = None
    return DetectedListEntry(
        kind=ListEntryKind.CASTLE,
        bounds=Bounds(x=0, y=row_top, width=image.width, height=row_height),
        title_text=castle_name_line.text.strip(),
        subtitle_text=row_lines[0].text.strip(),
        selected=selected,
        action_point=(image.width // 2, row_top + row_height // 2),
        metadata={
            "kingdom": kingdom,
            "castle_level": castle_level,
        },
    )


def _entry_to_current_castle(entry: DetectedListEntry | None) -> CastleIdentity | None:
    """Converts the selected castle-roster row into the active castle identity when available."""

    if entry is None or entry.title_text is None:
        return None
    kingdom = entry.metadata.get("kingdom")
    castle_level = entry.metadata.get("castle_level")
    if not isinstance(kingdom, str) or kingdom == "":
        return None
    if castle_level is not None and not isinstance(castle_level, int):
        return None
    return CastleIdentity(
        kingdom=kingdom,
        castle_name=entry.title_text,
        castle_level=castle_level,
    )


def _find_castle_name_line(
    row_lines: tuple[OcrLine, ...],
    *,
    row_anchors: tuple[DetectedTextAnchor, ...],
    level_line: OcrLine | None,
) -> OcrLine | None:
    """Returns the OCR line that most likely contains the castle name."""

    for line in row_lines[1:]:
        if _line_has_anchor(line, row_anchors, TextAnchorId.KINGDOM):
            continue
        if _line_has_anchor(line, row_anchors, TextAnchorId.CASTLE_LEVEL):
            continue
        if level_line is not None and line.bounds.y > level_line.bounds.y:
            continue
        if normalize_ocr_text(line.text) == "":
            continue
        return line
    return None


def _resolve_row_bottom(
    row_lines: tuple[OcrLine, ...],
    *,
    level_line: OcrLine | None,
    next_row_top: int | None,
    image_height: int,
) -> int:
    """Resolves a stable vertical tap target for one castle row."""

    content_bottom = row_lines[0].bounds.y + row_lines[0].bounds.height + 48
    if level_line is not None:
        content_bottom = level_line.bounds.y + level_line.bounds.height + 12
    if next_row_top is not None:
        return min(image_height, max(content_bottom, next_row_top - 8))
    return min(image_height, max(content_bottom, row_lines[0].bounds.y + 88))


def _has_selected_checkmark(image: Image.Image, *, row_top: int, row_bottom: int) -> bool:
    """Returns whether the castle row contains the green selection checkmark."""

    check_left = int(image.width * 0.82)
    crop = image.crop((check_left, row_top, image.width, row_bottom)).convert("RGB")
    green_pixels = 0
    threshold = max(24, (crop.width * crop.height) // 150)
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = pixels[x, y]
            if green >= 140 and green >= red + 35 and green >= blue + 35:
                green_pixels += 1
                if green_pixels >= threshold:
                    return True
    return False


def _build_home_action_additions(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
) -> dict[UiElementId, VisibleElement]:
    """Returns OCR-derived home-city action controls that support city classification."""

    visible_elements: dict[UiElementId, VisibleElement] = {}
    for anchor in anchors:
        selector_id = _HOME_ACTION_SELECTOR_BY_TEXT_ANCHOR.get(anchor.id)
        if selector_id is None or selector_id in visible_elements:
            continue
        if not _is_home_action_anchor(image=image, anchor=anchor, selector_id=selector_id):
            continue
        visible_elements[selector_id] = _make_visible_from_anchor(selector_id=selector_id, anchor=anchor)
    return visible_elements


def _is_home_action_anchor(
    *,
    image: Image.Image,
    anchor: DetectedTextAnchor,
    selector_id: UiElementId,
) -> bool:
    """Returns whether one OCR anchor sits in the expected home-city action area."""

    in_standard_action_band = (
        anchor.bounds.y >= int(image.height * 0.45)
        and anchor.bounds.y <= int(image.height * 0.85)
        and anchor.bounds.x <= int(image.width * 0.85)
    )
    if in_standard_action_band:
        return True
    if selector_id != UiElementId.PNC_HOME_BUILD_BUTTON:
        return False
    return (
        anchor.bounds.x <= int(image.width * 0.18)
        and anchor.bounds.y >= int(image.height * 0.15)
        and anchor.bounds.y <= int(image.height * 0.85)
    )


def _has_building_detail_conflicts(
    *,
    image: Image.Image,
    anchors: tuple[DetectedTextAnchor, ...],
) -> bool:
    """Returns whether OCR contains stronger evidence for a non-building screen."""

    if any(anchor.id in _BUILDING_DETAIL_CONFLICT_ANCHOR_IDS for anchor in anchors):
        return True
    return any(
        anchor.id in _HOME_NAV_SELECTOR_BY_TEXT_ANCHOR
        and anchor.bounds.y >= int(image.height * 0.86)
        for anchor in anchors
    )


def _find_building_title_line(*, image: Image.Image, lines: tuple[OcrLine, ...]) -> OcrLine | None:
    """Returns a conservative building-title candidate from the screen header."""

    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if normalized_text not in _BUILDING_DETAIL_TITLE_TEXTS:
            continue
        if line.bounds.y > int(image.height * 0.09):
            continue
        if line.bounds.x > int(image.width * 0.35):
            continue
        return line
    return None


def _find_building_detail_support_line(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    title_line: OcrLine,
) -> OcrLine | None:
    """Returns a supporting body line that makes the OCR building guess less ambiguous."""

    for line in lines:
        normalized_text = normalize_ocr_text(line.text)
        if line == title_line:
            continue
        if normalized_text in {"", "UPGRADE"}:
            continue
        if line.bounds.y <= title_line.bounds.y + title_line.bounds.height:
            continue
        if line.bounds.y >= int(image.height * 0.55):
            continue
        if line.bounds.x > int(image.width * 0.45):
            continue
        return line
    return None


def _make_visible(
    *,
    selector_id: UiElementId,
    x: int,
    y: int,
    width: int,
    height: int,
    extracted_text: str | None = None,
    action_point: tuple[int, int] | None = None,
) -> VisibleElement:
    """Builds one derived visible element from OCR or anchored geometry."""

    return VisibleElement(
        selector_id=selector_id,
        bounds=Bounds(x=x, y=y, width=max(1, width), height=max(1, height)),
        confidence=1.0,
        source_kind=VisibleElementSourceKind.OCR,
        extracted_text=extracted_text,
        action_point=action_point,
    )


def _make_visible_from_anchor(*, selector_id: UiElementId, anchor: DetectedTextAnchor) -> VisibleElement:
    """Builds one derived visible element from a detected text anchor."""

    return _make_visible(
        selector_id=selector_id,
        x=anchor.bounds.x,
        y=anchor.bounds.y,
        width=anchor.bounds.width,
        height=anchor.bounds.height,
        extracted_text=anchor.text,
    )


def _make_visible_from_line(*, selector_id: UiElementId, line: OcrLine) -> VisibleElement:
    """Builds one derived visible element from one OCR line region."""

    return _make_visible(
        selector_id=selector_id,
        x=line.bounds.x,
        y=line.bounds.y,
        width=line.bounds.width,
        height=line.bounds.height,
        extracted_text=line.text,
    )


def _make_visible_from_lines(*, selector_id: UiElementId, lines: tuple[OcrLine, ...]) -> VisibleElement:
    """Builds one derived visible element that spans a related group of OCR lines."""

    if not lines:
        raise ValueError("Visible OCR groups require at least one line.")
    left = min(line.bounds.x for line in lines)
    top = min(line.bounds.y for line in lines)
    right = max(line.bounds.x + line.bounds.width for line in lines)
    bottom = max(line.bounds.y + line.bounds.height for line in lines)
    return _make_visible(
        selector_id=selector_id,
        x=left,
        y=top,
        width=max(1, right - left),
        height=max(1, bottom - top),
    )


def _make_visible_from_mail_hub_row(*, image: Image.Image, selector_id: UiElementId, line: OcrLine) -> VisibleElement:
    """Builds one mail-hub row selector with a full-row tap target at the right-side affordance."""

    row_height = max(line.bounds.height * 3, int(image.height * 0.085))
    row_top = max(0, line.bounds.y - ((row_height - line.bounds.height) // 2))
    row_left = max(0, line.bounds.x - int(image.width * 0.23))
    row_width = min(image.width - row_left, int(image.width * 0.95))
    action_point = (
        min(image.width - 1, int(round(image.width * 0.91))),
        min(image.height - 1, row_top + (row_height // 2)),
    )
    return _make_visible(
        selector_id=selector_id,
        x=row_left,
        y=row_top,
        width=row_width,
        height=row_height,
        extracted_text=line.text,
        action_point=action_point,
    )


def _make_visible_from_bottom_nav_anchor(
    *,
    image: Image.Image,
    selector_id: UiElementId,
    anchor: DetectedTextAnchor,
) -> VisibleElement:
    """Builds one bottom-nav selector with a raised tap point instead of the text baseline."""

    label_center_x = anchor.bounds.x + (anchor.bounds.width // 2)
    target_width = max(anchor.bounds.width * 3, int(image.width * 0.12))
    target_height = max(anchor.bounds.height * 4, int(image.height * 0.09))
    target_left = min(max(0, label_center_x - (target_width // 2)), max(0, image.width - target_width))
    target_top = max(0, anchor.bounds.y - int(target_height * 0.82))
    action_point = (label_center_x, target_top + (target_height // 2))
    return _make_visible(
        selector_id=selector_id,
        x=target_left,
        y=target_top,
        width=target_width,
        height=target_height,
        extracted_text=anchor.text,
        action_point=action_point,
    )


def _make_visible_from_bottom_nav_line(
    *,
    image: Image.Image,
    selector_id: UiElementId,
    line: OcrLine,
) -> VisibleElement:
    """Builds one bottom-nav-like selector from an OCR line with a raised tap point over the icon area."""

    label_center_x = line.bounds.x + (line.bounds.width // 2)
    target_width = max(line.bounds.width * 3, int(image.width * 0.12))
    target_height = max(line.bounds.height * 4, int(image.height * 0.09))
    target_left = min(max(0, label_center_x - (target_width // 2)), max(0, image.width - target_width))
    target_top = max(0, line.bounds.y - int(target_height * 0.82))
    action_point = (label_center_x, target_top + (target_height // 2))
    return _make_visible(
        selector_id=selector_id,
        x=target_left,
        y=target_top,
        width=target_width,
        height=target_height,
        extracted_text=line.text,
        action_point=action_point,
    )


def _make_visible_from_bottom_nav_line_segment(
    *,
    image: Image.Image,
    selector_id: UiElementId,
    line: OcrLine,
    normalized_text_segment: str,
) -> VisibleElement:
    """Builds one bottom-tab selector from a proportional substring of an OCR line."""

    normalized_text = normalize_ocr_text(line.text)
    start = normalized_text.find(normalized_text_segment)
    if start < 0:
        return _make_visible_from_bottom_nav_line(image=image, selector_id=selector_id, line=line)
    total_length = max(len(normalized_text), 1)
    segment_start_ratio = start / total_length
    segment_end_ratio = (start + len(normalized_text_segment)) / total_length
    segment_left = line.bounds.x + int(round(line.bounds.width * segment_start_ratio))
    segment_right = line.bounds.x + int(round(line.bounds.width * segment_end_ratio))
    segment_line = OcrLine(
        text=normalized_text_segment,
        bounds=Region(
            x=segment_left,
            y=line.bounds.y,
            width=max(1, segment_right - segment_left),
            height=line.bounds.height,
        ),
        confidence=line.confidence,
    )
    return _make_visible_from_bottom_nav_line(image=image, selector_id=selector_id, line=segment_line)


def _make_visible_from_more_overlay_line(
    *,
    image: Image.Image,
    selector_id: UiElementId,
    line: OcrLine,
) -> VisibleElement:
    """Builds one More-overlay action target with a tap point raised above the footer label."""

    label_center_x = line.bounds.x + (line.bounds.width // 2)
    target_width = max(line.bounds.width + 36, int(image.width * 0.12))
    target_height = max(line.bounds.height + 72, int(image.height * 0.07))
    target_left = min(max(0, label_center_x - (target_width // 2)), max(0, image.width - target_width))
    target_top = max(0, line.bounds.y - int(target_height * 0.8))
    action_point = (label_center_x, max(0, line.bounds.y - max(24, line.bounds.height)))
    return _make_visible(
        selector_id=selector_id,
        x=target_left,
        y=target_top,
        width=target_width,
        height=target_height,
        extracted_text=line.text,
        action_point=action_point,
    )


def _make_visible_from_entry(*, selector_id: UiElementId, entry: DetectedListEntry) -> VisibleElement:
    """Builds one derived visible element from a detected list entry."""

    return _make_visible(
        selector_id=selector_id,
        x=entry.bounds.x,
        y=entry.bounds.y,
        width=entry.bounds.width,
        height=entry.bounds.height,
        extracted_text=entry.title_text,
    )


def _line_has_anchor(line: OcrLine, anchors: tuple[DetectedTextAnchor, ...], anchor_id: TextAnchorId) -> bool:
    """Returns whether one OCR line produced the requested structured anchor."""

    return any(anchor.id == anchor_id and anchor.bounds == line.bounds for anchor in anchors)


def _anchor_in_line_range(anchor: DetectedTextAnchor, row_lines: tuple[OcrLine, ...]) -> bool:
    """Returns whether one anchor belongs to the provided OCR line range."""

    if not row_lines:
        return False
    top = row_lines[0].bounds.y
    bottom = row_lines[-1].bounds.y + row_lines[-1].bounds.height
    return anchor.bounds.y >= top and anchor.bounds.y <= bottom


def _region_warmth(image: Image.Image, region: object) -> float:
    """Returns a simple warm-color score for one region used by the chat-tab state parser."""

    red, green, blue = _region_average_rgb(image, region)
    return red + green - blue


def _region_brightness(image: Image.Image, region: object) -> float:
    """Returns the mean brightness of one region used by the chat footer parser."""

    red, green, blue = _region_average_rgb(image, region)
    return (red + green + blue) / 3.0


def _region_average_rgb(image: Image.Image, region: object) -> tuple[float, float, float]:
    """Returns the average RGB values for one region-like object."""

    crop = image.crop((region.x, region.y, region.x + region.width, region.y + region.height)).convert("RGB")
    red_total = 0
    green_total = 0
    blue_total = 0
    pixel_count = crop.width * crop.height
    pixels = crop.load()
    for y in range(crop.height):
        for x in range(crop.width):
            red, green, blue = pixels[x, y]
            red_total += red
            green_total += green
            blue_total += blue
    return (
        red_total / pixel_count,
        green_total / pixel_count,
        blue_total / pixel_count,
    )
