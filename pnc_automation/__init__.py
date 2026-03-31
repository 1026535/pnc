"""Top-level package for the Puzzles & Conquest automation platform."""

from pnc_automation.api import (
    AutomationApi,
    build_api,
    building_upgrade,
    campaign,
    collect_kingdom_chat,
    gathering,
    open_building,
    research,
    send_alliance_chat_message,
    send_world_chat_message,
    use_account,
)
from pnc_automation.app import ApplicationRunner, build_application_runner

__all__ = [
    "ApplicationRunner",
    "AutomationApi",
    "build_api",
    "build_application_runner",
    "building_upgrade",
    "campaign",
    "collect_kingdom_chat",
    "gathering",
    "open_building",
    "research",
    "send_alliance_chat_message",
    "send_world_chat_message",
    "use_account",
]
