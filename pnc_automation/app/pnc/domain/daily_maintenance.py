"""Typed domain contracts for daily castle maintenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.enums.screen_type import ScreenType


class DailyQuestId(StrEnum):
    """Canonical identities for every supported or explicitly excluded Daily row."""

    CLAIM_COMPLETED = "claim_completed"
    HERO_ARENA = "hero_arena"
    USE_RESOURCE_ITEM = "use_resource_item"
    HERO_HALL = "hero_hall"
    UPGRADE_HERO = "upgrade_hero"
    CAMPAIGN = "campaign"
    GATHER_FOOD = "gather_food"
    GATHER_WOOD = "gather_wood"
    GATHER_IRON = "gather_iron"
    GATHER_GOLD = "gather_gold"
    GATHER_ALLIANCE_MINE = "gather_alliance_mine"
    RESOURCE_BUILDING_BOOST = "resource_building_boost"
    TRIAL_SHOP = "trial_shop"
    RARE_EARTH_SHOP = "rare_earth_shop"
    ALLIANCE_SHOP = "alliance_shop"
    PRAISE = "praise"
    SUMMON_SAURGIL = "summon_saurgil"
    ENHANCE_GEM = "enhance_gem"
    ENHANCE_SAURGEM = "enhance_saurgem"
    ENHANCE_GEAR = "enhance_gear"
    WISHES = "wishes"
    LAND_OF_TRIAL = "land_of_trial"
    LOST_LAND = "lost_land"
    ALLIANCE_DONATIONS = "alliance_donations"
    ALLIANCE_GIFT = "alliance_gift"
    UPGRADE_BUILDING = "upgrade_building"
    UPGRADE_RESEARCH = "upgrade_research"
    TRAIN_INFANTRY = "train_infantry"
    TRAIN_CAVALRY = "train_cavalry"
    TRAIN_RANGED = "train_ranged"
    TRAIN_SIEGE = "train_siege"
    DEFEAT_HELL_FORTRESS = "defeat_hell_fortress"
    CONSUME_STAMINA_20 = "consume_stamina_20"
    CONSUME_STAMINA_80 = "consume_stamina_80"
    BUY_PACK = "buy_pack"
    CRAFT_HERO_CURIO = "craft_hero_curio"
    ALLIANCE_HELP = "alliance_help"


class DailyQuestDisposition(StrEnum):
    """Controls whether a recognized Daily row may execute its underlying action."""

    ENABLED = "enabled"
    EXCLUDED_CLAIM_ONLY = "excluded_claim_only"
    DEFERRED_CLAIM_ONLY = "deferred_claim_only"


class DailyQuestRowState(StrEnum):
    """Describes the semantic action currently exposed by one Daily row."""

    GO = "go"
    CLAIM = "claim"
    COMPLETED = "completed"
    REQUIREMENT = "requirement"
    UNKNOWN_ACTION = "unknown_action"


class CoordinateProvenance(StrEnum):
    """Identifies the non-OCR source from which tappable geometry was materialized."""

    NORMALIZED_SELECTOR = "normalized_selector"
    VISUAL_GEOMETRY = "visual_geometry"
    DYNAMIC_ENTRY_GEOMETRY = "dynamic_entry_geometry"


@dataclass(frozen=True, slots=True)
class NormalizedBounds:
    """Stores one rectangle as normalized coordinates in the inclusive 0..1 range."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        """Rejects invalid or off-screen normalized rectangles."""

        values = (self.x, self.y, self.width, self.height)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise TypeError("NormalizedBounds values must be numeric.")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("NormalizedBounds requires non-negative origin and positive size.")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("NormalizedBounds must remain inside the normalized viewport.")


@dataclass(frozen=True, slots=True)
class DailyQuestRow:
    """Represents one stable, semantically classified Daily Quest row."""

    quest_id: DailyQuestId
    normalized_title: str
    state: DailyQuestRowState
    bounds: NormalizedBounds
    observation_fingerprint: str
    progress_current: int | None = None
    progress_required: int | None = None
    coordinate_provenance: CoordinateProvenance = CoordinateProvenance.DYNAMIC_ENTRY_GEOMETRY
    row_status: RowRecognitionStatus = RowRecognitionStatus.NOT_EVALUATED

    def __post_init__(self) -> None:
        """Rejects partial progress and OCR-derived action geometry."""

        if not self.normalized_title:
            raise ValueError("DailyQuestRow.normalized_title cannot be empty.")
        if not self.observation_fingerprint:
            raise ValueError("DailyQuestRow.observation_fingerprint cannot be empty.")
        if (self.progress_current is None) != (self.progress_required is None):
            raise ValueError("DailyQuestRow progress values must be supplied together.")
        if self.progress_current is not None and (
            self.progress_current < 0 or self.progress_required is None or self.progress_required <= 0
        ):
            raise ValueError("DailyQuestRow progress must be non-negative with a positive requirement.")


class CampaignExecutionMode(StrEnum):
    """Controls how a castle selects Campaign stages."""

    FIXED_STAGE = "fixed_stage"
    PROGRESS_THEN_FARM = "progress_then_farm"


@dataclass(frozen=True, slots=True)
class CampaignTarget:
    """Identifies one exact Campaign chapter and node."""

    chapter: int
    node: int

    def __post_init__(self) -> None:
        """Rejects non-positive Campaign coordinates."""

        if isinstance(self.chapter, bool) or self.chapter <= 0:
            raise ValueError("CampaignTarget.chapter must be a positive integer.")
        if isinstance(self.node, bool) or self.node <= 0:
            raise ValueError("CampaignTarget.node must be a positive integer.")


class TrialShopPolicyKind(StrEnum):
    """Names the two locked Trial Shop behavior variants."""

    ONE_SPEEDUP_THEN_GEM = "one_speedup_then_gem"
    ONE_STAR_GEM_ESSENCE = "one_star_gem_essence"


@dataclass(frozen=True, slots=True)
class TrialShopPolicy:
    """Constrains one castle's Trial Shop purchase behavior."""

    kind: TrialShopPolicyKind
    maximum_quantity: int

    def __post_init__(self) -> None:
        """Enforces the locked quantity bounds for each policy variant."""

        if isinstance(self.maximum_quantity, bool) or self.maximum_quantity <= 0:
            raise ValueError("TrialShopPolicy.maximum_quantity must be a positive integer.")
        expected = 1
        if self.maximum_quantity != expected:
            raise ValueError(f"Trial Shop policy '{self.kind.value}' requires maximum_quantity={expected}.")


def validate_daily_diamond_limit(limit: int | None, *, quest_id: DailyQuestId) -> None:
    """Allows an explicitly uncapped price only for the count-bounded Wishes policy."""

    if limit is None:
        if quest_id != DailyQuestId.WISHES:
            raise ValueError("Only wishes may have no diamond-price cap.")
        return
    if type(limit) is not int or limit < 0:
        raise ValueError("Daily diamond limit must be a non-negative integer or the wishes exception.")


@dataclass(frozen=True, slots=True)
class WishesPolicy:
    """Constrains free and premium wishes for one castle."""

    target_total: int = 5
    max_diamond_spend: int | None = 0
    game_day_limit: int = 50

    def __post_init__(self) -> None:
        """Separates five Daily wishes from the shared fifty-wish game-day ceiling."""

        if type(self.target_total) is not int or self.target_total != 5:
            raise ValueError("Daily wishes target must be five.")
        if type(self.game_day_limit) is not int or self.game_day_limit != 50:
            raise ValueError("Shared wishes game-day limit must be fifty.")
        validate_daily_diamond_limit(self.max_diamond_spend, quest_id=DailyQuestId.WISHES)


@dataclass(frozen=True, slots=True)
class ResourceBoostPolicy:
    """Constrains resource-building boost premium fallback."""

    max_diamond_spend: int = 0

    def __post_init__(self) -> None:
        """Enforces the plan's 200-diamond hard cap."""

        if (
            isinstance(self.max_diamond_spend, bool)
            or self.max_diamond_spend < 0
            or self.max_diamond_spend > 200
        ):
            raise ValueError("ResourceBoostPolicy.max_diamond_spend must be between 0 and 200.")


@dataclass(frozen=True, slots=True)
class MutationAcknowledgement:
    """Authorizes one exact live capability budget for one castle and local date."""

    account_id: str
    castle_ref: str
    quest_id: DailyQuestId
    maintenance_date: date
    max_mutations: int
    max_diamond_spend: int | None

    def __post_init__(self) -> None:
        """Rejects broad or unbounded live acknowledgements."""

        if not self.account_id.strip() or not self.castle_ref.strip():
            raise ValueError("Mutation acknowledgement account and castle cannot be empty.")
        if isinstance(self.max_mutations, bool) or self.max_mutations <= 0:
            raise ValueError("Mutation acknowledgement max_mutations must be positive.")
        validate_daily_diamond_limit(self.max_diamond_spend, quest_id=self.quest_id)

    def authorize(
        self,
        *,
        account_id: str,
        castle_ref: str,
        quest_id: DailyQuestId,
        max_mutations: int,
        max_diamond_spend: int | None,
        maintenance_date: date,
    ) -> None:
        """Fails unless this acknowledgement exactly matches the requested live slice."""

        expected = (account_id, castle_ref, quest_id, maintenance_date)
        actual = (self.account_id, self.castle_ref, self.quest_id, self.maintenance_date)
        if actual != expected:
            raise ValueError("Mutation acknowledgement does not match the requested live target and date.")
        if self.max_mutations != max_mutations:
            raise ValueError("Mutation acknowledgement must match the capability mutation limit exactly.")
        if self.max_diamond_spend != max_diamond_spend:
            raise ValueError("Mutation acknowledgement must match the capability diamond limit exactly.")


class DailyApplicabilitySkipReason(StrEnum):
    """Closed reasons for a capability that is genuinely inapplicable on a castle."""

    FEATURE_LOCKED = "feature_locked"
    INSUFFICIENT_INVENTORY = "insufficient_inventory"
    INSUFFICIENT_CURRENCY = "insufficient_currency"
    PROGRESSION_LOCKED = "progression_locked"
    NO_MARCH_SLOT = "no_march_slot"
    NO_CAVALRY = "no_cavalry"
    NO_ELIGIBLE_TARGET = "no_eligible_target"
    POLICY_DISABLED = "policy_disabled"


class DailyTargetOutcomeStatus(StrEnum):
    """Describes the terminal result of one capability on one castle."""

    SUCCESS = "success"
    APPLICABILITY_SKIP = "applicability_skip"
    WAITING_COOLDOWN = "waiting_cooldown"
    RUNTIME_UNKNOWN_SKIP = "runtime_unknown_skip"
    FAILED = "failed"
    PENDING_CLARIFICATION = "pending_clarification"


@dataclass(frozen=True, slots=True)
class DailyTargetOutcome:
    """Records one capability result with typed skip provenance and evidence."""

    quest_id: DailyQuestId
    status: DailyTargetOutcomeStatus
    message: str
    skip_reason: DailyApplicabilitySkipReason | None = None
    artifact_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Requires a closed skip reason only for applicability skips."""

        requires_reason = self.status == DailyTargetOutcomeStatus.APPLICABILITY_SKIP
        if requires_reason != (self.skip_reason is not None):
            raise ValueError("Only applicability-skip outcomes must define skip_reason.")


class MutationIntentState(StrEnum):
    """Tracks one exactly-once mutation through durable reconciliation."""

    PREPARED = "prepared"
    DISPATCHED = "dispatched"
    RECONCILED = "reconciled"
    COMMITTED = "committed"


@dataclass(frozen=True, slots=True)
class MutationIntent:
    """Represents one individually journaled mutating sub-operation."""

    operation_id: str
    quest_id: DailyQuestId
    state: MutationIntentState
    expected_precondition: str
    expected_postcondition: str
    diamond_budget: int = 0
    diamonds_spent: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects malformed identifiers and overspent premium budgets."""

        if not self.operation_id.strip():
            raise ValueError("MutationIntent.operation_id cannot be empty.")
        if not self.expected_precondition.strip() or not self.expected_postcondition.strip():
            raise ValueError("MutationIntent precondition and postcondition cannot be empty.")
        if self.diamond_budget < 0 or self.diamonds_spent < 0:
            raise ValueError("MutationIntent diamond values cannot be negative.")
        if self.diamonds_spent > self.diamond_budget:
            raise ValueError("MutationIntent cannot spend beyond its diamond budget.")


@dataclass(frozen=True, slots=True)
class DailyTaskCheckpoint:
    """Stores durable progress for one account/castle/game-reset boundary."""

    maintenance_date: str
    game_reset_id: str
    account_id: str
    castle: CastleIdentity
    current_quest_id: DailyQuestId | None = None
    completed_quest_ids: tuple[DailyQuestId, ...] = ()
    mutation_intents: tuple[MutationIntent, ...] = ()
    consumed_recovery_stages: tuple[str, ...] = ()
    last_typed_screen: ScreenType | None = None

    def __post_init__(self) -> None:
        """Rejects incomplete checkpoint identity and duplicate operation ids."""

        if not self.maintenance_date or not self.game_reset_id or not self.account_id:
            raise ValueError("DailyTaskCheckpoint identity fields cannot be empty.")
        operation_ids = [intent.operation_id for intent in self.mutation_intents]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("DailyTaskCheckpoint mutation operation ids must be unique.")
