"""Bounded replacement-core Kingdom Chat send navigation tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import unittest

from pnc_automation.app.automation.engine.navigation_core import NavigationCore, NavigationPolicy, reviewed_navigation_edges
from pnc_automation.app.pnc.domain.action_requests import InputTextAction, SelectChatChannelAction, TapAction
from pnc_automation.app.pnc.domain.castles import CastleIdentity
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import DetectedListEntry, ListEntryKind, VisibleElementSourceKind
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from tests.support.pnc.observations import make_entry, make_observation


class _Actuator:
    def __init__(self) -> None:
        self.actions = []

    def execute_action(self, action, observation) -> bool:
        self.actions.append(action)
        return True


class _SubmitRaisingActuator(_Actuator):
    """Raises at the single submit tap to prove the core does not replay it."""

    def execute_action(self, action, observation) -> bool:
        super().execute_action(action, observation)
        if isinstance(action, TapAction) and action.selector_id == UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON:
            raise RuntimeError("submit actuator failed")
        return True


def _entry(*, sender: str = "[NAX] freecookies", message: str = "hello", order: int = 0) -> DetectedListEntry:
    return make_entry(
        ListEntryKind.CHAT_MESSAGE,
        title=sender,
        metadata={
            "chat_entry_kind": "player",
            "message_text": message,
            "visible_order": order,
        },
    )


def _chat_frame(
    captured_at: datetime,
    *,
    kingdom_tab: bool = False,
    alliance_tab: bool = False,
    input_field: bool = False,
    focused_empty: bool = False,
    focused_send: bool = False,
    draft_empty: bool | None = True,
    draft_text: str | None = None,
    entries: tuple[DetectedListEntry, ...] = (),
    channel: ChatChannel | None = ChatChannel.WORLD,
    screen: ScreenType = ScreenType.PNC_CHAT,
):
    visible_ids = tuple(
        selector
        for selector, enabled in (
            (UiElementId.PNC_CHAT_TAB_KINGDOM, kingdom_tab),
            (UiElementId.PNC_CHAT_TAB_ALLIANCE, alliance_tab),
            (UiElementId.PNC_CHAT_INPUT_FIELD, input_field),
            (UiElementId.PNC_CHAT_FOCUSED_EMPTY_INPUT, focused_empty),
            (UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON, focused_send),
        )
        if enabled
    )
    return replace(make_observation(
        screen,
        visible_ids=visible_ids,
        active_chat_channel=channel,
        chat_draft_empty=draft_empty,
        chat_draft_text=draft_text,
        list_entries=entries,
        artifact_path=Path("chat.png"),
        image_size=(540, 960),
    ), captured_at=captured_at)


def _core(frames: tuple, actuator: _Actuator) -> NavigationCore:
    iterator = iter(frames)
    return NavigationCore(
        actuator,
        lambda _label: next(iterator),
        reviewed_navigation_edges(),
        NavigationPolicy(max_observations=4, poll_seconds=0, stable_observations=2),
        sleep=lambda _seconds: None,
    )


class KingdomChatSendNavigationTests(unittest.TestCase):
    """Verify one atomic observed focus, type, submit, and receipt sequence."""

    def test_send_focuses_types_and_submits_once_after_fresh_receipt(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        receipt = (_entry(),)
        frames = (
            _chat_frame(start, input_field=True),
            _chat_frame(start + timedelta(seconds=1), focused_empty=True, focused_send=True),
            _chat_frame(start + timedelta(seconds=2), focused_empty=True, focused_send=True),
            _chat_frame(start + timedelta(seconds=3), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=4), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=5), focused_send=True, entries=receipt),
            _chat_frame(start + timedelta(seconds=6), focused_send=True, entries=receipt),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)
        result = core.send_chat_message(
            ChatChannel.WORLD,
            "hello",
            CastleIdentity("K1", "free cookies"),
            observe_content=core.observe,
        )

        self.assertEqual(ScreenType.PNC_CHAT, result.screen_type)
        self.assertEqual(3, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapAction)
        self.assertEqual(UiElementId.PNC_CHAT_INPUT_FIELD, actuator.actions[0].selector_id)
        self.assertIsInstance(actuator.actions[1], InputTextAction)
        self.assertIsNone(actuator.actions[1].selector_id)
        self.assertFalse(actuator.actions[1].replace_existing)
        self.assertEqual("hello", actuator.actions[1].text)
        self.assertIsInstance(actuator.actions[2], TapAction)
        self.assertEqual(UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON, actuator.actions[2].selector_id)

    def test_send_supports_alliance_channel_through_the_same_observed_sequence(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        receipt = (_entry(),)
        frames = (
            _chat_frame(start, input_field=True, channel=ChatChannel.ALLIANCE),
            _chat_frame(
                start + timedelta(seconds=1),
                focused_empty=True,
                focused_send=True,
                channel=ChatChannel.ALLIANCE,
            ),
            _chat_frame(
                start + timedelta(seconds=2),
                focused_empty=True,
                focused_send=True,
                channel=ChatChannel.ALLIANCE,
            ),
            _chat_frame(
                start + timedelta(seconds=3),
                focused_send=True,
                draft_empty=False,
                draft_text="hello",
                channel=ChatChannel.ALLIANCE,
            ),
            _chat_frame(
                start + timedelta(seconds=4),
                focused_send=True,
                draft_empty=False,
                draft_text="hello",
                channel=ChatChannel.ALLIANCE,
            ),
            _chat_frame(
                start + timedelta(seconds=5),
                focused_send=True,
                entries=receipt,
                channel=ChatChannel.ALLIANCE,
            ),
            _chat_frame(
                start + timedelta(seconds=6),
                focused_send=True,
                entries=receipt,
                channel=ChatChannel.ALLIANCE,
            ),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)

        result = core.send_chat_message(
            ChatChannel.ALLIANCE,
            "hello",
            CastleIdentity("K1", "free cookies"),
            observe_content=core.observe,
        )

        self.assertEqual(ScreenType.PNC_CHAT, result.screen_type)
        self.assertEqual(3, len(actuator.actions))

    def test_send_switches_channel_only_after_empty_draft_guard(self) -> None:
        """Reacquires the requested channel after the initial no-draft proof."""

        start = datetime(2026, 9, 12, tzinfo=UTC)
        receipt = (_entry(),)
        tabs = {"kingdom_tab": True, "alliance_tab": True}
        frames = (
            _chat_frame(start, input_field=True, channel=ChatChannel.ALLIANCE, **tabs),
            _chat_frame(start + timedelta(seconds=1), input_field=True, channel=ChatChannel.ALLIANCE, **tabs),
            _chat_frame(start + timedelta(seconds=2), input_field=True, channel=ChatChannel.WORLD, **tabs),
            _chat_frame(start + timedelta(seconds=3), input_field=True, channel=ChatChannel.WORLD, **tabs),
            _chat_frame(start + timedelta(seconds=4), focused_empty=True, focused_send=True),
            _chat_frame(start + timedelta(seconds=5), focused_empty=True, focused_send=True),
            _chat_frame(start + timedelta(seconds=6), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=7), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=8), focused_send=True, entries=receipt),
            _chat_frame(start + timedelta(seconds=9), focused_send=True, entries=receipt),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)

        core.send_chat_message(
            ChatChannel.WORLD,
            "hello",
            CastleIdentity("K1", "free cookies"),
            observe_content=core.observe,
        )

        self.assertIsInstance(actuator.actions[0], SelectChatChannelAction)
        self.assertEqual(ChatChannel.WORLD, actuator.actions[0].channel)
        self.assertEqual(4, len(actuator.actions))

    def test_send_rejects_non_chat_channel_before_observing(self) -> None:
        actuator = _Actuator()
        core = _core((), actuator)

        with self.assertRaisesRegex(ValueError, "ChatChannel"):
            core.send_chat_message(
                "world",  # type: ignore[arg-type]
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual([], actuator.actions)

    def test_send_preserves_existing_or_unproven_draft_before_channel_selection(self) -> None:
        """A draft guard rejects both known and unknown emptiness without tapping a tab."""

        for draft_empty, expected in ((False, "not explicitly empty"), (None, "not explicitly empty")):
            with self.subTest(draft_empty=draft_empty):
                now = datetime(2026, 9, 12, tzinfo=UTC)
                source = _chat_frame(
                    now,
                    input_field=True,
                    draft_empty=draft_empty,
                    draft_text="existing" if draft_empty is False else None,
                    channel=ChatChannel.ALLIANCE,
                    kingdom_tab=True,
                    alliance_tab=True,
                )
                actuator = _Actuator()
                core = _core((source,), actuator)
                with self.assertRaisesRegex(RuntimeError, expected):
                    core.send_chat_message(
                        ChatChannel.WORLD,
                        "hello",
                        CastleIdentity("K1", "free cookies"),
                        observe_content=core.observe,
                    )
                self.assertEqual([], actuator.actions)

    def test_send_rejects_draft_reappearing_before_channel_selection(self) -> None:
        """The selection reacquisition cannot bypass the initial empty-draft safety guard."""

        start = datetime(2026, 9, 12, tzinfo=UTC)
        frames = (
            _chat_frame(
                start,
                input_field=True,
                channel=ChatChannel.ALLIANCE,
                kingdom_tab=True,
                alliance_tab=True,
            ),
            _chat_frame(
                start + timedelta(seconds=1),
                input_field=True,
                draft_empty=False,
                draft_text="existing",
                channel=ChatChannel.ALLIANCE,
                kingdom_tab=True,
                alliance_tab=True,
            ),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)

        with self.assertRaisesRegex(RuntimeError, "not explicitly empty"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual([], actuator.actions)

    def test_send_requires_positive_focused_empty_template_before_typing(self) -> None:
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = _chat_frame(now, focused_send=True, draft_empty=True)
        actuator = _Actuator()
        core = _core((source,), actuator)
        with self.assertRaisesRegex(RuntimeError, "positive template"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello", CastleIdentity("K1", "free cookies"), observe_content=core.observe
            )
        self.assertEqual([], actuator.actions)

    def test_send_does_not_type_when_focus_completion_has_ocr_empty_without_placeholder(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        frames = (
            _chat_frame(start, input_field=True),
            _chat_frame(start + timedelta(seconds=1), focused_send=True, draft_empty=True),
            _chat_frame(start + timedelta(seconds=2), focused_send=True, draft_empty=True),
            _chat_frame(start + timedelta(seconds=3), focused_send=True, draft_empty=True),
            _chat_frame(start + timedelta(seconds=4), focused_send=True, draft_empty=True),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello", CastleIdentity("K1", "free cookies"), observe_content=core.observe
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertFalse(any(isinstance(action, InputTextAction) for action in actuator.actions))

    def test_send_wrong_channel_or_stale_receipt_never_retypes_or_resubmits(self) -> None:
        now = datetime(2026, 9, 12, tzinfo=UTC)
        source = _chat_frame(now, focused_empty=True, focused_send=True)
        wrong = _chat_frame(now + timedelta(seconds=1), focused_send=True, draft_empty=True, channel=ChatChannel.ALLIANCE)
        stale = _chat_frame(now + timedelta(seconds=2), focused_send=True, draft_empty=True)
        actuator = _Actuator()
        core = _core((source, wrong), actuator)
        with self.assertRaisesRegex(RuntimeError, "wrong channel"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello", CastleIdentity("K1", "free cookies"), observe_content=core.observe
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], InputTextAction)

    def test_send_unknown_interruption_never_reaches_typing(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        frames = (
            _chat_frame(start, input_field=True),
            _chat_frame(start + timedelta(seconds=1), screen=ScreenType.UNKNOWN, channel=None),
            _chat_frame(start + timedelta(seconds=2), focused_empty=True, focused_send=True),
        )
        actuator = _Actuator()
        core = _core(frames, actuator)

        with self.assertRaisesRegex(RuntimeError, "unknown or loading"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapAction)
        self.assertFalse(any(isinstance(action, InputTextAction) for action in actuator.actions))

    def test_send_exact_draft_mismatch_never_submits(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        source = _chat_frame(start, focused_empty=True, focused_send=True)
        mismatch = tuple(
            _chat_frame(
                start + timedelta(seconds=index),
                focused_send=True,
                draft_empty=False,
                draft_text="hello!",
            )
            for index in range(1, 5)
        )
        actuator = _Actuator()
        core = _core((source, *mismatch), actuator)

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], InputTextAction)

    def test_send_missing_gold_control_never_reaches_typing(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        source = _chat_frame(start, input_field=True)
        focused_without_gold = tuple(
            _chat_frame(start + timedelta(seconds=index), focused_empty=True)
            for index in range(1, 5)
        )
        actuator = _Actuator()
        core = _core((source, *focused_without_gold), actuator)

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(1, len(actuator.actions))
        self.assertIsInstance(actuator.actions[0], TapAction)
        self.assertFalse(any(isinstance(action, InputTextAction) for action in actuator.actions))

    def test_send_submit_executor_exception_is_not_replayed(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        source = _chat_frame(start, focused_empty=True, focused_send=True)
        typed = (
            _chat_frame(start + timedelta(seconds=1), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=2), focused_send=True, draft_empty=False, draft_text="hello"),
        )
        actuator = _SubmitRaisingActuator()
        core = _core((source, *typed), actuator)

        with self.assertRaisesRegex(RuntimeError, "submit actuator failed"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(2, len(actuator.actions))
        self.assertEqual(1, sum(isinstance(action, InputTextAction) for action in actuator.actions))
        self.assertEqual(1, sum(
            isinstance(action, TapAction)
            and action.selector_id == UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON
            for action in actuator.actions
        ))

    def test_send_old_identical_receipt_after_submit_does_not_succeed_or_replay(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        old_receipt = (_entry(),)
        source = _chat_frame(start, focused_empty=True, focused_send=True, entries=old_receipt)
        typed = (
            _chat_frame(start + timedelta(seconds=1), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=2), focused_send=True, draft_empty=False, draft_text="hello"),
        )
        after_submit = tuple(
            _chat_frame(start + timedelta(seconds=index), focused_send=True, entries=old_receipt)
            for index in range(3, 7)
        )
        actuator = _Actuator()
        core = _core((source, *typed, *after_submit), actuator)

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(2, len(actuator.actions))
        self.assertEqual(1, sum(
            isinstance(action, TapAction)
            and action.selector_id == UiElementId.PNC_CHAT_FOCUSED_SEND_BUTTON
            for action in actuator.actions
        ))

    def test_send_rejects_other_sender_and_punctuation_variant_receipts(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        rows = (
            _entry(sender="other player"),
            _entry(message="hello!"),
        )
        source = _chat_frame(start, focused_empty=True, focused_send=True)
        typed = (
            _chat_frame(start + timedelta(seconds=1), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=2), focused_send=True, draft_empty=False, draft_text="hello"),
        )
        after_submit = tuple(
            _chat_frame(start + timedelta(seconds=index), focused_send=True, entries=rows)
            for index in range(3, 7)
        )
        actuator = _Actuator()
        core = _core((source, *typed, *after_submit), actuator)

        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            core.send_chat_message(
                ChatChannel.WORLD,
                "hello",
                CastleIdentity("K1", "free cookies"),
                observe_content=core.observe,
            )
        self.assertEqual(2, len(actuator.actions))

    def test_send_accepts_new_own_receipt_when_baseline_is_nonzero(self) -> None:
        start = datetime(2026, 9, 12, tzinfo=UTC)
        old_receipt = _entry(order=0)
        new_receipt = _entry(order=1)
        source = _chat_frame(start, focused_empty=True, focused_send=True, entries=(old_receipt,))
        typed = (
            _chat_frame(start + timedelta(seconds=1), focused_send=True, draft_empty=False, draft_text="hello"),
            _chat_frame(start + timedelta(seconds=2), focused_send=True, draft_empty=False, draft_text="hello"),
        )
        after_submit = (
            _chat_frame(start + timedelta(seconds=3), focused_send=True, entries=(old_receipt, new_receipt)),
            _chat_frame(start + timedelta(seconds=4), focused_send=True, entries=(old_receipt, new_receipt)),
        )
        actuator = _Actuator()
        core = _core((source, *typed, *after_submit), actuator)

        result = core.send_chat_message(
            ChatChannel.WORLD,
            "hello",
            CastleIdentity("K1", "free cookies"),
            observe_content=core.observe,
        )

        self.assertEqual(2, len(actuator.actions))
        self.assertEqual(2, len(result.entries(ListEntryKind.CHAT_MESSAGE)))


if __name__ == "__main__":
    unittest.main()
