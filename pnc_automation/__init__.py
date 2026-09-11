"""Top-level package for the Puzzles & Conquest automation platform."""

from importlib import import_module
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "ApplicationRunner": ("pnc_automation.app.entrypoints.app", "ApplicationRunner"),
    "AutomationApi": ("pnc_automation.app.entrypoints.api", "AutomationApi"),
    "build_api": ("pnc_automation.app.entrypoints.api", "build_api"),
    "build_application_runner": ("pnc_automation.app.entrypoints.app", "build_application_runner"),
    "building_construct": ("pnc_automation.app.entrypoints.api", "building_construct"),
    "building_upgrade": ("pnc_automation.app.entrypoints.api", "building_upgrade"),
    "campaign": ("pnc_automation.app.entrypoints.api", "campaign"),
    "collect_kingdom_chat": ("pnc_automation.app.entrypoints.api", "collect_kingdom_chat"),
    "gathering": ("pnc_automation.app.entrypoints.api", "gathering"),
    "open_building": ("pnc_automation.app.entrypoints.api", "open_building"),
    "research": ("pnc_automation.app.entrypoints.api", "research"),
    "reserve_accounts": ("pnc_automation.app.entrypoints.api", "reserve_accounts"),
    "send_alliance_chat_message": ("pnc_automation.app.entrypoints.api", "send_alliance_chat_message"),
    "send_world_chat_message": ("pnc_automation.app.entrypoints.api", "send_world_chat_message"),
    "use_account": ("pnc_automation.app.entrypoints.api", "use_account"),
}


def __getattr__(name: str) -> Any:
    """Loads a public application export only when that export is requested."""

    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "ApplicationRunner",
    "AutomationApi",
    "build_api",
    "build_application_runner",
    "building_construct",
    "building_upgrade",
    "campaign",
    "collect_kingdom_chat",
    "gathering",
    "open_building",
    "research",
    "reserve_accounts",
    "send_alliance_chat_message",
    "send_world_chat_message",
    "use_account",
]
