"""Measured Home-city camera localization from reviewed scene landmarks.

One prepared frame at the atlas reference size is matched against a small
package-data landmark catalog.  At least three accepted correspondences from at
least two independent scene groups must agree on a single image translation
within tolerance before a camera proof is published.  Institute-correlated
crops share one group so they cannot outvote contradictory evidence, and HUD,
nameplate, focus-pin, or promo material is never part of the catalog.

The atlas-to-reference offset is the accepted Castle / Infantry Barracks
calibration basis: measured reference nameplate centers (458, 847) and
(129, 1122) against catalog coordinates (991, 625) and (660, 899) resolve to
(-532, +222) within about one pixel.  The offset maps canonical atlas
coordinates into the authored reference view, so a landmark authored at
reference position ``p`` appears in the current frame's reference space at
``p + image_translation`` and an atlas point ``a`` projects to
``a + (offset + image_translation)``.  ``HomeCityCameraProof.translation``
publishes that combined atlas-to-frame value.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
    home_city_object_definition,
    home_city_object_id_from_metadata,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraEvidence,
    HomeCityCameraProof,
    HomeCityCameraStatus,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialObjectSourceKind,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

HOME_CITY_CAMERA_REFERENCE_SIZE = (900, 1600)
HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET = (-532, 222)
_CAMERA_DATA_DIR = Path(__file__).resolve().parent / "data" / "home_city_camera"
_CAMERA_CONSENSUS_TOLERANCE_PX = 3
_CAMERA_MIN_MATCHES = 3
_CAMERA_MIN_GROUPS = 2


@dataclass(frozen=True, slots=True)
class HomeCityCameraLandmark:
    """One authored scene crop and its position in the reference view."""

    id: str
    group_id: str
    file_name: str
    reference_bounds: Bounds
    min_score: float


@dataclass(frozen=True, slots=True)
class HomeCityCameraTarget:
    """One evidence-backed body crop with measured current-frame action geometry."""

    object_id: HomeCityObjectId
    landmark_id: str
    file_name: str
    reference_bounds: Bounds
    reference_action_bounds: Bounds
    reference_action_point: tuple[int, int]
    min_score: float
    max_projection_error: int

    def atlas_action_point(self) -> tuple[int, int]:
        """Returns the verified action point expressed in atlas coordinates."""

        offset_x, offset_y = HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET
        return (
            self.reference_action_point[0] - offset_x,
            self.reference_action_point[1] - offset_y,
        )


@dataclass(frozen=True, slots=True)
class HomeCityCameraTargetMatch:
    """One projection-agreed body match with its measured frame-space action geometry."""

    target: HomeCityCameraTarget
    bounds: Bounds
    action_bounds: Bounds
    action_point: tuple[int, int]
    score: float
    projection_error: float


@dataclass(frozen=True, slots=True)
class HomeCityCameraCatalog:
    """Immutable package-data landmark and target definitions for the Home camera."""

    landmarks: tuple[HomeCityCameraLandmark, ...]
    targets: tuple[HomeCityCameraTarget, ...]
    reference_size: tuple[int, int]
    atlas_to_reference_offset: tuple[int, int]
    anchor_object_ids: tuple[HomeCityObjectId, ...]
    reference_source: str
    data_dir: Path

    def template_path(self, file_name: str) -> Path:
        """Returns the resolved package-data path for one authored template."""

        return (self.data_dir / file_name).resolve()

    def target_for(self, object_id: HomeCityObjectId) -> HomeCityCameraTarget | None:
        """Returns the camera-qualified target spec for one canonical object id."""

        for target in self.targets:
            if target.object_id == object_id:
                return target
        return None


@dataclass(frozen=True, slots=True)
class _CameraVote:
    """One above-floor landmark correspondence before consensus fitting."""

    landmark: HomeCityCameraLandmark
    bounds: Bounds
    score: float
    translation: tuple[float, float]


@lru_cache(maxsize=1)
def load_home_city_camera_catalog() -> HomeCityCameraCatalog:
    """Loads the reviewed landmark catalog once and validates every packaged crop."""

    institute_body_bounds = Bounds(700, 1240, 80, 75)
    tower_body_bounds = Bounds(240, 1620, 130, 140)
    campaign_body_bounds = Bounds(1480, 1306, 150, 70)
    catalog = HomeCityCameraCatalog(
        landmarks=(
            HomeCityCameraLandmark(
                id="p2_institute_facade",
                group_id="institute_structure",
                file_name="p2_institute_facade.png",
                reference_bounds=Bounds(615, 1185, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p3_institute_base_left",
                group_id="institute_structure",
                file_name="p3_institute_base_left.png",
                reference_bounds=Bounds(585, 1250, 105, 70),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p4_garden_terrace",
                group_id="garden_terrace",
                file_name="p4_garden_terrace.png",
                reference_bounds=Bounds(583, 1071, 90, 110),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p5_plaza_low",
                group_id="plaza_low",
                file_name="p5_plaza_low.png",
                reference_bounds=Bounds(610, 1345, 120, 45),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="t6_plaza_south",
                group_id="plaza_low",
                file_name="t6_plaza_south.png",
                reference_bounds=Bounds(540, 1340, 130, 50),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="p6_path_right",
                group_id="institute_structure",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="t5_barracks_roofs",
                group_id="barracks_roofs",
                file_name="t5_barracks_roofs.png",
                reference_bounds=Bounds(121, 990, 140, 110),
                min_score=0.80,
            ),
            HomeCityCameraLandmark(
                id="tower_of_trial_body",
                group_id="tower_structure",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="blacksmith_structure",
                group_id="blacksmith_structure",
                file_name="blacksmith_structure.png",
                reference_bounds=Bounds(640, 1845, 120, 130),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="southern_courtyard",
                group_id="southern_courtyard",
                file_name="southern_courtyard.png",
                reference_bounds=Bounds(640, 1530, 100, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_aqueduct",
                group_id="east_fortification",
                file_name="east_aqueduct.png",
                reference_bounds=Bounds(1451, 1505, 120, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_parapet",
                group_id="east_fortification",
                file_name="east_parapet.png",
                reference_bounds=Bounds(1651, 1715, 80, 60),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_cliff_rock",
                group_id="east_cliff",
                file_name="east_cliff_rock.png",
                reference_bounds=Bounds(1681, 1825, 80, 140),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="east_rock_trees",
                group_id="east_cliff",
                file_name="east_rock_trees.png",
                reference_bounds=Bounds(1521, 1965, 120, 100),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="ridge_wall",
                group_id="east_fortification",
                file_name="ridge_wall.png",
                reference_bounds=Bounds(1117, 1365, 100, 130),
                min_score=0.90,
            ),
            HomeCityCameraLandmark(
                id="alliance_hall_structure",
                group_id="alliance_hall_structure",
                file_name="alliance_hall_structure.png",
                reference_bounds=Bounds(1197, 1675, 140, 80),
                min_score=0.90,
            ),
        ),
        targets=(
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.INSTITUTE,
                landmark_id="p6_path_right",
                file_name="p6_path_right.png",
                reference_bounds=institute_body_bounds,
                reference_action_bounds=Bounds(712, 1244, 30, 18),
                reference_action_point=(724, 1253),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.TOWER_OF_TRIAL,
                landmark_id="tower_of_trial_body",
                file_name="tower_of_trial_body.png",
                reference_bounds=tower_body_bounds,
                reference_action_bounds=Bounds(272, 1680, 56, 50),
                reference_action_point=(299, 1714),
                min_score=0.90,
                max_projection_error=8,
            ),
            HomeCityCameraTarget(
                object_id=HomeCityObjectId.CAMPAIGN,
                landmark_id="campaign_portal_body",
                file_name="campaign_portal_body.png",
                reference_bounds=campaign_body_bounds,
                reference_action_bounds=Bounds(1540, 1332, 22, 22),
                reference_action_point=(1551, 1343),
                # The independent post-pan live body scores .922; retained
                # non-Home negatives stay below .40. Projection agreement and
                # independent camera consensus remain mandatory.
                min_score=0.90,
                max_projection_error=8,
            ),
        ),
        reference_size=HOME_CITY_CAMERA_REFERENCE_SIZE,
        atlas_to_reference_offset=HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
        anchor_object_ids=(
            HomeCityObjectId.CASTLE,
            HomeCityObjectId.INFANTRY_BARRACKS,
        ),
        reference_source=(
            "20260915T160615Z_core_20260915T160413Z_018f500d_0025_06_fresh_fresh_home_for_pan.png"
        ),
        data_dir=_CAMERA_DATA_DIR,
    )
    for item in (*catalog.landmarks, *catalog.targets):
        path = catalog.template_path(item.file_name)
        if not path.is_file():
            raise SelectorResolutionError(
                "Home-camera catalog template is missing from package data.",
                template=str(path),
            )
        with Image.open(path) as template:
            if template.size != (item.reference_bounds.width, item.reference_bounds.height):
                raise SelectorResolutionError(
                    "Home-camera catalog template size does not match its reference bounds.",
                    template=str(path),
                    expected=(item.reference_bounds.width, item.reference_bounds.height),
                    actual=template.size,
                )
    for target in catalog.targets:
        if not target.reference_bounds.contains_bounds(target.reference_action_bounds):
            raise SelectorResolutionError(
                "Camera target action bounds must stay inside the authored body crop.",
                landmark_id=target.landmark_id,
            )
        if not target.reference_action_bounds.contains_point(target.reference_action_point):
            raise SelectorResolutionError(
                "Camera target action bounds must contain the verified action point.",
                landmark_id=target.landmark_id,
            )
    return catalog


def home_city_camera_target(object_id: HomeCityObjectId) -> HomeCityCameraTarget | None:
    """Returns the camera-qualified target spec for one canonical object id."""

    return load_home_city_camera_catalog().target_for(object_id)


class HomeCityCameraLocalizer:
    """Matches the shared scene-landmark catalog on one prepared frame per call."""

    def __init__(
        self,
        *,
        matcher: OpenCvTemplateMatcher,
        catalog: HomeCityCameraCatalog | None = None,
    ) -> None:
        self._matcher = matcher
        self._catalog = catalog if catalog is not None else load_home_city_camera_catalog()

    @property
    def catalog(self) -> HomeCityCameraCatalog:
        """Returns the loaded landmark/target catalog."""

        return self._catalog

    def prepare_frame(self, image: Image.Image) -> PreparedFrame | None:
        """Normalizes one screenshot at the atlas reference size, or None when unsupported."""

        return self._matcher.prepare_frame(
            image,
            reference_size=self._catalog.reference_size,
        )

    def localize(self, image: Image.Image | PreparedFrame) -> HomeCityCameraProof:
        """Publishes the current-frame camera verdict from scene correspondences only."""

        frame = self._coerce_frame(image)
        frame_size = frame.original_size if frame is not None else image.size
        if frame is None:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.UNSUPPORTED,
                reason="unsupported_frame_layout",
                frame_size=frame_size,
            )
        votes = self._collect_votes(frame)
        if not votes:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason="no_landmark_correspondences",
                frame_size=frame_size,
            )
        cluster = self._best_consensus_cluster(votes)
        cluster_groups = frozenset(vote.landmark.group_id for vote in cluster)
        if len(cluster) < _CAMERA_MIN_MATCHES or len(cluster_groups) < _CAMERA_MIN_GROUPS:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason=(
                    "insufficient_independent_landmark_groups"
                    if len(cluster_groups) < _CAMERA_MIN_GROUPS
                    else "insufficient_landmark_correspondences"
                ),
                frame_size=frame_size,
                evidence=tuple(self._evidence_for(cluster, self._consensus_translation(cluster))),
            )
        consensus = self._consensus_translation(cluster)
        remaining = tuple(vote for vote in votes if vote not in cluster)
        rival = self._best_consensus_cluster(remaining)
        rival_groups = frozenset(vote.landmark.group_id for vote in rival)
        if len(rival) >= _CAMERA_MIN_MATCHES and len(rival_groups) >= _CAMERA_MIN_GROUPS:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.AMBIGUOUS,
                reason="conflicting_landmark_clusters",
                frame_size=frame_size,
                evidence=tuple(self._evidence_for(cluster, consensus)),
            )
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        return HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="consensus_landmark_cluster",
            translation=(
                int(round(consensus[0])) + offset_x,
                int(round(consensus[1])) + offset_y,
            ),
            reference_size=self._catalog.reference_size,
            frame_size=frame.original_size,
            evidence=tuple(self._evidence_for(cluster, consensus)),
            matched_group_ids=cluster_groups,
        )

    def match_target(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        translation: tuple[int, int],
    ) -> HomeCityCameraTargetMatch | None:
        """Returns one body match only when it agrees with the localized projection."""

        frame = self._coerce_frame(image)
        if frame is None:
            return None
        image_translation = (
            translation[0] - self._catalog.atlas_to_reference_offset[0],
            translation[1] - self._catalog.atlas_to_reference_offset[1],
        )
        hit = self._matcher.find_best_match(
            frame,
            self._catalog.template_path(target.file_name),
            threshold=target.min_score,
        )
        if hit is None:
            return None
        match_reference = self._reference_bounds(hit.bounds, frame)
        projection_error = math.dist(
            (match_reference.x, match_reference.y),
            (
                target.reference_bounds.x + image_translation[0],
                target.reference_bounds.y + image_translation[1],
            ),
        )
        if projection_error > target.max_projection_error:
            return None
        scale_x = frame.original_size[0] / frame.reference_size[0]
        scale_y = frame.original_size[1] / frame.reference_size[1]
        origin_delta = (
            match_reference.x - target.reference_bounds.x,
            match_reference.y - target.reference_bounds.y,
        )

        def to_frame_point(reference_point: tuple[float, float]) -> tuple[int, int]:
            return (
                int(round(reference_point[0] * scale_x)),
                int(round(reference_point[1] * scale_y)),
            )

        action_point = to_frame_point(
            (
                target.reference_action_point[0] + origin_delta[0],
                target.reference_action_point[1] + origin_delta[1],
            )
        )
        action_left, action_top = to_frame_point(
            (
                target.reference_action_bounds.x + origin_delta[0],
                target.reference_action_bounds.y + origin_delta[1],
            )
        )
        action_right, action_bottom = to_frame_point(
            (
                target.reference_action_bounds.x
                + target.reference_action_bounds.width
                + origin_delta[0],
                target.reference_action_bounds.y
                + target.reference_action_bounds.height
                + origin_delta[1],
            )
        )
        return HomeCityCameraTargetMatch(
            target=target,
            bounds=hit.bounds,
            action_bounds=Bounds(
                action_left,
                action_top,
                max(1, action_right - action_left),
                max(1, action_bottom - action_top),
            ),
            action_point=action_point,
            score=hit.confidence,
            projection_error=projection_error,
        )

    def matched_target_objects(
        self,
        frame: PreparedFrame,
        *,
        proof: HomeCityCameraProof,
    ) -> tuple[DetectedSpatialObject, ...]:
        """Builds typed building objects for every projection-agreed body match."""

        if not proof.localized or proof.translation is None or proof.frame_size is None:
            return ()
        objects: list[DetectedSpatialObject] = []
        viewport_bounds = Bounds(0, 0, *proof.frame_size)
        for target in self._catalog.targets:
            match = self.match_target(frame, target, translation=proof.translation)
            if match is None:
                continue
            metadata = build_home_city_object_metadata(target.object_id)
            metadata.update(
                {
                    "detection_source": "camera_template",
                    "camera_landmark_id": target.landmark_id,
                    "camera_match_score": round(match.score, 4),
                    "camera_projection_error": round(match.projection_error, 2),
                }
            )
            objects.append(
                DetectedSpatialObject(
                    kind=SpatialObjectKind.HOME_BUILDING,
                    bounds=match.bounds,
                    relationship=SpatialObjectRelationship.SELF,
                    name_text=home_city_object_definition(target.object_id).display_name,
                    action_point=match.action_point,
                    action_bounds=match.action_bounds,
                    viewport_offset=(
                        match.bounds.center()[0] - viewport_bounds.center()[0],
                        match.bounds.center()[1] - viewport_bounds.center()[1],
                    ),
                    viewport_offset_ratio=(
                        (match.bounds.center()[0] - viewport_bounds.center()[0])
                        / max(viewport_bounds.width, 1),
                        (match.bounds.center()[1] - viewport_bounds.center()[1])
                        / max(viewport_bounds.height, 1),
                    ),
                    source_kind=SpatialObjectSourceKind.TEMPLATE,
                    metadata=metadata,
                )
            )
        return tuple(objects)

    def _coerce_frame(self, image: Image.Image | PreparedFrame) -> PreparedFrame | None:
        """Reuses an already normalized frame or prepares one at the reference size."""

        if isinstance(image, PreparedFrame):
            if image.reference_size != self._catalog.reference_size:
                raise SelectorResolutionError(
                    "Home-camera frames must be prepared at the catalog reference size.",
                    reference_size=image.reference_size,
                    expected=self._catalog.reference_size,
                )
            return image
        return self.prepare_frame(image)

    def _collect_votes(self, frame: PreparedFrame) -> tuple[_CameraVote, ...]:
        """Matches every landmark once and keeps only above-floor correspondences."""

        votes: list[_CameraVote] = []
        for landmark in self._catalog.landmarks:
            hit = self._matcher.find_best_match(
                frame,
                self._catalog.template_path(landmark.file_name),
                threshold=0.0,
            )
            if hit is None or hit.confidence < landmark.min_score:
                continue
            match_reference = self._reference_bounds(hit.bounds, frame)
            votes.append(
                _CameraVote(
                    landmark=landmark,
                    bounds=hit.bounds,
                    score=hit.confidence,
                    translation=(
                        match_reference.x - landmark.reference_bounds.x,
                        match_reference.y - landmark.reference_bounds.y,
                    ),
                )
            )
        return tuple(votes)

    def _reference_bounds(self, bounds: Bounds, frame: PreparedFrame) -> Bounds:
        """Converts original-frame match bounds back into normalized reference units."""

        scale_x = frame.reference_size[0] / frame.original_size[0]
        scale_y = frame.reference_size[1] / frame.original_size[1]
        return Bounds(
            x=int(round(bounds.x * scale_x)),
            y=int(round(bounds.y * scale_y)),
            width=max(1, int(round(bounds.width * scale_x))),
            height=max(1, int(round(bounds.height * scale_y))),
        )

    def _best_consensus_cluster(self, votes: tuple[_CameraVote, ...]) -> tuple[_CameraVote, ...]:
        """Selects the strongest translation cluster deterministically by seed consensus."""

        best: tuple[tuple[int, int, float], tuple[_CameraVote, ...]] | None = None
        for seed in votes:
            members = self._agreeing_members(votes, seed.translation)
            consensus = self._consensus_translation(members)
            members = self._agreeing_members(members, consensus)
            groups = frozenset(vote.landmark.group_id for vote in members)
            key = (len(members), len(groups), sum(vote.score for vote in members))
            if best is None or key > best[0]:
                best = (key, members)
        return () if best is None else best[1]

    def _agreeing_members(
        self,
        votes: tuple[_CameraVote, ...],
        translation: tuple[float, float],
    ) -> tuple[_CameraVote, ...]:
        """Keeps votes whose translation agrees with the candidate within tolerance."""

        return tuple(
            vote
            for vote in votes
            if abs(vote.translation[0] - translation[0]) <= _CAMERA_CONSENSUS_TOLERANCE_PX
            and abs(vote.translation[1] - translation[1]) <= _CAMERA_CONSENSUS_TOLERANCE_PX
        )

    def _consensus_translation(self, votes: tuple[_CameraVote, ...]) -> tuple[float, float]:
        """Fits the cluster translation as the component-wise median of its members."""

        return (
            statistics.median(vote.translation[0] for vote in votes),
            statistics.median(vote.translation[1] for vote in votes),
        )

    def _evidence_for(
        self,
        votes: tuple[_CameraVote, ...],
        consensus: tuple[float, float],
    ) -> list[HomeCityCameraEvidence]:
        """Publishes matched landmark evidence with its residual against consensus."""

        return [
            HomeCityCameraEvidence(
                landmark_id=vote.landmark.id,
                group_id=vote.landmark.group_id,
                bounds=vote.bounds,
                reference_bounds=vote.landmark.reference_bounds,
                score=vote.score,
                translation=(
                    int(round(vote.translation[0])),
                    int(round(vote.translation[1])),
                ),
                residual=math.dist(vote.translation, consensus),
            )
            for vote in votes
        ]


def merge_camera_target_objects(
    objects: tuple[DetectedSpatialObject, ...],
    camera_objects: tuple[DetectedSpatialObject, ...],
) -> tuple[DetectedSpatialObject, ...]:
    """Merges measured camera targets with OCR objects, one canonical object per id."""

    if not camera_objects:
        return objects
    camera_by_id = {
        object_id: object_
        for object_ in camera_objects
        for object_id in (home_city_object_id_from_metadata(object_.metadata),)
        if object_id is not None
    }
    merged: list[DetectedSpatialObject] = []
    for object_ in objects:
        object_id = home_city_object_id_from_metadata(object_.metadata)
        camera_object = camera_by_id.pop(object_id, None)
        if camera_object is None:
            merged.append(object_)
            continue
        merged.append(
            DetectedSpatialObject(
                kind=camera_object.kind,
                bounds=camera_object.bounds,
                relationship=camera_object.relationship,
                name_text=object_.name_text or camera_object.name_text,
                alliance_tag=camera_object.alliance_tag,
                level=object_.level if object_.level is not None else camera_object.level,
                kingdom=camera_object.kingdom,
                action_point=camera_object.action_point,
                viewport_offset=camera_object.viewport_offset,
                viewport_offset_ratio=camera_object.viewport_offset_ratio,
                estimated_world_coordinate=camera_object.estimated_world_coordinate,
                confirmed_world_coordinate=camera_object.confirmed_world_coordinate,
                action_bounds=camera_object.action_bounds,
                source_kind=camera_object.source_kind,
                metadata={**camera_object.metadata, **{
                    key: value
                    for key, value in object_.metadata.items()
                    if key == "home_city_label"
                }},
            )
        )
    merged.extend(camera_by_id.values())
    return tuple(merged)
