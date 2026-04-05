"""World-map survey index tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.app.pnc.domain.observation import SpatialObjectKind, SpatialSurfaceType
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.navigation.world_map_index import (
    WorldMapObjectAddressingKind,
    WorldMapSurveyIndex,
)
from tests.test_support import make_observation, make_spatial_object, make_spatial_surface


class WorldMapSurveyIndexTests(unittest.TestCase):
    """Validates canonical indexing of repeated typed world-map observations."""

    def test_ingest_observation_indexes_estimated_world_objects(self) -> None:
        """Stores typed visible objects under one estimated-world key when the surface exposes normalized coordinate estimates."""

        index = WorldMapSurveyIndex()
        observation = make_observation(
            screen_type=ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=197,
                y=407,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.CASTLE,
                        name_text="K2875067781632",
                        kingdom="K287",
                        viewport_offset=(4, 252),
                        viewport_offset_ratio=(4 / 900, 252 / 1184),
                        estimated_world_coordinate=(201, 659),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        viewport_offset=(-120, -80),
                        viewport_offset_ratio=(-120 / 900, -80 / 1184),
                        estimated_world_coordinate=(77, 327),
                    ),
                ),
            ),
            artifact_path=Path("artifacts/world_probe.png"),
        )

        sightings = index.ingest_observation(observation)

        self.assertEqual(len(sightings), 2)
        castle = index.castle_sightings()[0]
        self.assertEqual(castle.key.addressing_kind, WorldMapObjectAddressingKind.ESTIMATED_WORLD)
        self.assertEqual(castle.key.coordinate, (201, 659))
        self.assertEqual(castle.object_.kingdom, "K287")
        self.assertEqual(castle.artifact_path, Path("artifacts/world_probe.png"))

    def test_ingest_surface_updates_existing_estimated_sighting_with_latest_artifact(self) -> None:
        """Keeps one canonical sighting per estimated world object while refreshing the latest runtime provenance."""

        index = WorldMapSurveyIndex()
        first_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=197,
            y=407,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="K2875067781632",
                    kingdom="K287",
                    viewport_offset=(4, 252),
                    viewport_offset_ratio=(4 / 900, 252 / 1184),
                    estimated_world_coordinate=(201, 659),
                    action_point=(454, 1004),
                ),
            ),
        )
        second_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=205,
            y=412,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="K2875067781632",
                    kingdom="K287",
                    viewport_offset=(-6, 210),
                    viewport_offset_ratio=(-6 / 900, 210 / 1184),
                    estimated_world_coordinate=(201, 659),
                    action_point=(444, 962),
                ),
            ),
        )

        first = index.ingest_surface(first_surface, artifact_path=Path("artifacts/first.png"))[0]
        second = index.ingest_surface(second_surface, artifact_path=Path("artifacts/second.png"))[0]

        self.assertEqual(len(index.sightings), 1)
        self.assertEqual(first.key, second.key)
        self.assertEqual(second.artifact_path, Path("artifacts/second.png"))
        self.assertEqual(second.viewport_coordinate, (205, 412))
        self.assertEqual(second.object_.action_point, (444, 962))

    def test_annotate_castle_player_name_supports_exact_lookup(self) -> None:
        """Attaches resolved player names to castle sightings without changing their underlying map key."""

        index = WorldMapSurveyIndex()
        sighting = index.ingest_surface(
            make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=197,
                y=407,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.CASTLE,
                        name_text="K2875067781632",
                        kingdom="K287",
                        viewport_offset=(4, 252),
                        viewport_offset_ratio=(4 / 900, 252 / 1184),
                        estimated_world_coordinate=(201, 659),
                    ),
                ),
            ),
            artifact_path=Path("artifacts/world_probe.png"),
        )[0]

        annotated = index.annotate_castle_player_name(
            sighting.key,
            player_name="LadiesLoveCake",
            profile_artifact_path=Path("artifacts/profile.png"),
        )

        self.assertEqual(annotated.resolved_player_name, "LadiesLoveCake")
        self.assertEqual(index.find_castle_by_player_name("LadiesLoveCake"), annotated)
        self.assertIsNone(index.find_castle_by_player_name("ladieslovecake"))

    def test_find_castle_by_player_name_matches_direct_visible_castle_labels(self) -> None:
        """Uses the visible world-map castle label directly when the player name is already on-screen."""

        index = WorldMapSurveyIndex()
        sighting = index.ingest_surface(
            make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.CASTLE,
                        name_text="LadiesLoveCake",
                        viewport_offset=(96, 110),
                        viewport_offset_ratio=(96 / 900, 110 / 1184),
                        estimated_world_coordinate=(349, 557),
                    ),
                ),
            )
        )[0]

        self.assertEqual(index.find_castle_by_player_name("LadiesLoveCake"), sighting)

    def test_annotate_castle_player_name_rejects_non_castle_keys(self) -> None:
        """Fails fast when a caller tries to attach player ownership to a non-castle map object."""

        index = WorldMapSurveyIndex()
        resource = index.ingest_surface(
            make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=197,
                y=407,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        viewport_offset=(-120, -80),
                        viewport_offset_ratio=(-120 / 900, -80 / 1184),
                        estimated_world_coordinate=(77, 327),
                    ),
                ),
            )
        )[0]

        with self.assertRaises(SelectorResolutionError):
            index.annotate_castle_player_name(resource.key, player_name="LadiesLoveCake")

    def test_ingest_surface_prefers_confirmed_world_coordinates_over_estimated_keys(self) -> None:
        """Uses a confirmed-world key when authoritative object coordinates are available."""

        index = WorldMapSurveyIndex()

        sighting = index.ingest_surface(
            make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=197,
                y=407,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.CASTLE,
                        name_text="K2875067781632",
                        kingdom="K287",
                        viewport_offset=(4, 252),
                        viewport_offset_ratio=(4 / 900, 252 / 1184),
                        estimated_world_coordinate=(201, 659),
                        confirmed_world_coordinate=(198, 655),
                    ),
                ),
            )
        )[0]

        self.assertEqual(sighting.key.addressing_kind, WorldMapObjectAddressingKind.CONFIRMED_WORLD)
        self.assertEqual(sighting.key.coordinate, (198, 655))

    def test_snapshot_preserves_index_order_and_evidence_links_without_duplicate_history(self) -> None:
        """Exports the canonical indexed state in first-seen order while preserving screenshot and profile evidence."""

        index = WorldMapSurveyIndex()
        first_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=253,
            y=447,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="VisibleCastle",
                    kingdom="K287",
                    viewport_offset=(4, 252),
                    viewport_offset_ratio=(4 / 900, 252 / 1184),
                    estimated_world_coordinate=(201, 659),
                ),
                make_spatial_object(
                    SpatialObjectKind.MONSTER,
                    name_text="Lv.5 Fiend",
                    viewport_offset=(-80, -60),
                    viewport_offset_ratio=(-80 / 900, -60 / 1184),
                ),
            ),
        )
        updated_surface = make_spatial_surface(
            SpatialSurfaceType.WORLD_MAP,
            x=260,
            y=452,
            objects=(
                make_spatial_object(
                    SpatialObjectKind.CASTLE,
                    name_text="VisibleCastle",
                    kingdom="K287",
                    viewport_offset=(12, 210),
                    viewport_offset_ratio=(12 / 900, 210 / 1184),
                    estimated_world_coordinate=(201, 659),
                    action_point=(444, 962),
                ),
                make_spatial_object(
                    SpatialObjectKind.RESOURCE_NODE,
                    name_text="Mine",
                    viewport_offset=(96, 110),
                    viewport_offset_ratio=(96 / 900, 110 / 1184),
                    confirmed_world_coordinate=(349, 557),
                ),
            ),
        )

        first_castle = index.ingest_surface(first_surface, artifact_path=Path("artifacts/first.png"))[0]
        index.ingest_surface(updated_surface, artifact_path=Path("artifacts/second.png"))
        index.annotate_castle_player_name(
            first_castle.key,
            player_name="LadiesLoveCake",
            profile_artifact_path=Path("artifacts/profile.png"),
        )

        snapshot = index.snapshot(
            artifact_directory="k287_visible_castle",
            label="survey_step",
            captured_at=first_castle.captured_at or make_observation(ScreenType.PNC_WORLD_MAP).captured_at,
            artifact_path=Path("artifacts/second.png"),
            surface=updated_surface,
        )

        sightings = snapshot["sightings"]
        self.assertEqual(len(sightings), 3)
        self.assertEqual(
            [sighting["key"]["addressing_kind"] for sighting in sightings],
            [
                WorldMapObjectAddressingKind.ESTIMATED_WORLD.value,
                WorldMapObjectAddressingKind.VIEWPORT_RELATIVE.value,
                WorldMapObjectAddressingKind.CONFIRMED_WORLD.value,
            ],
        )
        self.assertEqual(
            sightings[0]["artifact_path"],
            str(Path("artifacts/second.png")),
        )
        self.assertEqual(
            sightings[0]["profile_artifact_path"],
            str(Path("artifacts/profile.png")),
        )
        self.assertEqual(sightings[0]["resolved_player_name"], "LadiesLoveCake")
        self.assertEqual(
            sightings[1]["key"]["viewport_offset_ratio"],
            {"x": round(-80 / 900, 4), "y": round(-60 / 1184, 4)},
        )
        self.assertEqual(snapshot["checkpoint"]["viewport"]["coordinate"], {"x": 260, "y": 452})
        self.assertEqual(snapshot["checkpoint"]["viewport"]["addressing_kind"], "coordinate_bar")


if __name__ == "__main__":
    unittest.main()
