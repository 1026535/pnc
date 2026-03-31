"""Selector discovery tests for reviewed registry refinement workflows."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.capture.artifact_store import ArtifactStore
from pnc_automation.capture.screenshot_service import ScreenshotService
from pnc_automation.errors import SelectorResolutionError
from pnc_automation.pnc.observation import Bounds, Observation, VisibleElement, VisibleElementSourceKind
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

    def test_analyze_artifact_path_discovers_institute_category_drafts(self) -> None:
        """Builds institute category draft selectors from one saved artifact."""

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

            self.assertEqual(snapshot.screen_type, ScreenType.PNC_INSTITUTE)
            self.assertEqual(
                {draft.id for draft in snapshot.draft_selectors},
                {
                    "PNC_INSTITUTE_DEVELOPMENT_BUTTON",
                    "PNC_INSTITUTE_ECONOMY_BUTTON",
                    "PNC_INSTITUTE_MILITARY_BUTTON",
                    "PNC_INSTITUTE_FORTIFICATION_BUTTON",
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
                            id="PNC_INSTITUTE_ECONOMY_BUTTON",
                            screens=("PNC_INSTITUTE",),
                            status="screenshot_seeded",
                            detection_kind="template",
                        ),
                    ),
                ),
            )

            snapshot = analyzer.analyze_artifact_path(screenshot.artifact.path)
            draft_ids = {draft.id for draft in snapshot.draft_selectors}

            self.assertEqual(snapshot.screen_type, ScreenType.PNC_INSTITUTE)
            self.assertIn("PNC_INSTITUTE_DEVELOPMENT_BUTTON", draft_ids)
            self.assertNotIn("PNC_INSTITUTE_ECONOMY_BUTTON", draft_ids)

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

    def test_build_visible_selector_drafts_promotes_ocr_backed_labels_to_relative_ocr_regions(self) -> None:
        """Promotes OCR-backed label selectors to normalized OCR-region draft updates."""

        analyzer = self._build_analyzer(
            lines=(),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_VIP_HEADER",
                        screens=("PNC_VIP",),
                        status="screenshot_seeded",
                        detection_kind="planned",
                        interaction_kind="label",
                    ),
                ),
            ),
        )
        observation = Observation(
            screen_type=ScreenType.PNC_VIP,
            visible_elements={
                UiElementId.PNC_VIP_HEADER: VisibleElement(
                    selector_id=UiElementId.PNC_VIP_HEADER,
                    bounds=Bounds(x=24, y=9, width=84, height=18),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.OCR,
                    extracted_text="VIP",
                ),
            },
            artifact_path=Path("vip.png"),
            image_size=(200, 100),
        )

        drafts = analyzer.build_visible_selector_drafts(
            observation=observation,
            artifact_path=Path("vip.png"),
            selector_ids=(UiElementId.PNC_VIP_HEADER,),
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].detection_kind, "ocr_region")
        self.assertIsNotNone(drafts[0].relative_bounds)
        self.assertAlmostEqual(drafts[0].relative_bounds.x_ratio, 0.12)
        self.assertAlmostEqual(drafts[0].relative_bounds.y_ratio, 0.09)
        self.assertAlmostEqual(drafts[0].relative_bounds.width_ratio, 0.42)
        self.assertAlmostEqual(drafts[0].relative_bounds.height_ratio, 0.18)

    def test_build_visible_selector_drafts_seed_relative_bounds_for_planned_geometry(self) -> None:
        """Stages screenshot-seeded geometry when a planned selector becomes visible live."""

        analyzer = self._build_analyzer(
            lines=(),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_MORE_LORD_INFO",
                        screens=("PNC_MORE_MENU",),
                        status="planned",
                        detection_kind="planned",
                    ),
                ),
            ),
        )
        observation = Observation(
            screen_type=ScreenType.PNC_MORE_MENU,
            visible_elements={
                UiElementId.PNC_MORE_LORD_INFO: VisibleElement(
                    selector_id=UiElementId.PNC_MORE_LORD_INFO,
                    bounds=Bounds(x=20, y=10, width=40, height=30),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.GEOMETRY,
                    action_point=(80, 40),
                ),
            },
            artifact_path=Path("more_menu.png"),
            image_size=(200, 100),
        )

        drafts = analyzer.build_visible_selector_drafts(
            observation=observation,
            artifact_path=Path("more_menu.png"),
            selector_ids=(UiElementId.PNC_MORE_LORD_INFO,),
        )

        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0].status, "screenshot_seeded")
        self.assertEqual(drafts[0].detection_kind, "planned")
        self.assertIsNotNone(drafts[0].relative_bounds)
        self.assertAlmostEqual(drafts[0].relative_bounds.x_ratio, 0.1)
        self.assertAlmostEqual(drafts[0].relative_bounds.y_ratio, 0.1)
        self.assertAlmostEqual(drafts[0].relative_bounds.width_ratio, 0.2)
        self.assertAlmostEqual(drafts[0].relative_bounds.height_ratio, 0.3)
        self.assertAlmostEqual(drafts[0].relative_bounds.action_x_ratio, 0.4)
        self.assertAlmostEqual(drafts[0].relative_bounds.action_y_ratio, 0.4)

    def test_build_visible_selector_drafts_stage_collection_title_and_timer_regions(self) -> None:
        """Stages row child OCR regions as normalized geometry from a visible Cash Mall collection row."""

        analyzer = self._build_analyzer(
            lines=(
                _ocr_line("Super Sale Bundle", x=18, y=36, width=120, height=16),
                _ocr_line("01:23:45", x=22, y=58, width=64, height=14),
            ),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_CASH_MALL_ENTRY_TITLE_REGION",
                        screens=("PNC_CASH_MALL",),
                        status="planned",
                        detection_kind="planned",
                    ),
                    SelectorCatalogEntry(
                        id="PNC_CASH_MALL_ENTRY_TIMER_REGION",
                        screens=("PNC_CASH_MALL",),
                        status="planned",
                        detection_kind="planned",
                    ),
                ),
            ),
        )
        observation = Observation(
            screen_type=ScreenType.PNC_CASH_MALL,
            visible_elements={
                UiElementId.PNC_CASH_MALL_ENTRY_ROW: VisibleElement(
                    selector_id=UiElementId.PNC_CASH_MALL_ENTRY_ROW,
                    bounds=Bounds(x=0, y=24, width=180, height=60),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.TEMPLATE,
                ),
            },
            artifact_path=Path("cash_mall.png"),
            image_size=(200, 100),
        )

        drafts = analyzer.build_visible_selector_drafts(
            observation=observation,
            artifact_path=Path("cash_mall.png"),
            selector_ids=(
                UiElementId.PNC_CASH_MALL_ENTRY_TITLE_REGION,
                UiElementId.PNC_CASH_MALL_ENTRY_TIMER_REGION,
            ),
            image=Image.new("RGB", (200, 100), (0, 0, 0)),
        )
        draft_by_id = {draft.id: draft for draft in drafts}

        self.assertEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TITLE_REGION"].detection_kind, "ocr_region")
        self.assertEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TITLE_REGION"].status, "screenshot_seeded")
        self.assertAlmostEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TITLE_REGION"].relative_bounds.x_ratio, 0.09)
        self.assertAlmostEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TITLE_REGION"].relative_bounds.y_ratio, 0.36)
        self.assertAlmostEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TIMER_REGION"].relative_bounds.x_ratio, 0.11)
        self.assertAlmostEqual(draft_by_id["PNC_CASH_MALL_ENTRY_TIMER_REGION"].relative_bounds.y_ratio, 0.58)

    def test_build_visible_selector_drafts_stage_collection_subtitle_and_expiry_regions(self) -> None:
        """Stages Gift Center subtitle and expiry OCR regions from the visible first row."""

        analyzer = self._build_analyzer(
            lines=(
                _ocr_line("Gift Pack", x=18, y=36, width=70, height=16),
                _ocr_line("Exclusive Rewards", x=18, y=56, width=110, height=16),
                _ocr_line("2d 03:12:44", x=18, y=76, width=86, height=16),
            ),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_GIFT_CENTER_ENTRY_TITLE_REGION",
                        screens=("PNC_GIFT_CENTER",),
                        status="planned",
                        detection_kind="planned",
                    ),
                    SelectorCatalogEntry(
                        id="PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION",
                        screens=("PNC_GIFT_CENTER",),
                        status="planned",
                        detection_kind="planned",
                    ),
                    SelectorCatalogEntry(
                        id="PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION",
                        screens=("PNC_GIFT_CENTER",),
                        status="planned",
                        detection_kind="planned",
                    ),
                ),
            ),
        )
        observation = Observation(
            screen_type=ScreenType.PNC_GIFT_CENTER,
            visible_elements={
                UiElementId.PNC_GIFT_CENTER_ENTRY_ROW: VisibleElement(
                    selector_id=UiElementId.PNC_GIFT_CENTER_ENTRY_ROW,
                    bounds=Bounds(x=0, y=24, width=180, height=72),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.TEMPLATE,
                ),
            },
            artifact_path=Path("gift_center.png"),
            image_size=(200, 100),
        )

        drafts = analyzer.build_visible_selector_drafts(
            observation=observation,
            artifact_path=Path("gift_center.png"),
            selector_ids=(
                UiElementId.PNC_GIFT_CENTER_ENTRY_TITLE_REGION,
                UiElementId.PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION,
                UiElementId.PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION,
            ),
            image=Image.new("RGB", (200, 100), (0, 0, 0)),
        )
        draft_by_id = {draft.id: draft for draft in drafts}

        self.assertAlmostEqual(draft_by_id["PNC_GIFT_CENTER_ENTRY_TITLE_REGION"].relative_bounds.y_ratio, 0.36)
        self.assertAlmostEqual(draft_by_id["PNC_GIFT_CENTER_ENTRY_SUBTITLE_REGION"].relative_bounds.y_ratio, 0.56)
        self.assertAlmostEqual(draft_by_id["PNC_GIFT_CENTER_ENTRY_EXPIRY_REGION"].relative_bounds.y_ratio, 0.76)

    def test_build_visible_selector_drafts_stage_event_center_title_and_timer_regions(self) -> None:
        """Stages Event Center title and timer OCR regions from the visible first row."""

        analyzer = self._build_analyzer(
            lines=(
                _ocr_line("Alliance Clash", x=22, y=34, width=94, height=16),
                _ocr_line("12:45:10", x=24, y=58, width=66, height=16),
            ),
            catalog=SelectorCatalogDocument(
                selectors=(
                    SelectorCatalogEntry(
                        id="PNC_EVENT_CENTER_ENTRY_TITLE_REGION",
                        screens=("PNC_EVENT_CENTER",),
                        status="planned",
                        detection_kind="planned",
                    ),
                    SelectorCatalogEntry(
                        id="PNC_EVENT_CENTER_ENTRY_TIMER_REGION",
                        screens=("PNC_EVENT_CENTER",),
                        status="planned",
                        detection_kind="planned",
                    ),
                ),
            ),
        )
        observation = Observation(
            screen_type=ScreenType.PNC_EVENT_CENTER,
            visible_elements={
                UiElementId.PNC_EVENT_CENTER_EVENT_ROW: VisibleElement(
                    selector_id=UiElementId.PNC_EVENT_CENTER_EVENT_ROW,
                    bounds=Bounds(x=0, y=24, width=180, height=60),
                    confidence=1.0,
                    source_kind=VisibleElementSourceKind.TEMPLATE,
                ),
            },
            artifact_path=Path("event_center.png"),
            image_size=(200, 100),
        )

        drafts = analyzer.build_visible_selector_drafts(
            observation=observation,
            artifact_path=Path("event_center.png"),
            selector_ids=(
                UiElementId.PNC_EVENT_CENTER_ENTRY_TITLE_REGION,
                UiElementId.PNC_EVENT_CENTER_ENTRY_TIMER_REGION,
            ),
            image=Image.new("RGB", (200, 100), (0, 0, 0)),
        )
        draft_by_id = {draft.id: draft for draft in drafts}

        self.assertAlmostEqual(draft_by_id["PNC_EVENT_CENTER_ENTRY_TITLE_REGION"].relative_bounds.y_ratio, 0.34)
        self.assertAlmostEqual(draft_by_id["PNC_EVENT_CENTER_ENTRY_TIMER_REGION"].relative_bounds.y_ratio, 0.58)

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
