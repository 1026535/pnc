"""Loads and resolves authored scheduled-mail configuration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from pnc_automation.app.authoring.config.yaml_helpers import (
    require_int,
    require_list,
    require_mapping,
    require_string,
)
from pnc_automation.app.authoring.mail.models import (
    AuthoredMailDefinition,
    AuthoredMailSchedule,
    MailScheduleCatalog,
)
from pnc_automation.app.pnc.domain.mail import parse_send_mail_params, serialize_send_mail_params
from pnc_automation.core.errors import ConfigurationError

_SUPPORTED_ROTATION_DAYS = 14


def load_mail_schedule_catalog(*, definitions_path: str | Path, schedules_path: str | Path) -> MailScheduleCatalog:
    """Loads, validates, and cross-links the authored scheduled-mail catalog."""

    resolved_definitions_path = Path(definitions_path).resolve()
    resolved_schedules_path = Path(schedules_path).resolve()
    if not resolved_definitions_path.is_file():
        raise ConfigurationError(
            f"Mail definitions file '{resolved_definitions_path}' does not exist.",
            path=str(resolved_definitions_path),
        )
    if not resolved_schedules_path.is_file():
        raise ConfigurationError(
            f"Mail schedules file '{resolved_schedules_path}' does not exist.",
            path=str(resolved_schedules_path),
        )

    definitions_root = _load_yaml_root(resolved_definitions_path, context="mail definitions root")
    schedules_root = _load_yaml_root(resolved_schedules_path, context="mail schedules root")
    _require_no_extra_keys(definitions_root, allowed={"mails"}, context="mail definitions root")
    _require_no_extra_keys(schedules_root, allowed={"rotation", "mail_schedules"}, context="mail schedules root")

    definitions = _load_mail_definitions(definitions_root.get("mails"))
    schedules = _load_mail_schedules(schedules_root.get("mail_schedules"))
    _validate_schedule_mail_references(definitions=definitions, schedules=schedules)
    return MailScheduleCatalog(
        start_utc=_load_rotation_start_utc(schedules_root.get("rotation")),
        definitions=definitions,
        schedules=schedules,
    )


def resolve_due_mail_definitions(
    catalog: MailScheduleCatalog,
    *,
    scheduled_for_utc: datetime | None = None,
    schedule_ids: Sequence[str] | None = None,
) -> tuple[AuthoredMailDefinition, ...]:
    """Returns the ordered mail definitions due for one UTC hourly execution window."""

    scheduled_hour = resolve_scheduled_hour_bucket(scheduled_for_utc)
    definition_by_id = {definition.id: definition for definition in catalog.definitions}
    due_mail_ids: list[str] = []
    seen_due_mail_ids: dict[str, str] = {}
    current_day_index = _resolve_current_day_index(catalog.start_utc, scheduled_hour)
    for schedule in _select_schedules(catalog, schedule_ids=schedule_ids):
        if not schedule.enabled:
            continue
        if current_day_index not in schedule.day_indices or scheduled_hour.hour != schedule.hour_utc:
            continue
        for mail_id in schedule.mail_ids:
            duplicate_schedule_id = seen_due_mail_ids.get(mail_id)
            if duplicate_schedule_id is not None:
                raise ConfigurationError(
                    "One execution window would dispatch the same mail id more than once.",
                    mail_id=mail_id,
                    first_schedule_id=duplicate_schedule_id,
                    duplicate_schedule_id=schedule.id,
                    scheduled_for_utc=scheduled_hour.isoformat(),
                )
            seen_due_mail_ids[mail_id] = schedule.id
            due_mail_ids.append(mail_id)
    return tuple(definition_by_id[mail_id] for mail_id in due_mail_ids)


def build_generated_send_mail_script(
    *,
    scheduled_for_utc: datetime | None = None,
    due_mail_definitions: Sequence[AuthoredMailDefinition],
) -> "RunScript":
    """Builds one generated canonical send-mail script for the resolved hourly window."""

    from pnc_automation.app.automation.engine.task import TaskId
    from pnc_automation.app.authoring.scripts.models import RunScript, ScriptStep

    scheduled_hour = resolve_scheduled_hour_bucket(scheduled_for_utc)
    stamp = scheduled_hour.strftime("%Y%m%dT%H0000Z")
    steps = [
        ScriptStep(task=TaskId.ENSURE_GAME_RUNNING),
        ScriptStep(task=TaskId.LOGIN),
    ]
    for definition in due_mail_definitions:
        steps.append(
            ScriptStep(
                task=TaskId.SEND_MAIL,
                castle_ref=definition.castle_ref,
                params=serialize_send_mail_params(definition.params),
            )
        )
    return RunScript(
        name=f"generated_mail_schedule_{stamp}",
        path=Path(f"<generated:mail_schedule:{stamp}>"),
        steps=tuple(steps),
    )


def resolve_scheduled_hour_bucket(value: datetime | None) -> datetime:
    """Normalizes one runtime timestamp into the canonical UTC hourly execution bucket."""

    raw_value = datetime.now(tz=UTC) if value is None else value
    if raw_value.tzinfo is None or raw_value.utcoffset() is None:
        raise ConfigurationError(
            "Scheduled mail timestamps must be timezone-aware UTC datetimes.",
            scheduled_for_utc=str(raw_value),
        )
    normalized = raw_value.astimezone(UTC)
    if normalized.utcoffset() != timedelta(0):
        raise ConfigurationError(
            "Scheduled mail timestamps must use UTC.",
            scheduled_for_utc=raw_value.isoformat(),
        )
    return normalized.replace(minute=0, second=0, microsecond=0)


def _load_yaml_root(path: Path, *, context: str) -> Mapping[str, Any]:
    """Loads one YAML file into a validated mapping root."""

    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    return require_mapping(raw_data, context=context)


def _load_mail_definitions(raw_mails: object) -> tuple[AuthoredMailDefinition, ...]:
    """Loads the authored reusable mail definitions keyed by id."""

    items = require_list(raw_mails or [], context="mail definitions root.mails")
    definitions: list[AuthoredMailDefinition] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"mails[{index}]"
        raw = require_mapping(item, context=context)
        mail_id = require_string(raw.get("id"), context=f"{context}.id")
        if mail_id in seen_ids:
            raise ConfigurationError(
                f"Mail definitions contain a duplicate id '{mail_id}'.",
                mail_id=mail_id,
                context=f"{context}.id",
            )
        castle_ref = raw.get("castle_ref")
        if castle_ref is not None:
            castle_ref = require_string(castle_ref, context=f"{context}.castle_ref")
        payload = {
            key: value
            for key, value in raw.items()
            if key not in {"id", "castle_ref"}
        }
        definitions.append(
            AuthoredMailDefinition(
                id=mail_id,
                castle_ref=castle_ref,
                params=parse_send_mail_params(task_label=f"mail_definition:{mail_id}", params=payload),
            )
        )
        seen_ids.add(mail_id)
    return tuple(definitions)


def _load_mail_schedules(raw_schedules: object) -> tuple[AuthoredMailSchedule, ...]:
    """Loads the authored reusable mail schedules keyed by id."""

    items = require_list(raw_schedules or [], context="mail schedules root.mail_schedules")
    schedules: list[AuthoredMailSchedule] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        context = f"mail_schedules[{index}]"
        raw = require_mapping(item, context=context)
        _require_no_extra_keys(
            raw,
            allowed={"id", "enabled", "day_indices", "hour_utc", "mail_ids"},
            context=context,
        )
        schedule_id = require_string(raw.get("id"), context=f"{context}.id")
        if schedule_id in seen_ids:
            raise ConfigurationError(
                f"Mail schedules contain a duplicate id '{schedule_id}'.",
                schedule_id=schedule_id,
                context=f"{context}.id",
            )
        enabled = _load_enabled(raw.get("enabled"), context=f"{context}.enabled")
        day_indices = _load_day_indices(raw.get("day_indices"), context=f"{context}.day_indices")
        hour_utc = require_int(raw.get("hour_utc"), context=f"{context}.hour_utc")
        if hour_utc < 0 or hour_utc > 23:
            raise ConfigurationError(
                "Mail schedules require hour_utc to be within 0..23.",
                context=f"{context}.hour_utc",
                hour_utc=hour_utc,
            )
        mail_ids = _load_mail_ids(raw.get("mail_ids"), context=f"{context}.mail_ids")
        schedules.append(
            AuthoredMailSchedule(
                id=schedule_id,
                enabled=enabled,
                day_indices=day_indices,
                hour_utc=hour_utc,
                mail_ids=mail_ids,
            )
        )
        seen_ids.add(schedule_id)
    return tuple(schedules)


def _load_rotation_start_utc(raw_rotation: object) -> datetime:
    """Loads and validates the fixed v1 14-day rotation anchor."""

    rotation = require_mapping(raw_rotation, context="mail schedules root.rotation")
    _require_no_extra_keys(rotation, allowed={"cycle_days", "start_utc"}, context="mail schedules root.rotation")
    cycle_days = require_int(rotation.get("cycle_days"), context="mail schedules root.rotation.cycle_days")
    if cycle_days != _SUPPORTED_ROTATION_DAYS:
        raise ConfigurationError(
            "Scheduled mail currently supports only a 14-day rotation.",
            context="mail schedules root.rotation.cycle_days",
            cycle_days=cycle_days,
        )
    start_utc = _load_utc_datetime_value(
        rotation.get("start_utc"),
        context="mail schedules root.rotation.start_utc",
    )
    if start_utc.weekday() != 0:
        raise ConfigurationError(
            "rotation.start_utc must point to Monday week 1 day index 0.",
            context="mail schedules root.rotation.start_utc",
            start_utc=start_utc.isoformat(),
        )
    if start_utc.hour != 0 or start_utc.minute != 0 or start_utc.second != 0 or start_utc.microsecond != 0:
        raise ConfigurationError(
            "rotation.start_utc must align to 00:00:00 UTC.",
            context="mail schedules root.rotation.start_utc",
            start_utc=start_utc.isoformat(),
        )
    return start_utc


def _validate_schedule_mail_references(
    *,
    definitions: Sequence[AuthoredMailDefinition],
    schedules: Sequence[AuthoredMailSchedule],
) -> None:
    """Ensures every schedule references an existing mail definition exactly by id."""

    definition_ids = {definition.id for definition in definitions}
    for schedule in schedules:
        for mail_id in schedule.mail_ids:
            if mail_id not in definition_ids:
                raise ConfigurationError(
                    f"Mail schedule '{schedule.id}' references unknown mail id '{mail_id}'.",
                    schedule_id=schedule.id,
                    mail_id=mail_id,
                )


def _select_schedules(
    catalog: MailScheduleCatalog,
    *,
    schedule_ids: Sequence[str] | None,
) -> tuple[AuthoredMailSchedule, ...]:
    """Returns the ordered schedule subset for one invocation."""

    if schedule_ids is None:
        return catalog.schedules
    schedule_by_id = {schedule.id: schedule for schedule in catalog.schedules}
    selected: list[AuthoredMailSchedule] = []
    seen_ids: set[str] = set()
    for schedule_id in schedule_ids:
        if schedule_id in seen_ids:
            raise ConfigurationError(
                "run_mail_schedules received the same schedule id more than once.",
                schedule_id=schedule_id,
            )
        try:
            selected.append(schedule_by_id[schedule_id])
        except KeyError as error:
            raise ConfigurationError(
                f"Unknown mail schedule id '{schedule_id}'.",
                schedule_id=schedule_id,
            ) from error
        seen_ids.add(schedule_id)
    return tuple(selected)


def _resolve_current_day_index(start_utc: datetime, scheduled_hour: datetime) -> int:
    """Returns the canonical 14-day day index for one resolved UTC hour bucket."""

    elapsed_days = (scheduled_hour - start_utc) // timedelta(days=1)
    return int(elapsed_days % _SUPPORTED_ROTATION_DAYS)


def _load_enabled(value: object, *, context: str) -> bool:
    """Loads one optional schedule enabled flag with the documented default."""

    if value is None:
        return True
    if not isinstance(value, bool):
        raise ConfigurationError(f"Expected {context} to be a boolean.", context=context)
    return value


def _load_day_indices(value: object, *, context: str) -> tuple[int, ...]:
    """Loads one non-empty ordered set of unique day indices."""

    items = require_list(value, context=context)
    if not items:
        raise ConfigurationError("Mail schedules require at least one day index.", context=context)
    parsed: list[int] = []
    seen_indices: set[int] = set()
    for index, item in enumerate(items):
        day_index = require_int(item, context=f"{context}[{index}]")
        if day_index < 0 or day_index >= _SUPPORTED_ROTATION_DAYS:
            raise ConfigurationError(
                "Mail schedules require each day index to be within 0..13.",
                context=f"{context}[{index}]",
                day_index=day_index,
            )
        if day_index in seen_indices:
            raise ConfigurationError(
                "Mail schedules must not repeat the same day index within one schedule.",
                context=f"{context}[{index}]",
                day_index=day_index,
            )
        seen_indices.add(day_index)
        parsed.append(day_index)
    return tuple(parsed)


def _load_mail_ids(value: object, *, context: str) -> tuple[str, ...]:
    """Loads one non-empty ordered set of unique mail ids."""

    items = require_list(value, context=context)
    if not items:
        raise ConfigurationError("Mail schedules require at least one mail id.", context=context)
    parsed: list[str] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        mail_id = require_string(item, context=f"{context}[{index}]")
        if mail_id in seen_ids:
            raise ConfigurationError(
                "Mail schedules must not repeat the same mail id within one schedule.",
                context=f"{context}[{index}]",
                mail_id=mail_id,
            )
        seen_ids.add(mail_id)
        parsed.append(mail_id)
    return tuple(parsed)


def _load_utc_datetime_value(value: object, *, context: str) -> datetime:
    """Loads one authored UTC datetime from either YAML-parsed or string ISO content."""

    if isinstance(value, datetime):
        parsed = value
    else:
        raw_value = require_string(value, context=context)
        try:
            parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ConfigurationError(
                f"Expected {context} to be an ISO-8601 UTC timestamp.",
                context=context,
                value=raw_value,
            ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConfigurationError(
            f"Expected {context} to include a UTC timezone offset.",
            context=context,
            value=str(value),
        )
    normalized = parsed.astimezone(UTC)
    if normalized.utcoffset() != timedelta(0):
        raise ConfigurationError(
            f"Expected {context} to use UTC.",
            context=context,
            value=str(value),
        )
    return normalized


def _require_no_extra_keys(raw: Mapping[str, Any], *, allowed: set[str], context: str) -> None:
    """Rejects unexpected keys instead of silently accepting stale authored schema."""

    extra_keys = sorted(key for key in raw.keys() if key not in allowed)
    if extra_keys:
        raise ConfigurationError(
            f"{context} received unsupported keys.",
            context=context,
            extra_keys=extra_keys,
        )
