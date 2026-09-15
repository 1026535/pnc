"""Live mutation authorization lookup for daily-maintenance operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.daily_maintenance import DailyCapabilityPolicy
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, MutationAcknowledgement


@dataclass(frozen=True, slots=True)
class DailyMutationAuthorizer:
    """Requires one exact acknowledgement for every mutating capability slice."""

    acknowledgements: tuple[MutationAcknowledgement, ...] = ()

    def require(
        self,
        *,
        account_id: str,
        castle_ref: str,
        policy: DailyCapabilityPolicy,
        maintenance_date: date,
    ) -> MutationAcknowledgement:
        """Returns the exact matching acknowledgement or fails before dispatch."""

        candidates = tuple(
            item
            for item in self.acknowledgements
            if item.account_id == account_id
            and item.castle_ref == castle_ref
            and item.quest_id == policy.quest_id
            and item.maintenance_date == maintenance_date
        )
        if len(candidates) != 1:
            raise PermissionError(
                "Live daily mutation requires exactly one matching acknowledgement for "
                f"{account_id}/{castle_ref}/{policy.quest_id.value}/{maintenance_date.isoformat()}."
            )
        acknowledgement = candidates[0]
        try:
            acknowledgement.authorize(
                account_id=account_id,
                castle_ref=castle_ref,
                quest_id=policy.quest_id,
                max_mutations=policy.max_mutations,
                max_diamond_spend=policy.max_diamond_spend,
                maintenance_date=maintenance_date,
            )
        except ValueError as error:
            raise PermissionError(str(error)) from error
        return acknowledgement

    def require_claims(
        self,
        *,
        account_id: str,
        castle_ref: str,
        maintenance_date: date,
        max_claims: int,
    ) -> MutationAcknowledgement:
        """Requires the operational claim capability acknowledgement with an exact cap."""

        return self.require(
            account_id=account_id,
            castle_ref=castle_ref,
            policy=DailyCapabilityPolicy(
                quest_id=DailyQuestId.CLAIM_COMPLETED,
                task_id=TaskId.DAILY_MAINTENANCE,
                max_mutations=max_claims,
            ),
            maintenance_date=maintenance_date,
        )

    def require_building(
        self,
        *,
        account_id: str,
        castle_ref: str,
        action_kind: str,
        maintenance_date: date,
        max_mutations: int = 1,
        max_diamond_spend: int = 0,
    ) -> MutationAcknowledgement:
        """Require an exact building acknowledgement without inventing a Daily quest row."""

        if not action_kind.strip():
            raise ValueError("Building action kind cannot be blank.")
        candidates = tuple(
            item
            for item in self.acknowledgements
            if item.account_id == account_id
            and item.castle_ref == castle_ref
            and item.quest_id is None
            and item.action_kind == action_kind
            and item.maintenance_date == maintenance_date
        )
        if len(candidates) != 1:
            raise PermissionError(
                "Building mutation requires exactly one matching acknowledgement for "
                f"{account_id}/{castle_ref}/{action_kind}/{maintenance_date.isoformat()}."
            )
        acknowledgement = candidates[0]
        try:
            acknowledgement.authorize(
                account_id=account_id,
                castle_ref=castle_ref,
                quest_id=None,
                max_mutations=max_mutations,
                max_diamond_spend=max_diamond_spend,
                maintenance_date=maintenance_date,
                action_kind=action_kind,
            )
        except ValueError as error:
            raise PermissionError(str(error)) from error
        return acknowledgement
