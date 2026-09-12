"""Conservative screen classification built from detected selector anchors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pnc_automation.app.pnc.domain.observation import VisibleElement, VisibleElementSourceKind
from pnc_automation.app.pnc.domain.screen_decision import (
    BLOCKING_SCREEN_TYPES,
    GuardVerdict,
    ScreenDecision,
    ScreenEvidence,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    """Defines anchor selectors that imply one screen type."""

    screen_type: ScreenType
    required_all: frozenset[UiElementId]
    required_any: frozenset[UiElementId] = frozenset()


class ScreenClassifier:
    """Classifies the current screen from detected selector anchors."""

    def __init__(self) -> None:
        """Initializes the ordered classification rules."""

        self._rules = (
            ClassificationRule(
                screen_type=ScreenType.PNC_LOGIN,
                required_all=frozenset(
                    {
                        UiElementId.PNC_LOGIN_USERNAME_FIELD,
                        UiElementId.PNC_LOGIN_PASSWORD_FIELD,
                        UiElementId.PNC_LOGIN_SUBMIT_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CASTLE_SELECTION,
                required_all=frozenset({UiElementId.PNC_CASTLE_LIST_ENTRY}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_LORD_INFO,
                required_all=frozenset(
                    {
                        UiElementId.PNC_LORD_INFO_HEADER,
                        UiElementId.PNC_LORD_INFO_NAME_LABEL,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SETTINGS,
                required_all=frozenset(
                    {
                        UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        UiElementId.PNC_MORE_MANAGE_CHAR,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_PLAYER_TERRITORY,
                required_all=frozenset(
                    {
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_PLAYER_PROFILE,
                required_all=frozenset(
                    {
                        UiElementId.PNC_PLAYER_PROFILE_HEADER,
                        UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_VIP,
                required_all=frozenset({UiElementId.PNC_VIP_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_VIP_DAILY_RESET,
                required_all=frozenset(
                    {
                        UiElementId.PNC_VIP_DAILY_RESET_HEADER,
                        UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_IMPROVE_MIGHT,
                required_all=frozenset({UiElementId.PNC_IMPROVE_MIGHT_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WORLD_MAP,
                required_all=frozenset({UiElementId.PNC_WORLD_HOME_NAV}),
                required_any=frozenset(
                    {
                        UiElementId.PNC_WORLD_COORDINATE_BAR,
                        UiElementId.PNC_WORLD_SEARCH_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WORLD_COORDINATE_DIALOG,
                required_all=frozenset(
                    {
                        UiElementId.PNC_WORLD_COORDINATE_DIALOG_GO_BUTTON,
                        UiElementId.PNC_WORLD_COORDINATE_DIALOG_CLOSE_BUTTON,
                    }
                ),
                required_any=frozenset(
                    {
                        UiElementId.PNC_WORLD_COORDINATE_DIALOG_K_FIELD,
                        UiElementId.PNC_WORLD_COORDINATE_DIALOG_X_FIELD,
                        UiElementId.PNC_WORLD_COORDINATE_DIALOG_Y_FIELD,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WORLD_MAP_OVERVIEW,
                required_all=frozenset(
                    {
                        UiElementId.PNC_WORLD_OVERVIEW_HEADER,
                        UiElementId.PNC_WORLD_OVERVIEW_CLOSE_BUTTON,
                        UiElementId.PNC_WORLD_OVERVIEW_MAP_REGION,
                    }
                ),
                required_any=frozenset(
                    {
                        UiElementId.PNC_WORLD_OVERVIEW_WORLD_ICON,
                        UiElementId.PNC_WORLD_OVERVIEW_LEGEND_BUTTON,
                        UiElementId.PNC_WORLD_OVERVIEW_VISIBILITY_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WORLD_KINGDOM_LIST,
                required_all=frozenset({UiElementId.PNC_WORLD_KINGDOM_LIST_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HOME_CITY,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HOME_WORLD_SWITCH,
                        UiElementId.PNC_HOME_CHARACTER_PANEL,
                    }
                ),
                required_any=frozenset(
                    {
                        UiElementId.PNC_HOME_BUILD_BUTTON,
                        UiElementId.PNC_HOME_RESEARCH_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BAG,
                required_all=frozenset(
                    {
                        UiElementId.PNC_BAG_MAIN_TAB_BAG,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_QUEST_DAILY,
                required_all=frozenset(
                    {
                        UiElementId.PNC_QUEST_TAB_DAILY,
                        UiElementId.PNC_QUEST_ROW,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_LIST,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HERO_TAB_HERO,
                        UiElementId.PNC_HERO_FILTER_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_DETAIL_UPGRADE,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HERO_DETAIL_TAB_UPGRADE,
                        UiElementId.PNC_HERO_EVOLVE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_DETAIL_ENHANCE,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HERO_DETAIL_TAB_ENHANCE,
                        UiElementId.PNC_HERO_ENHANCE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MAIL_COMPOSE_POPUP,
                required_all=frozenset(
                    {
                        UiElementId.PNC_MAIL_COMPOSE_HEADER,
                        UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MAIL_THREAD,
                required_all=frozenset(
                    {
                        UiElementId.PNC_MAIL_HEADER,
                        UiElementId.PNC_MAIL_THREAD_DELETE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MAILBOX_LIST,
                required_all=frozenset({UiElementId.PNC_MAIL_HEADER}),
                required_any=frozenset(
                    {
                        UiElementId.PNC_MAILBOX_MARK_ALL_AS_READ_BUTTON,
                        UiElementId.PNC_MAILBOX_MANAGE_BUTTON,
                        UiElementId.PNC_MAILBOX_EMPTY_LABEL,
                        UiElementId.PNC_MAIL_THREAD_ROW,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MAIL_HUB,
                required_all=frozenset({UiElementId.PNC_MAIL_ROW_PLAYER_MAIL}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_HOME,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_TILE_TERRITORY}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_MEMBER_LIST,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_ROW}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CHAT,
                required_all=frozenset(
                    {
                        UiElementId.PNC_CHAT_HEADER,
                        UiElementId.PNC_CHAT_SEND_BUTTON,
                    }
                ),
                required_any=frozenset(
                    {
                        UiElementId.PNC_CHAT_TAB_KINGDOM,
                        UiElementId.PNC_CHAT_TAB_ALLIANCE,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
                required_all=frozenset({UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MIGHT_RANK,
                required_all=frozenset({UiElementId.PNC_MIGHT_RANK_ROW}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_DAILY_TO_DO,
                required_all=frozenset({UiElementId.PNC_DAILY_TO_DO_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CASH_MALL,
                required_all=frozenset({UiElementId.PNC_CASH_MALL_TAB_DAILY_SALE}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_GIFT_CENTER,
                required_all=frozenset({UiElementId.PNC_GIFT_CENTER_ENTRY_ROW}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_EVENT_CENTER,
                required_all=frozenset({UiElementId.PNC_EVENT_CENTER_EVENT_ROW}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CASTLE,
                required_all=frozenset({UiElementId.PNC_CASTLE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_TERRITORY_OVERVIEW,
                required_all=frozenset({UiElementId.PNC_TERRITORY_OVERVIEW_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HALL_OF_WAR,
                required_all=frozenset({UiElementId.PNC_HALL_OF_WAR_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SACRED_TREE,
                required_all=frozenset({UiElementId.PNC_SACRED_TREE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SACRED_TREE_BLESSING_RECORD,
                required_all=frozenset({UiElementId.PNC_SACRED_TREE_BLESSING_RECORD_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_RARE_EARTH_FIELD,
                required_all=frozenset({UiElementId.PNC_RARE_EARTH_FIELD_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_DISPATCH,
                required_all=frozenset({UiElementId.PNC_DISPATCH_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SANCTUM,
                required_all=frozenset({UiElementId.PNC_SANCTUM_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_RELICS,
                required_all=frozenset({UiElementId.PNC_RELICS_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_TRIAL_CHALLENGE,
                required_all=frozenset({UiElementId.PNC_TRIAL_CHALLENGE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SAUREGG,
                required_all=frozenset({UiElementId.PNC_SAUREGG_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SAUROI_LAIR,
                required_all=frozenset({UiElementId.PNC_SAUROI_LAIR_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_VERSUS_CENTER,
                required_all=frozenset({UiElementId.PNC_VERSUS_CENTER_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_SHOWDOWN_ELEMENTAL_INTRO,
                required_all=frozenset({UiElementId.PNC_ELEMENTAL_FLUCTUATION_INTRO_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_FORMATION,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HERO_FORMATION_HEADER,
                        UiElementId.PNC_HERO_FORMATION_SAVE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_SHOWDOWN_RANKING,
                required_all=frozenset(
                    {
                        UiElementId.PNC_HERO_SHOWDOWN_RANKING_HEADER,
                        UiElementId.PNC_HERO_SHOWDOWN_CURRENT_RANK_LABEL,
                        UiElementId.PNC_HERO_SHOWDOWN_CHALLENGE_BUTTON,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_GODDESS_STATUE,
                required_all=frozenset({UiElementId.PNC_GODDESS_STATUE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BUILD_MENU_FIXED_SLOT,
                required_all=frozenset({UiElementId.PNC_BUILD_HEADER}),
                required_any=frozenset(
                    {
                        UiElementId.PNC_BUILD_INSTITUTE_OPTION,
                        UiElementId.PNC_BUILD_WAREHOUSE_OPTION,
                        UiElementId.PNC_BUILD_TRAP_WORKSHOP_OPTION,
                        UiElementId.PNC_BUILD_GODDESS_STATUE_OPTION,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BUILD_MENU_LARGE_SLOT,
                required_all=frozenset({UiElementId.PNC_BUILD_HEADER}),
                required_any=frozenset(
                    {
                        UiElementId.PNC_BUILD_ALLIANCE_HALL_OPTION,
                        UiElementId.PNC_BUILD_BLACKSMITH_OPTION,
                        UiElementId.PNC_BUILD_MARKET_OPTION,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BUILD_MENU_SMALL_SLOT,
                required_all=frozenset({UiElementId.PNC_BUILD_HEADER}),
                required_any=frozenset(
                    {
                        UiElementId.PNC_BUILD_FARM_OPTION,
                        UiElementId.PNC_BUILD_LUMBER_CAMP_OPTION,
                        UiElementId.PNC_BUILD_MOON_WELL_OPTION,
                        UiElementId.PNC_BUILD_RECRUITING_CENTER_OPTION,
                        UiElementId.PNC_BUILD_INFIRMARY_OPTION,
                        UiElementId.PNC_BUILD_IRON_MINE_OPTION,
                        UiElementId.PNC_BUILD_GOLD_MINE_OPTION,
                    }
                ),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_INSTITUTE,
                required_all=frozenset({UiElementId.PNC_INSTITUTE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WAREHOUSE,
                required_all=frozenset({UiElementId.PNC_WAREHOUSE_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_TRAP_WORKSHOP,
                required_all=frozenset({UiElementId.PNC_TRAP_WORKSHOP_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_HALL,
                required_all=frozenset({UiElementId.PNC_HERO_HALL_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WATCHTOWER,
                required_all=frozenset({UiElementId.PNC_WATCHTOWER_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BLACKSMITH,
                required_all=frozenset({UiElementId.PNC_BLACKSMITH_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_GEAR,
                required_all=frozenset({UiElementId.PNC_GEAR_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_GEM,
                required_all=frozenset({UiElementId.PNC_GEM_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SAURGEM,
                required_all=frozenset({UiElementId.PNC_SAURGEM_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WARSIGIL,
                required_all=frozenset({UiElementId.PNC_WARSIGIL_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_HERO_CURIO,
                required_all=frozenset({UiElementId.PNC_HERO_CURIO_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ASCEND,
                required_all=frozenset({UiElementId.PNC_ASCEND_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_HALL,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_HALL_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MARKET,
                required_all=frozenset({UiElementId.PNC_MARKET_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_MEMBER_REINFORCE,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_HEADER}),
                required_any=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_REINFORCE_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_MEMBER_TRANSPORT,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_HEADER}),
                required_any=frozenset({UiElementId.PNC_ALLIANCE_MEMBER_TRANSPORT_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_INFANTRY_BARRACKS,
                required_all=frozenset({UiElementId.PNC_INFANTRY_BARRACKS_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CAVALRY_BARRACKS,
                required_all=frozenset({UiElementId.PNC_CAVALRY_BARRACKS_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_RANGED_BARRACKS,
                required_all=frozenset({UiElementId.PNC_RANGED_BARRACKS_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SIEGE_FACTORY,
                required_all=frozenset({UiElementId.PNC_SIEGE_FACTORY_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WALL,
                required_all=frozenset({UiElementId.PNC_WALL_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_DEFENSE_INFO,
                required_all=frozenset({UiElementId.PNC_DEFENSE_INFO_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_BUILDING_DETAILS,
                required_all=frozenset({UiElementId.PNC_BUILDING_UPGRADE_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_INSTITUTE,
                required_all=frozenset({UiElementId.PNC_RESEARCH_AVAILABLE_BADGE}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_RESEARCH_TREE,
                required_all=frozenset({UiElementId.PNC_RESEARCH_START_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_GATHER_NODE,
                required_all=frozenset({UiElementId.PNC_GATHER_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_MARCH_CONFIRM,
                required_all=frozenset({UiElementId.PNC_MARCH_CONFIRM_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CAMPAIGN_MAP,
                required_all=frozenset({UiElementId.PNC_CAMPAIGN_ENTRY_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_CAMPAIGN_STAGE,
                required_all=frozenset({UiElementId.PNC_CAMPAIGN_BATTLE_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.ANDROID_HOME,
                required_all=frozenset({UiElementId.ANDROID_HOME_PNC_ICON}),
            ),
        )
        self._probe_selector_ids = tuple(
            sorted(
                {
                    UiElementId.PNC_POPUP_CLOSE_BUTTON,
                    *(selector_id for rule in self._rules for selector_id in rule.required_all),
                    *(selector_id for rule in self._rules for selector_id in rule.required_any),
                },
                key=lambda selector_id: selector_id.value,
            )
        )

    def probe_selector_ids(self) -> tuple[UiElementId, ...]:
        """Returns the small selector set needed for the initial classification pass."""

        return self._probe_selector_ids

    def classify(
        self,
        visible_elements: dict[UiElementId, VisibleElement],
        evidence: Sequence[ScreenEvidence] = (),
    ) -> ScreenType:
        """Returns the effective screen from the immutable decision."""

        return self.decide(visible_elements, evidence=evidence).effective_screen

    def decide(
        self,
        visible_elements: dict[UiElementId, VisibleElement],
        evidence: Sequence[ScreenEvidence] = (),
        *,
        guard: GuardVerdict = GuardVerdict.NOT_EVALUATED,
        coordinate_only: bool = False,
        viewport_reviewed: bool | None = None,
        background_evidence: Sequence[ScreenEvidence] = (),
    ) -> ScreenDecision:
        """Resolves all independent evidence into one conservative decision."""

        selector_ids = frozenset(
            selector_id
            for selector_id, element in visible_elements.items()
            if element.source_kind != VisibleElementSourceKind.GEOMETRY and element.identity_evidence
        )
        evidence_screen_types = {item.screen_type for item in evidence}
        selector_matches = self._classify_from_selectors(selector_ids)
        selector_blocker_types = {
            screen_type
            for screen_type in selector_matches
            if screen_type in BLOCKING_SCREEN_TYPES | {ScreenType.PNC_LOADING}
        }
        blocker_screen_types = {
            screen_type
            for screen_type in evidence_screen_types
            if screen_type in BLOCKING_SCREEN_TYPES | {ScreenType.PNC_LOADING}
        }
        blocker_screen_types.update(selector_blocker_types)
        # Independently observed background anchors may survive a foreground
        # interruption (including a dialog over another dialog). They inform
        # base identity, never compete as foreground guard evidence.
        base_evidence = tuple(background_evidence) + tuple(
            item for item in evidence if item.screen_type not in blocker_screen_types
        )
        base_evidence_screen_types = {item.screen_type for item in base_evidence}
        base_selector_matches = tuple(
            screen_type for screen_type in selector_matches if screen_type not in blocker_screen_types
        )
        collapsed_evidence = _collapse_evidence(base_evidence)
        selector_match = _collapse_screen_types(base_selector_matches)
        layout_ids_by_family: dict[frozenset[ScreenType], set[str]] = {}
        for item in base_evidence:
            if item.layout_id is None:
                continue
            layout_ids_by_family.setdefault(_screen_type_family(item.screen_type), set()).add(item.layout_id)
        base_layout_conflict = any(len(layout_ids) > 1 for layout_ids in layout_ids_by_family.values())
        blocker_layout_ids_by_family: dict[frozenset[ScreenType], set[str]] = {}
        for item in evidence:
            if item.screen_type not in blocker_screen_types or item.layout_id is None:
                continue
            blocker_layout_ids_by_family.setdefault(_screen_type_family(item.screen_type), set()).add(item.layout_id)
        blocker_layout_conflict = any(len(layout_ids) > 1 for layout_ids in blocker_layout_ids_by_family.values())
        if base_layout_conflict:
            base_screen = ScreenType.UNKNOWN
        elif base_selector_matches and selector_match is None:
            base_screen = ScreenType.UNKNOWN
        elif selector_match is not None:
            base_screen = selector_match
            if base_evidence and not _evidence_supports_selector_match(
                selector_match=selector_match,
                evidence_screen_types=base_evidence_screen_types,
            ):
                base_screen = ScreenType.UNKNOWN
        elif base_evidence and collapsed_evidence is None:
            base_screen = ScreenType.UNKNOWN
        elif collapsed_evidence is not None:
            base_screen = collapsed_evidence
        else:
            base_screen = ScreenType.UNKNOWN
        effective_screen = base_screen
        final_guard = guard
        if guard == GuardVerdict.UNRESOLVED:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        elif base_layout_conflict or blocker_layout_conflict:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        elif len(blocker_screen_types) > 1:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        elif blocker_screen_types:
            effective_screen = next(iter(blocker_screen_types))
            if guard in {GuardVerdict.CLEAR, GuardVerdict.BLOCKED}:
                final_guard = GuardVerdict.BLOCKED
            else:
                final_guard = GuardVerdict.NOT_EVALUATED
        elif guard == GuardVerdict.BLOCKED and base_screen == ScreenType.UNKNOWN:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        elif guard == GuardVerdict.BLOCKED:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        if viewport_reviewed is False and not coordinate_only:
            effective_screen = ScreenType.UNKNOWN
            final_guard = GuardVerdict.UNRESOLVED
        effective_family = _screen_type_family(effective_screen)
        effective_evidence = tuple(
            item for item in evidence if _screen_type_family(item.screen_type) == effective_family
        )
        return ScreenDecision(
            base_screen=base_screen,
            effective_screen=effective_screen,
            layout_id=_resolved_layout_id(effective_evidence),
            guard=final_guard,
            evidence=tuple(background_evidence) + tuple(evidence),
            coordinate_only=coordinate_only,
        )

    def _classify_from_selectors(self, selector_ids: frozenset[UiElementId]) -> tuple[ScreenType, ...]:
        """Returns every screen implied purely by non-geometry selector anchors."""

        matches: list[ScreenType] = []
        if UiElementId.PNC_POPUP_CLOSE_BUTTON in selector_ids:
            matches.append(ScreenType.PNC_POPUP)
        for rule in self._rules:
            if not rule.required_all.issubset(selector_ids):
                continue
            if rule.required_any and rule.required_any.isdisjoint(selector_ids):
                continue
            matches.append(rule.screen_type)
        return tuple(matches)


_COMPATIBLE_SCREEN_TYPE_FAMILIES = (
    frozenset({ScreenType.PNC_HOME_CITY_ROOT, ScreenType.PNC_HOME_CITY}),
    frozenset({ScreenType.PNC_WORLD_MAP_ROOT, ScreenType.PNC_WORLD_MAP}),
)


def _evidence_supports_selector_match(
    *,
    selector_match: ScreenType,
    evidence_screen_types: set[ScreenType],
) -> bool:
    """Returns whether parser evidence agrees with one selector-owned exact screen family."""

    selector_family = _screen_type_family(selector_match)
    return all(
        evidence_screen_type == selector_match
        or _screen_type_family(evidence_screen_type) == selector_family
        for evidence_screen_type in evidence_screen_types
    )


def _collapse_evidence_screen_types(evidence_screen_types: set[ScreenType]) -> ScreenType | None:
    """Returns one canonical screen type when all parser evidence belongs to the same compatible family."""

    if not evidence_screen_types:
        return None
    families = {_screen_type_family(screen_type) for screen_type in evidence_screen_types}
    if len(families) != 1:
        return None
    family = next(iter(families))
    for candidate in family:
        if candidate in evidence_screen_types and candidate not in {
            ScreenType.PNC_HOME_CITY_ROOT,
            ScreenType.PNC_WORLD_MAP_ROOT,
        }:
            return candidate
    return next(iter(sorted(evidence_screen_types, key=lambda item: item.value)))


def _collapse_evidence(evidence: Sequence[ScreenEvidence]) -> ScreenType | None:
    """Collapses evidence while rejecting incompatible screen and layout conclusions."""

    evidence_screen_types = {item.screen_type for item in evidence}
    return _collapse_evidence_screen_types(evidence_screen_types)


def _collapse_screen_types(screen_types: Sequence[ScreenType]) -> ScreenType | None:
    """Collapses selector matches using the same compatible root-family rule."""

    return _collapse_evidence_screen_types(set(screen_types))


def _resolved_layout_id(evidence: Sequence[ScreenEvidence]) -> str | None:
    """Returns one layout identity only when all supplied identities agree."""

    layout_ids = {item.layout_id for item in evidence if item.layout_id is not None}
    return next(iter(layout_ids)) if len(layout_ids) == 1 else None


def _screen_type_family(screen_type: ScreenType) -> frozenset[ScreenType]:
    """Returns the compatibility family used to reconcile coarse and exact root evidence."""

    for family in _COMPATIBLE_SCREEN_TYPE_FAMILIES:
        if screen_type in family:
            return family
    return frozenset({screen_type})
