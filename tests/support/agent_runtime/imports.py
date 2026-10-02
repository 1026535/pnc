"""Temporarily expose packaged agent scripts to ordinary literal imports."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterator, Literal

from tests.support.paths import REPOSITORY_ROOT

AgentScript = Literal["devin-implement", "devin-game-knowledge"]

_SCRIPT_MODULE_NAMES: dict[AgentScript, tuple[str, ...]] = {
    "devin-implement": ("devin_worker", "devin_monitor", "devin_acp", "windows_job"),
    "devin-game-knowledge": ("consult_game_knowledge",),
}


def _belongs_to_script_directory(module: ModuleType, directory: Path) -> bool:
    filename = getattr(module, "__file__", None)
    if not filename:
        return False
    try:
        return Path(filename).resolve().is_relative_to(directory)
    except (OSError, RuntimeError):
        return False


@contextmanager
def agent_script_import_path(skill: AgentScript) -> Iterator[Path]:
    """Scope a skill's script directory and restore its import state on exit."""
    directory = (REPOSITORY_ROOT / ".agents" / "skills" / skill / "scripts").resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Agent script directory does not exist: {directory}")

    previous_path = sys.path.copy()
    previous_modules = {
        name: module for name, module in sys.modules.items()
        if _belongs_to_script_directory(module, directory)
    }
    previous_named_modules = {
        name: sys.modules[name] for name in _SCRIPT_MODULE_NAMES[skill]
        if name in sys.modules
    }
    for name in _SCRIPT_MODULE_NAMES[skill]:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(directory))
    try:
        yield directory
    finally:
        sys.path[:] = previous_path
        for name in _SCRIPT_MODULE_NAMES[skill]:
            sys.modules.pop(name, None)
        for name, module in tuple(sys.modules.items()):
            if _belongs_to_script_directory(module, directory):
                if name in previous_modules:
                    sys.modules[name] = previous_modules[name]
                else:
                    del sys.modules[name]
        for name, module in previous_modules.items():
            sys.modules[name] = module
        for name, module in previous_named_modules.items():
            sys.modules[name] = module
