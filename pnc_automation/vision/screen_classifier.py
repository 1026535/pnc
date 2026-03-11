"""Conservative screen classification built from detected selector anchors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pnc_automation.pnc.observation import VisibleElement
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId


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
                screen_type=ScreenType.PNC_VIP,
                required_all=frozenset({UiElementId.PNC_VIP_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_IMPROVE_MIGHT,
                required_all=frozenset({UiElementId.PNC_IMPROVE_MIGHT_HEADER}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_WORLD_MAP,
                required_all=frozenset(
                    {
                        UiElementId.PNC_WORLD_HOME_NAV,
                        UiElementId.PNC_WORLD_SEARCH_BUTTON,
                    }
                ),
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
                screen_type=ScreenType.PNC_MAIL_LIST,
                required_all=frozenset({UiElementId.PNC_MAIL_ROW_SYSTEM_MESSAGE}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_SYSTEM_MESSAGE,
                required_all=frozenset({UiElementId.PNC_SYSTEM_MESSAGE_MARK_AS_READ_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ALLIANCE_HOME,
                required_all=frozenset({UiElementId.PNC_ALLIANCE_TILE_TERRITORY}),
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
                screen_type=ScreenType.PNC_BUILDING_DETAILS,
                required_all=frozenset({UiElementId.PNC_BUILDING_UPGRADE_BUTTON}),
            ),
            ClassificationRule(
                screen_type=ScreenType.PNC_ACADEMY,
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
                screen_type=ScreenType.PNC_CAMPAIGN,
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
            if evidence_screen_types and selector_match not in evidence_screen_types:
                return ScreenType.UNKNOWN
            return selector_match
        if len(evidence_screen_types) == 1:
            return next(iter(evidence_screen_types))
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
