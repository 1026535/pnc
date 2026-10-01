"""Canonical tap send/receipt boundary shared by every tap variant."""

from __future__ import annotations

import unittest
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import NamedTuple

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.pnc.domain.action_requests import (
    ActionRequest,
    InputTextAction,
    SelectChatChannelAction,
    TapAction,
    TapListEntryAction,
    TapPointAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.chat import ChatChannel
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    ListEntryKind,
    Observation,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectSourceKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import DeviceConnectionError, SelectorResolutionError
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchFailure,
    InputDispatchRecord,
    TapDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_entry, make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface


class _TapCase(NamedTuple):
    """One tap variant with its authorizing observation and expected send geometry."""

    action: ActionRequest
    observation: Observation
    expected_point: tuple[int, int]
    home_city: bool = False
    read_only_policy: ReadOnlyProbePolicy = ReadOnlyProbePolicy()
    expected_texts: tuple[str, ...] = ()
    expected_safe_bounds: Bounds | None = None


def _tap_cases() -> dict[str, Callable[[], _TapCase]]:
    """Returns one fresh case builder per tap variant so each run owns its frame."""

    def spatial_exact() -> _TapCase:
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_home_buildings=frozenset({HomeCityObjectId.CAMPAIGN}),
        )
        frame_ref = FrameRef(
            session_id="synthetic-test-session",
            session_epoch=1,
            capture_sequence=7,
            input_sequence=0,
            captured_at=datetime.now(tz=UTC),
        )
        expected_object = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING, action_point=(50, 50)),
            action_bounds=Bounds(x=45, y=45, width=10, height=10),
            frame_ref=frame_ref,
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": HomeCityObjectId.CAMPAIGN.value},
        )
        return _TapCase(
            action=TapSpatialObjectAction(
                target_point=(50, 50),
                expected_object=expected_object,
                exact_geometry=True,
            ),
            observation=make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(expected_object,),
                ),
                frame_ref=frame_ref,
            ),
            expected_point=(50, 50),
            home_city=True,
            read_only_policy=policy,
            expected_safe_bounds=expected_object.action_bounds,
        )

    return {
        "tap_action": lambda: _TapCase(
            action=TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_BAG),
            observation=make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_BAG,),
            ),
            expected_point=(5, 5),
        ),
        "tap_point": lambda: _TapCase(
            action=TapPointAction(x=10, y=20),
            observation=make_observation(ScreenType.PNC_HOME_CITY),
            expected_point=(10, 20),
        ),
        "tap_list_entry": lambda: _TapCase(
            action=TapListEntryAction(entry_kind=ListEntryKind.CASTLE, use_action_point=True),
            observation=make_observation(
                ScreenType.PNC_HOME_CITY,
                list_entries=(make_entry(ListEntryKind.CASTLE, title="Castle"),),
            ),
            expected_point=(50, 50),
        ),
        "tap_spatial_object": lambda: _TapCase(
            action=TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                ),
            ),
            observation=make_observation(
                ScreenType.PNC_HOME_CITY,
                spatial_surface=make_spatial_surface(
                    SpatialSurfaceType.HOME_CITY_SURFACE,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.HOME_BUILDING,
                            name_text="Castle",
                            action_point=(30, 30),
                        ),
                    ),
                ),
            ),
            expected_point=(30, 30),
        ),
        "tap_spatial_object_exact": spatial_exact,
        "select_chat_channel": lambda: _TapCase(
            action=SelectChatChannelAction(channel=ChatChannel.ALLIANCE),
            observation=make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_TAB_ALLIANCE,),
                active_chat_channel=ChatChannel.WORLD,
            ),
            expected_point=(5, 5),
        ),
        "input_text_focus": lambda: _TapCase(
            action=InputTextAction(selector_id=UiElementId.PNC_CHAT_INPUT_FIELD, text="hello"),
            observation=make_observation(
                ScreenType.PNC_CHAT,
                visible_ids=(UiElementId.PNC_CHAT_INPUT_FIELD,),
            ),
            expected_point=(5, 5),
            expected_texts=("hello",),
        ),
    }


class TapDispatchReceiptTests(unittest.TestCase):
    """Proves every tap variant shares one send/receipt exception boundary."""

    def _make_executor(
        self,
        *,
        session: FakeSession,
        records: list[object] | None = None,
        read_only_policy: ReadOnlyProbePolicy = ReadOnlyProbePolicy(),
    ) -> ActionExecutor:
        """Builds one executor wired to a synthetic session and optional dispatch recorder."""

        return ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session,
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
            read_only_policy=read_only_policy,
            input_dispatch_recorder=None if records is None else records.append,
        )

    def test_tap_send_failure_emits_one_typed_failure_receipt(self) -> None:
        """Each tap variant emits exactly one dispatch failure and preserves the send error."""

        for name, build in _tap_cases().items():
            with self.subTest(variant=name):
                case = build()
                session = FakeSession(
                    tap_error=DeviceConnectionError("tap send failed", failure_phase="dispatch"),
                )
                records: list[object] = []
                executor = self._make_executor(
                    session=session,
                    records=records,
                    read_only_policy=case.read_only_policy,
                )

                with self.assertRaises(DeviceConnectionError):
                    executor.execute_action(case.action, case.observation)

                self.assertEqual([case.expected_point], session.taps)
                if case.expected_safe_bounds is not None:
                    self.assertEqual([True], session.tap_exact_geometry)
                    self.assertEqual([case.expected_safe_bounds], session.tap_safe_bounds)
                self.assertEqual([], session.texts)
                self.assertEqual(1, len(records))
                record = records[0]
                self.assertIsInstance(record, InputDispatchFailure)
                assert isinstance(record, InputDispatchFailure)
                self.assertEqual("tap", record.input_kind)
                self.assertEqual("dispatch", record.failure_phase)
                self.assertEqual("DeviceConnectionError", record.exception_type)
                self.assertEqual(case.observation.frame_ref, record.source_frame)
                self.assertEqual(case.home_city, record.home_city)

    def test_tap_send_emits_one_dispatch_receipt_after_send(self) -> None:
        """Each tap variant publishes the backend's dispatch receipt bound to its frame."""

        for name, build in _tap_cases().items():
            with self.subTest(variant=name):
                case = build()
                session = FakeSession()
                records: list[object] = []
                executor = self._make_executor(
                    session=session,
                    records=records,
                    read_only_policy=case.read_only_policy,
                )

                executor.execute_action(case.action, case.observation)

                self.assertEqual([case.expected_point], session.taps)
                self.assertEqual(list(case.expected_texts), session.texts)
                self.assertEqual(1, len(records))
                record = records[0]
                self.assertIsInstance(record, InputDispatchRecord)
                assert isinstance(record, InputDispatchRecord)
                self.assertEqual(case.observation.frame_ref, record.source_frame)
                self.assertIsInstance(record.dispatch, TapDispatch)
                assert isinstance(record.dispatch, TapDispatch)
                self.assertEqual(case.expected_point, record.dispatch.point)
                self.assertEqual(1, record.dispatch.input_sequence)
                self.assertEqual(case.home_city, record.home_city)

    def test_tap_send_failure_stays_primary_when_failure_reporting_also_fails(self) -> None:
        """The send error surfaces with the reporting error preserved as its cause."""

        report_error = RuntimeError("receipt publish failed")
        send_error = DeviceConnectionError("tap send failed", failure_phase="dispatch")

        def recorder(_event: object) -> None:
            raise report_error

        session = FakeSession(tap_error=send_error)
        executor = self._make_executor(session=session)
        executor.input_dispatch_recorder = recorder
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        with self.assertRaises(DeviceConnectionError) as raised:
            executor.execute_action(TapPointAction(x=10, y=20), observation)

        self.assertIs(send_error, raised.exception)
        self.assertIs(report_error, raised.exception.__cause__)
        self.assertEqual([(10, 20)], session.taps)

    def test_post_send_receipt_failure_does_not_report_failure_or_replay(self) -> None:
        """A successful-send reporting failure cannot fabricate a failure event or a second tap."""

        events: list[object] = []
        publish_error = RuntimeError("receipt publish failed")

        def recorder(event: object) -> None:
            events.append(event)
            raise publish_error

        session = FakeSession()
        executor = self._make_executor(session=session)
        executor.input_dispatch_recorder = recorder
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        with self.assertRaises(RuntimeError) as raised:
            executor.execute_action(TapPointAction(x=10, y=20), observation)

        self.assertIs(publish_error, raised.exception)
        self.assertEqual([(10, 20)], session.taps)
        self.assertEqual(1, len(events))
        self.assertIsInstance(events[0], InputDispatchRecord)
        self.assertFalse(any(isinstance(event, InputDispatchFailure) for event in events))

    def test_rejected_frame_provenance_sends_no_tap(self) -> None:
        """Replaying one consumed frame refuses the second send before any tap reaches the session."""

        session = FakeSession()
        records: list[object] = []
        executor = self._make_executor(session=session, records=records)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        executor.execute_action(TapPointAction(x=10, y=20), observation)
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(TapPointAction(x=30, y=40), observation)

        self.assertEqual([(10, 20)], session.taps)
        self.assertEqual(1, len(records))
        self.assertIsInstance(records[0], InputDispatchRecord)
        self.assertFalse(any(isinstance(event, InputDispatchFailure) for event in records))
