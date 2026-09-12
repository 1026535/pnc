"""Strict authored configuration for daily castle maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.models import AppConfig
from pnc_automation.app.pnc.domain.castles import CastleIdentity, castle_identity_key
from pnc_automation.app.authoring.config.yaml_helpers import require_int, require_list, require_mapping, require_string
from pnc_automation.app.pnc.domain.daily_maintenance import (
    CampaignExecutionMode,
    CampaignTarget,
    DailyQuestDisposition,
    DailyQuestId,
    ResourceBoostPolicy,
    TrialShopPolicy,
    TrialShopPolicyKind,
    WishesPolicy,
    validate_daily_diamond_limit,
)
from pnc_automation.app.pnc.domain.daily_quest_catalog import DailyQuestCatalog
from pnc_automation.core.errors import ConfigurationError


_TASK_ID_BY_QUEST_ID = {
    DailyQuestId.HERO_ARENA: TaskId.HERO_ARENA,
    DailyQuestId.USE_RESOURCE_ITEM: TaskId.USE_RESOURCE_ITEM,
    DailyQuestId.HERO_HALL: TaskId.HERO_HALL,
    DailyQuestId.UPGRADE_HERO: TaskId.UPGRADE_HERO,
    DailyQuestId.CAMPAIGN: TaskId.CAMPAIGN,
    DailyQuestId.GATHER_FOOD: TaskId.GATHERING,
    DailyQuestId.GATHER_WOOD: TaskId.GATHERING,
    DailyQuestId.GATHER_IRON: TaskId.GATHERING,
    DailyQuestId.GATHER_GOLD: TaskId.GATHERING,
    DailyQuestId.GATHER_ALLIANCE_MINE: TaskId.GATHER_ALLIANCE_MINE,
    DailyQuestId.RESOURCE_BUILDING_BOOST: TaskId.RESOURCE_BUILDING_BOOST,
    DailyQuestId.TRIAL_SHOP: TaskId.TRIAL_SHOP,
    DailyQuestId.RARE_EARTH_SHOP: TaskId.RARE_EARTH_SHOP,
    DailyQuestId.ALLIANCE_SHOP: TaskId.ALLIANCE_SHOP,
    DailyQuestId.PRAISE: TaskId.PRAISE,
    DailyQuestId.SUMMON_SAURGIL: TaskId.SUMMON_SAURGIL,
    DailyQuestId.ENHANCE_GEM: TaskId.ENHANCE_GEM,
    DailyQuestId.ENHANCE_SAURGEM: TaskId.ENHANCE_SAURGEM,
    DailyQuestId.ENHANCE_GEAR: TaskId.ENHANCE_GEAR,
    DailyQuestId.WISHES: TaskId.WISHES,
    DailyQuestId.LAND_OF_TRIAL: TaskId.LAND_OF_TRIAL,
    DailyQuestId.LOST_LAND: TaskId.LOST_LAND,
    DailyQuestId.ALLIANCE_DONATIONS: TaskId.ALLIANCE_DONATIONS,
    DailyQuestId.ALLIANCE_GIFT: TaskId.ALLIANCE_GIFT,
}


@dataclass(frozen=True, slots=True)
class DailyCapabilityPolicy:
    """Binds one enabled Daily capability to its canonical task and mutation limits."""

    quest_id: DailyQuestId
    task_id: TaskId
    max_mutations: int
    max_diamond_spend: int | None = 0

    def __post_init__(self) -> None:
        """Rejects unbounded mutation or premium limits."""

        if isinstance(self.max_mutations, bool) or self.max_mutations <= 0:
            raise ValueError("DailyCapabilityPolicy.max_mutations must be a positive integer.")
        validate_daily_diamond_limit(self.max_diamond_spend, quest_id=self.quest_id)


@dataclass(frozen=True, slots=True)
class DailyCampaignPolicy:
    """Configures one castle's Campaign behavior variant and required target."""

    mode: CampaignExecutionMode
    target: CampaignTarget


@dataclass(frozen=True, slots=True)
class DailyMaintenanceTargetConfig:
    """Binds one account/castle alias to its enabled Daily policies."""

    account_id: str
    castle_ref: str
    castle: CastleIdentity
    capabilities: tuple[DailyCapabilityPolicy, ...]
    max_claims: int = 100
    campaign: DailyCampaignPolicy | None = None
    trial_shop: TrialShopPolicy | None = None
    wishes: WishesPolicy = WishesPolicy()
    resource_boost: ResourceBoostPolicy = ResourceBoostPolicy()

    def capability(self, quest_id: DailyQuestId) -> DailyCapabilityPolicy | None:
        """Returns one enabled capability policy when configured."""

        return next((item for item in self.capabilities if item.quest_id == quest_id), None)


@dataclass(frozen=True, slots=True)
class DailyMaintenanceConfig:
    """Owns the complete validated daily-maintenance target set."""

    maintenance_timezone: str
    maintenance_hour_local: int
    game_reset_hour_utc: int
    targets: tuple[DailyMaintenanceTargetConfig, ...]
    automatic_runs_enabled: bool = False
    canary_targets: tuple[DailyMaintenanceTargetConfig, ...] = ()

    def __post_init__(self) -> None:
        """Rejects unsupported scheduling semantics before runtime starts."""

        if self.maintenance_timezone != "America/Toronto":
            raise ValueError("Daily maintenance timezone must be 'America/Toronto'.")
        if not 0 <= self.maintenance_hour_local <= 23:
            raise ValueError("Daily maintenance hour must be between 0 and 23.")
        if self.game_reset_hour_utc != 0:
            raise ValueError("Game reset must be midnight UTC.")
        if not isinstance(self.automatic_runs_enabled, bool):
            raise ValueError("automatic_runs_enabled must be a boolean.")
        if not self.targets:
            raise ValueError("Daily maintenance requires at least one target.")


class DailyMaintenanceConfigLoader:
    """Loads and cross-validates the one canonical daily-maintenance schema."""

    _ROOT_FIELDS = {
        "automatic_runs_enabled",
        "canary_targets",
        "maintenance_timezone",
        "maintenance_hour_local",
        "game_reset_hour_utc",
        "targets",
    }
    _TARGET_FIELDS = {
        "account_id",
        "castle_ref",
        "enabled_capabilities",
        "campaign",
        "trial_shop",
        "wishes",
        "resource_boost",
        "max_claims",
    }

    def __init__(self, app_config: AppConfig, catalog: DailyQuestCatalog | None = None) -> None:
        """Stores canonical app configuration and semantic catalog dependencies."""

        self._app_config = app_config
        self._catalog = catalog or DailyQuestCatalog()

    def load(self, path: str | Path) -> DailyMaintenanceConfig:
        """Loads a YAML file and rejects invalid references or policy combinations."""

        config_path = Path(path).resolve()
        if not config_path.is_file():
            raise ConfigurationError(
                f"Daily-maintenance configuration '{config_path}' does not exist.",
                path=str(config_path),
            )
        with config_path.open("r", encoding="utf-8") as handle:
            raw_data = yaml.safe_load(handle) or {}
        raw = require_mapping(raw_data, context="daily maintenance root")
        self._reject_unexpected(raw, allowed=self._ROOT_FIELDS, context="daily maintenance root")
        targets_raw = require_list(raw.get("targets"), context="daily maintenance targets")
        targets = tuple(self._load_target(item, index=index) for index, item in enumerate(targets_raw))
        canaries_raw = require_list(raw.get("canary_targets", []), context="canary_targets")
        canaries = tuple(self._load_target(item, index=index) for index, item in enumerate(canaries_raw))
        self._validate_unique_targets(targets + canaries)
        try:
            return DailyMaintenanceConfig(
                automatic_runs_enabled=raw.get("automatic_runs_enabled", False),
                canary_targets=canaries,
                maintenance_timezone=require_string(
                    raw.get("maintenance_timezone"),
                    context="maintenance_timezone",
                ),
                maintenance_hour_local=require_int(
                    raw.get("maintenance_hour_local"),
                    context="maintenance_hour_local",
                ),
                game_reset_hour_utc=require_int(
                    raw.get("game_reset_hour_utc"),
                    context="game_reset_hour_utc",
                ),
                targets=targets,
            )
        except ValueError as error:
            raise ConfigurationError(str(error), path=str(config_path)) from error

    def _load_target(self, value: Any, *, index: int) -> DailyMaintenanceTargetConfig:
        """Loads and cross-validates one account/castle policy target."""

        context = f"targets[{index}]"
        raw = require_mapping(value, context=context)
        self._reject_unexpected(raw, allowed=self._TARGET_FIELDS, context=context)
        account_id = require_string(raw.get("account_id"), context=f"{context}.account_id")
        castle_ref = require_string(raw.get("castle_ref"), context=f"{context}.castle_ref")
        self._app_config.require_account(account_id)
        target_catalog = self._app_config.find_castle_targets(account_id)
        if target_catalog is None:
            raise ConfigurationError(
                f"Account '{account_id}' has no authored castle targets.",
                account_id=account_id,
                castle_ref=castle_ref,
            )
        castle = target_catalog.require(castle_ref)
        capability_ids = self._load_capability_ids(raw.get("enabled_capabilities"), context=context)
        campaign = self._load_campaign(raw.get("campaign"), enabled=DailyQuestId.CAMPAIGN in capability_ids, context=context)
        trial_shop = self._load_trial_shop(
            raw.get("trial_shop"),
            enabled=DailyQuestId.TRIAL_SHOP in capability_ids,
            context=context,
        )
        wishes = self._load_wishes(raw.get("wishes"), context=context)
        resource_boost = self._load_resource_boost(raw.get("resource_boost"), context=context)
        capabilities = tuple(
            self._build_capability_policy(
                quest_id,
                wishes=wishes,
                resource_boost=resource_boost,
            )
            for quest_id in capability_ids
        )
        return DailyMaintenanceTargetConfig(
            account_id=account_id,
            castle_ref=castle_ref,
            castle=castle,
            capabilities=capabilities,
            max_claims=self._load_positive_int(raw.get("max_claims", 100), context=f"{context}.max_claims"),
            campaign=campaign,
            trial_shop=trial_shop,
            wishes=wishes,
            resource_boost=resource_boost,
        )

    def _load_capability_ids(self, value: Any, *, context: str) -> tuple[DailyQuestId, ...]:
        """Loads enabled capabilities and rejects excluded, deferred, or duplicate ids."""

        items = require_list(value, context=f"{context}.enabled_capabilities")
        parsed: list[DailyQuestId] = []
        for item_index, item in enumerate(items):
            raw_id = require_string(item, context=f"{context}.enabled_capabilities[{item_index}]")
            try:
                quest_id = DailyQuestId(raw_id)
            except ValueError as error:
                raise ConfigurationError(
                    f"Unknown Daily capability '{raw_id}'.",
                    context=f"{context}.enabled_capabilities[{item_index}]",
                ) from error
            definition = self._catalog.require(quest_id)
            if definition.disposition != DailyQuestDisposition.ENABLED or quest_id not in _TASK_ID_BY_QUEST_ID:
                raise ConfigurationError(
                    f"Daily capability '{raw_id}' is claim-only and cannot be enabled.",
                    capability=raw_id,
                )
            if quest_id in parsed:
                raise ConfigurationError(
                    f"Daily capability '{raw_id}' is enabled more than once.",
                    capability=raw_id,
                )
            parsed.append(quest_id)
        return tuple(parsed)

    def _load_campaign(self, value: Any, *, enabled: bool, context: str) -> DailyCampaignPolicy | None:
        """Loads the required Campaign mode and exact target when Campaign is enabled."""

        if value is None:
            if enabled:
                raise ConfigurationError("Campaign capability requires a campaign policy.", context=context)
            return None
        if not enabled:
            raise ConfigurationError("Campaign policy is present but campaign is not enabled.", context=context)
        raw = require_mapping(value, context=f"{context}.campaign")
        self._reject_unexpected(raw, allowed={"mode", "target"}, context=f"{context}.campaign")
        mode = self._parse_enum(
            CampaignExecutionMode,
            raw.get("mode"),
            context=f"{context}.campaign.mode",
        )
        target_raw = require_mapping(raw.get("target"), context=f"{context}.campaign.target")
        self._reject_unexpected(target_raw, allowed={"chapter", "node"}, context=f"{context}.campaign.target")
        try:
            target = CampaignTarget(
                chapter=require_int(target_raw.get("chapter"), context=f"{context}.campaign.target.chapter"),
                node=require_int(target_raw.get("node"), context=f"{context}.campaign.target.node"),
            )
        except ValueError as error:
            raise ConfigurationError(str(error), context=f"{context}.campaign.target") from error
        return DailyCampaignPolicy(mode=mode, target=target)

    def _load_trial_shop(self, value: Any, *, enabled: bool, context: str) -> TrialShopPolicy | None:
        """Loads one of the two exact Trial Shop behavior variants."""

        if value is None:
            if enabled:
                raise ConfigurationError("Trial Shop capability requires a trial_shop policy.", context=context)
            return None
        if not enabled:
            raise ConfigurationError("Trial Shop policy is present but trial_shop is not enabled.", context=context)
        raw = require_mapping(value, context=f"{context}.trial_shop")
        self._reject_unexpected(raw, allowed={"kind", "maximum_quantity"}, context=f"{context}.trial_shop")
        try:
            return TrialShopPolicy(
                kind=self._parse_enum(
                    TrialShopPolicyKind,
                    raw.get("kind"),
                    context=f"{context}.trial_shop.kind",
                ),
                maximum_quantity=require_int(
                    raw.get("maximum_quantity"),
                    context=f"{context}.trial_shop.maximum_quantity",
                ),
            )
        except ValueError as error:
            raise ConfigurationError(str(error), context=f"{context}.trial_shop") from error

    def _load_wishes(self, value: Any, *, context: str) -> WishesPolicy:
        """Loads optional wishes limits using no-premium defaults."""

        raw = require_mapping(value or {}, context=f"{context}.wishes")
        self._reject_unexpected(raw, allowed={"target_total", "game_day_limit", "max_diamond_spend"}, context=f"{context}.wishes")
        try:
            return WishesPolicy(
                target_total=require_int(raw.get("target_total", 5), context=f"{context}.wishes.target_total"),
                game_day_limit=require_int(raw.get("game_day_limit", 50), context=f"{context}.wishes.game_day_limit"),
                max_diamond_spend=None if raw.get("max_diamond_spend", 0) is None else require_int(
                    raw.get("max_diamond_spend", 0),
                    context=f"{context}.wishes.max_diamond_spend",
                ),
            )
        except ValueError as error:
            raise ConfigurationError(str(error), context=f"{context}.wishes") from error

    def _load_resource_boost(self, value: Any, *, context: str) -> ResourceBoostPolicy:
        """Loads optional boost limits and enforces the 200-diamond hard cap."""

        raw = require_mapping(value or {}, context=f"{context}.resource_boost")
        self._reject_unexpected(raw, allowed={"max_diamond_spend"}, context=f"{context}.resource_boost")
        try:
            return ResourceBoostPolicy(
                max_diamond_spend=require_int(
                    raw.get("max_diamond_spend", 0),
                    context=f"{context}.resource_boost.max_diamond_spend",
                )
            )
        except ValueError as error:
            raise ConfigurationError(str(error), context=f"{context}.resource_boost") from error

    def _build_capability_policy(
        self,
        quest_id: DailyQuestId,
        *,
        wishes: WishesPolicy,
        resource_boost: ResourceBoostPolicy,
    ) -> DailyCapabilityPolicy:
        """Builds fixed mutation limits from the locked plan policy."""

        max_mutations = {
            DailyQuestId.HERO_ARENA: 3,
            DailyQuestId.USE_RESOURCE_ITEM: 1,
            DailyQuestId.HERO_HALL: 5,
            DailyQuestId.UPGRADE_HERO: 6,
            DailyQuestId.CAMPAIGN: 1,
            DailyQuestId.GATHER_FOOD: 1,
            DailyQuestId.GATHER_WOOD: 1,
            DailyQuestId.GATHER_IRON: 1,
            DailyQuestId.GATHER_GOLD: 1,
            DailyQuestId.GATHER_ALLIANCE_MINE: 1,
            DailyQuestId.RESOURCE_BUILDING_BOOST: 1,
            DailyQuestId.TRIAL_SHOP: 1,
            DailyQuestId.RARE_EARTH_SHOP: 1,
            DailyQuestId.ALLIANCE_SHOP: 1,
            DailyQuestId.PRAISE: 1,
            DailyQuestId.SUMMON_SAURGIL: 1,
            DailyQuestId.ENHANCE_GEM: 1,
            DailyQuestId.ENHANCE_SAURGEM: 1,
            DailyQuestId.ENHANCE_GEAR: 1,
            DailyQuestId.WISHES: wishes.target_total,
            DailyQuestId.LAND_OF_TRIAL: 1,
            DailyQuestId.LOST_LAND: 1,
            DailyQuestId.ALLIANCE_DONATIONS: 1,
            DailyQuestId.ALLIANCE_GIFT: 100,
        }[quest_id]
        diamond_budget = 0
        if quest_id == DailyQuestId.WISHES:
            diamond_budget = wishes.max_diamond_spend
        elif quest_id == DailyQuestId.RESOURCE_BUILDING_BOOST:
            diamond_budget = resource_boost.max_diamond_spend
        return DailyCapabilityPolicy(
            quest_id=quest_id,
            task_id=_TASK_ID_BY_QUEST_ID[quest_id],
            max_mutations=max_mutations,
            max_diamond_spend=diamond_budget,
        )

    def _validate_unique_targets(self, targets: tuple[DailyMaintenanceTargetConfig, ...]) -> None:
        """Rejects duplicate aliases and duplicate physical castles across the schedule."""

        aliases: set[tuple[str, str]] = set()
        castles: set[tuple[str, str]] = set()
        for target in targets:
            alias_key = (target.account_id, target.castle_ref)
            if alias_key in aliases:
                raise ConfigurationError(
                    "Daily maintenance selects the same account/castle alias more than once.",
                    account_id=target.account_id,
                    castle_ref=target.castle_ref,
                )
            aliases.add(alias_key)
            castle_key = castle_identity_key(target.castle)
            if castle_key in castles:
                raise ConfigurationError(
                    "Daily maintenance selects the same physical castle more than once.",
                    kingdom=target.castle.kingdom,
                    castle_name=target.castle.castle_name,
                )
            castles.add(castle_key)

    @staticmethod
    def _reject_unexpected(raw: Any, *, allowed: set[str], context: str) -> None:
        """Rejects misspelled or obsolete schema fields instead of ignoring them."""

        unexpected = set(raw) - allowed
        if unexpected:
            field = sorted(unexpected)[0]
            raise ConfigurationError(f"Unexpected field '{field}' in {context}.", context=context, field=field)

    @staticmethod
    def _parse_enum(enum_type: type[Any], value: Any, *, context: str) -> Any:
        """Parses one strict string enum with a configuration-shaped error."""

        raw_value = require_string(value, context=context)
        try:
            return enum_type(raw_value)
        except ValueError as error:
            raise ConfigurationError(
                f"Unsupported value '{raw_value}' for {context}.",
                context=context,
                value=raw_value,
            ) from error

    @staticmethod
    def _load_positive_int(value: Any, *, context: str) -> int:
        """Loads one strictly positive integer configuration limit."""

        parsed = require_int(value, context=context)
        if parsed <= 0:
            raise ConfigurationError(f"Expected {context} to be positive.", context=context)
        return parsed


def load_daily_maintenance_config(path: str | Path, *, app_config: AppConfig) -> DailyMaintenanceConfig:
    """Loads one daily-maintenance file through the canonical typed loader."""

    return DailyMaintenanceConfigLoader(app_config).load(path)
