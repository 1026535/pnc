"""Loads automation run scripts from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.task import TaskId
from pnc_automation.config.yaml_helpers import load_castle_identity, require_list, require_mapping, require_string
from pnc_automation.errors import ScriptValidationError


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

    steps: list[ScriptStep] = []
    for index, raw_step in enumerate(raw_steps):
        step = require_mapping(raw_step, context=f"steps[{index}]", error_builder=ScriptValidationError)
        raw_task = require_string(
            step.get("task"),
            context=f"steps[{index}].task",
            error_builder=ScriptValidationError,
        )
        try:
            task_id = TaskId(raw_task)
        except ValueError as error:
            raise ScriptValidationError(f"Unknown task id '{raw_task}'.", step_index=index, task=raw_task) from error
        raw_params = step.get("params", {})
        params = require_mapping(
            raw_params,
            context=f"steps[{index}].params",
            error_builder=ScriptValidationError,
        )
        castle = None
        if "castle" in step:
            castle = load_castle_identity(
                step.get("castle"),
                context=f"steps[{index}].castle",
                error_builder=ScriptValidationError,
            )
        steps.append(ScriptStep(task=task_id, castle=castle, params=dict(params)))

    return RunScript(name=name, path=script_path, steps=tuple(steps))
