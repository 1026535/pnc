"""Typed evidence produced while recognizing blocking popup overlays.

Perception reports measured controls and the evidence supporting them.  It does
not decide which controls the automation is authorized to press; that decision
belongs to the interruption executor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.vision.image.models import Bounds


class PopupControlKind(StrEnum):
    """Semantic kind of a candidate control on a popup overlay."""

    CLOSE_X = "close_x"
    CANCEL = "cancel"
    CLOSE_TEXT = "close_text"
    NEGATIVE_ACTION = "negative_action"
    POPUP_BACK = "popup_back"
    UPDATE_CONFIRM = "update_confirm"
    RECONNECT_CONFIRM = "reconnect_confirm"


class PopupEvidenceKind(StrEnum):
    """Evidence source used to localize a popup or one of its controls."""

    KNOWN_LAYOUT = "known_layout"
    OCR_TEXT = "ocr_text"
    TEMPLATE = "template"
    GEOMETRY = "geometry"


SAFE_TRANSIENT_POPUP_CONTROL_KINDS = (
    PopupControlKind.RECONNECT_CONFIRM,
    PopupControlKind.CANCEL,
    PopupControlKind.CLOSE_TEXT,
    PopupControlKind.NEGATIVE_ACTION,
    PopupControlKind.CLOSE_X,
)

TASK_OWNED_POPUP_SELECTOR_IDS = frozenset(
    {
        UiElementId.PNC_BUILDING_UPGRADE_CONFIRM_BUTTON,
        UiElementId.PNC_BUILDING_UPGRADE_WARNING_CONFIRM_BUTTON,
        UiElementId.PNC_BUILD_SPEEDUP_CONFIRM_BUTTON,
        UiElementId.PNC_MARCH_CONFIRM_BUTTON,
        UiElementId.PNC_MAIL_COMPOSE_SEND_BUTTON,
        UiElementId.PNC_CHAT_SEND_BUTTON,
        UiElementId.PNC_ALLIANCE_MEMBER_MANAGE_PERSONAL_INFO_BUTTON,
        UiElementId.PNC_CHAT_PLAYER_ACTION_PROFILE_BUTTON,
    }
)

TASK_OWNED_POPUP_SCREEN_TYPES = frozenset(
    {
        ScreenType.PNC_BUILDING_UPGRADE_WARNING,
        ScreenType.PNC_BUILD_SPEEDUP_CONFIRM,
        ScreenType.PNC_MARCH_CONFIRM,
        ScreenType.PNC_MAIL_COMPOSE_POPUP,
        ScreenType.PNC_CHAT_PLAYER_ACTION_POPUP,
        ScreenType.PNC_ALLIANCE_MEMBER_MANAGE_POPUP,
        ScreenType.PNC_WORLD_COORDINATE_DIALOG,
    }
)


@dataclass(frozen=True, slots=True)
class PopupRecoveryDecision:
    """Pure authorization result shared by planning and executor dispatch."""

    selector_id: UiElementId | None
    control_kind: PopupControlKind | None
    reason: str
    blocked: bool = False


def decide_popup_recovery(
    *,
    screen_type: ScreenType,
    blocking_popup: bool,
    visible_selector_ids: frozenset[UiElementId],
    popup_overlay: PopupOverlayObservation | None,
) -> PopupRecoveryDecision | None:
    """Select one typed popup action without dispatching or inspecting UI state.

    The function deliberately receives immutable evidence only.  It is the one
    authorization owner used by navigation planning and observed-action
    execution; callers remain responsible for constructing/dispatching actions.
    """

    if not blocking_popup and screen_type not in {ScreenType.PNC_POPUP, ScreenType.PNC_VIP_DAILY_RESET}:
        return None
    if screen_type in TASK_OWNED_POPUP_SCREEN_TYPES or visible_selector_ids.intersection(TASK_OWNED_POPUP_SELECTOR_IDS):
        return PopupRecoveryDecision(
            selector_id=None,
            control_kind=None,
            reason="Task-owned popup controls cannot be consumed by generic recovery.",
            blocked=True,
        )
    if popup_overlay is not None:
        update = popup_overlay.candidate(PopupControlKind.UPDATE_CONFIRM)
        if update is not None and UiElementId.PNC_UPDATE_CONFIRM_BUTTON in visible_selector_ids:
            return PopupRecoveryDecision(
                selector_id=UiElementId.PNC_UPDATE_CONFIRM_BUTTON,
                control_kind=PopupControlKind.UPDATE_CONFIRM,
                reason="confirm_required_game_update",
            )
        reconnect = popup_overlay.candidate(PopupControlKind.RECONNECT_CONFIRM)
        if reconnect is not None and UiElementId.PNC_RECONNECT_CONFIRM_BUTTON in visible_selector_ids:
            return PopupRecoveryDecision(
                selector_id=UiElementId.PNC_RECONNECT_CONFIRM_BUTTON,
                control_kind=PopupControlKind.RECONNECT_CONFIRM,
                reason="confirm_reconnect",
            )
        candidate = preferred_transient_popup_candidate(popup_overlay)
        if candidate is not None:
            if UiElementId.PNC_POPUP_CLOSE_BUTTON in visible_selector_ids:
                return PopupRecoveryDecision(
                    selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON,
                    control_kind=candidate.control_kind,
                    reason="close_popup",
                )
            if (
                screen_type == ScreenType.PNC_VIP_DAILY_RESET
                and UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON in visible_selector_ids
            ):
                return PopupRecoveryDecision(
                    selector_id=UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
                    control_kind=candidate.control_kind,
                    reason="close_vip_daily_reset",
                )
    if screen_type == ScreenType.PNC_VIP_DAILY_RESET and UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON in visible_selector_ids:
        return PopupRecoveryDecision(
            selector_id=UiElementId.PNC_VIP_DAILY_RESET_CLOSE_BUTTON,
            control_kind=PopupControlKind.CLOSE_TEXT,
            reason="close_vip_daily_reset",
        )
    # Preserve the reviewed legacy selector as a compatibility adapter while
    # typed candidates migrate through this same policy owner.
    if UiElementId.PNC_POPUP_CLOSE_BUTTON in visible_selector_ids:
        return PopupRecoveryDecision(
            selector_id=UiElementId.PNC_POPUP_CLOSE_BUTTON,
            control_kind=PopupControlKind.CLOSE_TEXT,
            reason="close_popup",
        )
    return PopupRecoveryDecision(
        selector_id=None,
        control_kind=None,
        reason="Blocking popup has no typed safe close or update action; Android Back is forbidden.",
    )


@dataclass(frozen=True, slots=True)
class PopupDismissCandidate:
    """One measured popup control candidate described by perception."""

    control_kind: PopupControlKind
    bounds: Bounds
    action_point: tuple[int, int]
    confidence: float
    evidence_kind: PopupEvidenceKind
    extracted_text: str | None = None
    reason: str | None = None

    def validate(self, *, image_size: tuple[int, int]) -> None:
        """Reject candidates that cannot safely identify an in-image tap."""

        image_width, image_height = image_size
        if image_width <= 0 or image_height <= 0:
            raise SelectorResolutionError("Popup evidence requires a positive image size.", image_size=image_size)
        bounds = self.bounds
        if bounds.width <= 0 or bounds.height <= 0:
            raise SelectorResolutionError("Popup candidate bounds must be positive.", bounds=bounds)
        if bounds.x < 0 or bounds.y < 0 or bounds.x + bounds.width > image_width or bounds.y + bounds.height > image_height:
            raise SelectorResolutionError(
                "Popup candidate bounds must remain inside the captured image.",
                bounds=bounds,
                image_size=image_size,
            )
        point_x, point_y = self.action_point
        if not bounds.x <= point_x < bounds.x + bounds.width or not bounds.y <= point_y < bounds.y + bounds.height:
            raise SelectorResolutionError(
                "Popup candidate action point must lie inside its measured bounds.",
                action_point=self.action_point,
                bounds=bounds,
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise SelectorResolutionError("Popup candidate confidence must be between 0 and 1.", confidence=self.confidence)


@dataclass(frozen=True, slots=True)
class PopupOverlayObservation:
    """Measured popup ownership and ordered descriptive control candidates."""

    image_size: tuple[int, int]
    modal_bounds: Bounds | None = None
    layout_id: str | None = None
    candidates: tuple[PopupDismissCandidate, ...] = ()
    confidence: float = 0.0
    evidence_kind: PopupEvidenceKind = PopupEvidenceKind.KNOWN_LAYOUT
    reason: str | None = None

    def __post_init__(self) -> None:
        """Validate the evidence contract before downstream consumers use it."""

        image_width, image_height = self.image_size
        if image_width <= 0 or image_height <= 0:
            raise SelectorResolutionError("Popup evidence requires a positive image size.", image_size=self.image_size)
        if not 0.0 <= self.confidence <= 1.0:
            raise SelectorResolutionError("Popup overlay confidence must be between 0 and 1.", confidence=self.confidence)
        if self.modal_bounds is not None:
            modal = self.modal_bounds
            if modal.width <= 0 or modal.height <= 0:
                raise SelectorResolutionError("Popup modal bounds must be positive.", modal_bounds=modal)
            if modal.x < 0 or modal.y < 0 or modal.x + modal.width > image_width or modal.y + modal.height > image_height:
                raise SelectorResolutionError(
                    "Popup modal bounds must remain inside the captured image.",
                    modal_bounds=modal,
                    image_size=self.image_size,
                )
        if self.layout_id is not None and self.layout_id.startswith("generic_") and self.modal_bounds is None:
            raise SelectorResolutionError(
                "Generic popup evidence requires measured modal ownership.",
                layout_id=self.layout_id,
            )
        seen: set[tuple[PopupControlKind, Bounds, tuple[int, int]]] = set()
        for candidate in self.candidates:
            candidate.validate(image_size=self.image_size)
            if self.layout_id is not None and self.layout_id.startswith("generic_"):
                assert self.modal_bounds is not None
                point_x, point_y = candidate.action_point
                modal = self.modal_bounds
                if not (
                    modal.x <= point_x < modal.x + modal.width
                    and modal.y <= point_y < modal.y + modal.height
                ):
                    raise SelectorResolutionError(
                        "Generic popup candidates must belong to the measured modal.",
                        layout_id=self.layout_id,
                        action_point=candidate.action_point,
                        modal_bounds=modal,
                    )
            key = (candidate.control_kind, candidate.bounds, candidate.action_point)
            if key in seen:
                raise SelectorResolutionError(
                    "Popup evidence contains duplicate indistinguishable candidates.",
                    candidate=key,
                )
            seen.add(key)

    @property
    def blocking(self) -> bool:
        """Whether this evidence represents a popup, even when no safe control exists."""

        return True

    def candidate(self, control_kind: PopupControlKind) -> PopupDismissCandidate | None:
        """Return the first candidate of one semantic kind, if present."""

        return next((candidate for candidate in self.candidates if candidate.control_kind == control_kind), None)


def preferred_transient_popup_candidate(
    overlay: PopupOverlayObservation,
) -> PopupDismissCandidate | None:
    """Return the highest-priority safe transient control described by perception."""

    for kind in SAFE_TRANSIENT_POPUP_CONTROL_KINDS:
        candidate = overlay.candidate(kind)
        if candidate is not None:
            return candidate
    return None
