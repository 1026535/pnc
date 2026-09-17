"""Parser for exact live daily-maintenance mutation acknowledgements."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pnc_automation.app.authoring.config.yaml_helpers import require_int, require_mapping, require_string
from pnc_automation.app.pnc.domain.daily_maintenance import (
    DailyQuestId,
    MutationAcknowledgement,
    MutationBudgetKind,
)
from pnc_automation.app.pnc.domain.feature_actions import normalize_feature_action_kind
from pnc_automation.core.errors import ConfigurationError

_FLAT_BUDGET_FIELDS = {"max_mutations", "max_diamond_spend"}


def parse_mutation_acknowledgement(value: str) -> MutationAcknowledgement:
    """Parses one strict JSON acknowledgement supplied at invocation time."""

    try:
        decoded: Any = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigurationError("Mutation acknowledgement must be valid JSON.") from error
    raw = require_mapping(decoded, context="mutation acknowledgement")
    common_fields = {"account_id", "castle_ref", "maintenance_date"}
    identity_fields = {"capability", "action_kind"} & set(raw)
    unexpected = set(raw) - common_fields - {"capability", "action_kind", "budget"} - _FLAT_BUDGET_FIELDS
    missing = common_fields - set(raw)
    if unexpected or missing or len(identity_fields) != 1:
        raise ConfigurationError(
            "Mutation acknowledgement fields must match the exact schema for a Daily or feature action.",
            unexpected_fields=sorted(unexpected),
            missing_fields=sorted(missing),
        )
    if "budget" in raw:
        if "capability" in identity_fields or set(raw) & _FLAT_BUDGET_FIELDS:
            raise ConfigurationError(
                "A nested acknowledgement budget requires one feature action_kind and no flat budget fields."
            )
        budget_kind, max_mutations, max_diamond_spend = _parse_budget(raw["budget"])
    else:
        if _FLAT_BUDGET_FIELDS - set(raw):
            raise ConfigurationError(
                "Mutation acknowledgement requires the exact counted max_mutations and max_diamond_spend fields.",
                missing_fields=sorted(_FLAT_BUDGET_FIELDS - set(raw)),
            )
        budget_kind = MutationBudgetKind.COUNTED
        max_mutations = require_int(raw.get("max_mutations"), context="mutation acknowledgement.max_mutations")
        max_diamond_spend = None if raw.get("max_diamond_spend") is None else require_int(
            raw.get("max_diamond_spend"),
            context="mutation acknowledgement.max_diamond_spend",
        )
    quest_id = None
    action_kind = None
    if "capability" in identity_fields:
        raw_capability = require_string(raw.get("capability"), context="mutation acknowledgement.capability")
        try:
            quest_id = DailyQuestId(raw_capability)
        except ValueError as error:
            raise ConfigurationError(
                f"Unknown mutation acknowledgement capability '{raw_capability}'.",
                capability=raw_capability,
            ) from error
    else:
        raw_action_kind = require_string(raw.get("action_kind"), context="mutation acknowledgement.action_kind")
        try:
            action_kind = normalize_feature_action_kind(raw_action_kind).value
        except ValueError as error:
            raise ConfigurationError(
                f"Unknown mutation acknowledgement action kind '{raw_action_kind}'.",
                action_kind=raw_action_kind,
            ) from error
    raw_date = require_string(raw.get("maintenance_date"), context="mutation acknowledgement.maintenance_date")
    try:
        maintenance_date = date.fromisoformat(raw_date)
    except ValueError as error:
        raise ConfigurationError(
            "Mutation acknowledgement maintenance_date must use YYYY-MM-DD.",
            maintenance_date=raw_date,
        ) from error
    try:
        return MutationAcknowledgement(
            account_id=require_string(raw.get("account_id"), context="mutation acknowledgement.account_id"),
            castle_ref=require_string(raw.get("castle_ref"), context="mutation acknowledgement.castle_ref"),
            quest_id=quest_id,
            maintenance_date=maintenance_date,
            max_mutations=max_mutations,
            max_diamond_spend=max_diamond_spend,
            action_kind=action_kind,
            budget_kind=budget_kind,
        )
    except ValueError as error:
        raise ConfigurationError(str(error)) from error


def _parse_budget(value: Any) -> tuple[MutationBudgetKind, int | None, int | None]:
    """Parses one nested exact budget object into its typed form and limits."""

    budget = require_mapping(value, context="mutation acknowledgement.budget")
    raw_kind = require_string(budget.get("kind"), context="mutation acknowledgement.budget.kind")
    try:
        budget_kind = MutationBudgetKind(raw_kind)
    except ValueError as error:
        raise ConfigurationError(
            f"Unknown mutation acknowledgement budget kind '{raw_kind}'.",
            budget_kind=raw_kind,
        ) from error
    required = {"kind", "max_diamond_spend"}
    if budget_kind is MutationBudgetKind.COUNTED:
        required.add("max_mutations")
    unexpected = set(budget) - required
    missing = required - set(budget)
    if unexpected or missing:
        raise ConfigurationError(
            f"A '{budget_kind.value}' acknowledgement budget must define exactly {sorted(required)}.",
            unexpected_fields=sorted(unexpected),
            missing_fields=sorted(missing),
        )
    max_mutations = None
    if budget_kind is MutationBudgetKind.COUNTED:
        max_mutations = require_int(
            budget.get("max_mutations"), context="mutation acknowledgement.budget.max_mutations"
        )
    max_diamond_spend = None if budget.get("max_diamond_spend") is None else require_int(
        budget.get("max_diamond_spend"),
        context="mutation acknowledgement.budget.max_diamond_spend",
    )
    return budget_kind, max_mutations, max_diamond_spend
