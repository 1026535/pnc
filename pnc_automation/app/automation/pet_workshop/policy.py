"""Solver-owned policy defaults and order assessment (Plan 02 PW03).

The package's single policy owner: the default reward hierarchy, the
two-total-piece admission rule and the restricted recycling allowlist live
here so no screenshot-time or runtime caller can substitute a different
policy. ``assess_order`` is the only place an order card is classified —
eligibility, reward tier and ranking-readiness in one pass.
"""

from __future__ import annotations

from dataclasses import dataclass

from pnc_automation.app.pnc.domain.pet_workshop import (
    WorkshopOrder,
    WorkshopOrderRewardCategory,
    WorkshopPolicy,
)
from pnc_automation.app.pnc.domain.observation import RowRecognitionStatus
from pnc_automation.app.pnc.pet_workshop_catalog import PetWorkshopCatalog

#: Default policy values for the solver lane (Plan 02 reward hierarchy).
DEFAULT_ORDER_PIECE_TOTAL = 2
DEFAULT_REWARD_PRIORITY: tuple[WorkshopOrderRewardCategory, ...] = (
    WorkshopOrderRewardCategory.BEAST_LASSO,
    WorkshopOrderRewardCategory.FEED,
    WorkshopOrderRewardCategory.WORKSHOP_EXP,
    WorkshopOrderRewardCategory.BOTTLE,
    WorkshopOrderRewardCategory.CHEST,
)
#: Restricted recycling allowlist: Fruit 5 (20105) and Statue 5 (10205).
DEFAULT_RECYCLABLE_ITEM_IDS = frozenset({20105, 10205})
DEFAULT_MAX_COOLDOWN_WAIT_MS = 60_000


def default_policy() -> WorkshopPolicy:
    """Returns the solver's default policy instance."""

    return WorkshopPolicy(
        order_piece_total=DEFAULT_ORDER_PIECE_TOTAL,
        reward_priority=DEFAULT_REWARD_PRIORITY,
        recyclable_item_ids=DEFAULT_RECYCLABLE_ITEM_IDS,
        max_cooldown_wait_ms=DEFAULT_MAX_COOLDOWN_WAIT_MS,
    )


@dataclass(frozen=True, slots=True)
class OrderAssessment:
    """Static classification of one surveyed order card.

    ``eligible`` means the card is complete, every requirement id resolves in
    the packaged catalog, and the quantities total exactly
    ``policy.order_piece_total``. ``category`` is the best policy-ranked
    reward category present; ``primary_quantity`` is that reward's observed
    count, or ``None`` when the card read left it unknown — ranking must not
    fabricate it. ``secondary_quantity`` sums the observed counts of the
    lower-priority categories on the same card.
    """

    order: WorkshopOrder
    survey_index: int
    eligible: bool
    ineligible_reason: str
    category: WorkshopOrderRewardCategory | None
    category_rank: int | None
    primary_quantity: int | None
    secondary_quantity: int | None

    @property
    def is_goal(self) -> bool:
        """Returns whether the order is an eligible, policy-ranked goal."""

        return self.eligible and self.category is not None

    @property
    def ranking_blocked(self) -> bool:
        """Returns whether ranking needs facts the card did not provide."""

        return self.is_goal and (
            self.primary_quantity is None or self.secondary_quantity is None
        )


def assess_order(
    order: WorkshopOrder,
    survey_index: int,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> OrderAssessment:
    """Classifies one surveyed order under the policy.

    Incomplete cards, unknown item ids and totals other than the configured
    piece total are ineligible — they are excluded from goals, never
    submitted, and do not trigger speculative inspection.
    """

    reason = ""
    if order.completeness != RowRecognitionStatus.COMPLETE:
        reason = f"card completeness is {order.completeness.value}"
    elif any(catalog.item(item_id) is None for item_id in order.requirements):
        reason = "requirement uses an unknown catalog item"
    elif order.total_pieces != policy.order_piece_total:
        reason = f"piece total {order.total_pieces} != {policy.order_piece_total}"
    eligible = not reason
    category: WorkshopOrderRewardCategory | None = None
    category_rank: int | None = None
    primary_quantity: int | None = None
    secondary_quantity: int | None = None
    if eligible:
        by_category = {reward.category: reward for reward in order.rewards}
        for rank, candidate in enumerate(policy.reward_priority):
            if candidate in by_category:
                category = candidate
                category_rank = rank
                primary_quantity = by_category[candidate].quantity
                break
        if category is not None:
            secondary = [
                reward.quantity
                for reward in order.rewards
                if reward.category in policy.reward_priority
                and policy.reward_priority.index(reward.category) > category_rank
            ]
            secondary_quantity = (
                None if any(qty is None for qty in secondary) else sum(secondary)
            )
    return OrderAssessment(
        order=order,
        survey_index=survey_index,
        eligible=eligible,
        ineligible_reason=reason,
        category=category,
        category_rank=category_rank,
        primary_quantity=primary_quantity,
        secondary_quantity=secondary_quantity,
    )
