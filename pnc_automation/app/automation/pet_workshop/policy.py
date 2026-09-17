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
    fabricate it. ``secondary_quantities`` carries the lower-priority
    categories' observed counts in policy order (absent categories read as
    0, unread counts as ``None``); ``secondary_quantity`` keeps their summed
    total for diagnostics.

    ``unresolved`` marks cards whose contents are not provably read — an
    incomplete recognition status with no proven disqualifier — and
    ``unknown_reward`` marks eligible cards carrying an UNKNOWN reward
    category. Both need an ORDER_CONTENTS read before the ranking is
    trusted; known ineligible cards (proven totals, unknown item ids) never
    trigger it.
    """

    order: WorkshopOrder
    survey_index: int
    eligible: bool
    ineligible_reason: str
    category: WorkshopOrderRewardCategory | None
    category_rank: int | None
    primary_quantity: int | None
    secondary_quantity: int | None
    secondary_quantities: tuple[int | None, ...] = ()
    unresolved: bool = False
    unknown_reward: bool = False

    @property
    def is_goal(self) -> bool:
        """Returns whether the order is an eligible, policy-ranked goal."""

        return self.eligible and self.category is not None

    @property
    def ranking_blocked(self) -> bool:
        """Returns whether ranking needs facts the card did not provide.

        Whether the unread facts actually block selection is decided against
        the other contenders — an unread count matters only where it could
        change the applicable ranking.
        """

        return (
            self.unresolved
            or self.unknown_reward
            or (
                self.is_goal
                and (
                    self.primary_quantity is None
                    or any(q is None for q in self.secondary_quantities)
                )
            )
        )


#: Recognition statuses whose card contents are not provably read.
#: ``NO_ACTION`` is a resolved non-order row, not an unresolved contender.
_UNRESOLVED_COMPLETENESS = frozenset(
    {
        RowRecognitionStatus.NOT_EVALUATED,
        RowRecognitionStatus.CLIPPED,
        RowRecognitionStatus.UNREADABLE,
        RowRecognitionStatus.AMBIGUOUS,
    }
)


def assess_order(
    order: WorkshopOrder,
    survey_index: int,
    catalog: PetWorkshopCatalog,
    policy: WorkshopPolicy,
) -> OrderAssessment:
    """Classifies one surveyed order under the policy.

    Complete cards with unknown item ids or a proven non-configured piece
    total are known ineligible — excluded from goals, never submitted, and
    never inspected. Incomplete cards that could still be a policy goal are
    ``unresolved``: the selection owner requests their contents before
    trusting any ranking they could change.
    """

    reason = ""
    unknown_items = any(
        catalog.item(item_id) is None for item_id in order.requirements
    )
    if order.completeness != RowRecognitionStatus.COMPLETE:
        reason = f"card completeness is {order.completeness.value}"
    elif unknown_items:
        reason = "requirement uses an unknown catalog item"
    elif order.total_pieces != policy.order_piece_total:
        reason = f"piece total {order.total_pieces} != {policy.order_piece_total}"
    eligible = not reason
    unresolved = (
        order.completeness in _UNRESOLVED_COMPLETENESS
        and order.total_pieces <= policy.order_piece_total
        and not unknown_items
    )
    category: WorkshopOrderRewardCategory | None = None
    category_rank: int | None = None
    primary_quantity: int | None = None
    secondary_quantity: int | None = None
    secondary_quantities: tuple[int | None, ...] = ()
    unknown_reward = False
    if eligible:
        by_category = {reward.category: reward for reward in order.rewards}
        unknown_reward = (
            WorkshopOrderRewardCategory.UNKNOWN in by_category
        )
        for rank, candidate in enumerate(policy.reward_priority):
            if candidate in by_category:
                category = candidate
                category_rank = rank
                primary_quantity = by_category[candidate].quantity
                break
        if category is not None:
            secondary_quantities = tuple(
                by_category[candidate].quantity
                if candidate in by_category
                else 0
                for candidate in policy.reward_priority[category_rank + 1 :]
            )
            secondary_quantity = (
                None
                if any(qty is None for qty in secondary_quantities)
                else sum(secondary_quantities)
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
        secondary_quantities=secondary_quantities,
        unresolved=unresolved,
        unknown_reward=unknown_reward,
    )
