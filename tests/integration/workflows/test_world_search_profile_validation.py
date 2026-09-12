"""World search profile validation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.observation import (
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialObjectRelationship,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.navigation.world_map_index import WorldMapCastleQuery
from pnc_automation.app.pnc.navigation.world_map_search import (
    ObservationBackedWorldMapCastleInspector,
    WorldMapCastleProfileQuery,
    WorldMapSearchOrigin,
    WorldMapSearchPattern,
    adapt_world_map_search_matcher,
    all_of_world_map_search,
    any_of_world_map_search,
)
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.pnc.observations import make_observation
from tests.support.pnc.spatial import make_spatial_object
from tests.support.pnc.world_search.world_map_runtime_fixtures import WorldMapRuntimeFixtures
from tests.support.pnc.world_search.make_world_map_observation import _make_world_map_observation
from tests.support.pnc.world_search.search_request import _search_request


class WorldSearchProfileValidationTests(WorldMapRuntimeFixtures, unittest.TestCase):
    """Proves world search profile validation."""

    def test_castle_profile_validation_query_opens_lord_profile_then_fails_fast_as_unimplemented(self) -> None:
        """Reaches lord profile for the dedicated profile-validation path before failing with the intentional unimplemented error."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="UnknownCastle",
                            kingdom="K1",
                            confirmed_world_coordinate=(0, 0),
                            action_point=(77, 88),
                        ),
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_PROFILE,
                    profile_player_name="Alice",
                    visible_ids=(
                        UiElementId.PNC_PLAYER_PROFILE_HEADER,
                        UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                _make_world_map_observation(0, 0),
            ]
        )
        inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=service.observation_service,
            survey_recorder=service.survey_recorder,
            movement_step_budget=1,
        )
        capture = service.survey_recorder.capture_checkpoint("visible_candidate")
        candidate = capture.updated_sightings[0]
        current = capture.capture.observation

        with self.assertRaises(SelectorResolutionError) as error:
            inspector.inspect_candidates(
                matcher=adapt_world_map_search_matcher(
                    WorldMapCastleProfileQuery(
                        castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
                    )
                ),
                candidates=(candidate,),
                current_observation=current,
                label_prefix="inspect_visible_candidate",
            )

        self.assertIn("gear validation is not implemented", str(error.exception).lower())
        self.assertEqual(observer.observations, [])

    def test_all_of_profile_validation_matcher_inspects_eligible_castle_candidates(self) -> None:
        """Preserves castle-inspection behavior when profile validation is composed with map-side constraints."""

        service, observer = self._build_runtime_service(
            observations=[
                _make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="UnknownCastle",
                            kingdom="K1",
                            confirmed_world_coordinate=(0, 0),
                            action_point=(77, 88),
                        ),
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_PROFILE,
                    profile_player_name="Alice",
                    visible_ids=(
                        UiElementId.PNC_PLAYER_PROFILE_HEADER,
                        UiElementId.PNC_PLAYER_PROFILE_NAME_LABEL,
                    ),
                ),
                make_observation(
                    ScreenType.PNC_PLAYER_TERRITORY,
                    visible_ids=(
                        UiElementId.PNC_PLAYER_TERRITORY_HEADER,
                        UiElementId.PNC_PLAYER_TERRITORY_PLAYER_INFO_BUTTON,
                    ),
                ),
                _make_world_map_observation(0, 0),
            ]
        )
        service.castle_inspector = ObservationBackedWorldMapCastleInspector(
            screen_flows=self.flows,
            action_executor=service.action_executor,
            observation_service=service.observation_service,
            survey_recorder=service.survey_recorder,
            movement_step_budget=1,
        )

        with self.assertRaises(SelectorResolutionError) as error:
            service.execute_search(
                _search_request(
                    matcher=all_of_world_map_search(
                        WorldMapCastleQuery(kingdom="K1"),
                        WorldMapCastleProfileQuery(
                            castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
                        ),
                    ),
                    pattern=WorldMapSearchPattern.row_major_sweep(),
                    origin=WorldMapSearchOrigin.current_viewport(),
                    checkpoint_spacing=10,
                ),
                label_prefix="composed_profile_validation",
                start_observation=_make_world_map_observation(
                    0,
                    0,
                    objects=(
                        make_spatial_object(
                            SpatialObjectKind.CASTLE,
                            name_text="UnknownCastle",
                            kingdom="K1",
                            confirmed_world_coordinate=(0, 0),
                            action_point=(77, 88),
                        ),
                    ),
                ),
            )

        self.assertIn("gear validation is not implemented", str(error.exception).lower())
        self.assertEqual(observer.observations, [])

    def test_any_of_profile_validation_matcher_ranks_candidates_from_profile_child(self) -> None:
        """Lets disjunctive profile-validation matchers advertise and rank castle candidates."""

        service, _observer = self._build_runtime_service(observations=[])
        capture = service.survey_recorder.ingest_capture(
            type(
                "Capture",
                (),
                {
                    "observation": _make_world_map_observation(
                        0,
                        0,
                        objects=(
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="UnknownCastle",
                                kingdom="K1",
                                confirmed_world_coordinate=(0, 0),
                            ),
                        ),
                    )
                },
            )()
        )
        matcher = any_of_world_map_search(
            SpatialObjectQuery(surface_type=SpatialSurfaceType.WORLD_MAP, kind=SpatialObjectKind.MONSTER),
            WorldMapCastleProfileQuery(
                castle=WorldMapCastleQuery(player_name="Alice", kingdom="K1"),
            ),
        )

        self.assertTrue(matcher.supports_castle_enrichment())
        self.assertGreaterEqual(matcher.rank_castle_candidate(capture[0]), 0)

    def test_player_name_castle_enrichment_ranking_excludes_self_castles(self) -> None:
        """Does not inspect self-territory castles when resolving a remote player-name search."""
        service, _observer = self._build_runtime_service(observations=[])
        capture = service.survey_recorder.ingest_capture(
            type(
                "Capture",
                (),
                {
                    "observation": _make_world_map_observation(
                        0,
                        0,
                        objects=(
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="My Territory",
                                relationship=SpatialObjectRelationship.SELF,
                                confirmed_world_coordinate=(0, 0),
                            ),
                            make_spatial_object(
                                SpatialObjectKind.CASTLE,
                                name_text="UnknownCastle",
                                kingdom="K1",
                                confirmed_world_coordinate=(10, 0),
                            ),
                        ),
                    )
                },
            )()
        )
        self.assertEqual(len(capture), 2)
        self_sighting = next(sighting for sighting in capture if sighting.object_.relationship == SpatialObjectRelationship.SELF)
        other_sighting = next(sighting for sighting in capture if sighting.object_.relationship != SpatialObjectRelationship.SELF)
        matcher = adapt_world_map_search_matcher(
            WorldMapCastleProfileQuery(
                castle=WorldMapCastleQuery(player_name="Alice"),
            )
        )

        self.assertEqual(matcher.rank_castle_candidate(self_sighting), -1)
        self.assertGreaterEqual(matcher.rank_castle_candidate(other_sighting), 0)
