"""Application-owned packages and entry points."""

from importlib import import_module
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ApplicationRunner": ("pnc_automation.app.entrypoints.app", "ApplicationRunner"),
    "build_application_runner": ("pnc_automation.app.entrypoints.app", "build_application_runner"),
}


def __getattr__(name: str) -> Any:
    """Loads public composition exports only when explicitly requested."""

    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Includes supported exports in introspection before their first import."""

    return sorted(set(globals()) | _LAZY_EXPORTS.keys())

__all__ = ["ApplicationRunner", "build_application_runner"]

