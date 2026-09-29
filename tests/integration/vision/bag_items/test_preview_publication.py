"""Captured Bag chest-preview publication and screen-isolation checks."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.bag_items import TreasureIdentity, TreasureKind
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from tests.support.pnc.bag_items.publication import (
    BagPublicationAssertions,
    BoundedRapidOcrService,
    _ARENA_LAYOUT_ID,
    _ARENA_REWARDS,
    _COMMON_LAYOUT_ID,
    _COMMON_REWARDS,
    build_both,
    capture,
    wire,
)
from tests.support.pnc.capture_vision.require_rapid_ocr_service import _require_rapid_ocr_service


class BagPreviewPublicationTests(BagPublicationAssertions, unittest.TestCase):
    """Replayed previews publish rewards without leaking Bag inventory."""

    def test_arena_preview_publishes_rewards_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        for fixture in ("bag_arena_chest_preview.png", "bag_arena_chest_preview_holdout_20260915.png"):
            current = capture(fixture, session_id=f"v11-arena:{fixture}")
            builder_observation, navigation_observation = build_both(
                builder, navigation, backend, current, ScreenType.PNC_BAG_CHEST_PREVIEW
            )
            for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
                with self.subTest(fixture=fixture, publisher=name):
                    self.assert_preview(
                        observation,
                        current,
                        _ARENA_LAYOUT_ID,
                        TreasureIdentity(TreasureKind.ARENA_SURPRISE_CHEST),
                        _ARENA_REWARDS,
                    )
            self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
            self.assertEqual(builder_observation.bag_preview, navigation_observation.bag_preview)

    def test_common_preview_publishes_duplicate_rows_on_both_paths(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        current = capture("bag_common_victory_preview_20260916.png", session_id="v11-common-preview")
        builder_observation, navigation_observation = build_both(
            builder, navigation, backend, current, ScreenType.PNC_BAG_CHEST_PREVIEW
        )
        for name, observation in (("observation_builder", builder_observation), ("navigation_perception", navigation_observation)):
            with self.subTest(publisher=name):
                self.assert_preview(
                    observation,
                    current,
                    _COMMON_LAYOUT_ID,
                    TreasureIdentity(TreasureKind.COMMON_FIRST_VICTORY_CHEST),
                    _COMMON_REWARDS,
                )
                names = [
                    entry.bag_reward_facts.reward_name_text
                    for entry in observation.list_entries
                    if entry.bag_reward_facts is not None
                ]
                self.assertEqual(3, names.count("Lost Project Book"))
        self.assertEqual(builder_observation.list_entries, navigation_observation.list_entries)
        self.assertEqual(builder_observation.bag_preview, navigation_observation.bag_preview)

    def test_bag_frames_publish_no_preview_and_previews_publish_no_bag_items(self):
        backend = BoundedRapidOcrService(_require_rapid_ocr_service(self))
        builder, navigation = wire(backend)
        bag_capture = capture("bag_variants/bag_treasure_tab.png", session_id="v11-boundary-bag")
        bag_observation = builder.build(
            bag_capture,
            request=ObservationRequest.source_screen_retry(ScreenType.PNC_BAG),
            ocr_context=builder.create_ocr_context(bag_capture),
        )
        self.assertIsNone(bag_observation.bag_preview)
        self.assertEqual((), bag_observation.entries(ListEntryKind.BAG_PREVIEW_REWARD))
        backend.bind(bag_capture.image.size)
        preview_capture = capture("bag_arena_chest_preview.png", session_id="v11-boundary-preview")
        preview_observation = navigation.build(preview_capture, include_content=True)
        self.assertEqual((), preview_observation.entries(ListEntryKind.BAG_ITEM))
        self.assertIsNotNone(preview_observation.bag_preview)


if __name__ == "__main__":
    unittest.main()
