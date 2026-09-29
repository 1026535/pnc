"""Typed Home-city camera proof produced by current-frame scene-landmark matching.

The proof carries one measured atlas-to-frame transform (uniform zoom plus
translation) and the independent landmark votes that established it.  Points
project as::

    reference_point = zoom * atlas_point + translation
    point_in_frame  = reference_point * (frame_width / reference_width,
                                         frame_height / reference_height)
    atlas_point     = (reference_point - translation) / zoom

The relative ``zoom`` is a game-camera property measured from landmark
geometry and is separate from the frame-to-reference resolution conversion;
at zoom 1 the transform degenerates to the reviewed V02 translation-only
model.  Translation therefore expresses where one atlas-space point lands
inside the current frame's normalized reference space; it is signed and
intentionally not clamped to the inferred panorama bounds.  Scores are
deterministic template similarity values, never probabilities.  Proof
provenance (frame, screen, layout) is bound by ``observation_provenance`` so
a published proof can never outlive the capture that produced it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.emulator.provenance import FrameRef
from pnc_automation.core.vision.image.models import Bounds


class HomeCityCameraStatus(StrEnum):
    """Disposition of one Home-city camera localization attempt."""

    LOCALIZED = "localized"
    INSUFFICIENT = "insufficient"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class HomeCityCameraEvidence:
    """One accepted scene-landmark correspondence on the current frame."""

    landmark_id: str
    group_id: str
    bounds: Bounds
    reference_bounds: Bounds
    score: float
    translation: tuple[int, int]
    residual: float
    zoom: float

    def __post_init__(self) -> None:
        """Rejects malformed evidence before camera consumers rely on it."""

        if not self.landmark_id or not self.group_id:
            raise SelectorResolutionError(
                "Camera evidence requires a landmark id and an independent scene group.",
                landmark_id=self.landmark_id,
            )
        if (
            len(self.translation) != 2
            or any(type(value) is not int for value in self.translation)
        ):
            raise SelectorResolutionError(
                "Camera evidence translation must be an integer reference-space pair.",
                landmark_id=self.landmark_id,
            )
        if not math.isfinite(self.zoom) or self.zoom <= 0:
            raise SelectorResolutionError(
                "Camera evidence requires a positive finite zoom.",
                landmark_id=self.landmark_id,
            )


@dataclass(frozen=True, slots=True)
class HomeCityCameraProof:
    """Current-frame Home-camera verdict plus the consensus evidence behind it."""

    status: HomeCityCameraStatus
    reason: str
    translation: tuple[int, int] | None = None
    zoom: float | None = None
    reference_size: tuple[int, int] = (900, 1600)
    frame_size: tuple[int, int] | None = None
    evidence: tuple[HomeCityCameraEvidence, ...] = ()
    matched_group_ids: frozenset[str] = frozenset()
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keeps localized proofs honest about the transform they publish."""

        if not isinstance(self.status, HomeCityCameraStatus):
            raise SelectorResolutionError(
                "Home-camera proofs require a typed status.",
                status=self.status,
            )
        if self.status == HomeCityCameraStatus.LOCALIZED:
            if (
                self.translation is None
                or len(self.translation) != 2
                or any(type(value) is not int for value in self.translation)
            ):
                raise SelectorResolutionError(
                    "A localized Home camera requires an integer translation pair."
                )
            if self.zoom is None or not math.isfinite(self.zoom) or self.zoom <= 0:
                raise SelectorResolutionError(
                    "A localized Home camera requires a positive finite zoom."
                )
            if self.frame_size is None:
                raise SelectorResolutionError(
                    "A localized Home camera requires the producing frame size."
                )
        elif self.translation is not None or self.zoom is not None:
            raise SelectorResolutionError(
                "Only a localized Home camera may publish a transform.",
                status=self.status,
            )

    @property
    def localized(self) -> bool:
        """Returns whether this proof carries a usable measured transform."""

        return self.status == HomeCityCameraStatus.LOCALIZED

    def project_atlas_to_reference(self, atlas_point: tuple[int, int]) -> tuple[float, float]:
        """Projects one atlas-space point into the frame's reference space."""

        if self.translation is None or self.zoom is None:
            raise SelectorResolutionError(
                "Camera projection requires a localized proof.",
                status=self.status,
            )
        return (
            self.zoom * atlas_point[0] + self.translation[0],
            self.zoom * atlas_point[1] + self.translation[1],
        )

    def project_reference_to_atlas(self, reference_point: tuple[float, float]) -> tuple[float, float]:
        """Inverse-projects one reference-space point back into atlas units."""

        if self.translation is None or self.zoom is None:
            raise SelectorResolutionError(
                "Camera inverse projection requires a localized proof.",
                status=self.status,
            )
        return (
            (reference_point[0] - self.translation[0]) / self.zoom,
            (reference_point[1] - self.translation[1]) / self.zoom,
        )

    def project_to_frame(self, atlas_point: tuple[int, int]) -> tuple[int, int]:
        """Projects one atlas-space point into current-frame pixels."""

        if self.translation is None or self.zoom is None or self.frame_size is None:
            raise SelectorResolutionError(
                "Camera projection requires a localized proof with a frame size.",
                status=self.status,
            )
        scale_x = self.frame_size[0] / self.reference_size[0]
        scale_y = self.frame_size[1] / self.reference_size[1]
        reference_x, reference_y = self.project_atlas_to_reference(atlas_point)
        return (
            int(round(reference_x * scale_x)),
            int(round(reference_y * scale_y)),
        )


class HomeCityZoomStatus(StrEnum):
    """Disposition of the current frame's measured zoom against the endpoint."""

    AT_ENDPOINT = "at_endpoint"
    NOT_AT_ENDPOINT = "not_at_endpoint"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class HomeCityCameraScanMode(StrEnum):
    """Select the camera evidence needed by one Home observation."""

    UNRESTRICTED = "unrestricted"
    ENDPOINT_PROBE = "endpoint_probe"
    NORMALIZED_ENDPOINT = "normalized_endpoint"


@dataclass(frozen=True, slots=True)
class HomeCityZoomAnchor:
    """One qualified pre-normalization gesture point in native frame pixels.

    ``bounds`` is the directly matched scenery patch's current rectangle and
    ``point`` is the calibrated dispatch point inside it; both come from the
    same measured patch placement so the point can never drift off the
    feature the qualification evidence was measured on.  Qualification is
    scoped to the input gesture the named spec's provenance establishes --
    currently wheel/scroll only; an anchor is never evidence that the point
    is a safe tap, a collider-free region, or a drag lane.
    """

    point: tuple[int, int]
    bounds: Bounds
    qualification_id: str

    def __post_init__(self) -> None:
        """A published anchor must name its qualification and keep its point inside."""

        if not self.qualification_id:
            raise SelectorResolutionError(
                "A zoom anchor requires a qualified anchor specification id."
            )
        if (
            len(self.point) != 2
            or any(type(value) is not int for value in self.point)
        ):
            raise SelectorResolutionError(
                "A zoom anchor point must be an integer frame-space pair.",
                qualification_id=self.qualification_id,
            )
        if not self.bounds.contains_point(self.point):
            raise SelectorResolutionError(
                "A zoom anchor point must lie inside its native bounds.",
                qualification_id=self.qualification_id,
            )


@dataclass(frozen=True, slots=True)
class HomeCityViewEvidence:
    """Current-frame Home view verdict: measured zoom class plus gesture anchor.

    The zoom status comes only from the current fixed-landmark scale evidence
    carried by the enclosing ``camera_proof``; the anchor is located on this
    frame independently of pose.  ``reason`` is diagnostic text -- decisions
    branch on the typed status or the anchor's presence, never on strings.
    """

    zoom_status: HomeCityZoomStatus
    reason: str
    calibration_id: str | None
    zoom_anchor: HomeCityZoomAnchor | None
    frame_size: tuple[int, int]
    frame_ref: FrameRef | None = None
    source_screen: ScreenType | None = None
    source_layout_id: str | None = None

    def __post_init__(self) -> None:
        """Keeps the endpoint verdict honest about its qualification."""

        if not isinstance(self.zoom_status, HomeCityZoomStatus):
            raise SelectorResolutionError(
                "Home view evidence requires a typed zoom status.",
                zoom_status=self.zoom_status,
            )
        if (
            self.zoom_status == HomeCityZoomStatus.AT_ENDPOINT
            and not self.calibration_id
        ):
            raise SelectorResolutionError(
                "An at-endpoint verdict requires a qualified calibration id."
            )
        if (
            len(self.frame_size) != 2
            or any(type(value) is not int or value <= 0 for value in self.frame_size)
        ):
            raise SelectorResolutionError(
                "Home view evidence requires a positive integer frame size.",
                frame_size=self.frame_size,
            )
