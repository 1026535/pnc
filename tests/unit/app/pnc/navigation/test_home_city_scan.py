"""Measured coverage and request-local occupancy never turn unknown into absent."""

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import HomeCityCameraProof, HomeCityCameraStatus
from pnc_automation.app.pnc.domain.observation import Bounds
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
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.app.pnc.vision.home_city_camera import home_city_camera_target
from tests.unit.app.pnc.navigation.test_home_city_slot_selection import _body, _core, _NOW
from tests.support.pnc.navigation.core_home import (
    camera_home_frame, home_building_frame, measured_building_object, qualified_pan_step,
)


_BLACKSMITH = home_city_camera_target(HomeCityObjectId.BLACKSMITH)
_INSTITUTE = home_city_camera_target(HomeCityObjectId.INSTITUTE)


class HomeCityTargetLocationTests(unittest.TestCase):
    @staticmethod
    def _provenanced(frame, sequence, *, session="source-session"):
        ref = FrameRef(session, 1, sequence, 0, frame.captured_at)
        surface = frame.spatial_surface
        return replace(frame, frame_ref=ref, spatial_surface=replace(
            surface,
            camera_proof=replace(surface.camera_proof, frame_ref=ref),
            home_city_view=replace(surface.home_city_view, frame_ref=ref),
        ))

    def test_prior_home_source_is_not_reused_as_target_or_endpoint_proof(self):
        core, actions = _core()
        target = HomeCityObjectId.CAVALRY_BARRACKS
        body = replace(
            measured_building_object(
                target, bounds=Bounds(300, 500, 100, 50),
                action_point=(350, 525), action_bounds=Bounds(340, 515, 20, 20),
            ),
            home_city_slot=HomeCitySlotSelector(6),
        )
        source = self._provenanced(camera_home_frame((body,), captured_at=_NOW), 1)
        frames = iter((
            self._provenanced(camera_home_frame(
                captured_at=_NOW + timedelta(seconds=1)), 2),
            self._provenanced(camera_home_frame(
                captured_at=_NOW + timedelta(seconds=2)), 3),
            self._provenanced(camera_home_frame(
                (body,), translation=(-240, 222),
                captured_at=_NOW + timedelta(seconds=3)), 4),
        ))
        requests = []

        def observe(request):
            requests.append(request)
            return next(frames)

        step = qualified_pan_step('right', axis='x', goal_atlas=(1100, 700))
        with patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   return_value=step):
            located = core.locate_building(
                target, observe_content=observe, source=source,
                home_city_slot=HomeCitySlotSelector(6),
            )
        self.assertIs(body, located.spatial_surface.objects[0])
        self.assertIsNot(source, located)
        self.assertEqual(3, len(requests))
        self.assertEqual(['right'], [action.direction for action in actions])
        self.assertEqual(1, len({request.label.split('_home_')[0] for request in requests}))

    def test_prior_home_source_requires_a_newer_capture(self):
        core, actions = _core()
        source = self._provenanced(camera_home_frame(captured_at=_NOW), 1)
        with self.assertRaisesRegex(RuntimeError, 'stale capture'):
            core.locate_building(
                HomeCityObjectId.CAVALRY_BARRACKS,
                observe_content=lambda _: self._provenanced(
                    camera_home_frame(captured_at=_NOW), 2),
                source=source,
            )
        self.assertEqual([], actions)

    def test_prior_home_source_rejects_foreign_session_before_input(self):
        core, actions = _core()
        source = self._provenanced(camera_home_frame(captured_at=_NOW), 1)
        foreign = self._provenanced(camera_home_frame(
            captured_at=_NOW + timedelta(seconds=1)), 2, session="other-session")
        with self.assertRaisesRegex(RuntimeError, 'instance/session continuity'):
            core.locate_building(
                HomeCityObjectId.CAVALRY_BARRACKS,
                observe_content=lambda _: foreign,
                source=source,
            )
        self.assertEqual([], actions)

    def test_prior_home_source_requires_both_frame_refs(self):
        core, actions = _core()
        source = camera_home_frame(captured_at=_NOW)
        with self.assertRaisesRegex(RuntimeError, 'no session provenance'):
            core.locate_building(
                HomeCityObjectId.CAVALRY_BARRACKS,
                observe_content=lambda _: self.fail('missing source reached capture'),
                source=source,
            )
        source = self._provenanced(source, 1)
        with self.assertRaisesRegex(RuntimeError, 'lost frame provenance'):
            core.locate_building(
                HomeCityObjectId.CAVALRY_BARRACKS,
                observe_content=lambda _: camera_home_frame(
                    captured_at=_NOW + timedelta(seconds=1)),
                source=source,
            )
        self.assertEqual([], actions)

    def test_unreviewed_target_can_be_located_without_opening(self):
        core, actions = _core()
        target = HomeCityObjectId.CAVALRY_BARRACKS
        body = replace(
            measured_building_object(
                target, bounds=Bounds(300, 500, 100, 50),
                action_point=(350, 525), action_bounds=Bounds(340, 515, 20, 20),
            ),
            home_city_slot=HomeCitySlotSelector(6),
        )
        frames = iter(camera_home_frame((body,), captured_at=_NOW + timedelta(seconds=i))
                      for i in range(2))
        located = core.locate_building(
            target, observe_content=lambda _: next(frames),
            home_city_slot=HomeCitySlotSelector(6),
        )
        self.assertIs(body, located.spatial_surface.objects[0])
        self.assertEqual([], actions)
        with self.assertRaisesRegex(ValueError, "reviewed"):
            core.open_building(target, observe_content=lambda _: self.fail("public route observed"))
        self.assertEqual([], actions)

    def test_target_only_scan_returns_current_post_pan_body_without_tap(self):
        core, actions = _core()
        target = HomeCityObjectId.CAVALRY_BARRACKS
        body = replace(
            measured_building_object(
                target, bounds=Bounds(300, 500, 100, 50),
                action_point=(350, 525), action_bounds=Bounds(340, 515, 20, 20),
            ),
            home_city_slot=HomeCitySlotSelector(6),
        )
        frames = iter((
            camera_home_frame(captured_at=_NOW),
            camera_home_frame(captured_at=_NOW + timedelta(seconds=1)),
            camera_home_frame((body,), translation=(-240, 222),
                              captured_at=_NOW + timedelta(seconds=2)),
        ))
        requests = []

        def observe(request):
            requests.append(request)
            return next(frames)

        step = qualified_pan_step('right', axis='x', goal_atlas=(1100, 700))
        with patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   return_value=step) as planner:
            located = core.locate_building(
                target, observe_content=observe, home_city_slot=HomeCitySlotSelector(6),
            )
        self.assertIs(body, located.spatial_surface.objects[0])
        self.assertEqual((-240, 222), located.spatial_surface.camera_proof.translation)
        self.assertEqual([target], [call.kwargs['target'] for call in planner.call_args_list])
        self.assertEqual([HomeCitySlotSelector(6)],
                         [call.kwargs['home_city_slot'] for call in planner.call_args_list])
        self.assertEqual(1, len(actions))
        self.assertEqual('right', actions[0].direction)
        self.assertEqual(1, len({request.label.split('_home_')[0] for request in requests}))

    def test_target_only_scan_does_not_return_a_rival_body(self):
        core, actions = _core()
        frames = iter((
            camera_home_frame(captured_at=_NOW),
            camera_home_frame(captured_at=_NOW + timedelta(seconds=1)),
            camera_home_frame((_body(12),), translation=(-240, 222),
                              captured_at=_NOW + timedelta(seconds=2)),
        ))
        step = qualified_pan_step('right', axis='x', goal_atlas=(1100, 700))
        with patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   return_value=step), \
             patch('pnc_automation.app.automation.engine.navigation_core.home_city_scan_step_budget',
                   return_value=1):
            with self.assertRaises(HomeCityScanError) as stopped:
                core.locate_building(
                    HomeCityObjectId.CAVALRY_BARRACKS,
                    observe_content=lambda _: next(frames),
                    home_city_slot=HomeCitySlotSelector(6),
                )
        self.assertIs(HomeCityScanStopReason.BUDGET_EXHAUSTED,
                      stopped.exception.result.stop_reason)
        self.assertEqual(['right'], [action.direction for action in actions])


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

            def capture(request):
                labels.append(request.label)
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

    def test_inspected_hint_is_never_replanned_for_discovery(self):
        """A measured occupancy hint cannot reintroduce an inspected candidate.

        At zoom .74 / translation (-500,-880) the usable band fully contains
        slot 12's canonical blacksmith body region, so the first observation
        both inspects it and records its measured OCCUPIED hint; the hint
        keeps it first in ``candidate_slots`` ordering.  Discovery must still
        never plan it: each later frame replans the retained candidate under
        the measured atlas-pose tolerance and moves on to the family's
        remaining uninspected slots.
        """
        core, actions = _core()
        pose, jittered = (-500, -880), (-497, -878)
        frames = [
            camera_home_frame((_body(12),), translation=pose if i < 2 else jittered,
                              zoom=.74, image_size=(900, 1600),
                              captured_at=_NOW + timedelta(seconds=i))
            for i in range(4)
        ]
        planned = []

        def plan(**kwargs):
            planned.append((kwargs["home_city_slot"], kwargs["observation"],
                            kwargs["inspect_body"]))
            return qualified_pan_step("up", axis="y", goal_atlas=(982, 1800),
                                      reason="qualified_lane")

        with patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                   return_value=SimpleNamespace(targets=(_BLACKSMITH,))), \
             patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   side_effect=plan):
            frames_iter = iter(frames)
            result = core.discover_home_city(observe_content=lambda _: next(frames_iter))

        self.assertIs(HomeCityScanStopReason.NO_PROGRESS, result.stop_reason)
        self.assertEqual(2, result.gestures)
        self.assertEqual(['up', 'up'], [action.direction for action in actions])
        # Slot 12 is hinted, nearest to the prior corridor, and inspected, so
        # the pre-correction ordering planned it first every pass.  The
        # inspected filter skips it without a planner call; the jittered
        # revisit then suppresses the retained slot-11 route under the
        # atlas-pose tolerance, so slot 13 is tried once instead.
        self.assertEqual(
            [11, 11, 11, 13],
            [slot.slot_index for slot, _observation, _inspect in planned],
        )
        # The retained slot-11 route replanned from the fresh jittered frame,
        # not from the pose it was originally qualified on.
        self.assertIs(frames[1], planned[0][1])
        self.assertIs(frames[2], planned[1][1])
        self.assertTrue(all(inspect for _slot, _observation, inspect in planned))
        self.assertEqual(HomeCitySlotOccupancyState.OCCUPIED, result.occupancy[0].state)
        self.assertEqual(12, result.occupancy[0].slot_index)
        self.assertIn((HomeCityObjectId.BLACKSMITH, HomeCitySlotSelector(12)),
                      result.inspected_candidates)

    def test_retained_candidate_is_replanned_from_each_fresh_observation(self):
        """A preferred slot follows fresh poses until its route is attempted.

        The retained (target, slot) preference survives across poses: it is
        replanned on every fresh observation, so a jittered pose can route it
        on a different axis and a materially moved pose can dispatch it on the
        original axis again.  Once the same candidate/direction was already
        attempted at that pose, the preference is released and the family's
        next uninspected candidate is considered instead.
        """
        core, actions = _core()
        # These poses keep every blacksmith body region outside the usable
        # band, so no candidate is inspected and the same slot stays
        # retained; pose_b jitters within the localization allowance while
        # pose_c moves the camera center ~80 atlas px from pose_a.
        poses = ((-100, -900), (-100, -900), (-97, -898),
                 (-160, -900), (-160, -900), (-160, -900), (-160, -900))
        frames = [
            camera_home_frame(translation=poses[i], zoom=.74, image_size=(900, 1600),
                              captured_at=_NOW + timedelta(seconds=i))
            for i in range(7)
        ]
        directions = {
            _NOW + timedelta(seconds=1): "up",
            _NOW + timedelta(seconds=2): "left",
            _NOW + timedelta(seconds=3): "up",
            _NOW + timedelta(seconds=4): "up",
        }
        planned = []

        def plan(**kwargs):
            observation = kwargs["observation"]
            direction = directions[observation.captured_at]
            planned.append((kwargs["home_city_slot"], observation, kwargs["inspect_body"]))
            axis = "x" if direction in ("left", "right") else "y"
            return qualified_pan_step(
                direction, axis=axis,
                goal_atlas=(1400, 578) if axis == "x" else (982, 1800),
                reason="qualified_lane",
            )

        with patch('pnc_automation.app.automation.engine.navigation_core.load_home_city_camera_catalog',
                   return_value=SimpleNamespace(targets=(_BLACKSMITH,))), \
             patch('pnc_automation.app.automation.engine.navigation_core.plan_home_city_camera_step',
                   side_effect=plan):
            frames_iter = iter(frames)
            result = core.discover_home_city(observe_content=lambda _: next(frames_iter))

        self.assertIs(HomeCityScanStopReason.NO_PROGRESS, result.stop_reason)
        self.assertEqual(4, result.gestures)
        self.assertEqual(['up', 'left', 'up', 'up'],
                         [action.direction for action in actions])
        # The preferred slot-12 candidate is replanned on each fresh frame:
        # 'left' at the jittered pose_b is a new route, 'up' at pose_c is
        # dispatched because the pose moved ~80 atlas px, and the second 'up'
        # at pose_c is suppressed as a repeat -- releasing the preference so
        # the family's next uninspected candidate (slot 11) is tried.
        self.assertEqual(
            [12, 12, 12, 12, 12, 11],
            [slot.slot_index for slot, _observation, _inspect in planned],
        )
        self.assertIs(frames[1], planned[0][1])
        self.assertIs(frames[2], planned[1][1])
        self.assertIs(frames[3], planned[2][1])
        self.assertIs(frames[4], planned[3][1])
        self.assertIs(frames[4], planned[5][1])
        self.assertTrue(all(inspect for _slot, _observation, inspect in planned))
