"""Conservative screen classification built from detected selector anchors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pnc_automation.app.pnc.domain.observation import VisibleElement
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId


@dataclass(frozen=True, slots=True)
class ClassificationRule:
    """Defines anchor selectors that imply one screen type."""

    screen_type: ScreenType
    required_all: frozenset[UiElementId]
    required_any: frozenset[UiElementId] = frozenset()


@dataclass(frozen=True, slots=True)
class ScreenEvidence:
    """Represents one strong parser conclusion about the current screen."""

    screen_type: ScreenType
    reason: str


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
                        UiElementId.PNC_BAG_USE_BUTTON,
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
                screen_type=ScreenType.PNC_OTHER_LORD_SACRED_TREE,
                required_all=frozenset({UiElementId.PNC_OTHER_LORD_SACRED_TREE_OWNER_NAME_LABEL}),
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
        """Returns the first matching screen classification or UNKNOWN."""

        selector_ids = frozenset(visible_elements.keys())
        evidence_screen_types = {item.screen_type for item in evidence}
        selector_match = self._classify_from_selectors(selector_ids)
        if selector_match is not None:
            if evidence_screen_types and not _evidence_supports_selector_match(
                selector_match=selector_match,
                evidence_screen_types=evidence_screen_types,
            ):
                return ScreenType.UNKNOWN
            return selector_match
        collapsed_evidence = _collapse_evidence_screen_types(evidence_screen_types)
        if collapsed_evidence is not None:
            return collapsed_evidence
        return ScreenType.UNKNOWN

    def _classify_from_selectors(self, selector_ids: frozenset[UiElementId]) -> ScreenType | None:
        """Returns the first screen implied purely by selector anchors."""

        if UiElementId.PNC_POPUP_CLOSE_BUTTON in selector_ids:
            return ScreenType.PNC_POPUP

        for rule in self._rules:
            if not rule.required_all.issubset(selector_ids):
                continue
            if rule.required_any and rule.required_any.isdisjoint(selector_ids):
                continue
            return rule.screen_type
        return None


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

    if selector_match in evidence_screen_types:
        return True
    selector_family = _screen_type_family(selector_match)
    return any(_screen_type_family(evidence_screen_type) == selector_family for evidence_screen_type in evidence_screen_types)


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


def _screen_type_family(screen_type: ScreenType) -> frozenset[ScreenType]:
    """Returns the compatibility family used to reconcile coarse and exact root evidence."""

    for family in _COMPATIBLE_SCREEN_TYPE_FAMILIES:
        if screen_type in family:
            return family
    return frozenset({screen_type})
