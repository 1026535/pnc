"""Selector discovery tests for reviewed registry refinement workflows."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.capture.artifact_store import ArtifactStore
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.screen_type import ScreenType
from pnc_automation.pnc.ui_element_id import UiElementId
from pnc_automation.vision.observation_builder import ObservationBuilder, PillowSelectorEngine
from pnc_automation.vision.ocr_service import UnavailableOcrService
from pnc_automation.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.vision.screen_classifier import ScreenClassifier
from pnc_automation.vision.selector_catalog import SelectorCatalogDocument, SelectorCatalogEntry
from pnc_automation.vision.selector_discovery import SelectorDiscoveryAnalyzer, load_artifact_paths
from pnc_automation.vision.selectors import SelectorRegistry
from pnc_automation.vision.template_matcher import PillowTemplateMatcher
from tests.test_capture_and_vision import _FakeOcrService, _FakeScreenshotSession, _encode_png, _ocr_line
from tests.test_support import make_observation


class SelectorDiscoveryTests(unittest.TestCase):
    """Validates artifact and live-probe discovery draft generation."""

    def test_analyze_artifact_path_discovers_academy_category_drafts(self) -> None:
        """Builds academy category draft selectors from one saved artifact."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot = self._capture_blank_screenshot(root=root, label="academy")
            analyzer = self._build_analyzer(
                lines=(
                    _ocr_line("Institute", x=108, y=12, width=115, height=29),
                    _ocr_line("Upgrade", x=404, y=263, width=88, height=25),
                    _ocr_line("Development", x=41, y=335, width=111, height=20),
                    _ocr_line("Economy", x=304, y=333, width=79, height=24),
                    _ocr_line("Military", x=38, y=412, width=67, height=24),
                    _ocr_line("Fortification", x=306, y=415, width=99, height=17),
                    _ocr_line("Unit Tactics", x=41, y=492, width=113, height=20),
                    _ocr_line("Formations", x=307, y=494, width=98, height=19),
                ),
            )

            snapshot = analyzer.analyze_artifact_path(screenshot.artifact.path)

            self.assertEqual(snapshot.screen_type, ScreenType.PNC_ACADEMY)
            self.assertEqual(
                {draft.id for draft in snapshot.draft_selectors},
                {
                    "PNC_ACADEMY_CATEGORY_DEVELOPMENT",
                    "PNC_ACADEMY_CATEGORY_ECONOMY",
                    "PNC_ACADEMY_CATEGORY_MILITARY",
                    "PNC_ACADEMY_CATEGORY_FORTIFICATION",
                    "PNC_ACADEMY_CATEGORY_UNIT_TACTICS",
                    "PNC_ACADEMY_CATEGORY_FORMATIONS",
                },
            )

    def test_analyze_artifact_path_skips_catalog_entries_already_seeded(self) -> None:
        """Suppresses drafts for selectors already refined in the static catalog."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot = self._capture_blank_screenshot(root=root, label="academy_existing")
            analyzer = self._build_analyzer(
                lines=(
                    _ocr_line("Institute", x=108, y=12, width=115, height=29),
                    _ocr_line("Upgrade", x=404, y=263, width=88, height=25),
                    _ocr_line("Development", x=41, y=335, width=111, height=20),
                    _ocr_line("Economy", x=304, y=333, width=79, height=24),
                    _ocr_line("Military", x=38, y=412, width=67, height=24),
                    _ocr_line("Fortification", x=306, y=415, width=99, height=17),
                ),
                catalog=SelectorCatalogDocument(
                    selectors=(
                        SelectorCatalogEntry(
                            id="PNC_ACADEMY_CATEGORY_ECONOMY",
                            screens=("PNC_ACADEMY",),
                            status="screenshot_seeded",
                            detection_kind="template",
                        ),
                    ),
                ),
            )

            snapshot = analyzer.analyze_artifact_path(screenshot.artifact.path)
            draft_ids = {draft.id for draft in snapshot.draft_selectors}

            self.assertEqual(snapshot.screen_type, ScreenType.PNC_ACADEMY)
            self.assertIn("PNC_ACADEMY_CATEGORY_DEVELOPMENT", draft_ids)
            self.assertNotIn("PNC_ACADEMY_CATEGORY_ECONOMY", draft_ids)

    def test_analyze_artifact_path_discovers_research_tree_collection_selector(self) -> None:
        """Builds the research-node collection draft from one research-tree artifact."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot = self._capture_blank_screenshot(root=root, label="research_tree")
            analyzer = self._build_analyzer(
                lines=(
                    _ocr_line("Military", x=107, y=9, width=109, height=38),
                    _ocr_line("Troop Size I", x=229, y=340, width=90, height=20),
                    _ocr_line("March Speed", x=221, y=714, width=103, height=19),
                    _ocr_line("0/3", x=106, y=425, width=25, height=14),
                    _ocr_line("0/5", x=230, y=615, width=27, height=16),
                ),
            )

            snapshot = analyzer.analyze_artifact_path(screenshot.artifact.path)
            draft_by_id = {draft.id: draft for draft in snapshot.draft_selectors}

            self.assertEqual(snapshot.screen_type, ScreenType.PNC_RESEARCH_TREE)
            self.assertEqual(draft_by_id["PNC_RESEARCH_NODE_ENTRY"].detection_kind, "collection")
            self.assertEqual(draft_by_id["PNC_RESEARCH_NODE_ENTRY"].status, "screenshot_seeded")

    def test_build_probe_draft_promotes_click_mapping_for_existing_selector(self) -> None:
        """Builds a click-mapped update draft from one reviewed live probe."""

        analyzer = self._build_analyzer(
            lines=(),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_BAG",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            ),
        )
        probe = analyzer.build_probe_draft(
            selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
            source_observation=make_observation(
                ScreenType.PNC_HOME_CITY,
                visible_ids=(UiElementId.PNC_BOTTOM_NAV_BAG, UiElementId.PNC_HOME_WORLD_SWITCH),
            ),
            destination_observation=make_observation(
                ScreenType.PNC_BAG,
                visible_ids=(UiElementId.PNC_BAG_MAIN_TAB_BAG, UiElementId.PNC_BAG_USE_BUTTON),
            ),
            source_artifact_path=Path("source.png"),
            destination_artifact_path=Path("destination.png"),
        )

        self.assertIsNotNone(probe.draft_selector)
        self.assertEqual(probe.destination_screen_type, ScreenType.PNC_BAG)
        self.assertEqual(probe.draft_selector.status, "click_mapped")
        self.assertEqual(probe.draft_selector.detection_kind, "template")
        self.assertEqual(probe.draft_selector.interaction_kind, "navigation")
        self.assertIsNotNone(probe.draft_selector.relative_bounds)
        self.assertEqual(probe.draft_selector.relative_bounds.x_ratio, 0.0)
        self.assertEqual(probe.draft_selector.relative_bounds.width_ratio, 0.05)
        self.assertEqual(probe.draft_selector.click.anchor, "center")
        self.assertEqual(probe.draft_selector.click.outcomes[0].target_screen, "PNC_BAG")
        self.assertEqual(
            probe.draft_selector.click.outcomes[0].verification_selectors,
            ("PNC_BAG_MAIN_TAB_BAG", "PNC_BAG_USE_BUTTON"),
        )

    def test_build_probe_draft_keeps_unknown_destination_as_probe_only(self) -> None:
        """Does not emit a promotable draft when the reviewed destination screen is still unknown."""

        analyzer = self._build_analyzer(
            lines=(),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_BAG",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            ),
        )

        probe = analyzer.build_probe_draft(
            selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
            source_observation=make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_BAG,)),
            destination_observation=make_observation(ScreenType.UNKNOWN, visible_ids=(UiElementId.PNC_BAG_MAIN_TAB_BAG,)),
            source_artifact_path=Path("source.png"),
            destination_artifact_path=Path("destination.png"),
        )

        self.assertIsNone(probe.draft_selector)
        self.assertEqual(probe.destination_screen_type, ScreenType.UNKNOWN)

    def test_build_probe_draft_requires_verification_selectors(self) -> None:
        """Does not emit a promotable draft when the destination lacks explicit selector evidence."""

        analyzer = self._build_analyzer(
            lines=(),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_BOTTOM_NAV_BAG",
                        screens=("PNC_HOME_CITY",),
                        status="screenshot_seeded",
                        detection_kind="template",
                    ),
                ),
            ),
        )

        probe = analyzer.build_probe_draft(
            selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
            source_observation=make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_BAG,)),
            destination_observation=make_observation(ScreenType.PNC_BAG),
            source_artifact_path=Path("source.png"),
            destination_artifact_path=Path("destination.png"),
        )

        self.assertIsNone(probe.draft_selector)
        self.assertEqual(probe.destination_screen_type, ScreenType.PNC_BAG)

    def test_build_probe_draft_requires_catalog_backed_selector(self) -> None:
        """Fails fast when a live probe targets a selector missing from the static catalog."""

        analyzer = self._build_analyzer(lines=(), catalog=SelectorCatalogDocument(selectors=()))

        with self.assertRaises(SelectorResolutionError):
            analyzer.build_probe_draft(
                selector_id=UiElementId.PNC_BOTTOM_NAV_BAG,
                source_observation=make_observation(ScreenType.PNC_HOME_CITY, visible_ids=(UiElementId.PNC_BOTTOM_NAV_BAG,)),
                destination_observation=make_observation(ScreenType.PNC_BAG, visible_ids=(UiElementId.PNC_BAG_MAIN_TAB_BAG,)),
                source_artifact_path=Path("source.png"),
                destination_artifact_path=Path("destination.png"),
            )

    def test_load_artifact_paths_deduplicates_and_accepts_uppercase_pngs(self) -> None:
        """Loads explicit and directory-sourced artifacts without duplicate resolved paths."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            lower_png = root / "alpha.png"
            upper_png = root / "beta.PNG"
            ignored = root / "gamma.txt"
            lower_png.write_bytes(b"png")
            upper_png.write_bytes(b"png")
            ignored.write_text("ignore", encoding="utf-8")

            paths = load_artifact_paths(
                artifact_paths=(lower_png, lower_png.resolve()),
                artifact_directory=root,
            )

            self.assertEqual(paths, (lower_png.resolve(), upper_png.resolve()))

    def _build_analyzer(
        self,
        *,
        lines: tuple,
        catalog: SelectorCatalogDocument | None = None,
    ) -> SelectorDiscoveryAnalyzer:
        """Builds one analyzer with a deterministic OCR-backed observation pipeline."""

        ocr_service = _FakeOcrService(lines=lines)
        observation_builder = ObservationBuilder(
            selector_registry=SelectorRegistry(selectors=()),
            selector_engine=PillowSelectorEngine(
                template_matcher=PillowTemplateMatcher(),
                ocr_service=UnavailableOcrService(),
            ),
            screen_classifier=ScreenClassifier(),
            enricher=PncObservationEnricher(ocr_service=ocr_service),
        )
        return SelectorDiscoveryAnalyzer(
            observation_builder=observation_builder,
            ocr_service=ocr_service,
            catalog=SelectorCatalogDocument(selectors=()) if catalog is None else catalog,
        )

    def _capture_blank_screenshot(self, *, root: Path, label: str) -> object:
        """Writes one blank PNG artifact consumable by artifact-path discovery tests."""

        screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
        return screenshot_service.capture(
            _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
            artifact_directory="k230_discovery",
            label=label,
        )


if __name__ == "__main__":
    unittest.main()
