"""Action tap targets."""

from __future__ import annotations

from dataclasses import replace
import unittest

from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.pnc.domain.action_requests import (
    TapAction,
    TapListEntryAction,
    TapSpatialObjectAction,
)
from pnc_automation.app.pnc.domain.building_catalog import (
    HomeCityObjectId,
    build_home_city_object_metadata,
)
from pnc_automation.app.pnc.domain.observation import (
    Bounds,
    DetectedListEntry,
    ListEntryKind,
    Observation,
    RowRecognitionStatus,
    SpatialObjectKind,
    SpatialObjectQuery,
    SpatialSurfaceType,
)
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict, ScreenDecision, ScreenEvidence
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.selectors import build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError

from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.pnc.observations import make_entry, make_observation, make_visible
from tests.support.pnc.spatial import make_spatial_object, make_spatial_surface
from tests.support.automation.engine.automation_framework_fixtures import (
    AutomationFrameworkFixtures,
)


def _protected_observation(
    kind: ListEntryKind,
    *,
    row_status: RowRecognitionStatus = RowRecognitionStatus.COMPLETE,
    item_id: str = "gold:50:normal",
) -> Observation:
    """Build one protected row with independently bounded single-action geometry."""

    screen = ScreenType.PNC_QUEST_DAILY if kind == ListEntryKind.DAILY_QUEST else ScreenType.PNC_BAG
    entry = DetectedListEntry(
        kind=kind,
        bounds=Bounds(40, 40, 20, 20),
        title_text="Protected row",
        action_point=(50, 50) if row_status == RowRecognitionStatus.COMPLETE else None,
        action_bounds=Bounds(44, 44, 12, 12) if row_status == RowRecognitionStatus.COMPLETE else None,
        row_status=row_status,
        metadata={"item_id": item_id},
    )
    return make_observation(screen, list_entries=(entry,))


class ActionTapTargetsTests(AutomationFrameworkFixtures, unittest.TestCase):
    """Proves action tap targets."""

    def test_tap_actions_prefer_visible_element_action_points(self) -> None:
        """Uses selector-specific action points when OCR-derived bounds are not the real touch target."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(ScreenType.PNC_HOME_CITY)
        observation = Observation(
            decision=ScreenDecision(
                base_screen=ScreenType.PNC_HOME_CITY,
                effective_screen=ScreenType.PNC_HOME_CITY,
                guard=GuardVerdict.CLEAR,
                evidence=(ScreenEvidence(ScreenType.PNC_HOME_CITY, "test"),),
            ),
            visible_elements={
                UiElementId.PNC_BOTTOM_NAV_BAG: replace(
                    make_visible(
                        UiElementId.PNC_BOTTOM_NAV_BAG,
                        x=440,
                        y=1560,
                        width=54,
                        height=33,
                        action_point=(482, 1529),
                    ),
                    frame_ref=observation.frame_ref,
                    source_screen=observation.screen_type,
                    source_layout_id=observation.decision.layout_id,
                )
            },
            frame_ref=observation.frame_ref,
        )

        executor.execute_action(
            TapAction(selector_id=UiElementId.PNC_BOTTOM_NAV_BAG),
            observation,
        )

        self.assertEqual(executor.session.taps, [(482, 1529)])

    def test_tap_list_entry_action_matches_castle_titles_with_spacing_only_ocr_drift(self) -> None:
        """Resolves castle-row taps through the shared OCR-tolerant castle-name matcher."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_CASTLE_SELECTION,
            list_entries=(
                make_entry(
                    ListEntryKind.CASTLE,
                    title="please bgentle",
                    metadata={"kingdom": "K226", "castle_level": 12},
                    action_point=(240, 872),
                ),
            ),
        )

        executor.execute_action(
            TapListEntryAction(
                entry_kind=ListEntryKind.CASTLE,
                title_text="please b gentle",
                metadata_key="kingdom",
                metadata_value="K226",
                use_action_point=True,
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(240, 872)])

    def test_tap_spatial_object_actions_use_current_viewport_action_points(self) -> None:
        """Uses the live spatial-object action point from the current viewport instead of any fixed building coordinate."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_HOME_CITY,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.HOME_CITY_SURFACE,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.HOME_BUILDING,
                        name_text="Castle",
                        metadata=build_home_city_object_metadata(HomeCityObjectId.CASTLE),
                        action_point=(167, 241),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.HOME_CITY_SURFACE,
                    kind=SpatialObjectKind.HOME_BUILDING,
                    name_text="Castle",
                    metadata_key="home_city_object_id",
                    metadata_value="castle",
                )
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(167, 241)])

    def test_tap_spatial_object_actions_preserve_duplicate_target_points(self) -> None:
        """Uses the concrete target point captured during planning instead of re-resolving duplicate semantic matches."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        observation = make_observation(
            ScreenType.PNC_WORLD_MAP,
            spatial_surface=make_spatial_surface(
                SpatialSurfaceType.WORLD_MAP,
                x=253,
                y=447,
                objects=(
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(55, 66),
                    ),
                    make_spatial_object(
                        SpatialObjectKind.RESOURCE_NODE,
                        name_text="Food Farm",
                        metadata={"resource_type": "food"},
                        action_point=(155, 166),
                    ),
                ),
            ),
        )

        executor.execute_action(
            TapSpatialObjectAction(
                query=SpatialObjectQuery(
                    surface_type=SpatialSurfaceType.WORLD_MAP,
                    kind=SpatialObjectKind.RESOURCE_NODE,
                    name_text="Food Farm",
                    metadata_key="resource_type",
                    metadata_value="food",
                ),
                target_point=(155, 166),
            ),
            observation,
        )

        self.assertEqual(executor.session.taps, [(155, 166)])

    def test_protected_rows_reject_stale_provenance_and_cross_row_ambiguity(self) -> None:
        """Fresh row identity and frame provenance prevent a tap from crossing rows or captures."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        first = _protected_observation(ListEntryKind.DAILY_QUEST, item_id="quest-a")
        duplicate = _protected_observation(ListEntryKind.DAILY_QUEST, item_id="quest-a")
        duplicate = Observation(
            decision=first.decision,
            visible_elements=first.visible_elements,
            list_entries=(first.list_entries[0], duplicate.list_entries[0]),
            image_size=first.image_size,
            frame_ref=first.frame_ref,
        )
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(
                TapListEntryAction(
                    entry_kind=ListEntryKind.DAILY_QUEST,
                    metadata_key="item_id",
                    metadata_value="quest-a",
                    use_action_point=True,
                ),
                duplicate,
            )
        stale_entry = first.list_entries[0].__class__(
            kind=first.list_entries[0].kind,
            bounds=first.list_entries[0].bounds,
            title_text=first.list_entries[0].title_text,
            action_point=first.list_entries[0].action_point,
            action_bounds=first.list_entries[0].action_bounds,
            row_status=first.list_entries[0].row_status,
            metadata=first.list_entries[0].metadata,
            frame_ref=None,
            source_screen=first.screen_type,
            source_layout_id=first.decision.layout_id,
        )
        stale = Observation(
            decision=first.decision,
            visible_elements=first.visible_elements,
            list_entries=(stale_entry,),
            image_size=first.image_size,
            frame_ref=first.frame_ref,
        )
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(
                TapListEntryAction(
                    entry_kind=ListEntryKind.DAILY_QUEST,
                    metadata_key="item_id",
                    metadata_value="quest-a",
                    use_action_point=True,
                ),
                stale,
            )
        self.assertEqual([], executor.session.taps)

    def test_protected_rows_require_complete_action_geometry_and_explicit_point(self) -> None:
        """Daily and Resource rows cannot fall back to card centers or incomplete geometry."""

        executor = ActionExecutor(
            selector_registry=build_default_selector_registry(),
            session=FakeSession(),
            stable_click_delay_ms=0,
            post_action_observe_delay_ms=0,
            chat_stable_click_delay_ms=0,
            chat_post_action_observe_delay_ms=0,
            logger=build_logger(),
            sleep=lambda _: None,
        )
        complete = _protected_observation(ListEntryKind.RESOURCE_ITEM)
        executor.execute_action(
            TapListEntryAction(
                entry_kind=ListEntryKind.RESOURCE_ITEM,
                metadata_key="item_id",
                metadata_value="gold:50:normal",
                use_action_point=True,
            ),
            complete,
        )
        self.assertEqual([(50, 50)], executor.session.taps)

        for row in (
            _protected_observation(ListEntryKind.RESOURCE_ITEM, row_status=RowRecognitionStatus.CLIPPED),
            _protected_observation(ListEntryKind.RESOURCE_ITEM, row_status=RowRecognitionStatus.NO_ACTION),
            _protected_observation(ListEntryKind.RESOURCE_INVENTORY_EXCLUSION),
            _protected_observation(ListEntryKind.RESOURCE_INVENTORY_UNRESOLVED),
        ):
            with self.subTest(status=row.list_entries[0].row_status):
                with self.assertRaises(SelectorResolutionError):
                    executor.execute_action(
                        TapListEntryAction(
                            entry_kind=row.list_entries[0].kind,
                            metadata_key="item_id",
                            metadata_value="gold:50:normal",
                            use_action_point=True,
                        ),
                        row,
                    )
        with self.assertRaises(SelectorResolutionError):
            executor.execute_action(
                TapListEntryAction(
                    entry_kind=ListEntryKind.RESOURCE_ITEM,
                    metadata_key="item_id",
                    metadata_value="gold:50:normal",
                    use_action_point=False,
                ),
                complete,
            )
        self.assertEqual([(50, 50)], executor.session.taps)
