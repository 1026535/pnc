"""Parser for exact live daily-maintenance mutation acknowledgements."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from pnc_automation.app.authoring.config.yaml_helpers import require_int, require_mapping, require_string
from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestId, MutationAcknowledgement
from pnc_automation.app.pnc.domain.building_operations import BuildingMutationKind
from pnc_automation.core.errors import ConfigurationError


def parse_mutation_acknowledgement(value: str) -> MutationAcknowledgement:
    """Parses one strict JSON acknowledgement supplied at invocation time."""

    try:
        decoded: Any = json.loads(value)
    except json.JSONDecodeError as error:
        raise ConfigurationError("Mutation acknowledgement must be valid JSON.") from error
    raw = require_mapping(decoded, context="mutation acknowledgement")
    common_fields = {
        "account_id",
        "castle_ref",
        "maintenance_date",
        "max_mutations",
        "max_diamond_spend",
    }
    identity_fields = {"capability", "action_kind"} & set(raw)
    unexpected = set(raw) - common_fields - {"capability", "action_kind"}
    missing = common_fields - set(raw)
    if unexpected or missing or len(identity_fields) != 1:
        raise ConfigurationError(
            "Mutation acknowledgement fields must match the exact schema for a Daily or building action.",
            unexpected_fields=sorted(unexpected),
            missing_fields=sorted(missing),
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
            action_kind = BuildingMutationKind(raw_action_kind).value
        except ValueError as error:
            raise ConfigurationError(
                f"Unknown building mutation action kind '{raw_action_kind}'.",
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
            max_mutations=require_int(raw.get("max_mutations"), context="mutation acknowledgement.max_mutations"),
            max_diamond_spend=None if raw.get("max_diamond_spend") is None else require_int(
                raw.get("max_diamond_spend"),
                context="mutation acknowledgement.max_diamond_spend",
            ),
            action_kind=action_kind,
        )
    except ValueError as error:
        raise ConfigurationError(str(error)) from error
