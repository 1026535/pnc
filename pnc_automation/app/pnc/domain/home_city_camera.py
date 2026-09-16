"""Typed Home-city camera proof produced by current-frame scene-landmark matching.

The proof carries one measured atlas-to-frame translation plus the independent
landmark votes that established it.  Points project as::

    point_in_frame = (atlas_point + translation) * (frame_width / reference_width,
                                                    frame_height / reference_height)

Translation therefore expresses where one atlas-space point lands inside the
current frame's normalized reference space; it is signed and intentionally not
clamped to the inferred panorama bounds.  Scores are deterministic template
similarity values, never probabilities.  Proof provenance (frame, screen,
layout) is bound by ``observation_provenance`` so a published proof can never
outlive the capture that produced it.
"""

from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class HomeCityCameraProof:
    """Current-frame Home-camera verdict plus the consensus evidence behind it."""

    status: HomeCityCameraStatus
    reason: str
    translation: tuple[int, int] | None = None
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
            if self.frame_size is None:
                raise SelectorResolutionError(
                    "A localized Home camera requires the producing frame size."
                )
        elif self.translation is not None:
            raise SelectorResolutionError(
                "Only a localized Home camera may publish a translation.",
                status=self.status,
            )

    @property
    def localized(self) -> bool:
        """Returns whether this proof carries a usable measured translation."""

        return self.status == HomeCityCameraStatus.LOCALIZED

    def project_to_frame(self, atlas_point: tuple[int, int]) -> tuple[int, int]:
        """Projects one atlas-space point into current-frame pixels."""

        if self.translation is None or self.frame_size is None:
            raise SelectorResolutionError(
                "Camera projection requires a localized proof with a frame size.",
                status=self.status,
            )
        scale_x = self.frame_size[0] / self.reference_size[0]
        scale_y = self.frame_size[1] / self.reference_size[1]
        return (
            int(round((atlas_point[0] + self.translation[0]) * scale_x)),
            int(round((atlas_point[1] + self.translation[1]) * scale_y)),
        )
