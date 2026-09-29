"""Fixed Home gesture profiles over current endpoint, body and mapped region proof."""

from dataclasses import replace
from datetime import UTC, datetime
import unittest

from pnc_automation.app.pnc.domain.action_requests import SwipePurpose, resolve_swipe_points_for_action
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof, HomeCityCameraStatus, HomeCityViewEvidence, HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import (
    Bounds, DetectedSpatialObject, Observation, SpatialObjectKind,
    SpatialObjectSourceKind, SpatialSurfaceObservation, SpatialSurfaceType,
    SpatialViewport, SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    plan_home_city_camera_pan, plan_home_city_camera_step,
)
from pnc_automation.core.errors import SelectorResolutionError


def _body(target=HomeCityObjectId.INSTITUTE, *, bounds=Bounds(634, 863, 60, 56),
          slot=9, point=None):
    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING, bounds=bounds,
        action_point=point or bounds.center(), source_kind=SpatialObjectSourceKind.TEMPLATE,
        home_city_slot=HomeCitySlotSelector(slot_index=slot) if slot is not None else None,
        metadata={"home_city_object_id": target.value},
    )


def _observation(*, translation=(-288, 100), zoom=.75, objects=(),
                 size=(900, 1600), status=HomeCityZoomStatus.AT_ENDPOINT):
    proof = HomeCityCameraProof(HomeCityCameraStatus.LOCALIZED, "controlled", translation,
                                zoom, frame_size=size)
    view = HomeCityViewEvidence(status, "controlled", "test_endpoint", None, size)
    return Observation(
        screen_type=ScreenType.PNC_HOME_CITY, image_size=size, captured_at=datetime.now(UTC),
        spatial_surface=SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE, objects=objects,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            camera_proof=proof, home_city_view=view,
        ),
    )


def _points(action):
    return resolve_swipe_points_for_action(width=900, height=1600, action=action)


class HomeCityCameraPanTests(unittest.TestCase):
    def test_live_horizontal_left_profile_exact_points(self):
        action = plan_home_city_camera_pan(observation=_observation(), target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual((753, 727, 639, 727), _points(action))
        self.assertEqual(429, action.duration_ms)
        self.assertEqual(SwipePurpose.HOME_CITY_CAMERA, action.purpose)
        self.assertTrue(action.exact_geometry)
        self.assertEqual(Bounds(624, 705, 145, 46), action.safe_bounds)
        self.assertTrue(action.follow_up_request.include_home_city_camera)

    def test_live_horizontal_right_profile_uses_new_measured_pose(self):
        body = _body(HomeCityObjectId.CAMPAIGN, bounds=Bounds(60, 690, 40, 30), slot=None)
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-542, 99), objects=(body,)),
            target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual((385, 726, 499, 726), _points(action))
        self.assertEqual("right", action.direction)

    def test_two_pixel_settle_clips_region_without_growing_or_shortening(self):
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-286, 100)), target=HomeCityObjectId.CAMPAIGN)
        x1, y1, x2, y2 = _points(action)
        self.assertEqual(114, x1 - x2)
        self.assertEqual(y1, y2)
        self.assertEqual(770, action.safe_bounds.x + action.safe_bounds.width)
        self.assertGreaterEqual(action.safe_bounds.x, 626)
        self.assertTrue(action.safe_bounds.contains_point((x1, y1)))
        self.assertTrue(action.safe_bounds.contains_point((x2, y2)))

    def test_too_little_remaining_horizontal_lane_is_refused(self):
        # The independently mapped alternative is occupied; the planner must
        # not shorten a courtyard stroke to fit its remaining capacity.
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(320, 1110, 30, 25), slot=12)
        with self.assertRaisesRegex(SelectorResolutionError, "No safe fixed gesture"):
            plan_home_city_camera_pan(observation=_observation(translation=(-800, 100), objects=(obstacle,)),
                                      target=HomeCityObjectId.CAMPAIGN)

    def test_hud_covered_ground_strip_is_never_dispatched(self):
        with self.assertRaisesRegex(SelectorResolutionError, "No safe fixed gesture"):
            plan_home_city_camera_pan(observation=_observation(), target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)

    def test_institute_bridge_uses_current_slot9_body_and_exact_stage0_vector(self):
        action = plan_home_city_camera_pan(observation=_observation(objects=(_body(),)),
                                          target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        self.assertEqual((664, 892, 737, 685), _points(action))
        self.assertEqual(488, action.duration_ms)
        self.assertIn("institute_bridge", action.reason)

    def test_institute_bridge_at_settled_pose_keeps_whole_stroke_safe(self):
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-286, 100), objects=(_body(bounds=Bounds(636, 863, 60, 56)),)),
            target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        self.assertEqual((666, 892, 739, 685), _points(action))
        self.assertEqual(770, action.safe_bounds.x + action.safe_bounds.width)

    def test_institute_bridge_refuses_unmatched_or_wrong_slot_body(self):
        for body in (_body(slot=None), _body(slot=12), replace(_body(), source_kind=SpatialObjectSourceKind.GEOMETRY)):
            with self.subTest(body=body), self.assertRaises(SelectorResolutionError):
                plan_home_city_camera_pan(observation=_observation(objects=(body,)),
                                          target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)

    def test_bridge_refuses_endpoint_outside_actual_region(self):
        # Recognized body near the right edge does not license a longer envelope.
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(
                observation=_observation(objects=(_body(bounds=Bounds(700, 863, 60, 56)),)),
                target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)

    def test_observed_body_intrusion_blocks_ground_region(self):
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(640, 710, 30, 25), slot=12)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(observation=_observation(objects=(obstacle,)), target=HomeCityObjectId.CAMPAIGN)

    def test_other_body_intrusion_blocks_institute_envelope(self):
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(610, 700, 30, 25), slot=12)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(observation=_observation(objects=(_body(), obstacle)),
                                      target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)

    def test_central_ground_strip_up_has_fixed_length_and_duration(self):
        action = plan_home_city_camera_pan(observation=_observation(translation=(-114, -350)),
                                          target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        x1, y1, x2, y2 = _points(action)
        self.assertEqual(x1, x2)
        self.assertEqual(179, y1 - y2)
        self.assertEqual(425, action.duration_ms)
        self.assertIn("ground_strip", action.reason)
        self.assertLess(action.safe_bounds.y + action.safe_bounds.height, 1170)

    def test_ground_reverse_uses_fixed_length_not_error_scaled_microdrag(self):
        body = _body(HomeCityObjectId.CAMPAIGN, bounds=Bounds(410, 225, 40, 40), slot=None)
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-288, -350), objects=(body,)), target=HomeCityObjectId.CAMPAIGN)
        _, y1, _, y2 = _points(action)
        self.assertEqual(179, y2 - y1)
        self.assertEqual("down", action.direction)

    def test_retained_manor_pose_can_use_surveyed_road_at_measured_endpoint_scale(self):
        obs = _observation(translation=(-360, -753), zoom=.7389549110743511)
        action = plan_home_city_camera_pan(observation=obs, target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual("pan_home_city_ground_strip_down", action.reason)
        self.assertEqual(Bounds(410, 363, 44, 206), action.safe_bounds)
        self.assertEqual((431, 376, 431, 555), _points(action))
        self.assertEqual(425, action.duration_ms)
        self.assertGreaterEqual(376 - action.safe_bounds.y, 9)
        self.assertGreaterEqual(action.safe_bounds.y + action.safe_bounds.height - 1 - 555, 9)

    def test_newly_surveyed_road_remains_subject_to_current_body_occlusion(self):
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(420, 562, 12, 6), slot=12)
        obs = _observation(translation=(-360, -753), zoom=.7389549110743511,
                           objects=(obstacle,))
        action = plan_home_city_camera_pan(observation=obs, target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual("pan_home_city_southern_terrace_left", action.reason)
        # Blocking the old road cannot authorize crossing it. The independent
        # terrace may supply a different route until it too has a body intrusion.
        terrace_obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(300, 600, 20, 20), slot=11)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(
                observation=replace(obs, spatial_surface=replace(
                    obs.spatial_surface, objects=(obstacle, terrace_obstacle))),
                target=HomeCityObjectId.CAMPAIGN,
            )

    def test_unsupported_native_size_or_scale_does_not_resize_profiles(self):
        for overrides in ({"size": (540, 960)}, {"zoom": 1.0}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(SelectorResolutionError, "display/scale"):
                plan_home_city_camera_pan(observation=_observation(**overrides), target=HomeCityObjectId.CAMPAIGN)

    def test_southern_pose_has_left_terrace_for_wall_and_exact_blacksmith(self):
        blacksmith = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(756, 786, 89, 96),
                           slot=12, point=(807, 844))
        obs = _observation(translation=(-110, -414), zoom=.7388729965534407,
                           objects=(blacksmith,))
        for target, slot in ((HomeCityObjectId.WALL, None),
                             (HomeCityObjectId.BLACKSMITH, HomeCitySlotSelector(12))):
            with self.subTest(target=target):
                step = plan_home_city_camera_step(
                    observation=obs, target=target, home_city_slot=slot,
                )
                self.assertEqual("pan_home_city_southern_terrace_left", step.action.reason)
                self.assertEqual(Bounds(526, 928, 158, 50), step.action.safe_bounds)
                self.assertEqual((661, 952, 547, 952), _points(step.action))
                self.assertEqual(429, step.action.duration_ms)
                self.assertTrue(step.action.exact_geometry)
                self.assertGreater(step.distance_to_goal(obs.spatial_surface.camera_proof), 0)

    def test_southern_terrace_observed_body_or_stalled_direction_refuses(self):
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(570, 940, 20, 20), slot=11)
        for objects, avoid in (((obstacle,), None), ((), "left")):
            with self.subTest(objects=objects, avoid=avoid), self.assertRaises(SelectorResolutionError):
                plan_home_city_camera_step(
                    observation=_observation(translation=(-110, -414), zoom=.7388729965534407,
                                             objects=objects),
                    target=HomeCityObjectId.WALL, avoid_direction=avoid,
                )

    def test_southern_terrace_does_not_authorize_unqualified_reverse(self):
        left_body = _body(HomeCityObjectId.CAMPAIGN, bounds=Bounds(40, 600, 45, 40), slot=None)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(
                observation=_observation(translation=(-110, -414), zoom=.7388729965534407,
                                         objects=(left_body,)),
                target=HomeCityObjectId.CAMPAIGN,
            )

    def test_nonendpoint_or_missing_current_view_refuses_motion(self):
        for status in (HomeCityZoomStatus.NOT_AT_ENDPOINT, HomeCityZoomStatus.UNRESOLVED):
            with self.subTest(status=status), self.assertRaisesRegex(SelectorResolutionError, "normalized endpoint"):
                plan_home_city_camera_pan(observation=_observation(status=status), target=HomeCityObjectId.CAMPAIGN)
        obs = _observation()
        obs = replace(obs, spatial_surface=replace(obs.spatial_surface, home_city_view=None))
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(observation=obs, target=HomeCityObjectId.CAMPAIGN)

    def test_mismatched_camera_dimensions_refuse_motion(self):
        obs = replace(_observation(), image_size=(540, 960))
        with self.assertRaisesRegex(SelectorResolutionError, "localized current-frame"):
            plan_home_city_camera_pan(observation=obs, target=HomeCityObjectId.CAMPAIGN)

    def test_stalled_direction_is_not_repeated(self):
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_step(observation=_observation(), target=HomeCityObjectId.CAMPAIGN,
                                       avoid_direction="left")

    def test_current_body_overrides_static_hint_and_already_visible_needs_no_pan(self):
        body = _body(HomeCityObjectId.CAMPAIGN, bounds=Bounds(400, 500, 60, 60), slot=None)
        with self.assertRaisesRegex(SelectorResolutionError, "no pan is needed"):
            plan_home_city_camera_pan(observation=_observation(objects=(body,)), target=HomeCityObjectId.CAMPAIGN)

    def test_missing_body_inside_safe_band_does_not_invent_search_input(self):
        with self.assertRaisesRegex(SelectorResolutionError, "no current-frame match"):
            plan_home_city_camera_pan(observation=_observation(), target=HomeCityObjectId.INSTITUTE)

    def test_goal_is_recomputed_from_measured_pose_without_gesture_gain(self):
        first = plan_home_city_camera_step(observation=_observation(), target=HomeCityObjectId.CAMPAIGN)
        after = _observation(translation=(-542, 99))
        second = plan_home_city_camera_step(observation=after, target=HomeCityObjectId.CAMPAIGN)
        self.assertEqual(first.goal_atlas[0], second.goal_atlas[0])
        self.assertLess(second.distance_to_goal(after.spatial_surface.camera_proof),
                        first.distance_to_goal(_observation().spatial_surface.camera_proof))
        self.assertEqual(114, _points(second.action)[0] - _points(second.action)[2])

    def test_eastern_pose_can_return_right_through_independent_paved_strip(self):
        action = plan_home_city_camera_pan(observation=_observation(translation=(-886, -372)),
                                          target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        self.assertEqual("pan_home_city_eastern_return_right", action.reason)
        self.assertEqual((222, 659, 336, 659), _points(action))
        self.assertEqual(Bounds(200, 636, 159, 48), action.safe_bounds)

    def test_eastern_return_cannot_cross_a_foreign_body_in_either_direction(self):
        obstacle = _body(HomeCityObjectId.BLACKSMITH, bounds=Bounds(230, 642, 30, 30), slot=12)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(
                observation=_observation(translation=(-886, -372), objects=(obstacle,)),
                target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)
        campaign = _body(HomeCityObjectId.CAMPAIGN, bounds=Bounds(800, 450, 50, 50), slot=None)
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(
                observation=_observation(translation=(-886, -372), objects=(campaign, obstacle)),
                target=HomeCityObjectId.CAMPAIGN)

    def test_m008_campaign_right_edge_uses_measured_eastern_lane_to_pan_left(self):
        # Actual native M008 run4 frame0029 and run5 frame0028, independently
        # replayed September29: bodies match .938/.949, but x766/761 is outside
        # the x738 tap limit. Courtyard capacities100/92 cannot fit114px.
        for translation, zoom, point, bounds in (
            ((-773, 54), .739249339502473, (766, 883), Bounds(714, 856, 111, 52)),
            ((-786, 50), .7429132891403993, (761, 883), Bounds(708, 856, 111, 52)),
        ):
            with self.subTest(translation=translation):
                campaign = _body(HomeCityObjectId.CAMPAIGN, bounds=bounds, point=point, slot=None)
                observation = _observation(translation=translation, zoom=zoom, objects=(campaign,))
                step = plan_home_city_camera_step(observation=observation, target=HomeCityObjectId.CAMPAIGN)
                action = step.action
                self.assertEqual("pan_home_city_eastern_return_left", action.reason)
                x1, y1, x2, y2 = _points(action)
                self.assertEqual(114, x1 - x2)
                self.assertEqual(y1, y2)
                self.assertEqual(429, action.duration_ms)
                self.assertTrue(action.exact_geometry)
                self.assertTrue(action.safe_bounds.contains_point((x1, y1)))
                self.assertTrue(action.safe_bounds.contains_point((x2, y2)))
                self.assertEqual("x", step.axis)
                with self.assertRaises(SelectorResolutionError):
                    plan_home_city_camera_step(
                        observation=observation, target=HomeCityObjectId.CAMPAIGN, avoid_direction="left",
                    )

    def test_thin_clipped_region_cannot_lose_perpendicular_margin(self):
        with self.assertRaises(SelectorResolutionError):
            plan_home_city_camera_pan(observation=_observation(translation=(-886, -796)),
                                      target=HomeCityObjectId.ILLUSORY_BEAST_MANOR)

    def test_inspection_moves_until_the_whole_body_region_is_exposed(self):
        """At this pose the institute slot-9 anchor is inside the band while its
        projected body region still protrudes past the right edge. Acquisition
        refuses -- there is no current-frame body match to tap -- but discovery
        inspection still moves the canonical region into the safe band."""
        observation = _observation(translation=(-760, -460), zoom=.74)
        with self.assertRaisesRegex(SelectorResolutionError, "no current-frame match"):
            plan_home_city_camera_step(
                observation=observation, target=HomeCityObjectId.INSTITUTE,
                home_city_slot=HomeCitySlotSelector(9))

        step = plan_home_city_camera_step(
            observation=observation, target=HomeCityObjectId.INSTITUTE,
            home_city_slot=HomeCitySlotSelector(9), inspect_body=True)

        self.assertEqual("right", step.action.direction)
        self.assertEqual("pan_home_city_eastern_return_right", step.action.reason)
        x1, y1, x2, y2 = _points(step.action)
        self.assertTrue(step.action.safe_bounds.contains_point((x1, y1)))
        self.assertTrue(step.action.safe_bounds.contains_point((x2, y2)))

    def test_inspection_refuses_once_the_whole_region_is_exposed(self):
        """A fully-exposed projected region is a refusal, not another pan."""
        with self.assertRaisesRegex(SelectorResolutionError, "already fully inside"):
            plan_home_city_camera_step(
                observation=_observation(translation=(-720, -460), zoom=.74),
                target=HomeCityObjectId.INSTITUTE,
                home_city_slot=HomeCitySlotSelector(9), inspect_body=True)

    def test_inspection_uses_the_projected_region_not_an_observed_body(self):
        """Inspection exposure is decided by canonical region geometry; a
        measured body elsewhere inside the band cannot satisfy it (and the
        observed body keeps acquisition at its own no-pan refusal)."""
        body = _body()
        observation = _observation(translation=(-760, -460), zoom=.74, objects=(body,))
        with self.assertRaisesRegex(SelectorResolutionError, "no pan is needed"):
            plan_home_city_camera_step(
                observation=observation, target=HomeCityObjectId.INSTITUTE,
                home_city_slot=HomeCitySlotSelector(9))

        step = plan_home_city_camera_step(
            observation=observation, target=HomeCityObjectId.INSTITUTE,
            home_city_slot=HomeCitySlotSelector(9), inspect_body=True)

        self.assertEqual("right", step.action.direction)
        self.assertTrue(step.action.safe_bounds.contains_point(_points(step.action)[:2]))
