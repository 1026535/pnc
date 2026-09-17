"""Typed domain contracts for daily castle maintenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.domain.pet_workshop import WorkshopMutationKind
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


class MutationBudgetKind(StrEnum):
    """The budget form one mutation acknowledgement authorizes.

    ``COUNTED`` is the existing exact-operation-count budget shared by Daily
    capabilities, building actions and bounded Workshop canaries.
    ``OBSERVED_WORKSHOP_BAR`` is the closed Workshop run budget: only the
    observed energy bar, observed natural gains and restricted observed
    recycling results may fund actions; it stops at observed zero, never
    refills from inventory or energy pieces, and carries no counted cap.
    """

    COUNTED = "counted"
    OBSERVED_WORKSHOP_BAR = "observed_workshop_bar"


@dataclass(frozen=True, slots=True)
class MutationAcknowledgement:
    """Authorizes one exact live capability budget for one castle and local date."""

    account_id: str
    castle_ref: str
    quest_id: DailyQuestId | None
    maintenance_date: date
    max_mutations: int | None
    max_diamond_spend: int | None
    action_kind: str | None = None
    budget_kind: MutationBudgetKind = MutationBudgetKind.COUNTED

    def __post_init__(self) -> None:
        """Rejects broad or unbounded live acknowledgements."""

        if not self.account_id.strip() or not self.castle_ref.strip():
            raise ValueError("Mutation acknowledgement account and castle cannot be empty.")
        if not isinstance(self.budget_kind, MutationBudgetKind):
            raise TypeError("Mutation acknowledgement budget_kind must be a MutationBudgetKind.")
        if (self.quest_id is None) == (self.action_kind is None):
            raise ValueError(
                "Mutation acknowledgement requires exactly one Daily capability or feature action kind."
            )
        if self.action_kind is not None and not self.action_kind.strip():
            raise ValueError("Mutation acknowledgement action_kind cannot be blank.")
        workshop = self.action_kind == WorkshopMutationKind.RUN.value
        if self.budget_kind is MutationBudgetKind.COUNTED:
            if (
                isinstance(self.max_mutations, bool)
                or not isinstance(self.max_mutations, int)
                or self.max_mutations <= 0
            ):
                raise ValueError("Mutation acknowledgement max_mutations must be positive.")
        elif self.max_mutations is not None:
            raise ValueError("The observed Workshop bar budget cannot carry a counted mutation cap.")
        if self.budget_kind is MutationBudgetKind.OBSERVED_WORKSHOP_BAR and not workshop:
            raise ValueError("The observed Workshop bar budget requires the pet_workshop.run scope.")
        if workshop and self.max_diamond_spend != 0:
            raise ValueError("Workshop acknowledgements cannot spend diamonds.")
        if self.quest_id is not None:
            validate_daily_diamond_limit(self.max_diamond_spend, quest_id=self.quest_id)
        elif self.max_diamond_spend is None or self.max_diamond_spend < 0:
            raise ValueError("Feature mutation acknowledgement requires a finite premium budget.")

    def authorize(
        self,
        *,
        account_id: str,
        castle_ref: str,
        quest_id: DailyQuestId | None,
        max_mutations: int | None,
        max_diamond_spend: int | None,
        maintenance_date: date,
        action_kind: str | None = None,
        budget_kind: MutationBudgetKind = MutationBudgetKind.COUNTED,
    ) -> None:
        """Fails unless this acknowledgement exactly matches the requested live slice."""

        expected = (account_id, castle_ref, quest_id, maintenance_date)
        actual = (self.account_id, self.castle_ref, self.quest_id, self.maintenance_date)
        if actual != expected:
            raise ValueError("Mutation acknowledgement does not match the requested live target and date.")
        if self.budget_kind is not budget_kind:
            raise ValueError("Mutation acknowledgement must match the exact budget form.")
        if self.max_mutations != max_mutations:
            raise ValueError("Mutation acknowledgement must match the capability mutation limit exactly.")
        if self.max_diamond_spend != max_diamond_spend:
            raise ValueError("Mutation acknowledgement must match the capability diamond limit exactly.")
        if self.action_kind != action_kind:
            raise ValueError("Mutation acknowledgement must match the exact action kind.")


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
    quest_id: DailyQuestId | None
    state: MutationIntentState
    expected_precondition: str
    expected_postcondition: str
    diamond_budget: int = 0
    diamonds_spent: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    action_kind: str | None = None
    target: dict[str, Any] | None = None
    invocation_id: str | None = None

    def __post_init__(self) -> None:
        """Rejects malformed identifiers and overspent premium budgets."""

        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("MutationIntent.operation_id cannot be empty.")
        if self.quest_id is not None and not isinstance(self.quest_id, DailyQuestId):
            raise TypeError("MutationIntent.quest_id must be a DailyQuestId or None.")
        if not self.expected_precondition.strip() or not self.expected_postcondition.strip():
            raise ValueError("MutationIntent precondition and postcondition cannot be empty.")
        if self.diamond_budget < 0 or self.diamonds_spent < 0:
            raise ValueError("MutationIntent diamond values cannot be negative.")
        if self.diamonds_spent > self.diamond_budget:
            raise ValueError("MutationIntent cannot spend beyond its diamond budget.")
        if self.action_kind is not None and not self.action_kind.strip():
            raise ValueError("MutationIntent.action_kind cannot be blank.")
        if self.target is not None and not isinstance(self.target, dict):
            raise TypeError("MutationIntent.target must be a mapping or None.")
        if self.invocation_id is not None and not self.invocation_id.strip():
            raise ValueError("MutationIntent.invocation_id cannot be blank.")


@dataclass(frozen=True, slots=True)
class WorkshopInvocationRecord:
    """Durable identity and progress for one authorized Workshop run.

    ``invocation_id`` is generated once after scope validation and persisted
    before the first mutation. ``operation_sequence`` assigns each planned
    operation id independently of frame fingerprints, so a resumed operation
    retains its id while a new invocation gets a fresh one even on the same
    day. ``pending_operation_id`` references the latest unresolved journaled
    operation and ``stop_reason`` the latest observed stop/result; ``metadata``
    retains energy and reward evidence.
    """

    invocation_id: str
    action_kind: str
    budget_kind: MutationBudgetKind
    max_mutations: int | None = None
    operation_sequence: int = 0
    pending_operation_id: str | None = None
    stop_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Rejects malformed invocation identity, budgets, and sequence state."""

        if not isinstance(self.invocation_id, str) or not self.invocation_id.strip():
            raise ValueError("WorkshopInvocationRecord.invocation_id cannot be empty.")
        if self.action_kind != WorkshopMutationKind.RUN.value:
            raise ValueError("WorkshopInvocationRecord requires the pet_workshop.run action kind.")
        if not isinstance(self.budget_kind, MutationBudgetKind):
            raise TypeError("WorkshopInvocationRecord.budget_kind must be a MutationBudgetKind.")
        if self.budget_kind is MutationBudgetKind.COUNTED:
            if (
                isinstance(self.max_mutations, bool)
                or not isinstance(self.max_mutations, int)
                or self.max_mutations <= 0
            ):
                raise ValueError("A counted Workshop invocation requires a positive mutation cap.")
        elif self.max_mutations is not None:
            raise ValueError("The observed Workshop bar budget cannot carry a counted mutation cap.")
        if type(self.operation_sequence) is not int or self.operation_sequence < 0:
            raise ValueError("WorkshopInvocationRecord.operation_sequence cannot be negative.")
        if self.pending_operation_id is not None and not self.pending_operation_id.strip():
            raise ValueError("WorkshopInvocationRecord.pending_operation_id cannot be blank.")
        if self.stop_reason is not None and not self.stop_reason.strip():
            raise ValueError("WorkshopInvocationRecord.stop_reason cannot be blank.")
        if not isinstance(self.metadata, dict):
            raise TypeError("WorkshopInvocationRecord.metadata must be a mapping.")


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
    workshop_invocations: tuple[WorkshopInvocationRecord, ...] = ()

    def __post_init__(self) -> None:
        """Rejects incomplete checkpoint identity and duplicate operation ids."""

        if not self.maintenance_date or not self.game_reset_id or not self.account_id:
            raise ValueError("DailyTaskCheckpoint identity fields cannot be empty.")
        operation_ids = [intent.operation_id for intent in self.mutation_intents]
        if len(operation_ids) != len(set(operation_ids)):
            raise ValueError("DailyTaskCheckpoint mutation operation ids must be unique.")
        invocation_ids = [record.invocation_id for record in self.workshop_invocations]
        if len(invocation_ids) != len(set(invocation_ids)):
            raise ValueError("DailyTaskCheckpoint Workshop invocation ids must be unique.")
