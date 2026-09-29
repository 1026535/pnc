"""Home-city camera localization, consensus fitting, and view analysis."""

from __future__ import annotations

import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from threading import RLock

from PIL import Image

from pnc_automation.app.pnc.domain.building_catalog import (
    build_home_city_object_metadata,
    home_city_object_definition,
)
from pnc_automation.app.pnc.domain.home_city_camera import (
    HomeCityCameraEvidence,
    HomeCityCameraProof,
    HomeCityCameraStatus,
    HomeCityViewEvidence,
    HomeCityZoomAnchor,
    HomeCityZoomStatus,
)
from pnc_automation.app.pnc.domain.home_city_slots import HomeCitySlotSelector
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedSpatialObject,
    SpatialObjectKind,
    SpatialObjectRelationship,
    SpatialObjectSourceKind,
)
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.diagnostics.performance import (
    current_performance_run,
    performance_span,
)
from pnc_automation.core.vision.image.models import TemplateMatch
from pnc_automation.core.vision.template.template_matcher import (
    OpenCvTemplateMatcher,
    PreparedFrame,
)

from .catalog import load_home_city_camera_catalog
from .models import (
    HOME_CITY_CAMERA_ATLAS_TO_REFERENCE_OFFSET,
    HOME_CITY_CAMERA_REFERENCE_SIZE,
    HomeCityCameraCatalog,
    HomeCityCameraLandmark,
    HomeCityCameraTarget,
    HomeCityCameraTargetMatch,
    HomeCityViewNormalization,
    HomeCityZoomAnchorSpec,
)

_CAMERA_CONSENSUS_TOLERANCE_PX = 3
_CAMERA_MIN_MATCHES = 3
_CAMERA_MIN_GROUPS = 2
_CAMERA_ZOOM_SEARCH = tuple(round(0.70 + 0.05 * index, 2) for index in range(15))
_CAMERA_ZOOM_MIN = _CAMERA_ZOOM_SEARCH[0]
_CAMERA_ZOOM_MAX = _CAMERA_ZOOM_SEARCH[-1]
_CAMERA_ZOOM_FIT_SNAP = 0.02
_CAMERA_SCALE_SEPARATION_MIN_PX = 100.0
_CAMERA_RIVAL_ZOOM_DELTA = 0.10
_CAMERA_RIVAL_TRANSLATION_PX = 10.0
_CAMERA_SWEEP_WORKERS = 8
_ANCHOR_CORRESPONDENCE_PX = 30.0

@dataclass(frozen=True, slots=True)
class _CameraVote:
    """One above-floor landmark correspondence before consensus fitting.

    ``observed`` is the matched bounds center in reference coordinates and
    ``translation`` the per-vote implied image translation at the evaluated
    ``zoom``; ``bounds`` retains the exact measured rectangle for evidence.
    """

    landmark: HomeCityCameraLandmark
    bounds: Bounds
    score: float
    observed: tuple[float, float]
    translation: tuple[float, float]
    zoom: float


@dataclass(frozen=True, slots=True)
class _CameraHypothesis:
    """One evaluated template scale with its surviving fitted transform."""

    evaluated_zoom: float
    zoom: float
    translation: tuple[float, float]
    votes: tuple[_CameraVote, ...]
    cluster: tuple[_CameraVote, ...]
    groups: frozenset[str]
    separation: float

    @property
    def qualified(self) -> bool:
        """Returns whether the cluster can establish a transform on its own.

        The fitted zoom must stay inside the searched domain: a cluster whose
        positions imply an out-of-domain zoom is honest unresolved evidence,
        not a usable camera measurement.
        """

        return (
            len(self.cluster) >= _CAMERA_MIN_MATCHES
            and len(self.groups) >= _CAMERA_MIN_GROUPS
            and self.separation >= _CAMERA_SCALE_SEPARATION_MIN_PX
            and _CAMERA_ZOOM_MIN <= self.zoom <= _CAMERA_ZOOM_MAX
        )


class HomeCityCameraLocalizer:
    """Matches the shared scene-landmark catalog on one prepared frame per call."""

    def __init__(
        self,
        *,
        matcher: OpenCvTemplateMatcher,
        catalog: HomeCityCameraCatalog | None = None,
        zoom_search: tuple[float, ...] | None = None,
    ) -> None:
        self._matcher = matcher
        self._catalog = catalog if catalog is not None else load_home_city_camera_catalog()
        self._zoom_search = _CAMERA_ZOOM_SEARCH if zoom_search is None else zoom_search
        self._proposal_source: PreparedFrame | None = None
        self._proposal_cache: PreparedFrame | None = None
        self._proposal_lock = RLock()
        if (
            not self._zoom_search
            or any(
                not math.isfinite(zoom) or zoom <= 0.0 for zoom in self._zoom_search
            )
        ):
            raise ValueError("zoom_search must be a non-empty tuple of finite positive scales")

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

    def _proposal_frame(self, frame: PreparedFrame) -> PreparedFrame:
        """Returns one immutable proposal frame for the current prepared frame.

        The observation surface asks for localization and view analysis in
        sequence over the same prepared pixels. Reusing this read-only
        half-resolution representation avoids a second expensive resize while
        retaining frame identity and never caching an observation or OCR
        result.
        """

        with self._proposal_lock:
            if self._proposal_source is frame and self._proposal_cache is not None:
                return self._proposal_cache
            proposal = self._matcher.prepare_proposal_frame(frame)
            self._proposal_source = frame
            self._proposal_cache = proposal
            return proposal

    def localize(self, image: Image.Image | PreparedFrame) -> HomeCityCameraProof:
        """Publishes the current-frame camera verdict from scene correspondences only."""

        with performance_span("home_camera.localize") as measured:
            proof = self._localize(image)
            if measured is not None:
                measured.set_attribute("status", proof.status.value)
                measured.set_attribute("localized", proof.localized)
            return proof

    def localize_endpoint(self, image: Image.Image | PreparedFrame) -> HomeCityCameraProof:
        """Measure one calibrated endpoint-scale hypothesis on the current frame.

        This scoped probe is not the unrestricted ambiguity search. Navigation
        certifies its first endpoint candidate with ``localize`` before use.
        """

        normalization = self._catalog.normalization
        endpoint = None if normalization is None else normalization.endpoint
        frame = self._coerce_frame(image)
        frame_size = (
            image.original_size if isinstance(image, PreparedFrame) else image.size
        )
        if endpoint is None or frame is None:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.UNSUPPORTED,
                reason=(
                    "missing_endpoint_calibration"
                    if endpoint is None else "unsupported_frame_layout"
                ),
                frame_size=frame_size,
            )
        proposal_frame = self._proposal_frame(frame)
        midpoint = sum(endpoint.zoom_interval) / 2
        scale = min(self._zoom_search, key=lambda value: abs(value - midpoint))
        hypothesis = self._evaluate_zoom(frame, proposal_frame, scale)
        if not hypothesis.qualified:
            if self._is_ambiguous(hypothesis):
                return self._ambiguous("conflicting_landmark_clusters", hypothesis, frame_size)
            return self._insufficient([hypothesis], frame_size)
        if self._rival_cluster(hypothesis) is not None:
            return self._ambiguous("conflicting_landmark_clusters", hypothesis, frame_size)
        return self._publish(frame, hypothesis, frame_size, proposal_frame)

    def _localize(self, image: Image.Image | PreparedFrame) -> HomeCityCameraProof:
        """Compute one camera proof; ``localize`` owns optional timing."""

        frame = self._coerce_frame(image)
        frame_size = frame.original_size if frame is not None else image.size
        if frame is None:
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.UNSUPPORTED,
                reason="unsupported_frame_layout",
                frame_size=frame_size,
            )
        # One compatible proposal frame serves every scale hypothesis of
        # this localization; it is immutable prepared data, not matcher state.
        proposal_frame = self._proposal_frame(frame)
        hypotheses = self._evaluate_zoom_sweep(frame, proposal_frame)
        qualifying = [
            hypothesis for hypothesis in hypotheses if hypothesis.qualified
        ]
        if not qualifying:
            for hypothesis in hypotheses:
                if self._is_ambiguous(hypothesis):
                    return self._ambiguous(
                        "conflicting_landmark_clusters", hypothesis, frame_size
                    )
            return self._insufficient(hypotheses, frame_size)
        winner = max(
            qualifying,
            key=lambda hypothesis: (
                len(hypothesis.cluster),
                len(hypothesis.groups),
                sum(vote.score for vote in hypothesis.cluster),
            ),
        )
        for index, first in enumerate(qualifying):
            for second in qualifying[index + 1 :]:
                if self._contradicts(first, second):
                    return self._ambiguous(
                        "conflicting_zoom_hypotheses", winner, frame_size
                    )
        for hypothesis in hypotheses:
            if self._rival_cluster(hypothesis, reference=winner) is not None:
                return self._ambiguous(
                    "conflicting_landmark_clusters", winner, frame_size
                )
        return self._publish(frame, winner, frame_size, proposal_frame)

    def analyze_view(
        self,
        image: Image.Image | PreparedFrame,
        *,
        camera_proof: HomeCityCameraProof,
    ) -> HomeCityViewEvidence:
        """Publishes the current view's measured zoom class plus qualified anchor.

        The zoom verdict consumes the camera proof this frame already
        produced: a localized proof's fixed-landmark correspondences are refit
        without the published grid snap so the verdict answers the scene's
        true measured scale.  Anchor recognition runs on the frame's own
        pixels independently of that pose, so an anchor can publish on a view
        whose camera is still unresolved and a localized view can carry no
        anchor.  Both verdicts apply only to captures at the calibration's
        authored native frame size -- a resized or otherwise unqualified
        capture publishes UNSUPPORTED and no anchor, though the enclosing
        camera proof still localizes and measures bodies normally.
        """

        frame = self._coerce_frame(image)
        if frame is None:
            return HomeCityViewEvidence(
                zoom_status=HomeCityZoomStatus.UNSUPPORTED,
                reason="unsupported_frame_layout",
                calibration_id=None,
                zoom_anchor=None,
                frame_size=image.size,
            )
        if (
            camera_proof.frame_size is not None
            and tuple(camera_proof.frame_size) != tuple(frame.original_size)
        ):
            raise SelectorResolutionError(
                "Home view evidence requires the camera proof produced on the same frame.",
                proof_frame_size=camera_proof.frame_size,
                frame_size=frame.original_size,
            )
        if tuple(camera_proof.reference_size) != tuple(frame.reference_size):
            raise SelectorResolutionError(
                "Home view evidence requires a camera proof at the catalog reference size.",
                proof_reference_size=camera_proof.reference_size,
                reference_size=frame.reference_size,
            )
        normalization = self._catalog.normalization
        if (
            normalization is not None
            and tuple(frame.original_size) != tuple(normalization.native_frame_size)
        ):
            endpoint_id = (
                normalization.endpoint.id
                if normalization.endpoint is not None
                else None
            )
            return HomeCityViewEvidence(
                zoom_status=HomeCityZoomStatus.UNSUPPORTED,
                reason="unsupported_capture_size",
                calibration_id=endpoint_id,
                zoom_anchor=None,
                frame_size=frame.original_size,
            )
        zoom_status, reason, calibration_id = self._classify_zoom(camera_proof)
        return HomeCityViewEvidence(
            zoom_status=zoom_status,
            reason=reason,
            calibration_id=calibration_id,
            zoom_anchor=self._match_zoom_anchor(frame),
            frame_size=frame.original_size,
        )

    def _evaluate_zoom_sweep(
        self, frame: PreparedFrame, proposal_frame: PreparedFrame
    ) -> list[_CameraHypothesis]:
        """Evaluates every configured scale, bounded workers when sweeping.

        Fixed-landmark evaluation is read-only over the immutable prepared
        frames and the lock-guarded matcher caches, so concurrent evaluation
        is deterministic; results stay in configured grid order.
        """

        zoom_search = self._zoom_search
        if len(zoom_search) == 1:
            return [self._evaluate_zoom_with_span(frame, proposal_frame, zoom_search[0])]
        with ThreadPoolExecutor(
            max_workers=min(_CAMERA_SWEEP_WORKERS, len(zoom_search)),
            thread_name_prefix="home-camera-zoom",
        ) as pool:
            if current_performance_run() is None:
                futures = [
                    pool.submit(
                        self._evaluate_zoom_with_span,
                        frame,
                        proposal_frame,
                        zoom,
                    )
                    for zoom in zoom_search
                ]
            else:
                futures = []
                for zoom in zoom_search:
                    context = copy_context()
                    futures.append(
                        pool.submit(
                            context.run,
                            self._evaluate_zoom_with_span,
                            frame,
                            proposal_frame,
                            zoom,
                        )
                    )
            return [future.result() for future in futures]

    def _evaluate_zoom_with_span(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        zoom: float,
    ) -> _CameraHypothesis:
        """Measure one scale hypothesis while retaining worker-thread identity."""

        with performance_span(
            "home_camera.zoom_hypothesis",
            attributes={"zoom_scale": zoom},
        ):
            return self._evaluate_zoom(frame, proposal_frame, zoom)

    def _evaluate_zoom(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        zoom: float,
    ) -> _CameraHypothesis:
        """Evaluates one template scale over fixed landmarks only.

        Movable landmarks are excluded because their buildings occupy
        player-chosen slots: their scene position legitimately varies between
        accounts, so they can neither establish nor contradict a transform.
        Matched positions carry the scene's true scale, so the surviving
        cluster is refit rather than quantized to the evaluated grid value.
        """

        votes = self._collect_votes(
            frame,
            proposal_frame,
            zoom=zoom,
            landmarks=tuple(
                landmark for landmark in self._catalog.landmarks if not landmark.movable
            ),
        )
        cluster, fitted_zoom, translation = self._best_fit_cluster(
            votes, evaluated_zoom=zoom
        )
        return _CameraHypothesis(
            evaluated_zoom=zoom,
            zoom=fitted_zoom,
            translation=translation,
            votes=votes,
            cluster=cluster,
            groups=frozenset(vote.landmark.group_id for vote in cluster),
            separation=self._cluster_separation(cluster),
        )

    def _best_fit_cluster(
        self,
        votes: tuple[_CameraVote, ...],
        *,
        evaluated_zoom: float,
    ) -> tuple[tuple[_CameraVote, ...], float, tuple[float, float]]:
        """Selects the strongest transform-consistent cluster over the votes.

        Every vote seeds the translation-only candidate at the evaluated
        scale, and every sufficiently separated vote pair seeds the similarity
        transform its positions imply; the winner is refit by least squares
        and snapped back to the evaluated scale only inside the snap
        tolerance.
        """

        seeds: list[tuple[float, tuple[float, float]]] = [
            (evaluated_zoom, vote.translation) for vote in votes
        ]
        for index, first in enumerate(votes):
            for second in votes[index + 1 :]:
                delta_px = (
                    second.landmark.reference_center[0]
                    - first.landmark.reference_center[0]
                )
                delta_py = (
                    second.landmark.reference_center[1]
                    - first.landmark.reference_center[1]
                )
                span_squared = delta_px * delta_px + delta_py * delta_py
                if span_squared < _CAMERA_SCALE_SEPARATION_MIN_PX**2:
                    continue
                delta_qx = second.observed[0] - first.observed[0]
                delta_qy = second.observed[1] - first.observed[1]
                seed_zoom = (delta_qx * delta_px + delta_qy * delta_py) / span_squared
                if (
                    not math.isfinite(seed_zoom)
                    or not _CAMERA_ZOOM_MIN <= seed_zoom <= _CAMERA_ZOOM_MAX
                ):
                    continue
                seeds.append(
                    (
                        seed_zoom,
                        (
                            (first.observed[0] + second.observed[0]) / 2
                            - seed_zoom
                            * (
                                first.landmark.reference_center[0]
                                + second.landmark.reference_center[0]
                            )
                            / 2,
                            (first.observed[1] + second.observed[1]) / 2
                            - seed_zoom
                            * (
                                first.landmark.reference_center[1]
                                + second.landmark.reference_center[1]
                            )
                            / 2,
                        ),
                    )
                )
        best_key: tuple[int, int, float] | None = None
        best: tuple[_CameraVote, ...] = ()
        for seed_zoom, seed_translation in seeds:
            members = tuple(
                vote
                for vote in votes
                if self._residual(vote, seed_zoom, seed_translation)
                <= _CAMERA_CONSENSUS_TOLERANCE_PX
            )
            groups = frozenset(vote.landmark.group_id for vote in members)
            key = (
                len(members),
                len(groups),
                sum(vote.score for vote in members),
            )
            if best_key is None or key > best_key:
                best_key = key
                best = members
        if not best:
            return (), evaluated_zoom, (0.0, 0.0)
        fitted_zoom, fitted_translation = self._fit_transform(best)
        if abs(fitted_zoom - evaluated_zoom) <= _CAMERA_ZOOM_FIT_SNAP:
            fitted_zoom = evaluated_zoom
            fitted_translation = self._consensus_translation(best, zoom=fitted_zoom)
        inliers = tuple(
            vote
            for vote in best
            if self._residual(vote, fitted_zoom, fitted_translation)
            <= _CAMERA_CONSENSUS_TOLERANCE_PX
        )
        return inliers, fitted_zoom, fitted_translation

    def _residual(
        self,
        vote: _CameraVote,
        zoom: float,
        translation: tuple[float, float],
    ) -> float:
        """Returns the vote's center error under one candidate transform."""

        return math.dist(
            vote.observed,
            (
                zoom * vote.landmark.reference_center[0] + translation[0],
                zoom * vote.landmark.reference_center[1] + translation[1],
            ),
        )

    def _rival_cluster(
        self,
        hypothesis: _CameraHypothesis,
        *,
        reference: _CameraHypothesis | None = None,
    ) -> tuple[_CameraVote, ...] | None:
        """Returns a qualifying contradictory cluster left over at one zoom.

        The leftover fit is compared against ``reference`` (the hypothesis
        itself when omitted) so agreeing leftover clusters do not veto a
        consistent transform measured at another scale.
        """

        reference = reference or hypothesis
        remaining = tuple(
            vote for vote in hypothesis.votes if vote not in hypothesis.cluster
        )
        rival, rival_zoom, rival_translation = self._best_fit_cluster(
            remaining, evaluated_zoom=hypothesis.evaluated_zoom
        )
        rival_groups = frozenset(vote.landmark.group_id for vote in rival)
        if (
            len(rival) < _CAMERA_MIN_MATCHES
            or len(rival_groups) < _CAMERA_MIN_GROUPS
            or self._cluster_separation(rival) < _CAMERA_SCALE_SEPARATION_MIN_PX
            or not _CAMERA_ZOOM_MIN <= rival_zoom <= _CAMERA_ZOOM_MAX
        ):
            return None
        if abs(rival_zoom - reference.zoom) <= _CAMERA_RIVAL_ZOOM_DELTA and (
            self._transforms_agree(
                rival_zoom,
                rival_translation,
                reference.zoom,
                reference.translation,
                self._evidence_centroid(rival),
            )
        ):
            return None
        return rival

    def _is_ambiguous(self, hypothesis: _CameraHypothesis) -> bool:
        """Returns whether an unqualified hypothesis still shows rival clusters."""

        return self._rival_cluster(hypothesis) is not None

    def _contradicts(
        self, winner: _CameraHypothesis, other: _CameraHypothesis
    ) -> bool:
        """Returns whether two qualifying hypotheses publish contradictory transforms."""

        if abs(winner.zoom - other.zoom) > _CAMERA_RIVAL_ZOOM_DELTA:
            return True
        centroid = self._evidence_centroid((*winner.cluster, *other.cluster))
        return not self._transforms_agree(
            winner.zoom,
            winner.translation,
            other.zoom,
            other.translation,
            centroid,
        )

    def _evidence_centroid(
        self, votes: tuple[_CameraVote, ...]
    ) -> tuple[float, float]:
        """Returns the mean authored center of the votes' landmarks."""

        return (
            statistics.fmean(
                vote.landmark.reference_center[0] for vote in votes
            ),
            statistics.fmean(
                vote.landmark.reference_center[1] for vote in votes
            ),
        )

    def _transforms_agree(
        self,
        zoom_a: float,
        translation_a: tuple[float, float],
        zoom_b: float,
        translation_b: tuple[float, float],
        centroid: tuple[float, float],
    ) -> bool:
        """Returns whether two transforms place the evidence centroid together.

        Translation is origin-relative, so a small zoom difference between
        two fits of the same correspondences scales into a large origin gap
        (``Δt ≈ -Δz · centroid``): comparing raw translations would flag
        re-measurements of the same scene as rivals. Comparing where each
        transform puts the evidence itself is the scale-invariant check.
        """

        return math.dist(
            (
                zoom_a * centroid[0] + translation_a[0],
                zoom_a * centroid[1] + translation_a[1],
            ),
            (
                zoom_b * centroid[0] + translation_b[0],
                zoom_b * centroid[1] + translation_b[1],
            ),
        ) <= _CAMERA_RIVAL_TRANSLATION_PX

    def _ambiguous(
        self,
        reason: str,
        hypothesis: _CameraHypothesis,
        frame_size: tuple[int, int],
    ) -> HomeCityCameraProof:
        """Publishes an ambiguous verdict with the winning cluster's evidence."""

        return HomeCityCameraProof(
            status=HomeCityCameraStatus.AMBIGUOUS,
            reason=reason,
            frame_size=frame_size,
            evidence=tuple(
                self._evidence_for_transform(
                    hypothesis.cluster, hypothesis.zoom, hypothesis.translation
                )
            ),
        )

    def _insufficient(
        self,
        hypotheses: list[_CameraHypothesis],
        frame_size: tuple[int, int],
    ) -> HomeCityCameraProof:
        """Publishes the most informative unresolved verdict across hypotheses."""

        if not any(hypothesis.votes for hypothesis in hypotheses):
            return HomeCityCameraProof(
                status=HomeCityCameraStatus.INSUFFICIENT,
                reason="no_landmark_correspondences",
                frame_size=frame_size,
            )
        strongest = max(
            hypotheses,
            key=lambda hypothesis: (
                len(hypothesis.cluster),
                len(hypothesis.groups),
                hypothesis.separation,
            ),
        )
        if (
            len(strongest.cluster) >= _CAMERA_MIN_MATCHES
            and len(strongest.groups) >= _CAMERA_MIN_GROUPS
            and strongest.separation >= _CAMERA_SCALE_SEPARATION_MIN_PX
            and not _CAMERA_ZOOM_MIN <= strongest.zoom <= _CAMERA_ZOOM_MAX
        ):
            reason = "unsupported_zoom_fit"
        elif (
            len(strongest.cluster) >= _CAMERA_MIN_MATCHES
            and len(strongest.groups) >= _CAMERA_MIN_GROUPS
        ):
            reason = "insufficient_scale_separation"
        elif len(strongest.groups) < _CAMERA_MIN_GROUPS:
            reason = "insufficient_independent_landmark_groups"
        else:
            reason = "insufficient_landmark_correspondences"
        return HomeCityCameraProof(
            status=HomeCityCameraStatus.INSUFFICIENT,
            reason=reason,
            frame_size=frame_size,
            evidence=tuple(
                self._evidence_for_transform(
                    strongest.cluster, strongest.zoom, strongest.translation
                )
            ),
        )

    def _publish(
        self,
        frame: PreparedFrame,
        hypothesis: _CameraHypothesis,
        frame_size: tuple[int, int],
        proposal_frame: PreparedFrame,
    ) -> HomeCityCameraProof:
        """Publishes the measured transform for the surviving hypothesis.

        Agreeing movable landmarks attach as residual-verified evidence at the
        published zoom without counting toward the qualifying minimums.
        """

        zoom, translation = hypothesis.zoom, hypothesis.translation
        movable = self._collect_votes(
            frame,
            proposal_frame,
            zoom=zoom,
            landmarks=tuple(
                landmark for landmark in self._catalog.landmarks if landmark.movable
            ),
        )
        attached = tuple(
            vote for vote in movable if self._residual(vote, zoom, translation)
            <= _CAMERA_CONSENSUS_TOLERANCE_PX
        )
        cluster = (*hypothesis.cluster, *attached)
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        return HomeCityCameraProof(
            status=HomeCityCameraStatus.LOCALIZED,
            reason="consensus_landmark_cluster",
            translation=(
                int(round(translation[0] + zoom * offset_x)),
                int(round(translation[1] + zoom * offset_y)),
            ),
            zoom=zoom,
            reference_size=self._catalog.reference_size,
            frame_size=frame.original_size,
            evidence=tuple(
                self._evidence_for_transform(cluster, zoom, translation)
            ),
            matched_group_ids=frozenset(
                vote.landmark.group_id for vote in cluster
            ),
        )

    def _fit_transform(
        self,
        cluster: tuple[_CameraVote, ...],
    ) -> tuple[float, tuple[float, float]]:
        """Least-squares fit of ``(zoom, image_translation)`` for one cluster.

        ``q_i = zoom * p_i + T`` is fitted across both axes jointly over the
        reference/observed center pairs; centers carry the scene's true
        scale, so the fitted zoom recovers the measured camera zoom rather
        than the evaluated template scale.  A degenerate cluster that cannot
        separate zoom from translation degrades to the unit transform.
        """

        fitted = _fit_zoom_translation(
            tuple(
                (vote.landmark.reference_center, vote.observed)
                for vote in cluster
            )
        )
        if fitted is not None:
            return fitted
        mean_px = statistics.fmean(
            vote.landmark.reference_center[0] for vote in cluster
        )
        mean_py = statistics.fmean(
            vote.landmark.reference_center[1] for vote in cluster
        )
        mean_qx = statistics.fmean(vote.observed[0] for vote in cluster)
        mean_qy = statistics.fmean(vote.observed[1] for vote in cluster)
        return 1.0, (mean_qx - mean_px, mean_qy - mean_py)

    def _cluster_separation(self, cluster: tuple[_CameraVote, ...]) -> float:
        """Returns the widest authored-center distance inside a cluster."""

        separation = 0.0
        for index, vote in enumerate(cluster):
            for other in cluster[index + 1 :]:
                separation = max(
                    separation,
                    math.dist(
                        vote.landmark.reference_center,
                        other.landmark.reference_center,
                    ),
                )
        return separation

    def match_target(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> HomeCityCameraTargetMatch | None:
        """Returns one body match only when it agrees with the localized projection.

        Slot-bound targets publish through the plural candidate matcher and
        return a match only while exactly one eligible slot claims a
        projection-agreed body; an ambiguous claim stays unpublished rather
        than choosing the first slot.
        """

        if target.reference_slot is not None:
            matches = self.match_target_candidates(image, target, proof=proof)
            return matches[0] if len(matches) == 1 else None
        return self._match_fixed_target(image, target, proof=proof)

    def match_target_candidates(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> tuple[HomeCityCameraTargetMatch, ...]:
        """Returns every eligible slot carrying a projection-agreed body match.

        Fixed targets delegate to the singular matcher.  A slot-bound target
        derives each candidate's predicted body rectangle by translating the
        authored reference bounds from the calibrated reference pivot to the
        candidate pivot, then projecting through the proof transform.  The
        OpenCV search is bounded to the predicted neighborhood clipped to the
        frame, bodies must stay fully visible, and measured hits that would
        claim the same physical body for two slots are ambiguity evidence --
        every claim is rejected rather than picking the first slot.  Distinct
        bodies measured at different eligible slots remain separate matches.
        """

        if target.reference_slot is None:
            match = self._match_fixed_target(image, target, proof=proof)
            return () if match is None else (match,)
        frame = self._coerce_frame(image)
        if (
            frame is None
            or not proof.localized
            or proof.translation is None
            or proof.zoom is None
        ):
            return ()
        zoom = proof.zoom
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        image_translation = (
            proof.translation[0] - zoom * offset_x,
            proof.translation[1] - zoom * offset_y,
        )
        slots = target._eligible_slots()
        reference_slot = slots[target.reference_slot.slot_index]
        reference_pivot = reference_slot.atlas_coordinate
        if reference_pivot is None:
            raise SelectorResolutionError(
                "A slot-bound camera target requires a calibrated reference pivot.",
                landmark_id=target.landmark_id,
            )
        frame_bounds = Bounds(0, 0, *frame.reference_size)
        padding = target.max_projection_error
        matches: list[HomeCityCameraTargetMatch] = []
        for slot in sorted(slots.values(), key=lambda item: item.slot_index):
            pivot = slot.atlas_coordinate
            if pivot is None:
                continue
            predicted = (
                zoom * (target.reference_bounds.x + pivot.x - reference_pivot.x)
                + image_translation[0],
                zoom * (target.reference_bounds.y + pivot.y - reference_pivot.y)
                + image_translation[1],
            )
            predicted_bounds = Bounds(
                int(round(predicted[0])),
                int(round(predicted[1])),
                max(1, int(round(zoom * target.reference_bounds.width))),
                max(1, int(round(zoom * target.reference_bounds.height))),
            )
            if not frame_bounds.contains_bounds(predicted_bounds):
                continue
            region_left = max(frame_bounds.x, predicted_bounds.x - padding)
            region_top = max(frame_bounds.y, predicted_bounds.y - padding)
            region_right = min(
                frame_bounds.x + frame_bounds.width,
                predicted_bounds.x + predicted_bounds.width + padding,
            )
            region_bottom = min(
                frame_bounds.y + frame_bounds.height,
                predicted_bounds.y + predicted_bounds.height + padding,
            )
            if region_right - region_left <= 0 or region_bottom - region_top <= 0:
                continue
            hit = self._matcher.find_best_match(
                frame,
                self._catalog.template_path(target.file_name),
                threshold=target.min_score,
                search_region=Bounds(
                    region_left,
                    region_top,
                    region_right - region_left,
                    region_bottom - region_top,
                ),
                template_scale=zoom,
            )
            if hit is None:
                continue
            match_reference = self._reference_bounds(hit.bounds, frame)
            projection_error = math.dist(
                (match_reference.x, match_reference.y), predicted
            )
            if projection_error > target.max_projection_error:
                continue
            matches.append(
                self._build_match(
                    target,
                    hit,
                    match_reference,
                    zoom,
                    frame,
                    projection_error,
                    home_city_slot=HomeCitySlotSelector(slot.slot_index),
                )
            )
        kept = [
            match
            for match in matches
            if not any(
                other is not match
                and _claims_same_body(match.bounds, other.bounds)
                for other in matches
            )
        ]
        return tuple(kept)

    def _match_fixed_target(
        self,
        image: Image.Image | PreparedFrame,
        target: HomeCityCameraTarget,
        *,
        proof: HomeCityCameraProof,
    ) -> HomeCityCameraTargetMatch | None:
        """Returns the fixed-target body match when it agrees with the projection."""

        frame = self._coerce_frame(image)
        if (
            frame is None
            or not proof.localized
            or proof.translation is None
            or proof.zoom is None
        ):
            return None
        zoom = proof.zoom
        offset_x, offset_y = self._catalog.atlas_to_reference_offset
        image_translation = (
            proof.translation[0] - zoom * offset_x,
            proof.translation[1] - zoom * offset_y,
        )
        hit = self._matcher.find_best_match(
            frame,
            self._catalog.template_path(target.file_name),
            threshold=target.min_score,
            template_scale=zoom,
        )
        if hit is None:
            return None
        match_reference = self._reference_bounds(hit.bounds, frame)
        projection_error = math.dist(
            (match_reference.x, match_reference.y),
            (
                zoom * target.reference_bounds.x + image_translation[0],
                zoom * target.reference_bounds.y + image_translation[1],
            ),
        )
        if projection_error > target.max_projection_error:
            return None
        return self._build_match(
            target,
            hit,
            match_reference,
            zoom,
            frame,
            projection_error,
            home_city_slot=None,
        )

    def _build_match(
        self,
        target: HomeCityCameraTarget,
        hit: TemplateMatch,
        match_reference: Bounds,
        zoom: float,
        frame: PreparedFrame,
        projection_error: float,
        *,
        home_city_slot: HomeCitySlotSelector | None,
    ) -> HomeCityCameraTargetMatch:
        """Publishes measured action geometry anchored on the observed match."""

        scale_x = frame.original_size[0] / frame.reference_size[0]
        scale_y = frame.original_size[1] / frame.reference_size[1]

        def to_frame_point(reference_point: tuple[float, float]) -> tuple[int, int]:
            observed_x = match_reference.x + zoom * (
                reference_point[0] - target.reference_bounds.x
            )
            observed_y = match_reference.y + zoom * (
                reference_point[1] - target.reference_bounds.y
            )
            return (
                int(round(observed_x * scale_x)),
                int(round(observed_y * scale_y)),
            )

        action_point = to_frame_point(target.reference_action_point)
        action_left, action_top = to_frame_point(
            (
                target.reference_action_bounds.x,
                target.reference_action_bounds.y,
            )
        )
        action_right, action_bottom = to_frame_point(
            (
                target.reference_action_bounds.x
                + target.reference_action_bounds.width,
                target.reference_action_bounds.y
                + target.reference_action_bounds.height,
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
            home_city_slot=home_city_slot,
        )

    def matched_target_objects(
        self,
        frame: PreparedFrame,
        *,
        proof: HomeCityCameraProof,
    ) -> tuple[DetectedSpatialObject, ...]:
        """Builds typed building objects for every projection-agreed body match.

        Slot-bound targets contribute one measured object per unambiguous
        eligible slot, each tagged with the observed ``home_city_slot``; the
        tag records the current frame's body evidence, never static occupancy.
        """

        if (
            not proof.localized
            or proof.translation is None
            or proof.zoom is None
            or proof.frame_size is None
        ):
            return ()
        targets = self._catalog.targets
        if len(targets) > 1:
            # Independent post-proof matches share the bounded sweep capacity;
            # they only read the immutable frame and lock-guarded template
            # caches. Results keep catalog order so object assembly stays
            # deterministic; tracing carries a separate context per task.
            with ThreadPoolExecutor(
                max_workers=min(_CAMERA_SWEEP_WORKERS, len(targets)),
                thread_name_prefix="home-camera-target",
            ) as pool:
                if current_performance_run() is None:
                    match_sets = tuple(
                        pool.map(
                            lambda target: self.match_target_candidates(
                                frame, target, proof=proof
                            ),
                            targets,
                        )
                    )
                else:
                    futures = []
                    for target in targets:
                        context = copy_context()
                        futures.append(
                            pool.submit(
                                context.run,
                                self.match_target_candidates,
                                frame,
                                target,
                                proof=proof,
                            )
                        )
                    match_sets = tuple(future.result() for future in futures)
        else:
            match_sets = tuple(
                self.match_target_candidates(frame, target, proof=proof)
                for target in targets
            )
        objects: list[DetectedSpatialObject] = []
        viewport_bounds = Bounds(0, 0, *proof.frame_size)
        for target, matches in zip(targets, match_sets):
            for match in matches:
                metadata = build_home_city_object_metadata(target.object_id)
                metadata.update(
                    {
                        "detection_source": "camera_template",
                        "camera_landmark_id": target.landmark_id,
                        "camera_match_score": round(match.score, 4),
                        "camera_projection_error": round(match.projection_error, 2),
                    }
                )
                if match.home_city_slot is not None:
                    metadata["home_city_slot_index"] = match.home_city_slot.slot_index
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
                        home_city_slot=match.home_city_slot,
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

    def _collect_votes(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        *,
        zoom: float,
        landmarks: tuple[HomeCityCameraLandmark, ...],
    ) -> tuple[_CameraVote, ...]:
        """Matches each landmark at one template scale and keeps above-floor hits."""

        votes: list[_CameraVote] = []
        for landmark in landmarks:
            # Coarse proposals bound the global search, but a vote exists only
            # when the best-confidence natively refined candidate reaches the
            # landmark's floor, so the floor can be passed down directly.
            hit = self._matcher.find_best_match_coarse_to_fine(
                frame,
                proposal_frame,
                self._catalog.template_path(landmark.file_name),
                threshold=landmark.min_score,
                template_scale=zoom,
            )
            if hit is None:
                continue
            match_reference = self._reference_bounds(hit.bounds, frame)
            observed = (
                match_reference.x + match_reference.width / 2,
                match_reference.y + match_reference.height / 2,
            )
            votes.append(
                _CameraVote(
                    landmark=landmark,
                    bounds=hit.bounds,
                    score=hit.confidence,
                    observed=observed,
                    translation=(
                        observed[0] - zoom * landmark.reference_center[0],
                        observed[1] - zoom * landmark.reference_center[1],
                    ),
                    zoom=zoom,
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

    def _consensus_translation(
        self, votes: tuple[_CameraVote, ...], *, zoom: float
    ) -> tuple[float, float]:
        """Fits the cluster translation as the component-wise median of its members."""

        return (
            statistics.median(
                vote.observed[0] - zoom * vote.landmark.reference_center[0]
                for vote in votes
            ),
            statistics.median(
                vote.observed[1] - zoom * vote.landmark.reference_center[1]
                for vote in votes
            ),
        )

    def _evidence_for_transform(
        self,
        votes: tuple[_CameraVote, ...],
        zoom: float,
        translation: tuple[float, float],
    ) -> list[HomeCityCameraEvidence]:
        """Publishes evidence with residuals measured against the published transform."""

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
                residual=math.dist(
                    vote.observed,
                    (
                        zoom * vote.landmark.reference_center[0] + translation[0],
                        zoom * vote.landmark.reference_center[1] + translation[1],
                    ),
                ),
                zoom=vote.zoom,
            )
            for vote in votes
        ]

    def _classify_zoom(
        self,
        camera_proof: HomeCityCameraProof,
    ) -> tuple[HomeCityZoomStatus, str, str | None]:
        """Classifies the proof's fixed-landmark scale against the endpoint calibration.

        The published ``zoom`` is grid-snapped within the consensus tolerance,
        which erases the few-hundredths separation between the endpoint band
        and the nearest closer rung; the verdict therefore refits the raw
        similarity scale over the proof's fixed-landmark center pairs.  A
        movable occupant corroborates pose but never establishes scale, so it
        is excluded from the fit exactly as it is excluded from consensus.
        """

        normalization = self._catalog.normalization
        endpoint = None if normalization is None else normalization.endpoint
        if endpoint is None:
            return HomeCityZoomStatus.UNSUPPORTED, "missing_zoom_calibration", None
        if not camera_proof.localized:
            return HomeCityZoomStatus.UNRESOLVED, camera_proof.reason, endpoint.id
        movable_ids = frozenset(
            landmark.id for landmark in self._catalog.landmarks if landmark.movable
        )
        fixed_evidence = tuple(
            item for item in camera_proof.evidence if item.landmark_id not in movable_ids
        )
        if len(fixed_evidence) < 2:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_fixed_scale_evidence",
                endpoint.id,
            )
        if (
            len({item.group_id for item in fixed_evidence})
            < endpoint.min_fixed_groups
        ):
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_independent_landmark_groups",
                endpoint.id,
            )
        pairs = tuple(
            self._evidence_center_pair(item, camera_proof) for item in fixed_evidence
        )
        fitted = _fit_zoom_translation(pairs)
        if fitted is None:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "insufficient_scale_separation",
                endpoint.id,
            )
        zoom, translation = fitted
        mean_residual = statistics.fmean(
            math.dist(
                observed,
                (
                    zoom * authored[0] + translation[0],
                    zoom * authored[1] + translation[1],
                ),
            )
            for authored, observed in pairs
        )
        if mean_residual > endpoint.max_mean_residual_px:
            return (
                HomeCityZoomStatus.UNRESOLVED,
                "zoom_fit_residual_exceeded",
                endpoint.id,
            )
        if endpoint.zoom_interval[0] <= zoom <= endpoint.zoom_interval[1]:
            return HomeCityZoomStatus.AT_ENDPOINT, "measured_zoom_at_endpoint", endpoint.id
        if zoom >= endpoint.non_endpoint_floor:
            return (
                HomeCityZoomStatus.NOT_AT_ENDPOINT,
                "measured_zoom_closer_than_endpoint",
                endpoint.id,
            )
        return (
            HomeCityZoomStatus.UNRESOLVED,
            "measured_zoom_between_classes",
            endpoint.id,
        )

    def _evidence_center_pair(
        self,
        evidence: HomeCityCameraEvidence,
        camera_proof: HomeCityCameraProof,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Returns one evidence item's authored/observed center pair in reference units."""

        if camera_proof.frame_size is None:
            raise SelectorResolutionError(
                "A localized camera proof must carry its producing frame size.",
                landmark_id=evidence.landmark_id,
            )
        scale_x = camera_proof.reference_size[0] / camera_proof.frame_size[0]
        scale_y = camera_proof.reference_size[1] / camera_proof.frame_size[1]
        return (
            (
                evidence.reference_bounds.x + evidence.reference_bounds.width / 2,
                evidence.reference_bounds.y + evidence.reference_bounds.height / 2,
            ),
            (
                (evidence.bounds.x + evidence.bounds.width / 2) * scale_x,
                (evidence.bounds.y + evidence.bounds.height / 2) * scale_y,
            ),
        )

    def _match_zoom_anchor(self, frame: PreparedFrame) -> HomeCityZoomAnchor | None:
        """Locates a qualified scenery patch on the current frame's own pixels.

        Anchor recognition is pose-independent: each spec's native crop --
        which contains the reviewed dispatch point -- is matched across its
        evidence-backed scales, every qualifying hit must land on the same
        physical feature, and the patch's contained point must stay inside
        the match, the viewport, and outside every authored HUD/occlusion
        region.  Ambiguous, occluded, or offscreen placements publish no
        anchor rather than falling back to a corner, center, or unqualified
        patch.
        """

        normalization = self._catalog.normalization
        if normalization is None:
            return None
        proposal_frame = self._proposal_frame(frame)
        for spec in normalization.zoom_anchors:
            anchor = self._match_anchor_spec(
                frame,
                proposal_frame,
                normalization,
                spec,
            )
            if anchor is not None:
                return anchor
        return None

    def _match_anchor_spec(
        self,
        frame: PreparedFrame,
        proposal_frame: PreparedFrame,
        normalization: HomeCityViewNormalization,
        spec: HomeCityZoomAnchorSpec,
    ) -> HomeCityZoomAnchor | None:
        """Resolves one spec's patch placement when every qualifying hit agrees.

        The published bounds are the match's own rectangle in the frame's
        reference space; the published point is ``bounds.origin + scale *
        point_offset`` -- the native offset the reviewed dispatch point
        occupies inside the crop -- so the pixels checked are the same
        pixels the point sits on.
        """

        if len(spec.scales) > 1:
            # Independent scale hypotheses share the bounded sweep capacity and
            # stay in authored spec order, so hit correspondence and spec
            # priority are unchanged.
            with ThreadPoolExecutor(
                max_workers=min(_CAMERA_SWEEP_WORKERS, len(spec.scales)),
                thread_name_prefix="home-camera-anchor",
            ) as pool:
                if current_performance_run() is None:
                    results = tuple(
                        pool.map(
                            lambda scale: self._matcher.find_best_match_coarse_to_fine(
                                frame,
                                proposal_frame,
                                self._catalog.template_path(spec.file_name),
                                threshold=spec.min_score,
                                template_scale=scale,
                            ),
                            spec.scales,
                        )
                    )
                else:
                    futures = []
                    for scale in spec.scales:
                        context = copy_context()
                        futures.append(
                            pool.submit(
                                context.run,
                                self._matcher.find_best_match_coarse_to_fine,
                                frame,
                                proposal_frame,
                                self._catalog.template_path(spec.file_name),
                                threshold=spec.min_score,
                                template_scale=scale,
                            )
                        )
                    results = tuple(future.result() for future in futures)
        else:
            results = (
                self._matcher.find_best_match_coarse_to_fine(
                    frame,
                    proposal_frame,
                    self._catalog.template_path(spec.file_name),
                    threshold=spec.min_score,
                    template_scale=spec.scales[0],
                ),
            )
        hits = [(scale, hit) for scale, hit in zip(spec.scales, results) if hit is not None]
        if not hits:
            return None
        best_scale, best = max(hits, key=lambda item: item[1].confidence)
        best_center = (
            best.bounds.x + best.bounds.width / 2,
            best.bounds.y + best.bounds.height / 2,
        )
        for _, hit in hits:
            center = (
                hit.bounds.x + hit.bounds.width / 2,
                hit.bounds.y + hit.bounds.height / 2,
            )
            if math.dist(center, best_center) > _ANCHOR_CORRESPONDENCE_PX:
                return None
        lane = self._reference_bounds(best.bounds, frame)
        lane_tuple = (
            float(lane.x),
            float(lane.y),
            float(lane.width),
            float(lane.height),
        )
        point = (
            lane.x + best_scale * spec.point_offset[0],
            lane.y + best_scale * spec.point_offset[1],
        )
        if not _bounds_tuple_contains_point(lane_tuple, point):
            return None
        if not (
            lane_tuple[0] >= 0
            and lane_tuple[1] >= 0
            and lane_tuple[0] + lane_tuple[2] <= frame.reference_size[0]
            and lane_tuple[1] + lane_tuple[3] <= frame.reference_size[1]
        ):
            return None
        if any(
            _bounds_contains_float_point(excluded, point)
            for excluded in normalization.hud_exclusion_bounds
        ):
            return None
        scale_x = frame.original_size[0] / frame.reference_size[0]
        scale_y = frame.original_size[1] / frame.reference_size[1]
        return HomeCityZoomAnchor(
            point=(
                int(round(point[0] * scale_x)),
                int(round(point[1] * scale_y)),
            ),
            bounds=Bounds(
                int(round(lane_tuple[0] * scale_x)),
                int(round(lane_tuple[1] * scale_y)),
                max(1, int(round(lane_tuple[2] * scale_x))),
                max(1, int(round(lane_tuple[3] * scale_y))),
            ),
            qualification_id=spec.id,
        )


def _fit_zoom_translation(
    pairs: tuple[tuple[tuple[float, float], tuple[float, float]], ...],
) -> tuple[float, tuple[float, float]] | None:
    """Least-squares ``q = zoom * p + T`` fit over authored/observed center pairs.

    The pairs carry the scene's true scale, so the fitted zoom recovers the
    measured camera zoom rather than a grid hypothesis.  ``None`` is the
    honest answer when the authored centers are degenerate and cannot
    separate zoom from translation.
    """

    if len(pairs) < 2:
        return None
    mean_px = statistics.fmean(pair[0][0] for pair in pairs)
    mean_py = statistics.fmean(pair[0][1] for pair in pairs)
    mean_qx = statistics.fmean(pair[1][0] for pair in pairs)
    mean_qy = statistics.fmean(pair[1][1] for pair in pairs)
    numerator = 0.0
    denominator = 0.0
    for (authored_x, authored_y), (observed_x, observed_y) in pairs:
        delta_px = authored_x - mean_px
        delta_py = authored_y - mean_py
        numerator += (observed_x - mean_qx) * delta_px + (
            observed_y - mean_qy
        ) * delta_py
        denominator += delta_px * delta_px + delta_py * delta_py
    if denominator <= 0.0:
        return None
    zoom = numerator / denominator
    return zoom, (mean_qx - zoom * mean_px, mean_qy - zoom * mean_py)


def _bounds_tuple_contains_point(
    bounds: tuple[float, float, float, float],
    point: tuple[float, float],
) -> bool:
    """Returns whether a float point lies inside one projected float rectangle."""

    return (
        bounds[0] <= point[0] <= bounds[0] + bounds[2]
        and bounds[1] <= point[1] <= bounds[1] + bounds[3]
    )


def _bounds_contains_float_point(bounds: Bounds, point: tuple[float, float]) -> bool:
    """Returns whether a float point lies inside one integer-authored region."""

    return (
        bounds.x <= point[0] <= bounds.x + bounds.width
        and bounds.y <= point[1] <= bounds.y + bounds.height
    )


def _claims_same_body(first: Bounds, second: Bounds) -> bool:
    """Returns whether two matches describe the same physical building body."""

    return first.contains_point(second.center()) or second.contains_point(
        first.center()
    )
