"""Shared core home doubles and fixtures."""

from datetime import UTC, datetime

from pnc_automation.app.automation.engine.navigation_core import NavigationEdge
from pnc_automation.app.pnc.domain.action_requests import SwipeAction, SwipePurpose
from pnc_automation.app.pnc.domain.building_catalog import HomeCityObjectId
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomStatus,
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
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.spatial_navigation import HomeCityCameraPanStep


def home_building_object(
    target: HomeCityObjectId,
    *,
    action_point: tuple[int, int] | None = (270, 520),
) -> DetectedSpatialObject:
    """Build one exact observed home-city building candidate for navigation tests."""

    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=Bounds(220, 470, 100, 100),
        action_point=action_point,
        metadata={"home_city_object_id": target.value},
    )


def measured_building_object(
    target: HomeCityObjectId,
    *,
    bounds: Bounds = Bounds(139, 185, 48, 45),
    action_point: tuple[int, int] = (154, 193),
    action_bounds: Bounds = Bounds(146, 187, 18, 11),
) -> DetectedSpatialObject:
    """Build one camera-verified building object with measured action geometry."""

    return DetectedSpatialObject(
        kind=SpatialObjectKind.HOME_BUILDING,
        bounds=bounds,
        action_point=action_point,
        action_bounds=action_bounds,
        source_kind=SpatialObjectSourceKind.TEMPLATE,
        metadata={"home_city_object_id": target.value},
    )


def camera_home_frame(
    objects: tuple[DetectedSpatialObject, ...] = (),
    *,
    translation: tuple[int, int] = (-532, 222),
    zoom: float = 1.0,
    captured_at: datetime | None = None,
    image_size: tuple[int, int] = (540, 960),
    blocked: bool = False,
    zoom_status: HomeCityZoomStatus = HomeCityZoomStatus.AT_ENDPOINT,
    localized: bool = True,
) -> Observation:
    """Build controlled camera and endpoint evidence for consumer-policy tests.

    The synthetic calibration deliberately supports these fixture dimensions;
    it does not qualify a native resolution or a production gesture profile.
    Tests for missing camera/view evidence use ``home_building_frame`` instead.
    """

    return Observation(
        screen_type=ScreenType.PNC_HOME_CITY,
        visible_elements={},
        spatial_surface=SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
            camera_proof=HomeCityCameraProof(
                status=HomeCityCameraStatus.LOCALIZED if localized else HomeCityCameraStatus.INSUFFICIENT,
                reason="test",
                translation=translation if localized else None,
                zoom=zoom if localized else None,
                frame_size=image_size or (540, 960),
            ),
            home_city_view=HomeCityViewEvidence(
                zoom_status=zoom_status,
                reason="controlled_consumer_fixture",
                calibration_id="test_endpoint",
                zoom_anchor=None,
                frame_size=image_size or (540, 960),
            ),
        ),
        image_size=image_size,
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def home_building_frame(
    objects: tuple[DetectedSpatialObject, ...] = (),
    *,
    captured_at: datetime | None = None,
    image_size: tuple[int, int] | None = (540, 960),
    blocked: bool = False,
) -> Observation:
    """Build one typed Home frame with a canonical camera-relative spatial surface."""

    return Observation(
        screen_type=ScreenType.PNC_HOME_CITY,
        visible_elements={},
        spatial_surface=SpatialSurfaceObservation(
            surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
            viewport=SpatialViewport(addressing_kind=SpatialViewportAddressingKind.CAMERA_RELATIVE),
            objects=objects,
        ),
        image_size=image_size,
        captured_at=captured_at or datetime.now(UTC),
        blocking_popup=blocked,
    )


def qualified_pan_step(
    direction: str,
    *,
    axis: str,
    goal_atlas: tuple[float, float],
    reason: str = "qualified_test_pan",
) -> HomeCityCameraPanStep:
    """Build one lane-qualified measured step for core-policy planner mocks.

    The step carries the planner's independent lane evidence: a typed
    home-camera purpose, exact explicit geometry, and safe bounds that
    contain the whole resolved stroke. Consumer tests mock the planner with
    this shape so the core exercises its bounded dispatch policy, not lane
    qualification itself.
    """

    action = SwipeAction(
        direction=direction,
        purpose=SwipePurpose.HOME_CITY_CAMERA,
        exact_geometry=True,
        safe_bounds=Bounds(150, 250, 620, 920),
        start_x_ratio=0.5,
        start_y_ratio=0.5,
        end_x_ratio=0.4,
        end_y_ratio=0.4,
        reason=reason,
    )
    return HomeCityCameraPanStep(action=action, axis=axis, goal_atlas=goal_atlas)


_MANOR_RETURN_EDGE = NavigationEdge(
    ScreenType.PNC_ILLUSORY_BEAST_MANOR,
    UiElementId.PNC_BACK_BUTTON_TOP_LEFT,
    frozenset({ScreenType.PNC_HOME_CITY}),
)
