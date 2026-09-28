"""Exact Home slot selection survives fresh captures and measured panning."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pnc_automation.app.automation.engine.core_workflow import WorkflowContext
from pnc_automation.app.automation.engine.navigation_core import (
    NavigationCore,
    NavigationEdge,
    NavigationPolicy,
)
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import Bounds, SpatialObjectSourceKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.spatial_navigation import plan_home_city_camera_pan
from pnc_automation.core.errors import SelectorResolutionError
from tests.support.pnc.navigation.core_frames import observation
from tests.support.pnc.navigation.core_home import (
    camera_home_frame,
    measured_building_object,
)


_NOW = datetime(2026, 9, 22, tzinfo=UTC)


def _body(slot: int, *, x: int = 200, y: int = 400, level: int = 1):
    return replace(
        measured_building_object(
            HomeCityObjectId.BLACKSMITH,
            bounds=Bounds(x - 20, y - 20, 40, 40),
            action_point=(x, y), action_bounds=Bounds(x - 5, y - 5, 10, 10),
        ),
        home_city_slot=HomeCitySlotSelector(slot), level=level,
    )


def _core():
    actions = []
    frames = iter(replace(
        observation(ScreenType.PNC_BLACKSMITH), captured_at=_NOW + timedelta(seconds=i),
    ) for i in (10, 11))
    core = NavigationCore(
        SimpleNamespace(execute_action=lambda action, before: actions.append(action) or True),
        lambda _: next(frames),
        (NavigationEdge(ScreenType.PNC_BLACKSMITH, UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
                        frozenset({ScreenType.PNC_HOME_CITY})),),
        NavigationPolicy(max_observations=4), sleep=lambda _: None,
    )
    return core, actions


class HomeCitySlotSelectionTests(unittest.TestCase):
    def test_exact_slot_overrides_other_visible_instances(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame((_body(11), _body(12, x=300)), captured_at=_NOW),
            camera_home_frame((_body(11), _body(12, x=300)), captured_at=_NOW + timedelta(seconds=1)),
        ))
        core.open_visible_building(
            HomeCityObjectId.BLACKSMITH, observe_content=lambda _: next(frames),
            home_city_slot=HomeCitySlotSelector(12),
        )
        self.assertEqual([(300, 400)], [a.target_point for a in actions])

    def test_generic_prefers_safe_then_stable_slot_not_highest_level(self):
        for bodies, expected in (
            ((_body(12, x=300, level=40), _body(11)), (200, 400)),
            ((_body(11, y=800), _body(12, x=300)), (300, 400)),
        ):
            with self.subTest(expected=expected):
                core, actions = _core()
                frames = iter((
                    camera_home_frame(bodies, captured_at=_NOW),
                    camera_home_frame(bodies, captured_at=_NOW + timedelta(seconds=1)),
                ))
                core.open_visible_building(
                    HomeCityObjectId.BLACKSMITH,
                    observe_content=lambda _: next(frames),
                )
                self.assertEqual(expected, actions[0].target_point)

    def test_conflicting_same_slot_is_still_ambiguous(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame((_body(12), _body(12, x=300)), captured_at=_NOW),
            camera_home_frame((_body(12), _body(12, x=300)), captured_at=_NOW + timedelta(seconds=1)),
        ))
        with self.assertRaisesRegex(RuntimeError, "ambiguous"):
            core.open_visible_building(
                HomeCityObjectId.BLACKSMITH,
                observe_content=lambda _: next(frames),
            )
        self.assertEqual([], actions)

    def test_incompatible_slot_rejected_before_observation(self):
        for method in ("open_building", "open_visible_building"):
            core, actions = _core()
            capture = Mock()
            with self.assertRaisesRegex(SelectorResolutionError, "cannot host"):
                getattr(core, method)(
                    HomeCityObjectId.BLACKSMITH, observe_content=capture,
                    home_city_slot=HomeCitySlotSelector(9),
                )
            capture.assert_not_called()
            self.assertEqual([], actions)

    def test_exact_slot_cannot_use_ocr_or_untagged_body(self):
        for body in (replace(_body(12), source_kind=SpatialObjectSourceKind.OCR),
                     replace(_body(12), home_city_slot=None)):
            core, actions = _core()
            frames = iter((
                camera_home_frame((body,), captured_at=_NOW),
                camera_home_frame((body,), captured_at=_NOW + timedelta(seconds=1)),
            ))
            with self.assertRaisesRegex(RuntimeError, "absent or ambiguous"):
                core.open_visible_building(
                    HomeCityObjectId.BLACKSMITH,
                    observe_content=lambda _: next(frames),
                    home_city_slot=HomeCitySlotSelector(12),
                )
            self.assertEqual([], actions)

    def test_generic_acquisition_pins_slot_during_reacquisition(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame((_body(12),), captured_at=_NOW),
            camera_home_frame((_body(12),), captured_at=_NOW + timedelta(seconds=1)),
            camera_home_frame((_body(13),), captured_at=_NOW + timedelta(seconds=2)),
        ))
        with self.assertRaisesRegex(RuntimeError, "absent or ambiguous"):
            core.open_building(
                HomeCityObjectId.BLACKSMITH, observe_content=lambda _: next(frames),
                on_target_acquired=lambda body: None,
            )
        self.assertEqual([], actions)

    def test_exact_reacquisition_uses_new_point_for_same_slot(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame((_body(12),), captured_at=_NOW),
            camera_home_frame((_body(12, x=300),), captured_at=_NOW + timedelta(seconds=1)),
        ))
        core.open_building(
            HomeCityObjectId.BLACKSMITH, observe_content=lambda _: next(frames),
            home_city_slot=HomeCitySlotSelector(12),
        )
        self.assertEqual([(300, 400)], [a.target_point for a in actions])

    def test_pan_uses_selected_slot_instead_of_other_visible_body(self):
        # Slot 12 projects below the band at this camera pose. A visible slot
        # 11 in the band must not cause a no-pan decision for a slot 12 request.
        action = plan_home_city_camera_pan(
            observation=camera_home_frame((_body(11),), translation=(-500, -240), zoom=.75,
                                          image_size=(900, 1600)),
            target=HomeCityObjectId.BLACKSMITH, home_city_slot=HomeCitySlotSelector(12),
        )
        self.assertEqual("up", action.direction)

    def test_workflow_context_forwards_exact_selector(self):
        runtime = Mock(observation_count=1)
        runtime.navigation.open_building.return_value = observation(ScreenType.PNC_BLACKSMITH)
        context = WorkflowContext(runtime, last_observation=camera_home_frame())
        selector = HomeCitySlotSelector(12)
        context.open_building(HomeCityObjectId.BLACKSMITH, home_city_slot=selector)
        self.assertEqual(selector, runtime.navigation.open_building.call_args.kwargs['home_city_slot'])
