"""P&C-specific OCR enrichment for dynamic screens without template anchors."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from PIL import Image

from pnc_automation.config.models import CastleIdentity
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.mail import MailboxType, compose_text_field_selector_ids
from pnc_automation.pnc.observation import (
    Bounds,
    CurrentCastleEvidenceKind,
    DetectedListEntry,
    ListEntryKind,
    ObservedTextFieldState,
    VisibleElement,
    VisibleElementSourceKind,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import ObservationAdditions
from pnc_automation.vision.observation_request import ObservationRequest
from pnc_automation.vision.pnc_ocr_capabilities import can_attempt_screen_family_ocr
from pnc_automation.vision.ocr_service import OcrLine, OcrService
from pnc_automation.vision.screen_classifier import ScreenEvidence
from pnc_automation.vision.selectors import Region, SelectorRegistry
from pnc_automation.vision.spatial_surfaces import (
    build_home_city_spatial_surface,
    build_world_map_spatial_surface,
    parse_world_viewport,
)
from pnc_automation.vision.text_anchors import (
    DetectedTextAnchor,
    TextAnchorDetector,
    TextAnchorId,
    normalize_ocr_text,
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
_POPUP_PRIMARY_ACTION_ANCHOR_IDS = frozenset(
    {
        TextAnchorId.LABEL_CONFIRM,
        TextAnchorId.LABEL_JOIN_APPLY,
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
_CURRENCY_TEXT_PATTERN = re.compile(r"\$\s*\d+(?:[.,]\d+)?")
_RESEARCH_TREE_HEADER_TEXTS = frozenset(
    {
        "MILITARY",
        "DEVELOPMENT",
        "ECONOMY",
        "COMBAT",
    }
)
_ACADEMY_TITLE_TEXTS = frozenset(
    {
        "ACADEMY",
        "INSTITUTE",
    }
)
_ACADEMY_CATEGORY_TEXTS = frozenset(
    {
        "DEVELOPMENT",
        "ECONOMY",
        "MILITARY",
        "FORTIFICATION",
        "UNITTACTICS",
        "FORMATIONS",
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
        if chat_geometry is not None and not request.include_popup_guard and not request.include_loading_guard:
            return chat_geometry
        if not request.requires_ocr(screen_type):
            return ObservationAdditions()
        ocr_result = self.ocr_service.read_result(image)
        lines = tuple(sorted(ocr_result.lines, key=lambda line: (line.bounds.y, line.bounds.x)))
        anchors = self.text_anchor_detector.detect(ocr_result)
        alliance_status_banner = _build_alliance_home_status_banner_additions(
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
        if request.allows_screen(ScreenType.PNC_BUILDING_DETAILS) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_BUILDING_DETAILS,
            observed_screen=screen_type,
        ):
            building_detail = _build_building_detail_additions(image=image, lines=lines, anchors=anchors)
            if building_detail is not None:
                return building_detail
        if request.allows_screen(ScreenType.PNC_WORLD_MAP) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_WORLD_MAP,
            observed_screen=screen_type,
        ):
            world_map = _build_world_map_additions(
                image=image,
                lines=lines,
                anchors=anchors,
                selector_registry=self.selector_registry,
            )
            if world_map is not None:
                return world_map
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
        if request.allows_screen(ScreenType.PNC_ACADEMY) and can_attempt_screen_family_ocr(
            request_screen=ScreenType.PNC_ACADEMY,
            observed_screen=screen_type,
        ):
            academy = _build_academy_additions(image=image, lines=lines, anchors=anchors)
            if academy is not None:
                return academy
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
            return ObservationAdditions() if alliance_status_banner is None else alliance_status_banner
        entries = _extract_castle_entries(image=image, lines=lines, anchors=anchors)
        if not _looks_like_castle_selection(anchors, entries):
            return ObservationAdditions() if alliance_status_banner is None else alliance_status_banner

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
            list_entries=_extract_chat_message_entries(image=image, lines=lines),
            screen_evidence=chat.screen_evidence,
            active_chat_channel=chat_state.active_chat_channel,
            text_field_states=chat_state.text_field_states,
            chat_draft_empty=chat_state.chat_draft_empty,
            chat_draft_text=chat_state.chat_draft_text,
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
        visible_elements[UiElementId.PNC_STATUS_BANNER] = _make_visible_from_line(
            selector_id=UiElementId.PNC_STATUS_BANNER,
            line=status_banner,
        )
    return ObservationAdditions(
        visible_elements=visible_elements,
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ALLIANCE_HOME, "ocr_alliance_home"),),
    )


def _build_alliance_home_status_banner_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    request: ObservationRequest,
) -> ObservationAdditions | None:
    """Returns the transient alliance-home status banner even when the rest of the screen is not classifiable."""

    if not request.allows_screen(ScreenType.PNC_ALLIANCE_HOME):
        return None
    status_banner = _find_alliance_home_status_banner_line(image=image, lines=lines)
    if status_banner is None:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_STATUS_BANNER: _make_visible_from_line(
                selector_id=UiElementId.PNC_STATUS_BANNER,
                line=status_banner,
            )
        }
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


def _extract_chat_message_entries(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
) -> tuple[DetectedListEntry, ...]:
    """Extracts visible chat sender rows that can open the shared player-action popup."""

    candidate_lines = [line for line in lines if _is_chat_message_candidate_line(image=image, line=line)]
    grouped_rows = _group_lines_by_vertical_gap(candidate_lines, gap=max(24, image.height // 36))
    entries: list[DetectedListEntry] = []
    for row_lines in grouped_rows:
        if not row_lines:
            continue
        sender_line = row_lines[0]
        sender_name = sender_line.text.strip()
        if sender_name == "":
            continue
        message_lines = tuple(line.text.strip() for line in row_lines[1:] if line.text.strip() != "")
        bounds = _entry_bounds_from_lines(image=image, row_lines=row_lines)
        entries.append(
            DetectedListEntry(
                kind=ListEntryKind.CHAT_MESSAGE,
                bounds=bounds,
                title_text=sender_name,
                subtitle_text=" ".join(message_lines) or None,
                action_point=bounds.center(),
                metadata={"message_preview": " ".join(message_lines) or None},
            )
        )
    return tuple(entries)


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


def _is_chat_message_candidate_line(*, image: Image.Image, line: OcrLine) -> bool:
    """Returns whether one OCR line can belong to the visible chat-message list."""

    normalized_text = normalize_ocr_text(line.text)
    if normalized_text == "":
        return False
    if line.bounds.y < int(image.height * 0.16) or line.bounds.y > int(image.height * 0.8):
        return False
    if normalized_text in {_CHAT_HEADER_TEXT, _CHAT_KINGDOM_TEXT, _CHAT_ALLIANCE_TEXT, *_SEND_TEXTS}:
        return False
    if _is_empty_chat_draft_text(normalized_text):
        return False
    return True


def _build_popup_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns popup dismissal controls when OCR matches a blocking modal footer."""

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
    """Returns whether one OCR anchor sits where centered modal buttons normally appear."""

    return (
        anchor.bounds.y >= int(image.height * 0.45)
        and anchor.bounds.y <= int(image.height * 0.78)
        and anchor.bounds.x >= int(image.width * 0.08)
        and anchor.bounds.x <= int(image.width * 0.85)
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
    support_count = sum(1 for line in lines if normalize_ocr_text(line.text) in _MORE_MENU_SUPPORT_TEXTS)
    if support_count + len(visible_elements) < 3:
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
) -> ObservationAdditions | None:
    """Returns world-map classification when coordinates and bottom navigation are both OCR-proven."""

    visible_nav_elements, nav_anchors = _extract_bottom_nav_additions(image=image, anchors=anchors)
    if len(visible_nav_elements) < 3:
        return None
    home_anchor = nav_anchors.get(TextAnchorId.LABEL_HOME)
    if home_anchor is None:
        return None
    parsed_viewport = parse_world_viewport(image=image, lines=lines)
    if parsed_viewport is None:
        return None
    visible_elements = dict(visible_nav_elements)
    visible_elements[UiElementId.PNC_WORLD_HOME_NAV] = _make_visible_from_bottom_nav_anchor(
        image=image,
        selector_id=UiElementId.PNC_WORLD_HOME_NAV,
        anchor=home_anchor,
    )
    visible_elements[UiElementId.PNC_WORLD_COORDINATE_BAR] = _make_visible(
        selector_id=UiElementId.PNC_WORLD_COORDINATE_BAR,
        x=parsed_viewport.coordinate_bounds.x,
        y=parsed_viewport.coordinate_bounds.y,
        width=parsed_viewport.coordinate_bounds.width,
        height=parsed_viewport.coordinate_bounds.height,
        extracted_text=parsed_viewport.coordinate_text,
    )
    return ObservationAdditions(
        visible_elements=visible_elements,
        spatial_surface=build_world_map_spatial_surface(
            image=image,
            lines=lines,
            selector_registry=selector_registry,
        ),
        screen_evidence=(ScreenEvidence(ScreenType.PNC_WORLD_MAP, "ocr_world_coordinates_and_bottom_nav"),),
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


def _build_academy_additions(
    *,
    image: Image.Image,
    lines: tuple[OcrLine, ...],
    anchors: tuple[DetectedTextAnchor, ...],
) -> ObservationAdditions | None:
    """Returns the academy or institute overview screen from live OCR structure."""

    title_line = _find_line_matching(
        lines=lines,
        predicate=lambda line: normalize_ocr_text(line.text) in _ACADEMY_TITLE_TEXTS,
        max_y=int(image.height * 0.1),
    )
    if title_line is None:
        return None
    upgrade_anchor = next(
        (
            anchor
            for anchor in anchors
            if anchor.id == TextAnchorId.LABEL_UPGRADE
            and anchor.bounds.x >= int(image.width * 0.55)
            and anchor.bounds.y <= int(image.height * 0.4)
        ),
        None,
    )
    if upgrade_anchor is None:
        return None
    category_count = sum(
        1
        for line in lines
        if normalize_ocr_text(line.text) in _ACADEMY_CATEGORY_TEXTS
    )
    if category_count < 3:
        return None
    return ObservationAdditions(
        visible_elements={
            UiElementId.PNC_BACK_BUTTON_TOP_LEFT: _make_visible(
                selector_id=UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                x=0,
                y=0,
                width=max(1, int(image.width * 0.12)),
                height=max(1, int(image.height * 0.08)),
            )
        },
        screen_evidence=(ScreenEvidence(ScreenType.PNC_ACADEMY, "ocr_academy_overview"),),
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
        castle_name=name_text.strip(),
    )


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
        return True
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
