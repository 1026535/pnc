"""Offline tests for the canonical Daily Quest semantic catalog."""

from __future__ import annotations

import unittest

from pnc_automation.app.pnc.domain.daily_maintenance import DailyQuestDisposition, DailyQuestId
from pnc_automation.app.pnc.domain.daily_quest_catalog import (
    DailyQuestCatalog,
    DailyQuestDefinition,
)


class DailyQuestCatalogTests(unittest.TestCase):
    """Covers exact normalized aliases and disposition ownership."""

    def test_resolves_case_and_spacing_without_fuzzy_guessing(self) -> None:
        """Normalizes presentation differences but preserves unknown wording."""

        catalog = DailyQuestCatalog()

        self.assertEqual(DailyQuestId.HERO_ARENA, catalog.resolve_title("  hero arena 3 TIMES ").quest_id)
        self.assertIsNone(catalog.resolve_title("Hero championship 3 times"))

    def test_resolves_live_ocr_confusion_for_resource_item(self) -> None:
        """Accepts the observed OCR L-for-1 form without broad fuzzy matching."""

        catalog = DailyQuestCatalog()

        self.assertEqual(
            DailyQuestId.USE_RESOURCE_ITEM,
            catalog.resolve_title("Use resource item xL").quest_id,
        )

    def test_excluded_rows_remain_claim_only(self) -> None:
        """Keeps building, research, and training work out of task execution."""

        catalog = DailyQuestCatalog()

        for quest_id in (
            DailyQuestId.UPGRADE_BUILDING,
            DailyQuestId.UPGRADE_RESEARCH,
            DailyQuestId.TRAIN_INFANTRY,
            DailyQuestId.DEFEAT_HELL_FORTRESS,
        ):
            definition = catalog.require(quest_id)
            self.assertEqual(DailyQuestDisposition.EXCLUDED_CLAIM_ONLY, definition.disposition)

    def test_rejects_duplicate_normalized_alias(self) -> None:
        """Ensures one title can never select two capability owners."""

        definitions = (
            DailyQuestDefinition(
                quest_id=DailyQuestId.PRAISE,
                disposition=DailyQuestDisposition.ENABLED,
                title_aliases=frozenset({"Praise once"}),
            ),
            DailyQuestDefinition(
                quest_id=DailyQuestId.WISHES,
                disposition=DailyQuestDisposition.ENABLED,
                title_aliases=frozenset({" praise  ONCE "}),
            ),
        )

        with self.assertRaisesRegex(ValueError, "belongs to both"):
            DailyQuestCatalog(definitions)


if __name__ == "__main__":
    unittest.main()
