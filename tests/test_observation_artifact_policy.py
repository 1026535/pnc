"""Shared observation artifact policy and world-map survey recorder tests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.world_map_survey_recorder import WorldMapSurveyRecorder
from pnc_automation.app.pnc.persistence.world_map_survey_debug_store import WorldMapSurveyDebugStore
from pnc_automation.app.pnc.vision.observation_builder import ObservationService
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.app.runtime.observation_artifacts import (
    ObservationArtifactKind,
    observation_artifact_selection,
    resolve_observation_artifact_selection,
)
from pnc_automation.app.runtime.observation_mode import ObservationMode
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from tests.test_support import make_observation, make_spatial_object, make_spatial_surface


class ObservationArtifactSelectionTests(unittest.TestCase):
    """Validates the shared runtime artifact-selection resolver."""

    def test_mode_defaults_match_debug_and_light(self) -> None:
        """Maps debug mode to screenshots and light mode to no routine artifacts."""

        self.assertEqual(
            resolve_observation_artifact_selection(mode=ObservationMode.DEBUG),
            observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
        )
        self.assertEqual(
            resolve_observation_artifact_selection(mode=ObservationMode.LIGHT),
            frozenset(),
        )

    def test_request_override_wins_over_mode_default(self) -> None:
        """Honors one request-level override ahead of the runtime mode default."""

        self.assertEqual(
            resolve_observation_artifact_selection(
                mode=ObservationMode.DEBUG,
                request_selection=observation_artifact_selection(ObservationArtifactKind.WORLD_MAP_SURVEY_STATE),
            ),
            observation_artifact_selection(ObservationArtifactKind.WORLD_MAP_SURVEY_STATE),
        )

    def test_call_site_override_wins_over_request_override(self) -> None:
        """Lets the immediate caller replace the request-level artifact selection when needed."""

        self.assertEqual(
            resolve_observation_artifact_selection(
                mode=ObservationMode.DEBUG,
                request_selection=observation_artifact_selection(ObservationArtifactKind.WORLD_MAP_SURVEY_STATE),
                override_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            ),
            observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
        )


class ObservationArtifactBoundaryTests(unittest.TestCase):
    """Validates that artifact ownership stays separated between observation and survey layers."""

    def test_observation_service_rejects_world_map_survey_artifacts_outside_survey_boundary(self) -> None:
        """Fails fast when survey-state persistence is requested at a plain observation boundary."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            service = ObservationService(
                screenshot_service=ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")),
                observation_builder=_ArtifactAwareObservationBuilder(
                    observations=[make_observation(ScreenType.PNC_WORLD_MAP)]
                ),
                session=_FakeScreenshotSession(),
                artifact_directory="k230_boundary_test",
                mode=ObservationMode.LIGHT,
            )

            with self.assertRaises(ValueError):
                service.capture_observation(
                    "world_scan",
                    request=ObservationRequest(
                        artifact_selection=observation_artifact_selection(
                            ObservationArtifactKind.WORLD_MAP_SURVEY_STATE
                        )
                    ),
                )

    def test_explicit_failure_style_screenshot_override_still_persists_in_light_mode(self) -> None:
        """Keeps forced screenshot capture available even when routine light-mode observations stay ephemeral."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            service = ObservationService(
                screenshot_service=ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")),
                observation_builder=_ArtifactAwareObservationBuilder(
                    observations=[
                        make_observation(ScreenType.PNC_WORLD_MAP),
                        make_observation(ScreenType.PNC_WORLD_MAP),
                    ]
                ),
                session=_FakeScreenshotSession(),
                artifact_directory="k230_failure_style",
                mode=ObservationMode.LIGHT,
            )

            routine_observation = service.observe("routine")
            failure_observation = service.observe(
                "failure",
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            )

            self.assertIsNone(routine_observation.artifact_path)
            self.assertIsNotNone(failure_observation.artifact_path)
            self.assertEqual(len(tuple((root / "artifacts").rglob("*.png"))), 1)


class WorldMapSurveyRecorderTests(unittest.TestCase):
    """Validates world-map survey checkpoint capture and debug dump persistence."""

    def test_screenshot_only_path_persists_only_png_artifacts(self) -> None:
        """Writes the screenshot artifact without emitting a world-map survey dump when only screenshots are enabled."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            recorder = _make_recorder(
                root=root,
                observations=[_world_map_observation("VisibleCastle", estimated_coordinate=(201, 659))],
                mode=ObservationMode.LIGHT,
            )

            result = recorder.capture_checkpoint(
                "survey_step",
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.SCREENSHOT),
            )

            self.assertIsNotNone(result.capture.screenshot.artifact_path)
            self.assertIsNone(result.debug_dump)
            self.assertEqual(len(tuple((root / "artifacts").rglob("*.png"))), 1)
            self.assertFalse(any((root / "artifacts").rglob("*.json")))

    def test_world_map_survey_only_path_persists_only_json_dump(self) -> None:
        """Writes one checkpoint dump without persisting a screenshot when only survey-state dumping is enabled."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            recorder = _make_recorder(
                root=root,
                observations=[_world_map_observation("VisibleCastle", estimated_coordinate=(201, 659))],
                mode=ObservationMode.LIGHT,
            )

            result = recorder.capture_checkpoint(
                "survey_step",
                artifact_selection=observation_artifact_selection(ObservationArtifactKind.WORLD_MAP_SURVEY_STATE),
            )

            self.assertIsNone(result.capture.screenshot.artifact_path)
            self.assertIsNotNone(result.debug_dump)
            assert result.debug_dump is not None
            sighting = result.debug_dump.document["sightings"][0]
            self.assertIsNone(sighting["artifact_path"])
            self.assertFalse(any((root / "artifacts").rglob("*.png")))
            self.assertEqual(len(tuple((root / "artifacts").rglob("*.json"))), 1)

    def test_combined_path_persists_both_png_and_world_map_dump_with_linked_screenshot(self) -> None:
        """Persists both artifact kinds and keeps the dump linked to the screenshot evidence path."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            recorder = _make_recorder(
                root=root,
                observations=[_world_map_observation("VisibleCastle", estimated_coordinate=(201, 659))],
                mode=ObservationMode.LIGHT,
            )

            result = recorder.capture_checkpoint(
                "survey_step",
                artifact_selection=observation_artifact_selection(
                    ObservationArtifactKind.SCREENSHOT,
                    ObservationArtifactKind.WORLD_MAP_SURVEY_STATE,
                ),
            )

            self.assertIsNotNone(result.capture.screenshot.artifact_path)
            self.assertIsNotNone(result.debug_dump)
            assert result.debug_dump is not None
            sighting = result.debug_dump.document["sightings"][0]
            self.assertEqual(
                sighting["artifact_path"],
                str(result.capture.screenshot.artifact_path),
            )
            self.assertEqual(len(tuple((root / "artifacts").rglob("*.png"))), 1)
            self.assertEqual(len(tuple((root / "artifacts").rglob("*.json"))), 1)

    def test_none_path_persists_no_routine_artifacts(self) -> None:
        """Leaves both screenshots and survey dumps disabled when the effective selection is empty."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            recorder = _make_recorder(
                root=root,
                observations=[_world_map_observation("VisibleCastle", estimated_coordinate=(201, 659))],
                mode=ObservationMode.LIGHT,
            )

            result = recorder.capture_checkpoint("survey_step", artifact_selection=frozenset())

            self.assertIsNone(result.capture.screenshot.artifact_path)
            self.assertIsNone(result.debug_dump)
            self.assertFalse(any((root / "artifacts").rglob("*.png")))
            self.assertFalse(any((root / "artifacts").rglob("*.json")))

    def test_persist_checkpoint_requires_an_ingested_world_map_checkpoint(self) -> None:
        """Fails fast when survey-state dumping is requested before any valid checkpoint has been ingested."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            recorder = _make_recorder(root=root, observations=[], mode=ObservationMode.LIGHT)

            with self.assertRaises(SelectorResolutionError):
                recorder.persist_checkpoint(
                    "survey_step",
                    artifact_selection=observation_artifact_selection(
                        ObservationArtifactKind.WORLD_MAP_SURVEY_STATE
                    ),
                )


@dataclass(slots=True)
class _ArtifactAwareObservationBuilder:
    """Returns queued observations while mirroring screenshot artifact metadata into the typed result."""

    observations: list

    def build(self, screenshot: object, *, request: ObservationRequest | None = None) -> object:
        """Returns the next queued observation while preserving the current screenshot provenance."""

        del request
        if not self.observations:
            raise AssertionError("No observation queued for ObservationService.")
        observation = self.observations.pop(0)
        return replace(
            observation,
            artifact_path=screenshot.artifact_path if screenshot.artifact_path is not None else observation.artifact_path,
            captured_at=screenshot.captured_at,
        )


class _FakeScreenshotSession:
    """Returns one deterministic in-memory PNG payload for screenshot capture tests."""

    def capture_screenshot_bytes(self) -> bytes:
        """Returns a simple valid PNG payload."""

        image = Image.new("RGB", (40, 40), (15, 28, 68))
        from io import BytesIO

        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def _make_recorder(
    *,
    root: Path,
    observations: list,
    mode: ObservationMode,
) -> WorldMapSurveyRecorder:
    """Builds one world-map survey recorder with a real observation service and temporary artifact root."""

    return WorldMapSurveyRecorder(
        observation_service=ObservationService(
            screenshot_service=ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts")),
            observation_builder=_ArtifactAwareObservationBuilder(observations=observations),
            session=_FakeScreenshotSession(),
            artifact_directory="k230_world_map_survey",
            mode=mode,
        ),
        debug_store=WorldMapSurveyDebugStore(root=root / "artifacts"),
    )


def _world_map_observation(
    name_text: str,
    *,
    estimated_coordinate: tuple[int, int],
) -> object:
    """Builds one deterministic world-map observation for survey recorder tests."""

    return make_observation(
        ScreenType.PNC_WORLD_MAP,
        spatial_surface=make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=253,
            y=447,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text=name_text,
                    kingdom="K287",
                    viewport_offset=(4, 252),
                    viewport_offset_ratio=(4 / 900, 252 / 1184),
                    estimated_world_coordinate=estimated_coordinate,
                ),
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
