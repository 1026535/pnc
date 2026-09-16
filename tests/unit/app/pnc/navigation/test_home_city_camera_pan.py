"""Measured single-pan planning for camera-qualified Home building targets."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime

from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    Observation,
    SpatialObjectKind,
    SpatialObjectSourceKind,
    SpatialSurfaceObservation,
    SpatialSurfaceType,
    SpatialViewport,
    SpatialViewportAddressingKind,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.spatial_navigation import (
    plan_home_city_camera_pan,
)
from pnc_automation.core.errors import SelectorResolutionError


def _measured_object(
    target: HomeCityObjectId,
    *,
    bounds: Bounds,
    action_point: tuple[int, int],
    action_bounds: Bounds,
) -> DetectedSpatialObject:
    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=bounds,
        action_point=action_point,
        action_bounds=action_bounds,
        source_kind=SpatialObjectSourceKind.TEMPLATE,
        metadata={"home_city_object_id": target.value},
    )


def _observation(
    *,
    translation: tuple[int, int] | None = (-532, 222),
    objects: tuple[DetectedSpatialObject, ...] = (),
    screen: ScreenType = ScreenType.PNC_HOME_CITY,
) -> Observation:
    proof = (
        None
        if translation is None
        else HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="test",
            translation=translation,
            frame_size=(540, 960),
        )
    )
    return Observation(
        screen_type=screen,
        spatial_surface=SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
            camera_proof=proof,
        ),
        image_size=(540, 960),
        captured_at=datetime.now(UTC),
    )


class HomeCityCameraPanTests(unittest.TestCase):
    """One measured pan moves the qualified target into the HUD-safe band."""

    def test_institute_at_reference_pans_up_toward_the_safe_band(self) -> None:
        action = plan_home_city_camera_pan(
            observation=_observation(),
            target=HomeCityObjectId.INSTITUTE,
        )

        # Institute anchor projects to reference (724,1253); the band top edge is
        # at 928 reference units, so content must move up by ~645.
        self.assertEqual("up", action.direction)
        self.assertAlmostEqual(645 / (1600 * 2.33), action.distance_ratio, places=2)
        self.assertEqual("pan_home_city_camera_institute_y", action.reason)
        self.assertTrue(action.observe_after)
        self.assertGreater(action.start_y_ratio, action.end_y_ratio)

    def test_tower_at_reference_pans_up_with_a_larger_bounded_step(self) -> None:
        action = plan_home_city_camera_pan(
            observation=_observation(),
            target=HomeCityObjectId.TOWER_OF_TRIAL,
        )

        self.assertEqual("up", action.direction)
        self.assertAlmostEqual(0.297, action.distance_ratio, places=2)
        self.assertLessEqual(action.distance_ratio, 0.56)

    def test_measured_object_point_drives_the_pan_when_body_is_visible(self) -> None:
        # Body-verified object sitting below the tap band on a 540x960 frame:
        # reference-space action point (300, 1500) -> needs an upward pan.
        target = _measured_object(
            HomeCityObjectId.INSTITUTE,
            bounds=Bounds(165, 890, 30, 24),
            action_point=(180, 900),
            action_bounds=Bounds(170, 892, 20, 20),
        )
        action = plan_home_city_camera_pan(
            observation=_observation(objects=(target,)),
            target=HomeCityObjectId.INSTITUTE,
        )

        self.assertEqual("up", action.direction)
        # 900 frame px is 1500 reference units; needed delta 608-1500 = -892.
        self.assertAlmostEqual(892 / (1600 * 2.33), action.distance_ratio, places=2)

    def test_visible_in_band_body_needs_no_pan_step(self) -> None:
        # The measured route taps an in-band body directly; asked anyway, the
        # planner must refuse to invent a step.
        target = _measured_object(
            HomeCityObjectId.INSTITUTE,
            bounds=Bounds(139, 185, 48, 45),
            action_point=(154, 193),
            action_bounds=Bounds(146, 187, 18, 11),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "no pan is needed"):
            plan_home_city_camera_pan(
                observation=_observation(objects=(target,), translation=(-1000, -710)),
                target=HomeCityObjectId.INSTITUTE,
            )

    def test_anchor_inside_band_without_body_match_is_rejected(self) -> None:
        # Tower anchor on the tower view projects inside the band; without a
        # current-frame body match the planner must not invent a target.
        with self.assertRaisesRegex(SelectorResolutionError, "no current-frame match"):
            plan_home_city_camera_pan(
                observation=_observation(translation=(-532, -638)),
                target=HomeCityObjectId.TOWER_OF_TRIAL,
            )

    def test_missing_or_unlocalized_proof_is_rejected(self) -> None:
        with self.assertRaisesRegex(SelectorResolutionError, "localized"):
            plan_home_city_camera_pan(
                observation=_observation(translation=None),
                target=HomeCityObjectId.INSTITUTE,
            )
        insufficient = _observation()
        insufficient = replace(
            insufficient,
            spatial_surface=replace(
                insufficient.spatial_surface,
                camera_proof=HomeCityCameraProof(
                    status=HomeCityCameraStatus.INSUFFICIENT,
                    reason="test",
                    frame_size=(540, 960),
                ),
            ),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "localized"):
            plan_home_city_camera_pan(
                observation=insufficient,
                target=HomeCityObjectId.INSTITUTE,
            )

    def test_unqualified_target_is_rejected(self) -> None:
        with self.assertRaisesRegex(SelectorResolutionError, "no camera-qualified target"):
            plan_home_city_camera_pan(
                observation=_observation(),
                target=HomeCityObjectId.CASTLE,
            )

    def test_vertical_pan_uses_the_reviewed_safe_lane(self) -> None:
        # Institute objects visible -> the castle-utility courtyard lane.
        target = _measured_object(
            HomeCityObjectId.INSTITUTE,
            bounds=Bounds(165, 890, 30, 24),
            action_point=(180, 900),
            action_bounds=Bounds(170, 892, 20, 20),
        )
        action = plan_home_city_camera_pan(
            observation=_observation(objects=(target,)),
            target=HomeCityObjectId.INSTITUTE,
        )
        self.assertAlmostEqual(0.69, action.start_x_ratio)
        self.assertAlmostEqual(0.69, action.end_x_ratio)

    def test_lower_tower_pan_uses_translated_ground_instead_of_blacksmith(self) -> None:
        """The observed lower-city lane must avoid the Blacksmith body."""
        target = _measured_object(
            HomeCityObjectId.INSTITUTE,
            bounds=Bounds(420, 107, 48, 45),
            action_point=(434, 115),
            action_bounds=Bounds(425, 110, 20, 20),
        )
        for translation_x in (-532, -600):
            with self.subTest(translation_x=translation_x):
                action = plan_home_city_camera_pan(
                    observation=_observation(
                        translation=(translation_x, -840), objects=(target,),
                    ),
                    target=HomeCityObjectId.INSTITUTE,
                )
                self.assertEqual("down", action.direction)
                self.assertAlmostEqual((1072 + translation_x) / 900, action.start_x_ratio)
                self.assertEqual(action.start_x_ratio, action.end_x_ratio)

    def test_ground_lane_does_not_extend_beyond_its_observed_vertical_extent(self) -> None:
        target = _measured_object(
            HomeCityObjectId.INSTITUTE,
            bounds=Bounds(165, 890, 30, 24),
            action_point=(180, 900),
            action_bounds=Bounds(170, 892, 20, 20),
        )
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-532, -840), objects=(target,)),
            target=HomeCityObjectId.INSTITUTE,
        )
        self.assertAlmostEqual(0.69, action.start_x_ratio)
        self.assertAlmostEqual(0.69, action.end_x_ratio)

    def test_campaign_at_northern_camera_descends_to_corridor_first(self) -> None:
        """Horizontal acquisition off-corridor would outrun the landmark catalog."""
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-532, 222)),
            target=HomeCityObjectId.CAMPAIGN,
        )

        # Corridor aim -709 from camera row 222 requires image motion -931.
        self.assertEqual("up", action.direction)
        self.assertEqual("pan_home_city_camera_campaign_y", action.reason)
        self.assertAlmostEqual(931 / (1600 * 2.33), action.distance_ratio, places=2)
        self.assertTrue(action.observe_after)

    def test_campaign_below_corridor_moves_up_into_the_band(self) -> None:
        """A camera just below the corridor steps back up toward -709."""
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-700, -880)),
            target=HomeCityObjectId.CAMPAIGN,
        )

        # A 0.10 minimum would overshoot the entire corridor and reverse again.
        self.assertEqual("down", action.direction)
        self.assertEqual("pan_home_city_camera_campaign_y", action.reason)
        self.assertAlmostEqual(171 / (1600 * 2.33), action.distance_ratio)

    def test_campaign_near_corridor_edge_does_not_force_an_overshooting_step(self) -> None:
        """A short correction remains proportional on either side of the corridor."""
        for source_y in (-600, -880):
            with self.subTest(source_y=source_y):
                action = plan_home_city_camera_pan(
                    observation=_observation(translation=(-700, source_y)),
                    target=HomeCityObjectId.CAMPAIGN,
                )
                self.assertLess(action.distance_ratio, 0.10)
                signed_motion = action.distance_ratio * 1600 * 2.33
                if action.direction == "up":
                    signed_motion = -signed_motion
                planned_y = source_y + signed_motion
                self.assertGreaterEqual(planned_y, -850)
                self.assertLessEqual(planned_y, -620)
                # A fresh measurement in the corridor resumes horizontal work;
                # the runtime never promotes this estimate to camera evidence.
                next_action = plan_home_city_camera_pan(
                    observation=_observation(translation=(-700, round(planned_y))),
                    target=HomeCityObjectId.CAMPAIGN,
                )
                self.assertEqual("left", next_action.direction)

    def test_campaign_in_corridor_pans_horizontally_toward_the_body(self) -> None:
        """Inside the measured corridor the ordinary horizontal plan applies."""
        action = plan_home_city_camera_pan(
            observation=_observation(translation=(-1000, -709)),
            target=HomeCityObjectId.CAMPAIGN,
        )

        # Atlas action anchor (2083,1121) projects to reference (1083,412): only
        # horizontal acquisition is needed.
        self.assertEqual("left", action.direction)
        self.assertEqual("pan_home_city_camera_campaign_x", action.reason)
        self.assertAlmostEqual(633 / (900 * 2.33), action.distance_ratio, places=2)

    def test_campaign_body_above_band_pans_down_without_corridor_override(self) -> None:
        """A matched body needing only vertical motion keeps the ordinary plan."""
        target = _measured_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(353, 145, 90, 42),
            action_point=(395, 167),
            action_bounds=Bounds(389, 161, 13, 13),
        )
        action = plan_home_city_camera_pan(
            observation=_observation(objects=(target,), translation=(-1423, -843)),
            target=HomeCityObjectId.CAMPAIGN,
        )

        # Reference point (658,278) sits above the band; content must move down.
        self.assertEqual("down", action.direction)
        self.assertEqual("pan_home_city_camera_campaign_y", action.reason)

    def test_campaign_in_band_body_needs_no_pan_step(self) -> None:
        target = _measured_object(
            HomeCityObjectId.CAMPAIGN,
            bounds=Bounds(78, 225, 90, 42),
            action_point=(121, 247),
            action_bounds=Bounds(114, 241, 13, 13),
        )
        with self.assertRaisesRegex(SelectorResolutionError, "no pan is needed"):
            plan_home_city_camera_pan(
                observation=_observation(objects=(target,), translation=(-1882, -709)),
                target=HomeCityObjectId.CAMPAIGN,
            )


if __name__ == "__main__":
    unittest.main()
