"""Measured coverage and request-local occupancy never turn unknown into absent."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraProof, HomeCityCameraStatus
from pnc_automation.app.pnc.domain.home_city_slots import (
    HomeCitySlotOccupancy, HomeCitySlotOccupancyState, HomeCitySlotSelector, home_city_slot,
)
from pnc_automation.app.pnc.navigation.home_city_scan import (
    HomeCityCoverageRegion,
    HomeCityScanError,
    HomeCityScanState,
    HomeCityScanStopReason,
    projected_body_region,
)
from pnc_automation.app.pnc.navigation.spatial_navigation import plan_home_city_camera_step
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.vision.home_city_camera import home_city_camera_target
from tests.unit.app.pnc.navigation.test_home_city_slot_selection import _body, _core, _NOW
from tests.support.pnc.navigation.core_home import (
    camera_home_frame, home_building_frame, qualified_pan_step,
)


_BLACKSMITH = home_city_camera_target(HomeCityObjectId.BLACKSMITH)
_INSTITUTE = home_city_camera_target(HomeCityObjectId.INSTITUTE)


class HomeCityScanStateTests(unittest.TestCase):
    def test_duplicate_slot_claims_do_not_publish_arbitrary_occupancy(self):
        state = HomeCityScanState()
        region = projected_body_region(_BLACKSMITH, HomeCitySlotSelector(12))
        state.observe(camera_home_frame((_body(12), _body(12, x=300)), captured_at=_NOW),
                      targets=(_BLACKSMITH,), usable_region=region)
        self.assertIs(HomeCitySlotOccupancyState.UNKNOWN, state.occupancy[12].state)

    def test_region_inspection_without_match_stays_unknown(self):
        state = HomeCityScanState()
        slot = HomeCitySlotSelector(12)
        region = projected_body_region(_BLACKSMITH, slot)
        state.observe(camera_home_frame(captured_at=_NOW), targets=(_BLACKSMITH,),
                      usable_region=region)
        self.assertEqual({slot}, state.inspected_slots)
        self.assertIs(HomeCitySlotOccupancyState.UNKNOWN, state.occupancy[12].state)
        self.assertIsNone(state.occupancy[12].observed_object_id)
        result = state.result(HomeCityScanStopReason.NO_QUALIFIED_ROUTE)
        self.assertEqual(53, len(result.remaining_slots))
        self.assertIn(HomeCitySlotSelector(3), result.remaining_slots)

    def test_partial_body_visibility_is_terrain_coverage_not_slot_inspection(self):
        state = HomeCityScanState()
        region = projected_body_region(_BLACKSMITH, HomeCitySlotSelector(12))
        partial = replace(region, bottom=region.bottom - 10)
        self.assertTrue(state.observe(camera_home_frame(captured_at=_NOW),
                                      targets=(_BLACKSMITH,), usable_region=partial))
        self.assertTrue(state.coverage)
        self.assertEqual(set(), state.inspected_slots)
        self.assertEqual({}, state.occupancy)

    def test_repeated_body_and_animation_do_not_count_as_new_progress(self):
        state = HomeCityScanState()
        region = projected_body_region(_BLACKSMITH, HomeCitySlotSelector(12))
        first = camera_home_frame((_body(12),), captured_at=_NOW)
        self.assertTrue(state.observe(first, targets=(_BLACKSMITH,), usable_region=region))
        self.assertFalse(state.observe(
            replace(first, captured_at=_NOW + timedelta(seconds=1)),
            targets=(_BLACKSMITH,), usable_region=region,
        ))
        self.assertIs(HomeCitySlotOccupancyState.OCCUPIED, state.occupancy[12].state)

    def test_coverage_union_and_noise_do_not_keep_revisits_alive(self):
        state = HomeCityScanState(coverage=[
            HomeCityCoverageRegion(0, 0, 50, 100), HomeCityCoverageRegion(50, 0, 100, 100),
        ])
        for index, region in enumerate((HomeCityCoverageRegion(0, 0, 100, 100),
                                        HomeCityCoverageRegion(1, 1, 101, 101))):
            self.assertFalse(state.observe(
                camera_home_frame(captured_at=_NOW + timedelta(seconds=index)),
                targets=(), usable_region=region,
            ))

    def test_candidates_use_calibrated_distance_then_prior_compatible_hint(self):
        state = HomeCityScanState()
        pivot = home_city_slot(13).atlas_coordinate
        proof = camera_home_frame(translation=(450 - pivot.x, 800 - pivot.y)).spatial_surface.camera_proof
        self.assertEqual(HomeCitySlotSelector(13), state.candidate_slots(_BLACKSMITH, proof)[0])
        state.occupancy[12] = HomeCitySlotOccupancy(
            12, HomeCitySlotOccupancyState.OCCUPIED, HomeCityObjectId.BLACKSMITH, "prior request frame",
        )
        self.assertEqual(HomeCitySlotSelector(12), state.candidate_slots(_BLACKSMITH, proof)[0])
        self.assertEqual(HomeCitySlotSelector(11), state.candidate_slots(
            _BLACKSMITH, proof, exact=HomeCitySlotSelector(11),
        )[0])

    def test_inspecting_one_type_does_not_inspect_another_eligible_occupant(self):
        state = HomeCityScanState(inspected_candidates={
            (HomeCityObjectId.BLACKSMITH, HomeCitySlotSelector(i)) for i in (11, 12, 13)
        })
        proof = camera_home_frame().spatial_surface.camera_proof
        self.assertEqual((), state.candidate_slots(_BLACKSMITH, proof))
        alternate_family = replace(_BLACKSMITH, object_id=HomeCityObjectId.ALLIANCE_HALL)
        self.assertIn(state.candidate_slots(alternate_family, proof)[0].slot_index, (11, 12, 13))

    def test_state_is_request_local_and_rejects_stale_capture(self):
        state = HomeCityScanState()
        first = camera_home_frame((_body(12),), captured_at=_NOW)
        region = projected_body_region(_BLACKSMITH, HomeCitySlotSelector(12))
        state.observe(first, targets=(_BLACKSMITH,), usable_region=region)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            state.observe(first, targets=(_BLACKSMITH,), usable_region=region)
        self.assertEqual({}, HomeCityScanState().occupancy)
        self.assertEqual([], HomeCityScanState().coverage)

    def test_revisited_camera_lane_keeps_its_measured_advancement_goal(self):
        before = camera_home_frame(translation=(-480, -120), zoom=.74, image_size=(900, 1600))
        after = camera_home_frame(translation=(-900, -120), zoom=.74, image_size=(900, 1600))
        step = plan_home_city_camera_step(observation=before, target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual("left", step.action.direction)
        self.assertGreater(step.distance_to_goal(before.spatial_surface.camera_proof)
                           - step.distance_to_goal(after.spatial_surface.camera_proof), 12)

    def test_a_distinct_axis_alone_does_not_qualify_an_alternate_lane(self):
        with self.assertRaisesRegex(SelectorResolutionError, "No safe fixed gesture"):
            plan_home_city_camera_step(
                observation=camera_home_frame(translation=(-500, -240), zoom=.75,
                                              image_size=(900, 1600)),
                target=HomeCityObjectId.BLACKSMITH, home_city_slot=HomeCitySlotSelector(12),
                avoid_direction="up",
            )


class HomeCityMeasuredScanTests(unittest.TestCase):
    def test_qualified_inspection_completion_retains_unknown_slots_and_scope(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame(translation=(-1060, -720), captured_at=_NOW),
            camera_home_frame(translation=(-1060, -720), captured_at=_NOW + timedelta(seconds=1)),
        ))
        with patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                   return_value=SimpleNamespace(targets=(_INSTITUTE,))):
            result = core.discover_home_city(observe_content=lambda _: next(frames))
        self.assertIs(HomeCityScanStopReason.CANDIDATES_INSPECTED, result.stop_reason)
        self.assertEqual((HomeCityObjectId.INSTITUTE,), result.qualified_targets)
        self.assertIs(HomeCitySlotOccupancyState.UNKNOWN, result.occupancy[0].state)
        self.assertEqual(53, len(result.remaining_slots))
        self.assertEqual([], actions)

    def test_initial_unlocalized_discovery_is_input_free_and_retains_gaps(self):
        core, actions = _core()
        frames = iter(home_building_frame(captured_at=_NOW + timedelta(seconds=i)) for i in range(3))
        result = core.discover_home_city(observe_content=lambda _: next(frames))
        self.assertIs(HomeCityScanStopReason.ZOOM_UNRESOLVED, result.stop_reason)
        self.assertEqual(54, len(result.remaining_slots))
        self.assertEqual(0, result.gestures)
        self.assertEqual([], actions)

    def test_one_budget_covers_all_directed_discovery_pans_without_taps(self):
        core, actions = _core()
        frames = iter(camera_home_frame(
            translation=(-532, ty), captured_at=_NOW + timedelta(seconds=i),
        ) for i, ty in enumerate((222, 222, 150, 78)))
        steps = (
            qualified_pan_step("up", axis="y", goal_atlas=(982, 1800), reason="qualified_lane"),
            qualified_pan_step("up", axis="y", goal_atlas=(982, 1800), reason="qualified_lane"),
            qualified_pan_step("up", axis="y", goal_atlas=(982, 1800), reason="qualified_lane"),
        )
        with patch('pnc_automation.app.automation.engine.navigation_core.home_city_scan_step_budget', return_value=2), \
             patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                   return_value=SimpleNamespace(targets=(_INSTITUTE,))), \
             patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   side_effect=steps):
            result = core.discover_home_city(observe_content=lambda _: next(frames))
        self.assertIs(HomeCityScanStopReason.BUDGET_EXHAUSTED, result.stop_reason)
        self.assertEqual(2, result.gestures)
        self.assertEqual(['up', 'up'], [action.direction for action in actions])
        self.assertEqual(54, len(result.remaining_slots))

    def test_stall_allows_one_distinct_axis_then_stops_without_repeating(self):
        core, actions = _core()
        frames = iter(camera_home_frame(translation=(-100, 222),
                      captured_at=_NOW + timedelta(seconds=i)) for i in range(4))
        # Isolate the core's bounded policy from lane qualification, which is
        # separately tested above. Both supplied steps represent qualified lanes.
        steps = (
            qualified_pan_step('up', axis='y', goal_atlas=(550, 1800), reason='qualified_primary'),
            qualified_pan_step('left', axis='x', goal_atlas=(1400, 578), reason='qualified_alternate'),
        )
        with patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   side_effect=steps) as planner:
            with self.assertRaises(HomeCityScanError) as stopped:
                core.open_building(HomeCityObjectId.BLACKSMITH,
                                   home_city_slot=HomeCitySlotSelector(12),
                                   observe_content=lambda _: next(frames))
        self.assertIsNone(planner.call_args_list[0].kwargs['avoid_direction'])
        self.assertEqual('up', planner.call_args_list[1].kwargs['avoid_direction'])
        self.assertIs(HomeCityScanStopReason.NO_PROGRESS, stopped.exception.result.stop_reason)
        self.assertEqual(['up', 'left'], [action.direction for action in actions])
        self.assertEqual(2, stopped.exception.result.gestures)

    def test_lost_fit_gets_bounded_passive_captures_under_the_same_budget(self):
        for recovers in (True, False):
            core, actions = _core()
            initial = camera_home_frame(captured_at=_NOW)
            confirm = camera_home_frame(captured_at=_NOW + timedelta(seconds=1))
            lost = home_building_frame(captured_at=_NOW + timedelta(seconds=2))
            lost_again = home_building_frame(captured_at=_NOW + timedelta(seconds=3))
            passive = (camera_home_frame(translation=(-532, 150), captured_at=_NOW + timedelta(seconds=4))
                       if recovers else home_building_frame(captured_at=_NOW + timedelta(seconds=4)))
            frames = iter((initial, confirm, lost, lost_again, passive))
            labels = []

            def capture(label):
                labels.append(label)
                return next(frames)

            steps = (
                qualified_pan_step('up', axis='y', goal_atlas=(802, 1800), reason='qualified_lane'),
                qualified_pan_step('up', axis='y', goal_atlas=(802, 1800), reason='qualified_lane'),
            )
            with self.subTest(recovers=recovers), \
                 patch('pnc_automation.app.automation.engine.navigation_core.home_city_scan_step_budget', return_value=1), \
                 patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                       return_value=SimpleNamespace(targets=(_INSTITUTE,))), \
                 patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                       side_effect=steps):
                result = core.discover_home_city(observe_content=capture)
            self.assertEqual(1, len(actions))
            self.assertEqual(3, sum('_after_pan_1_' in label for label in labels))
            self.assertIs(HomeCityScanStopReason.BUDGET_EXHAUSTED if recovers
                          else HomeCityScanStopReason.LOCALIZATION_UNRESOLVED, result.stop_reason)

    def test_ambiguous_after_pan_stops_without_recovery_or_another_gesture(self):
        core, actions = _core()
        before = camera_home_frame(captured_at=_NOW)
        ambiguous = replace(before, spatial_surface=replace(before.spatial_surface, camera_proof=HomeCityCameraProof(
            HomeCityCameraStatus.AMBIGUOUS, 'conflicting groups', frame_size=(540, 960),
        )))
        frames = iter((before, camera_home_frame(captured_at=_NOW + timedelta(seconds=1)),
                       replace(ambiguous, captured_at=_NOW + timedelta(seconds=2)),
                       replace(ambiguous, captured_at=_NOW + timedelta(seconds=3)),
                       replace(ambiguous, captured_at=_NOW + timedelta(seconds=4))))
        step = qualified_pan_step('up', axis='y', goal_atlas=(802, 1800), reason='qualified_lane')
        with patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                   return_value=SimpleNamespace(targets=(_INSTITUTE,))), \
             patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   return_value=step):
            result = core.discover_home_city(observe_content=lambda _: next(frames))
        self.assertEqual(1, len(actions))
        self.assertIs(HomeCityScanStopReason.LOCALIZATION_UNRESOLVED, result.stop_reason)
