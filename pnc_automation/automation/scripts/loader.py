"""Loads automation run scripts from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from pnc_automation.automation.scripts.models import RunScript, ScriptStep
from pnc_automation.automation.task import TaskId
from pnc_automation.errors import ScriptValidationError


def load_run_script(path: str | Path) -> RunScript:
    """Loads and validates one run script YAML file."""

    script_path = Path(path).resolve()
    if not script_path.is_file():
        raise ScriptValidationError("Run script file does not exist.", path=str(script_path))
    with script_path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}
    if not isinstance(raw_data, dict):
        raise ScriptValidationError("Run script root must be a mapping.", path=str(script_path))

    name = raw_data.get("name")
    if not isinstance(name, str) or name.strip() == "":
        raise ScriptValidationError("Run script requires a non-empty name.", path=str(script_path))

    raw_steps = raw_data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ScriptValidationError("Run script requires a non-empty steps list.", path=str(script_path))

    steps: list[ScriptStep] = []
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, dict):
            raise ScriptValidationError("Each script step must be a mapping.", step_index=index)
        raw_task = raw_step.get("task")
        if not isinstance(raw_task, str):
            raise ScriptValidationError("Each script step requires a string task id.", step_index=index)
        try:
            task_id = TaskId(raw_task)
        except ValueError as error:
            raise ScriptValidationError(f"Unknown task id '{raw_task}'.", step_index=index, task=raw_task) from error
        raw_params = raw_step.get("params", {})
        if not isinstance(raw_params, dict):
            raise ScriptValidationError("Step params must be a mapping.", step_index=index, task=raw_task)
        steps.append(ScriptStep(task=task_id, params=dict(raw_params)))

    return RunScript(name=name, path=script_path, steps=tuple(steps))
