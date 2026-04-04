"""Loads automation run scripts from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pnc_automation.app.automation.engine.task import TaskId
from pnc_automation.app.authoring.config.yaml_helpers import require_list, require_mapping, require_string
from pnc_automation.core.errors import ScriptValidationError
from pnc_automation.app.authoring.scripts.models import CastleRefRepeatBlock, RunScript, ScriptNode, ScriptStep


def load_run_script(path: str | Path) -> RunScript:
    """Loads and validates one run script YAML file."""

    script_path = Path(path).resolve()
    if not script_path.is_file():
        raise ScriptValidationError("Run script file does not exist.", path=str(script_path))
    with script_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    raw = require_mapping(raw_data, context="run script root", error_builder=ScriptValidationError)

    name = require_string(raw.get("name"), context="run script name", error_builder=ScriptValidationError)
    raw_steps = require_list(raw.get("steps"), context="run script steps", error_builder=ScriptValidationError)
    if not raw_steps:
        raise ScriptValidationError("Run script requires a non-empty steps list.", path=str(script_path))

    steps = _load_script_nodes(raw_steps, context="steps", step_index=None, inside_repeat_block=False)

    return RunScript(name=name, path=script_path, steps=tuple(steps))


def _load_script_nodes(
    raw_steps: list[Any],
    *,
    context: str,
    step_index: int | None,
    inside_repeat_block: bool,
) -> list[ScriptNode]:
    """Loads one ordered authored node list while enforcing repeat-block ownership rules."""

    steps: list[ScriptNode] = []
    for index, raw_step in enumerate(raw_steps):
        node_context = f"{context}[{index}]"
        authored_index = index if step_index is None else step_index
        step = require_mapping(raw_step, context=node_context, error_builder=ScriptValidationError)
        has_task = "task" in step
        has_repeat = "castle_refs" in step
        if has_task and has_repeat:
            raise ScriptValidationError(
                "Run script steps cannot define both 'task' and 'castle_refs'.",
                step_index=authored_index,
                step_path=node_context,
            )
        if not has_task and not has_repeat:
            raise ScriptValidationError(
                "Run script steps must define either 'task' or 'castle_refs'.",
                step_index=authored_index,
                step_path=node_context,
            )
        if has_repeat:
            if inside_repeat_block:
                raise ScriptValidationError(
                    "Repeat blocks may only contain ordinary task steps, not nested repeat blocks.",
                    step_index=authored_index,
                    step_path=node_context,
                )
            steps.append(_load_repeat_block(step, context=node_context, step_index=index))
            continue
        steps.append(_load_task_step(step, context=node_context, step_index=authored_index, inside_repeat_block=inside_repeat_block))
    return steps


def _load_repeat_block(
    step: dict[str, Any] | Any,
    *,
    context: str,
    step_index: int,
) -> CastleRefRepeatBlock:
    """Loads one authored multi-castle repeat block and its nested ordinary steps."""

    if "params" in step:
        raise ScriptValidationError(
            "Repeat blocks cannot define 'params'; move parameters onto the nested task steps.",
            step_index=step_index,
            step_path=context,
        )
    if "castle_ref" in step:
        raise ScriptValidationError(
            "Repeat blocks cannot define 'castle_ref'; use 'castle_refs' only on the block.",
            step_index=step_index,
            step_path=context,
        )
    if "castle" in step:
        raise ScriptValidationError(
            "Run scripts no longer support inline 'castle'; use 'castle_ref' and configure the alias in castle_targets.yaml.",
            step_index=step_index,
            step_path=context,
        )
    raw_castle_refs = require_list(
        step.get("castle_refs"),
        context=f"{context}.castle_refs",
        error_builder=ScriptValidationError,
    )
    if not raw_castle_refs:
        raise ScriptValidationError(
            "Repeat blocks require a non-empty 'castle_refs' list.",
            step_index=step_index,
            step_path=context,
        )
    castle_refs = tuple(
        require_string(
            raw_castle_ref,
            context=f"{context}.castle_refs[{castle_index}]",
            error_builder=ScriptValidationError,
        )
        for castle_index, raw_castle_ref in enumerate(raw_castle_refs)
    )
    raw_nested_steps = require_list(
        step.get("steps"),
        context=f"{context}.steps",
        error_builder=ScriptValidationError,
    )
    if not raw_nested_steps:
        raise ScriptValidationError(
            "Repeat blocks require a non-empty nested 'steps' list.",
            step_index=step_index,
            step_path=context,
        )
    nested_steps = _load_script_nodes(
        raw_nested_steps,
        context=f"{context}.steps",
        step_index=step_index,
        inside_repeat_block=True,
    )
    task_steps = tuple(node for node in nested_steps if isinstance(node, ScriptStep))
    if len(task_steps) != len(nested_steps):
        raise AssertionError("Repeat blocks must flatten to ordinary task steps during loading.")
    return CastleRefRepeatBlock(castle_refs=castle_refs, steps=task_steps)


def _load_task_step(
    step: dict[str, Any] | Any,
    *,
    context: str,
    step_index: int,
    inside_repeat_block: bool,
) -> ScriptStep:
    """Loads one ordinary authored task step."""

    raw_task = require_string(
        step.get("task"),
        context=f"{context}.task",
        error_builder=ScriptValidationError,
    )
    try:
        task_id = TaskId(raw_task)
    except ValueError as error:
        raise ScriptValidationError(
            f"Unknown task id '{raw_task}'.",
            step_index=step_index,
            step_path=context,
            task=raw_task,
        ) from error
    if "steps" in step:
        raise ScriptValidationError(
            "Ordinary task steps cannot define nested 'steps'; use a repeat block with 'castle_refs' when you need nested workflows.",
            step_index=step_index,
            step_path=context,
            task=task_id,
        )
    raw_params = step.get("params", {})
    params = require_mapping(
        raw_params,
        context=f"{context}.params",
        error_builder=ScriptValidationError,
    )
    if "castle" in step:
        raise ScriptValidationError(
            "Run scripts no longer support inline 'castle'; use 'castle_ref' and configure the alias in castle_targets.yaml.",
            step_index=step_index,
            step_path=context,
            task=task_id,
        )
    castle_ref = None
    if "castle_ref" in step:
        if inside_repeat_block:
            raise ScriptValidationError(
                "Nested repeat-block steps cannot define 'castle_ref'; the repeat block owns castle targeting for its nested workflow.",
                step_index=step_index,
                step_path=context,
                task=task_id,
            )
        castle_ref = require_string(
            step.get("castle_ref"),
            context=f"{context}.castle_ref",
            error_builder=ScriptValidationError,
        )
    return ScriptStep(task=task_id, castle_ref=castle_ref, params=dict(params))
