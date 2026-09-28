"""Swipe and native wheel input."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry

import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.read_only_policy import ReadOnlyProbePolicy
from pnc_automation.app.pnc.domain.action_requests import (
    SwipeGesturePrimitive,
    SwipeAction,
    SwipeInputSource,
    SwipePurpose,
    TapSpatialObjectAction,
    WheelAction,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    SpatialObjectKind,
    SpatialObjectSourceKind,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import (
    DeviceConnectionError,
    FrameProvenanceError,
    SelectorResolutionError,
)
from pnc_automation.core.infra.emulator.input_dispatch import (
    InputDispatchFailure,
    InputDispatchRecord,
    SwipeDispatch,
    TapDispatch,
    WheelDispatch,
)
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.infra.emulator.scroll_transport import SCROLL_TRANSPORT_NAME

from tests.support.automation.session import FakeSession
from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.pnc.mail.mail_workflow_fixtures import MailWorkflowFixtures


class SwipeInputTests(MailWorkflowFixtures, unittest.TestCase):
    """Proves swipe input."""

    def test_action_executor_uses_explicit_swipe_ratios_when_present(self) -> None:
        """Resolves selector-independent swipe geometry from explicit normalized start/end ratios when provided."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="down",
                start_x_ratio=0.5,
                start_y_ratio=0.25,
                end_x_ratio=0.5,
                end_y_ratio=0.75,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(executor.session.swipes, [(100, 25, 100, 75, 500)])

    def test_action_executor_preserves_swipe_input_source(self) -> None:
        """Forwards the requested swipe input source so profile-level gesture calibration survives execution."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="right",
                input_source=SwipeInputSource.DEFAULT,
                start_x_ratio=0.4,
                start_y_ratio=0.5,
                end_x_ratio=0.6,
                end_y_ratio=0.5,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(executor.session.swipe_input_sources, [SwipeInputSource.DEFAULT])

    def test_action_executor_preserves_swipe_gesture_primitive(self) -> None:
        """Forwards the requested drag primitive so callers can opt into motion-event gestures."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
        )

        executor.execute_action(
            SwipeAction(
                direction="right",
                gesture_primitive=SwipeGesturePrimitive.PRESS_MOVE_RELEASE,
                start_x_ratio=0.4,
                start_y_ratio=0.5,
                end_x_ratio=0.6,
                end_y_ratio=0.5,
                duration_ms=500,
            ),
            make_observation(ScreenType.PNC_ALLIANCE_MEMBER_LIST),
        )

        self.assertEqual(
            executor.session.swipe_gesture_primitives,
            [SwipeGesturePrimitive.PRESS_MOVE_RELEASE],
        )

    def _make_executor(
        self,
        *,
        session: FakeSession | None = None,
        records: list[object] | None = None,
        read_only_policy: ReadOnlyProbePolicy = ReadOnlyProbePolicy(),
    ) -> ActionExecutor:
        """Builds one executor wired to a synthetic session and optional dispatch recorder."""

        return ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=session or FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=self.logger,
            sleep=lambda _: None,
            read_only_policy=read_only_policy,
            input_dispatch_recorder=None if records is None else records.append,
        )

    def test_action_executor_prepares_transport_and_dispatches_one_signed_wheel_detent(self) -> None:
        """Sends exactly one signed wheel detent through the lazily prepared control transport."""

        session = FakeSession()
        executor = self._make_executor(session=session)

        executor.execute_action(
            WheelAction(x=64, y=40, vertical_detent=-1),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(1, session.wheel_prepares)
        self.assertEqual([(64, 40, -1, (200, 100))], session.wheel_calls)

    def test_action_executor_records_actual_wheel_dispatch_receipt(self) -> None:
        """Publishes the transport's dispatch receipt bound to the authorizing frame."""

        records: list[object] = []
        session = FakeSession()
        executor = self._make_executor(session=session, records=records)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        executor.execute_action(WheelAction(x=64, y=40, vertical_detent=-1), observation)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, InputDispatchRecord)
        assert isinstance(record, InputDispatchRecord)
        self.assertEqual(observation.frame_ref, record.source_frame)
        self.assertIsInstance(record.dispatch, WheelDispatch)
        assert isinstance(record.dispatch, WheelDispatch)
        self.assertEqual((64, 40), record.dispatch.point)
        self.assertEqual((200, 100), record.dispatch.frame_size)
        self.assertEqual(-1, record.dispatch.vertical_detent)
        self.assertEqual(SCROLL_TRANSPORT_NAME, record.dispatch.transport)
        self.assertEqual(1, record.dispatch.input_sequence)
        self.assertTrue(record.home_city)

    def test_action_executor_records_wheel_dispatch_failure_phase(self) -> None:
        """Publishes the transport send failure phase instead of a false success receipt."""

        records: list[object] = []
        session = FakeSession(
            wheel_send_error=DeviceConnectionError("wheel send failed", failure_phase="dispatch"),
        )
        executor = self._make_executor(session=session, records=records)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        with self.assertRaises(DeviceConnectionError):
            executor.execute_action(WheelAction(x=64, y=40, vertical_detent=-1), observation)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, InputDispatchFailure)
        assert isinstance(record, InputDispatchFailure)
        self.assertEqual("wheel", record.input_kind)
        self.assertEqual("dispatch", record.failure_phase)
        self.assertEqual("DeviceConnectionError", record.exception_type)
        self.assertEqual(observation.frame_ref, record.source_frame)
        self.assertTrue(record.home_city)

    def test_action_executor_records_wheel_prepare_failure_phase(self) -> None:
        """Publishes the bounded setup failure phase when transport preparation stops."""

        records: list[object] = []
        session = FakeSession(
            wheel_prepare_error=DeviceConnectionError("transport setup failed", failure_phase="setup"),
        )
        executor = self._make_executor(session=session, records=records)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        with self.assertRaises(DeviceConnectionError):
            executor.execute_action(WheelAction(x=64, y=40, vertical_detent=-1), observation)

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, InputDispatchFailure)
        assert isinstance(record, InputDispatchFailure)
        self.assertEqual("wheel", record.input_kind)
        self.assertEqual("setup", record.failure_phase)
        self.assertEqual("DeviceConnectionError", record.exception_type)
        self.assertEqual(observation.frame_ref, record.source_frame)
        self.assertTrue(record.home_city)
        self.assertEqual([], session.wheel_calls)

    def test_action_executor_wheel_frame_expiry_at_send_emits_failure_not_receipt(self) -> None:
        """Emits the send-boundary provenance failure instead of a dispatch receipt."""

        records: list[object] = []
        session = FakeSession(
            wheel_send_error=FrameProvenanceError(
                "Action proof exceeded the bounded frame age policy.",
                age_seconds=31.0,
                max_age_seconds=30.0,
            ),
        )
        executor = self._make_executor(session=session, records=records)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        with self.assertRaises(SelectorResolutionError) as context:
            executor.execute_action(WheelAction(x=64, y=40, vertical_detent=-1), observation)

        self.assertEqual("FrameProvenanceError", context.exception.details["provenance_error_type"])
        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, InputDispatchFailure)
        assert isinstance(record, InputDispatchFailure)
        self.assertEqual("wheel", record.input_kind)
        self.assertEqual("dispatch", record.failure_phase)
        self.assertEqual("FrameProvenanceError", record.exception_type)
        self.assertEqual(observation.frame_ref, record.source_frame)
        self.assertTrue(record.home_city)

    def test_wheel_action_accepts_only_integer_signed_detents(self) -> None:
        """Rejects bool/float lookalikes and accepts exactly +/-1 at construction."""

        WheelAction(x=64, y=40, vertical_detent=1)
        WheelAction(x=64, y=40, vertical_detent=-1)
        for detent in (True, False, 1.0, -1.0, 0, 2, "1"):
            with self.subTest(detent=detent), self.assertRaises(SelectorResolutionError):
                WheelAction(x=64, y=40, vertical_detent=detent)

    def test_action_executor_wheel_requires_explicit_read_only_wheel_authorization(self) -> None:
        """Rejects wheel input unless the read-only policy explicitly allowlists the wheel screen."""

        for policy in (
            ReadOnlyProbePolicy(enabled=True),
            ReadOnlyProbePolicy(
                enabled=True,
                allow_swipe=True,
                allowed_swipe_screens=frozenset({ScreenType.PNC_HOME_CITY}),
            ),
        ):
            with self.subTest(policy=policy):
                session = FakeSession()
                executor = self._make_executor(session=session, read_only_policy=policy)

                with self.assertRaises(SelectorResolutionError) as context:
                    executor.execute_action(
                        WheelAction(x=64, y=40, vertical_detent=-1),
                        make_observation(ScreenType.PNC_HOME_CITY),
                    )

                self.assertEqual("WheelAction", context.exception.details["action_type"])
                self.assertEqual(0, session.wheel_prepares)
                self.assertEqual([], session.wheel_calls)

    def test_action_executor_wheel_dispatch_under_explicit_read_only_wheel_authorization(self) -> None:
        """Allows one signed wheel detent when the policy allowlists the wheel screen."""

        session = FakeSession()
        executor = self._make_executor(
            session=session,
            read_only_policy=ReadOnlyProbePolicy(
                enabled=True,
                allow_wheel=True,
                allowed_wheel_screens=frozenset({ScreenType.PNC_HOME_CITY}),
            ),
        )

        executor.execute_action(
            WheelAction(x=64, y=40, vertical_detent=-1),
            make_observation(ScreenType.PNC_HOME_CITY),
        )

        self.assertEqual(1, session.wheel_prepares)
        self.assertEqual([(64, 40, -1, (200, 100))], session.wheel_calls)

    def test_action_executor_forwards_exact_home_city_swipe(self) -> None:
        """Carries reviewed exact geometry and safe bounds into one Home camera swipe."""

        records: list[object] = []
        session = FakeSession()
        executor = self._make_executor(session=session, records=records)
        safe_bounds = Bounds(x=90, y=20, width=20, height=60)
        observation = make_observation(ScreenType.PNC_HOME_CITY)

        executor.execute_action(
            SwipeAction(
                direction="right",
                purpose=SwipePurpose.HOME_CITY_CAMERA,
                start_x_ratio=0.5,
                start_y_ratio=0.25,
                end_x_ratio=0.5,
                end_y_ratio=0.75,
                duration_ms=400,
                exact_geometry=True,
                safe_bounds=safe_bounds,
            ),
            observation,
        )

        self.assertEqual([(100, 25, 100, 75, 400)], session.swipes)
        self.assertEqual([True], session.swipe_exact_geometry)
        self.assertEqual([safe_bounds], session.swipe_safe_bounds)
        self.assertEqual(1, len(records))
        record = records[0]
        assert isinstance(record, InputDispatchRecord)
        self.assertIsInstance(record.dispatch, SwipeDispatch)
        self.assertTrue(record.home_city)

    def test_action_executor_requires_exact_geometry_for_home_city_swipe(self) -> None:
        """Rejects Home camera swipes that lack reviewed exact geometry or safe bounds."""

        session = FakeSession()
        executor = self._make_executor(session=session)
        observation = make_observation(ScreenType.PNC_HOME_CITY)
        swipe = SwipeAction(
            direction="right",
            purpose=SwipePurpose.HOME_CITY_CAMERA,
            start_x_ratio=0.5,
            start_y_ratio=0.25,
            end_x_ratio=0.5,
            end_y_ratio=0.75,
            duration_ms=400,
            safe_bounds=Bounds(x=90, y=20, width=20, height=60),
        )

        with self.assertRaisesRegex(SelectorResolutionError, "exact geometry"):
            executor.execute_action(swipe, observation)
        with self.assertRaisesRegex(SelectorResolutionError, "safe bounds"):
            executor.execute_action(replace(swipe, exact_geometry=True, safe_bounds=None), observation)

        self.assertEqual([], session.swipes)

    def test_action_executor_forwards_exact_spatial_tap(self) -> None:
        """Dispatches one explicitly authorized building tap with policy enabled."""

        records: list[object] = []
        session = FakeSession()
        policy = ReadOnlyProbePolicy(
            enabled=True,
            allowed_home_buildings=frozenset({HomeCityObjectId.CAMPAIGN}),
        )
        executor = self._make_executor(session=session, records=records, read_only_policy=policy)
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
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(expected_object,),
            ),
            frame_ref=frame_ref,
        )

        executor.execute_action(
            TapSpatialObjectAction(
                target_point=(50, 50),
                expected_object=expected_object,
                exact_geometry=True,
            ),
            observation,
        )

        self.assertEqual([(50, 50)], session.taps)
        self.assertEqual([True], session.tap_exact_geometry)
        self.assertEqual([expected_object.action_bounds], session.tap_safe_bounds)
        self.assertEqual(1, len(records))
        record = records[0]
        assert isinstance(record, InputDispatchRecord)
        self.assertIsInstance(record.dispatch, TapDispatch)
        assert isinstance(record.dispatch, TapDispatch)
        self.assertEqual((50, 50), record.dispatch.point)
        self.assertTrue(record.home_city)
        self.assertIs(policy, executor.read_only_policy)

    def test_building_probe_permission_is_explicit_and_target_scoped(self) -> None:
        body = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": HomeCityObjectId.CAMPAIGN.value},
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE, objects=(body,)),
        )
        action = TapSpatialObjectAction(target_point=body.action_point, expected_object=body, exact_geometry=True)
        for policy in (
            ReadOnlyProbePolicy(enabled=True),
            ReadOnlyProbePolicy(enabled=True, allowed_home_buildings=frozenset({HomeCityObjectId.ILLUSORY_BEAST_MANOR})),
        ):
            with self.subTest(policy=policy), self.assertRaises(SelectorResolutionError):
                policy.validate(action, observation)

    def test_building_probe_permission_does_not_authorize_unverified_spatial_input(self) -> None:
        policy = ReadOnlyProbePolicy(enabled=True, allowed_home_buildings=frozenset({HomeCityObjectId.CAMPAIGN}))
        body = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            metadata={"home_city_object_id": HomeCityObjectId.CAMPAIGN.value},
        )
        surface = make_spatial_surface(SpatialSurfaceType.HOME_CITY_SURFACE, objects=(body,))
        observation = make_observation(ScreenType.PNC_HOME_CITY, spatial_surface=surface)
        action = TapSpatialObjectAction(target_point=body.action_point, expected_object=body, exact_geometry=True)
        cases = (
            (replace(action, exact_geometry=False), observation),
            (TapSpatialObjectAction(target_point=(50, 50)), observation),
            (action, make_observation(ScreenType.PNC_BAG, spatial_surface=surface)),
            (action, make_observation(ScreenType.PNC_HOME_CITY)),
            (action, make_observation(ScreenType.PNC_HOME_CITY, spatial_surface=make_spatial_surface(SpatialSurfaceType.WORLD_MAP))),
            (replace(action, expected_object=replace(body, source_kind=SpatialObjectSourceKind.OCR)), observation),
            (replace(action, expected_object=replace(body, metadata={})), observation),
        )
        for candidate, source in cases:
            with self.subTest(action=candidate, screen=source.screen_type), self.assertRaises(SelectorResolutionError):
                policy.validate(candidate, source)

    def test_building_probe_allowlist_retains_executor_current_object_validation(self) -> None:
        session = FakeSession()
        executor = self._make_executor(session=session, read_only_policy=ReadOnlyProbePolicy(
            enabled=True, allowed_home_buildings=frozenset({HomeCityObjectId.CAMPAIGN}),
        ))
        body = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING),
            source_kind=SpatialObjectSourceKind.TEMPLATE,
            action_bounds=Bounds(45, 45, 10, 10),
            metadata={"home_city_object_id": HomeCityObjectId.CAMPAIGN.value},
        )
        observation = make_observation(ScreenType.PNC_HOME_CITY, spatial_surface=make_spatial_surface(
            SpatialSurfaceType.HOME_CITY_SURFACE, objects=(),
        ))
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(TapSpatialObjectAction(
                target_point=(50, 50), expected_object=body, exact_geometry=True,
            ), observation)
        self.assertEqual([], session.taps)

    def test_action_executor_rejects_exact_spatial_tap_without_action_bounds(self) -> None:
        """Rejects exact body taps when the observed object lacks nonempty action bounds."""

        session = FakeSession()
        executor = self._make_executor(session=session)
        frame_ref = FrameRef(
            session_id="synthetic-test-session",
            session_epoch=1,
            capture_sequence=8,
            input_sequence=0,
            captured_at=datetime.now(tz=UTC),
        )
        expected_object = replace(
            make_spatial_object(SpatialObjectKind.HOME_BUILDING, action_point=(50, 50)),
            frame_ref=frame_ref,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(expected_object,),
            ),
            frame_ref=frame_ref,
        )

        with self.assertRaisesRegex(SelectorResolutionError, "action bounds"):
            executor.execute_action(
                TapSpatialObjectAction(
                    target_point=(50, 50),
                    expected_object=expected_object,
                    exact_geometry=True,
                ),
                observation,
            )

        self.assertEqual([], session.taps)
