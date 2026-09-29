"""Home-city camera catalog, localization, and target publication facade.

The package keeps the historical vision.home_city_camera import path while
giving catalog values, localization, and measured target merging independent
owners.
"""

from .catalog import home_city_camera_target, load_home_city_camera_catalog
from .localization import HomeCityCameraLocalizer
from .models import (
    HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
    HOME_CITY_CAMERA_REFERENCE_SIZE,
    HomeCityCameraCatalog,
    HomeCityCameraLandmark,
    HomeCityCameraTarget,
    HomeCityCameraTargetMatch,
    HomeCityViewNormalization,
    HomeCityZoomAnchorSpec,
    HomeCityZoomEndpointCalibration,
)
from .targets import merge_camera_target_objects

__all__ = [
    "HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET",
    "HOME_CITY_CAMERA_REFERENCE_SIZE",
    "HomeCityCameraCatalog",
    "HomeCityCameraLandmark",
    "HomeCityCameraLocalizer",
    "HomeCityCameraTarget",
    "HomeCityCameraTargetMatch",
    "HomeCityViewNormalization",
    "HomeCityZoomAnchorSpec",
    "HomeCityZoomEndpointCalibration",
    "home_city_camera_target",
    "load_home_city_camera_catalog",
    "merge_camera_target_objects",
]
