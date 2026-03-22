"""Puzzles & Conquest-specific domain models."""

from pnc_automation.pnc.action_requests import (
    ActionRequest,
    InputTextAction,
    KeyEventAction,
    LaunchAppAction,
    SelectChatChannelAction,
    SwipeAction,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    WaitAction,
)
from pnc_automation.pnc.chat import ChatChannel
from pnc_automation.pnc.mail import (
    CollectMailParams,
    MailArchiveMode,
    MailRecipientKind,
    MailThreadFingerprint,
    MailboxType,
    PlayerProfileRoute,
    PlayerProfileRouteKind,
    SendMailParams,
)
from pnc_automation.pnc.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    ObservedTextFieldState,
    VisibleElement,
)
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId

__all__ = [
    "Bounds",
    "CollectMailParams",
    "DetectedListEntry",
    "ActionRequest",
    "ChatChannel",
    "InputTextAction",
    "KeyEventAction",
    "LaunchAppAction",
    "ListEntryKind",
    "MailArchiveMode",
    "MailboxType",
    "MailRecipientKind",
    "MailThreadFingerprint",
    "Observation",
    "ObservedTextFieldState",
    "PlayerProfileRoute",
    "PlayerProfileRouteKind",
    "ScreenType",
    "SendMailParams",
    "SwipeAction",
    "SelectChatChannelAction",
    "TapAction",
    "TapListEntryAction",
    "TapPointAction",
    "UiElementId",
    "VisibleElement",
    "WaitAction",
]
