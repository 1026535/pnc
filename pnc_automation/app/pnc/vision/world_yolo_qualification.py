"""Training-owner contract for the exact World YOLO model accepted by navigation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType

from pnc_automation.app.pnc.domain.observation import SpatialObjectKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType


@dataclass(frozen=True, slots=True)
class WorldYoloClassInteraction:
    """One reviewed click policy and expected read-only destination for a YOLO class."""

    point_ratio: tuple[float, float]
    expected_screen: ScreenType
    review_ref: str

    def __post_init__(self) -> None:
        """Keep interaction geometry explicit and strictly inside a detection box."""

        if (
            not isinstance(self.point_ratio, tuple)
            or len(self.point_ratio) != 2
            or any(
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 < value < 1
                for value in self.point_ratio
            )
        ):
            raise ValueError("World YOLO interaction point ratios must be finite values inside (0, 1).")
        if not isinstance(self.expected_screen, ScreenType) or self.expected_screen == ScreenType.UNKNOWN:
            raise ValueError("World YOLO interaction requires a known destination screen.")
        if not self.review_ref.strip():
            raise ValueError("World YOLO interaction requires a review reference.")


@dataclass(frozen=True, slots=True)
class WorldYoloInteractionQualification:
    """Pins actionable geometry to one exact reviewed model and ROI revision."""

    model_sha256: str
    roi_version: str
    classes: Mapping[str, WorldYoloClassInteraction]

    def __post_init__(self) -> None:
        """Freeze the class policy and reject incomplete model identity."""

        if len(self.model_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.model_sha256):
            raise ValueError("World YOLO interaction requires a lowercase SHA-256 model identity.")
        if not self.roi_version.strip():
            raise ValueError("World YOLO interaction requires a reviewed ROI version.")
        if not self.classes:
            raise ValueError("World YOLO interaction requires at least one reviewed class.")
        for label, policy in self.classes.items():
            if not label.strip() or not isinstance(policy, WorldYoloClassInteraction):
                raise TypeError("World YOLO interaction classes require typed policies.")
        object.__setattr__(self, "classes", MappingProxyType(dict(self.classes)))


@dataclass(frozen=True, slots=True)
class WorldYoloQualification:
    """One reviewed model identity, inference settings, and approved class map."""

    model_sha256: str
    class_names: tuple[str, ...]
    confidence_threshold: float
    nms_iou_threshold: float
    roi_version: str
    qualified_class_map: Mapping[str, SpatialObjectKind] = field(default_factory=dict)
    review_ref: str | None = None

    def __post_init__(self) -> None:
        """Freeze the allowlist so runtime consumers share an immutable decision."""

        if len(self.model_sha256) != 64 or any(char not in "0123456789abcdef" for char in self.model_sha256):
            raise ValueError("World YOLO qualification requires a lowercase SHA-256 model identity.")
        if not self.class_names or len(set(self.class_names)) != len(self.class_names):
            raise ValueError("World YOLO qualification requires distinct ordered class names.")
        if not self.roi_version.strip():
            raise ValueError("World YOLO qualification requires a reviewed ROI version.")
        if self.qualified_class_map and (self.review_ref is None or not self.review_ref.strip()):
            raise ValueError("Qualified World YOLO classes require an acceptance review reference.")
        for setting in (self.confidence_threshold, self.nms_iou_threshold):
            if (
                isinstance(setting, bool)
                or not isinstance(setting, (float, int))
                or not math.isfinite(setting)
                or not 0 <= setting <= 1
            ):
                raise ValueError("World YOLO qualification thresholds must be finite values in [0, 1].")
        for label, kind in self.qualified_class_map.items():
            if label not in self.class_names:
                raise ValueError(f"Qualified World YOLO label is absent from the model: {label}")
            if not isinstance(kind, SpatialObjectKind):
                raise TypeError("Qualified World YOLO mappings require SpatialObjectKind values.")
        object.__setattr__(self, "qualified_class_map", MappingProxyType(dict(self.qualified_class_map)))


# Training-owner review permits Castle observation publication only. It does
# not qualify a tap point, detail identity, or any other model class.
WORLD_YOLO_QUALIFICATION = WorldYoloQualification(
    model_sha256="225f4c6f423d887bf116cc8b637ecd49d1cf10e8249a681d0a6b76f502463552",
    class_names=(
        "monster",
        "farm",
        "castle",
        "hell_fortress",
        "border_stone",
        "castle_away_marker",
        "alliance_fort",
        "gate_of_the_abyss",
        "alliance_warehouse",
        "alliance_infirmary",
        "treasure_goblin",
        "lumber_camp",
        "iron_mine",
        "gold_mine",
        "diamond_mine",
        "alliance_farm",
        "alliance_lumber_camp",
    ),
    confidence_threshold=0.35,
    nms_iou_threshold=0.7,
    roi_version="v19_center_20260922",
    qualified_class_map={"castle": SpatialObjectKind.CASTLE},
    review_ref="v19_consultation_20260922/castle_observation_evidence_review.json",
)
