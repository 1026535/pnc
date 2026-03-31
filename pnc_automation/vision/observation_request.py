"""Typed observation requests that control OCR-backed enrichment cost."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pnc_automation.pnc.mail import MailboxType, compose_text_field_selector_ids
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.pnc_ocr_capabilities import runtime_screen_family_ocr_types
from pnc_automation.vision.selectors import ClickOutcome


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    """Describes which OCR-backed fact families are allowed for one observation."""

    candidate_screen_types: frozenset[ScreenType] = frozenset()
    ocr_screen_types: frozenset[ScreenType] = frozenset()
    include_popup_guard: bool = False
    include_loading_guard: bool = False
    include_chat_state: bool = False
    include_chat_entries: bool = False
    text_field_selectors: frozenset[UiElementId] = frozenset()
    expected_mailbox: MailboxType | None = None
    persist_artifact: bool | None = None

    @classmethod
    def base(cls) -> "ObservationRequest":
        """Returns the cheap selector-and-geometry-only observation request."""

        return cls()

    @classmethod
    def full_runtime_default(cls) -> "ObservationRequest":
        """Returns the broad full-frame OCR request used for unattended runtime observations."""

        return cls(
            ocr_screen_types=runtime_screen_family_ocr_types(),
            include_popup_guard=True,
            include_loading_guard=True,
            include_chat_state=True,
            text_field_selectors=frozenset({UiElementId.PNC_CHAT_INPUT_FIELD}),
        )

    @classmethod
    def runtime_default(cls) -> "ObservationRequest":
        """Returns the legacy alias for the canonical full-frame runtime request."""

        return cls.full_runtime_default()

    @classmethod
    def navigation_follow_up(cls, reviewed_outcomes: Sequence[ClickOutcome]) -> "ObservationRequest":
        """Returns the narrow OCR scope used after one reviewed navigation tap."""

        target_screens = frozenset(
            outcome.target_screen
            for outcome in reviewed_outcomes
            if outcome.target_screen not in {None, ScreenType.PNC_LOADING, ScreenType.PNC_POPUP}
        )
        return cls(
            candidate_screen_types=target_screens,
            ocr_screen_types=target_screens,
            include_popup_guard=True,
            include_loading_guard=True,
            include_chat_state=ScreenType.PNC_CHAT in target_screens,
            text_field_selectors=(
                frozenset({UiElementId.PNC_CHAT_INPUT_FIELD})
                if ScreenType.PNC_CHAT in target_screens
                else frozenset(compose_text_field_selector_ids())
                if ScreenType.PNC_MAIL_COMPOSE_POPUP in target_screens
                else frozenset()
            ),
        )

    @classmethod
    def source_screen_retry(cls, screen_type: ScreenType) -> "ObservationRequest":
        """Returns the OCR scope used to re-resolve one selector on its source screen."""

        return cls(
            candidate_screen_types=frozenset({screen_type}),
            ocr_screen_types=frozenset({screen_type}),
            include_chat_state=screen_type == ScreenType.PNC_CHAT,
            text_field_selectors=(
                frozenset({UiElementId.PNC_CHAT_INPUT_FIELD})
                if screen_type == ScreenType.PNC_CHAT
                else frozenset(compose_text_field_selector_ids())
                if screen_type == ScreenType.PNC_MAIL_COMPOSE_POPUP
                else frozenset()
            ),
        )

    @classmethod
    def chat_send_follow_up(cls) -> "ObservationRequest":
        """Returns the narrow non-navigation follow-up used after sending one chat message."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_CHAT}),
            ocr_screen_types=frozenset({ScreenType.PNC_CHAT}),
            include_chat_state=True,
            text_field_selectors=frozenset({UiElementId.PNC_CHAT_INPUT_FIELD}),
        )

    @classmethod
    def build_queue_follow_up(cls) -> "ObservationRequest":
        """Returns the narrow OCR scope used while verifying one home-city build queue open attempt."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILD_QUEUE}),
            ocr_screen_types=frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_BUILD_QUEUE}),
            include_popup_guard=True,
            include_loading_guard=True,
        )

    @classmethod
    def chat_transcript_observation(cls) -> "ObservationRequest":
        """Returns the narrow OCR scope used for Kingdom Chat transcript polling."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_CHAT}),
            ocr_screen_types=frozenset({ScreenType.PNC_CHAT}),
            include_chat_state=True,
            include_chat_entries=True,
            text_field_selectors=frozenset({UiElementId.PNC_CHAT_INPUT_FIELD}),
        )

    @classmethod
    def home_city_follow_up(cls, *source_screens: ScreenType) -> "ObservationRequest":
        """Returns the narrow follow-up used while backing out toward the home-city root."""

        target_screens = frozenset({ScreenType.PNC_HOME_CITY, ScreenType.PNC_MORE_MENU, *source_screens})
        return cls(
            candidate_screen_types=target_screens,
            ocr_screen_types=target_screens,
            include_popup_guard=True,
            include_loading_guard=True,
        )

    @classmethod
    def mail_navigation_follow_up(cls, *screen_types: ScreenType) -> "ObservationRequest":
        """Returns the narrow OCR scope used after one mail-related navigation action."""

        target_screens = frozenset(
            screen_types
            or (
                ScreenType.PNC_MAIL_HUB,
                ScreenType.PNC_MAILBOX_LIST,
                ScreenType.PNC_MAIL_THREAD,
                ScreenType.PNC_MAIL_COMPOSE_POPUP,
                ScreenType.PNC_PLAYER_PROFILE,
                ScreenType.PNC_ALLIANCE_HOME,
            )
        )
        return cls(
            candidate_screen_types=target_screens,
            ocr_screen_types=target_screens,
            include_popup_guard=True,
            include_loading_guard=True,
            text_field_selectors=(
                frozenset(compose_text_field_selector_ids())
                if ScreenType.PNC_MAIL_COMPOSE_POPUP in target_screens
                else frozenset()
            ),
        )

    @classmethod
    def mailbox_observation(cls, mailbox: MailboxType) -> "ObservationRequest":
        """Returns the OCR scope used for one specific mailbox list observation."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_MAILBOX_LIST}),
            ocr_screen_types=frozenset({ScreenType.PNC_MAILBOX_LIST}),
            expected_mailbox=mailbox,
        )

    @classmethod
    def mail_thread_observation(cls) -> "ObservationRequest":
        """Returns the OCR scope used while reading one opened mail thread."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_MAIL_THREAD}),
            ocr_screen_types=frozenset({ScreenType.PNC_MAIL_THREAD}),
            persist_artifact=True,
        )

    @classmethod
    def mail_compose_follow_up(cls) -> "ObservationRequest":
        """Returns the OCR scope used for compose-popup verification and field-state reads."""

        return cls(
            candidate_screen_types=frozenset(
                {
                    ScreenType.PNC_MAIL_COMPOSE_POPUP,
                    ScreenType.PNC_ALLIANCE_HOME,
                    ScreenType.PNC_PLAYER_PROFILE,
                }
            ),
            ocr_screen_types=frozenset(
                {
                    ScreenType.PNC_MAIL_COMPOSE_POPUP,
                    ScreenType.PNC_ALLIANCE_HOME,
                    ScreenType.PNC_PLAYER_PROFILE,
                }
            ),
            text_field_selectors=frozenset(compose_text_field_selector_ids()),
        )

    @classmethod
    def player_profile_follow_up(cls) -> "ObservationRequest":
        """Returns the OCR scope used for remote player-profile verification."""

        return cls(
            candidate_screen_types=frozenset({ScreenType.PNC_PLAYER_PROFILE}),
            ocr_screen_types=frozenset({ScreenType.PNC_PLAYER_PROFILE}),
        )

    def requires_ocr(self, screen_type: ScreenType) -> bool:
        """Returns whether the request needs OCR for the current coarse screen state."""

        if self.include_popup_guard:
            return True
        if self.include_loading_guard and screen_type in {ScreenType.UNKNOWN, ScreenType.PNC_LOADING}:
            return True
        if screen_type == ScreenType.UNKNOWN:
            return bool(self.ocr_screen_types)
        return screen_type in self.ocr_screen_types

    def allows_screen(self, screen_type: ScreenType) -> bool:
        """Returns whether the request allows OCR builders for the requested screen family."""

        return screen_type in self.ocr_screen_types

    def allows_candidate_screen(self, screen_type: ScreenType) -> bool:
        """Returns whether the request allows cheap candidate-screen validators for one screen family."""

        return screen_type in self.candidate_screen_types
