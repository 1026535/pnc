"""Canonical semantic catalog for PNC Daily Quest row titles."""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestDisposition, DailyQuestId
from pnc_automation.core.text.normalization import normalize_ocr_text


@dataclass(frozen=True, slots=True)
class DailyQuestDefinition:
    """Defines one Daily row identity, disposition, task owner, and exact aliases."""

    quest_id: DailyQuestId
    disposition: DailyQuestDisposition
    title_aliases: frozenset[str]


class DailyQuestCatalog:
    """Resolves normalized row titles through one exact, ambiguity-free catalog."""

    def __init__(self, definitions: tuple[DailyQuestDefinition, ...] | None = None) -> None:
        """Builds an exact alias index and rejects duplicate semantic ownership."""

        self._definitions = definitions or default_daily_quest_definitions()
        by_id: dict[DailyQuestId, DailyQuestDefinition] = {}
        by_alias: dict[str, DailyQuestDefinition] = {}
        for definition in self._definitions:
            if definition.quest_id in by_id:
                raise ValueError(f"Duplicate Daily quest definition '{definition.quest_id.value}'.")
            by_id[definition.quest_id] = definition
            for alias in definition.title_aliases:
                normalized = normalize_ocr_text(alias)
                if not normalized:
                    raise ValueError(f"Daily quest '{definition.quest_id.value}' has an empty alias.")
                previous = by_alias.get(normalized)
                if previous is not None:
                    raise ValueError(
                        f"Daily quest alias '{alias}' belongs to both "
                        f"'{previous.quest_id.value}' and '{definition.quest_id.value}'."
                    )
                by_alias[normalized] = definition
        self._by_id = by_id
        self._by_alias = by_alias

    @property
    def definitions(self) -> tuple[DailyQuestDefinition, ...]:
        """Returns all catalog definitions in canonical execution-independent order."""

        return self._definitions

    def require(self, quest_id: DailyQuestId) -> DailyQuestDefinition:
        """Returns one canonical definition or fails for a non-catalog identity."""

        try:
            return self._by_id[quest_id]
        except KeyError as error:
            raise KeyError(f"Daily quest '{quest_id.value}' is not defined.") from error

    def resolve_title(self, title: str) -> DailyQuestDefinition | None:
        """Returns the exact normalized title match, preserving unknown rows as unknown."""

        return self._by_alias.get(normalize_ocr_text(title))


def default_daily_quest_definitions() -> tuple[DailyQuestDefinition, ...]:
    """Returns the locked Daily Quest catalog and execution dispositions."""

    enabled = DailyQuestDisposition.ENABLED
    excluded = DailyQuestDisposition.EXCLUDED_CLAIM_ONLY
    deferred = DailyQuestDisposition.DEFERRED_CLAIM_ONLY
    return (
        DailyQuestDefinition(DailyQuestId.HERO_ARENA, enabled, frozenset({"Challenge in Hero Arena 3 times", "Hero Arena 3 times", "Challenge 3x in Hero Arena"})),
        DailyQuestDefinition(
            DailyQuestId.USE_RESOURCE_ITEM,
            enabled,
            frozenset({"Use resource items", "Use a resource item", "Use resource item x1", "Use resource item xL"}),
        ),
        DailyQuestDefinition(DailyQuestId.HERO_HALL, enabled, frozenset({"Recruit heroes 5 times", "Recruit in Hero Hall 5 times", "Recruit 5x in Hero Hall"})),
        DailyQuestDefinition(DailyQuestId.UPGRADE_HERO, enabled, frozenset({"Upgrade a hero 3 times", "Upgrade hero 3 times", "Upgrade hero 3x"})),
        DailyQuestDefinition(DailyQuestId.CAMPAIGN, enabled, frozenset({"Challenge Campaign", "Campaign challenge", "Consume 20 AP", "Clear Campaign Ch.6"})),
        DailyQuestDefinition(DailyQuestId.GATHER_FOOD, enabled, frozenset({"Gather Food", "Gather Food x30000"})),
        DailyQuestDefinition(DailyQuestId.GATHER_WOOD, enabled, frozenset({"Gather Wood", "Gather Wood x30000"})),
        DailyQuestDefinition(DailyQuestId.GATHER_IRON, enabled, frozenset({"Gather Iron", "Gather Iron x6000"})),
        DailyQuestDefinition(DailyQuestId.GATHER_GOLD, enabled, frozenset({"Gather Gold", "Gather Gold x1500"})),
        DailyQuestDefinition(DailyQuestId.GATHER_ALLIANCE_MINE, enabled, frozenset({"Gather in Alliance Mine", "Gather Alliance Mine"})),
        DailyQuestDefinition(DailyQuestId.RESOURCE_BUILDING_BOOST, enabled, frozenset({"Use resource output boost", "Boost resource output", "Boost any resource building's output 1x"})),
        DailyQuestDefinition(DailyQuestId.TRIAL_SHOP, enabled, frozenset({"Purchase in Trial Shop", "Buy an item in Trial Shop", "Make purchase 1x in Tower Shop"})),
        DailyQuestDefinition(DailyQuestId.RARE_EARTH_SHOP, enabled, frozenset({"Purchase in Rare Earth Shop", "Buy an item in Rare Earth Shop", "Make 1 purchase(s) in Rare Earth Shop"})),
        DailyQuestDefinition(DailyQuestId.ALLIANCE_SHOP, enabled, frozenset({"Purchase in Alliance Shop", "Buy an item in Alliance Shop", "Make 1 purchase(s) in Alliance Shop"})),
        DailyQuestDefinition(DailyQuestId.PRAISE, enabled, frozenset({"Praise a Lord", "Praise once", "Praise 1x in Personal Might Rank"})),
        DailyQuestDefinition(DailyQuestId.SUMMON_SAURGIL, enabled, frozenset({"Summon Saurgil", "Summon Saurgil once", "Summon Saurgil 1x"})),
        DailyQuestDefinition(DailyQuestId.ENHANCE_GEM, enabled, frozenset({"Enhance Gem", "Enhance a Gem", "Enhance a gem 1x"})),
        DailyQuestDefinition(DailyQuestId.ENHANCE_SAURGEM, enabled, frozenset({"Enhance Saurgem", "Enhance a Saurgem", "Enhance a saurgem 1x"})),
        DailyQuestDefinition(DailyQuestId.ENHANCE_GEAR, enabled, frozenset({"Enhance Gear", "Enhance a piece of Gear", "Enhance gear 1x"})),
        DailyQuestDefinition(DailyQuestId.WISHES, enabled, frozenset({"Make wishes", "Wish 50 times", "Make 5 wish(es)"})),
        DailyQuestDefinition(DailyQuestId.LAND_OF_TRIAL, enabled, frozenset({"Challenge Land of Trial", "Land of Trial", "Challenge Land of Trial 1x"})),
        DailyQuestDefinition(DailyQuestId.LOST_LAND, enabled, frozenset({"Challenge Lost Land", "Lost Land", "Challenge Lost Land 1x"})),
        DailyQuestDefinition(DailyQuestId.ALLIANCE_DONATIONS, enabled, frozenset({"Donate Alliance Tech", "Alliance donations", "Donate for alliance tech 10x"})),
        DailyQuestDefinition(DailyQuestId.ALLIANCE_GIFT, enabled, frozenset({"Open Alliance Gifts", "Alliance Gift"})),
        DailyQuestDefinition(DailyQuestId.UPGRADE_BUILDING, excluded, frozenset({"Upgrade a building", "Upgrade building", "Upgrade building 1x"})),
        DailyQuestDefinition(DailyQuestId.UPGRADE_RESEARCH, excluded, frozenset({"Upgrade technology", "Research technology", "Upgrade tech 1x"})),
        DailyQuestDefinition(DailyQuestId.TRAIN_INFANTRY, excluded, frozenset({"Train Infantry", "Train Infantry x250"})),
        DailyQuestDefinition(DailyQuestId.TRAIN_CAVALRY, excluded, frozenset({"Train Cavalry", "Train Cavalry x250"})),
        DailyQuestDefinition(DailyQuestId.TRAIN_RANGED, excluded, frozenset({"Train Ranged", "Train Ranged units", "Train Ranged x250"})),
        DailyQuestDefinition(DailyQuestId.TRAIN_SIEGE, excluded, frozenset({"Train Siege", "Train Siege units", "Train Siege x250"})),
        DailyQuestDefinition(DailyQuestId.DEFEAT_HELL_FORTRESS, excluded, frozenset({"Defeat Hell Fortress", "Defeat Hell Fortress 1x"})),
        DailyQuestDefinition(DailyQuestId.CONSUME_STAMINA_20, excluded, frozenset({"Consume 20 Stamina"})),
        DailyQuestDefinition(DailyQuestId.CONSUME_STAMINA_80, excluded, frozenset({"Consume 80 Stamina"})),
        DailyQuestDefinition(DailyQuestId.BUY_PACK, excluded, frozenset({"Buy any pack", "Purchase any pack", "Buy any pack 1x"})),
        DailyQuestDefinition(DailyQuestId.CRAFT_HERO_CURIO, excluded, frozenset({"Craft Hero Curio", "Craft a Hero Curio", "Craft Hero Curio 1x"})),
        DailyQuestDefinition(DailyQuestId.ALLIANCE_HELP, deferred, frozenset({"Help allies", "Alliance Help", "Help allies 10x"})),
    )
