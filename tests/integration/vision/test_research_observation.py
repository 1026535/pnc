"""Research observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from pnc_automation.app.pnc.domain.observation import Bounds, ListEntryKind, RowRecognitionStatus
from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.navigation_perception import NavigationPerception
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry
from pnc_automation.app.pnc.vision.visual_screen_recognizer import load_visual_screen_recognizer
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
from pnc_automation.core.vision.ocr.ocr_service import ObservationOcrContext, OcrLine
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.fake_screenshot_session import make_captured_frame
from tests.support.paths import TEST_DATA_ROOT


RESEARCH_FIXTURE_PATH = TEST_DATA_ROOT / "screen_recognition" / "research_tree_development.png"
RESEARCH_ICON_BOXES = {
    "Construction I": Bounds(228, 76, 88, 84),
    "Research Speed I": Bounds(228, 266, 87, 84),
    "Troop Load I": Bounds(103, 456, 87, 84),
    "Storage I": Bounds(351, 456, 88, 84),
    "Infirmary Cap I": Bounds(228, 647, 87, 85),
}
RESEARCH_LABEL_BOXES = {
    "Construction I": Bounds(218, 159, 107, 49),
    "Research Speed I": Bounds(218, 350, 108, 48),
    "Troop Load I": Bounds(93, 541, 108, 48),
    "Storage I": Bounds(343, 541, 107, 48),
    "Infirmary Cap I": Bounds(218, 731, 108, 48),
}


def _load_research_fixture() -> Image.Image:
    """Load the reviewed Development tree fixture for content tests."""

    with Image.open(RESEARCH_FIXTURE_PATH) as source:
        return source.convert("RGB")


def _captured_research_image(image: Image.Image, *, session_id: str) -> CapturedScreenshot:
    """Attach frame provenance to one deterministic Development tree image."""

    frame = make_captured_frame(
        _encode_png(image),
        session_id=session_id,
    )
    return CapturedScreenshot(
        artifact=None,
        image=image,
        image_format="PNG",
        payload=frame.payload,
        ephemeral_captured_at=datetime.now(UTC),
        frame_ref=frame.frame_ref,
    )


def _captured_research_fixture() -> CapturedScreenshot:
    """Attach frame provenance to the reviewed Development tree fixture."""

    return _captured_research_image(
        _load_research_fixture(),
        session_id="research-observation-content",
    )


def _development_ocr_lines(*, scale: float = 1.0) -> tuple[OcrLine, ...]:
    """Return deterministic OCR output with the reviewed repair and split cases."""

    def scaled(value: int) -> int:
        return round(value * scale)

    return (
        _ocr_line("Development", x=scaled(112), y=scaled(14), width=scaled(183), height=scaled(27)),
        _ocr_line("Construction", x=scaled(222), y=scaled(183), width=scaled(102), height=scaled(17)),
        _ocr_line("Research", x=scaled(239), y=scaled(367), width=scaled(68), height=scaled(15)),
        _ocr_line("Speed I", x=scaled(245), y=scaled(382), width=scaled(57), height=scaled(18)),
        _ocr_line("TroopLoadi", x=scaled(103), y=scaled(563), width=scaled(93), height=scaled(18)),
        _ocr_line("Storagel", x=scaled(363), y=scaled(562), width=scaled(69), height=scaled(21)),
        _ocr_line("Infirmary Cap", x=scaled(219), y=scaled(746), width=scaled(105), height=scaled(19)),
        _ocr_line("Miraculous", x=scaled(231), y=scaled(936), width=scaled(84), height=scaled(19)),
    )


def _research_perception(lines: tuple[OcrLine, ...]) -> NavigationPerception:
    """Build replacement perception with one deterministic frame-local OCR backend."""

    ocr = _FakeOcrService(lines=lines)
    return NavigationPerception(
        load_visual_screen_recognizer(),
        PncObservationEnricher(),
        ScreenClassifier(),
        lambda capture: ObservationOcrContext(
            capture.image,
            ocr,
            capture.frame_ref,
            "research-observation-content-test",
        ),
    )


class ResearchObservationTests(unittest.TestCase):
    """Proves research observation."""

    def test_development_tree_emits_complete_rows_from_frame_local_ocr(self) -> None:
        """Publishes only fully visible Development labels as actionable rows."""

        screenshot = _captured_research_fixture()
        observation = _research_perception(_development_ocr_lines()).build(
            screenshot,
            include_content=True,
        )

        rows = observation.entries(ListEntryKind.RESEARCH)
        complete = tuple(row for row in rows if row.row_status == RowRecognitionStatus.COMPLETE)
        self.assertEqual(
            (
                "Construction I",
                "Research Speed I",
                "Storage I",
                "Troop Load I",
                "Infirmary Cap I",
            ),
            tuple(row.title_text for row in complete),
        )
        for row in complete:
            self.assertEqual("development", row.metadata["category"])
            self.assertIsNotNone(row.action_bounds)
            self.assertIsNotNone(row.action_point)
            self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
            self.assertTrue(row.action_bounds.contains_point(row.action_point))
            self.assertTrue(RESEARCH_ICON_BOXES[row.title_text].contains_point(row.action_point))
            self.assertTrue(row.bounds.contains_bounds(RESEARCH_LABEL_BOXES[row.title_text]))
            self.assertTrue(Bounds(0, 0, *screenshot.image.size).contains_bounds(row.bounds))
            self.assertEqual(screenshot.frame_ref, row.frame_ref)
            self.assertEqual(ScreenType.PNC_RESEARCH_TREE, row.source_screen)

        clipped = next(row for row in rows if row.title_text == "Miraculous Survival")
        self.assertEqual(RowRecognitionStatus.CLIPPED, clipped.row_status)
        self.assertIsNone(clipped.action_bounds)
        self.assertIsNone(clipped.action_point)

    def test_scaled_development_tree_keeps_icon_action_points_in_scaled_boxes(self) -> None:
        """Scales icon-derived action geometry with the 540x960 source fixture."""

        scale = 900 / 540
        image = _load_research_fixture().resize((900, 1600), Image.Resampling.NEAREST)
        observation = _research_perception(_development_ocr_lines(scale=scale)).build(
            _captured_research_image(image, session_id="research-observation-scaled"),
            include_content=True,
        )

        rows = {
            row.title_text: row
            for row in observation.entries(ListEntryKind.RESEARCH)
            if row.row_status == RowRecognitionStatus.COMPLETE
        }
        self.assertEqual(set(RESEARCH_ICON_BOXES), set(rows))
        for title, fixture_icon in RESEARCH_ICON_BOXES.items():
            row = rows[title]
            assert row.action_point is not None
            self.assertTrue(
                Bounds(
                    *(round(value * scale) for value in (
                        fixture_icon.x,
                        fixture_icon.y,
                        fixture_icon.width,
                        fixture_icon.height,
                    ))
                ).contains_point(row.action_point)
            )
            self.assertTrue(row.bounds.contains_bounds(row.action_bounds))
            self.assertTrue(Bounds(0, 0, 900, 1600).contains_bounds(row.bounds))

    def test_construction_ocr_repair_variant_remains_complete_with_geometry(self) -> None:
        """Keeps the reviewed Constructionl OCR repair bounded by its blue tile."""

        lines = tuple(
            _ocr_line("Constructionl", x=222, y=183, width=102, height=17)
            if line.text == "Construction"
            else line
            for line in _development_ocr_lines()
        )
        observation = _research_perception(lines).build(
            _captured_research_fixture(),
            include_content=True,
        )

        construction = tuple(
            row for row in observation.entries(ListEntryKind.RESEARCH)
            if row.title_text == "Construction I"
        )
        self.assertEqual(1, len(construction))
        self.assertEqual(RowRecognitionStatus.COMPLETE, construction[0].row_status)
        self.assertIsNotNone(construction[0].action_bounds)
        self.assertIsNotNone(construction[0].action_point)

    def test_duplicate_development_labels_are_ambiguous(self) -> None:
        """Does not expose a tap point when one reviewed label appears twice."""

        lines = (*_development_ocr_lines(), _ocr_line("Construction I", x=80, y=235, width=105, height=18))
        observation = _research_perception(lines).build(
            _captured_research_fixture(),
            include_content=True,
        )

        construction_rows = tuple(
            row for row in observation.entries(ListEntryKind.RESEARCH)
            if row.title_text == "Construction I"
        )
        self.assertEqual(2, len(construction_rows))
        self.assertTrue(all(row.row_status == RowRecognitionStatus.AMBIGUOUS for row in construction_rows))
        self.assertTrue(all(row.action_bounds is None and row.action_point is None for row in construction_rows))

    def test_missing_visible_label_geometry_is_unreadable(self) -> None:
        """OCR text cannot authorize a node tap when its blue label is absent."""

        image = _load_research_fixture()
        for box in (
            (218, 175, 326, 209),
            (218, 366, 326, 399),
            (93, 556, 201, 590),
            (343, 556, 451, 590),
            (217, 747, 326, 780),
        ):
            image.paste((15, 28, 68), box)
        frame = make_captured_frame(
            _encode_png(image),
            session_id="research-observation-missing-label",
        )
        screenshot = CapturedScreenshot(
            artifact=None,
            image=image,
            image_format="PNG",
            payload=frame.payload,
            ephemeral_captured_at=datetime.now(UTC),
            frame_ref=frame.frame_ref,
        )
        observation = _research_perception(_development_ocr_lines()).build(
            screenshot,
            include_content=True,
        )

        rows = observation.entries(ListEntryKind.RESEARCH)
        self.assertTrue(rows)
        self.assertFalse(any(row.row_status == RowRecognitionStatus.COMPLETE for row in rows))
        self.assertTrue(all(row.action_bounds is None and row.action_point is None for row in rows))

    def test_observation_builder_classifies_research_tree_from_live_like_ocr(self) -> None:
        """Recognizes the live research grid so flows can back out to home safely."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_live_research_tree",
                label="research_tree_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Troop Size I", x=229, y=340, width=90, height=20),
                            _ocr_line("March Speed", x=221, y=714, width=103, height=19),
                            _ocr_line("0/3", x=106, y=425, width=25, height=14),
                            _ocr_line("0/5", x=230, y=615, width=27, height=16),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_RESEARCH_TREE)

    def test_observation_builder_classifies_institute_overview_from_live_like_ocr(self) -> None:
        """Recognizes the live institute overview and exposes a safe back target."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_live_academy",
                label="academy_live_like",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Institute", x=108, y=12, width=115, height=29),
                            _ocr_line("Upgrade", x=404, y=263, width=88, height=25),
                            _ocr_line("Development", x=41, y=335, width=111, height=20),
                            _ocr_line("Economy", x=304, y=333, width=79, height=24),
                            _ocr_line("Military", x=38, y=412, width=67, height=24),
                            _ocr_line("Fortification", x=306, y=415, width=99, height=17),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_INSTITUTE)
            self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_INSTITUTE_DEVELOPMENT_BUTTON))
            self.assertTrue(observation.has(UiElementId.PNC_INSTITUTE_ECONOMY_BUTTON))

    def test_observation_builder_rejects_academy_title_without_upgrade_and_categories(self) -> None:
        """Keeps isolated academy-like titles unknown when the overview structure is absent."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_academy_probe",
                label="academy_near_match",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Institute", x=108, y=12, width=115, height=29),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_rejects_research_tree_header_without_grid_evidence(self) -> None:
        """Keeps isolated research-like headers unknown when the node-grid evidence is absent."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_research_tree_probe",
                label="research_tree_near_match",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Military", x=107, y=9, width=109, height=38),
                            _ocr_line("Rewards", x=220, y=300, width=100, height=24),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)

    def test_observation_builder_rejects_bottom_nav_only_non_home_screens(self) -> None:
        """Keeps bag, quest, hero, and mail OCR fixtures unknown without city-only anchors."""

        cases = (
            (
                "bag",
                (
                    _ocr_line("Inventory", x=360, y=240, width=110, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "quest",
                (
                    _ocr_line("Quest", x=360, y=240, width=92, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "hero",
                (
                    _ocr_line("Hero", x=360, y=240, width=80, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
            (
                "mail",
                (
                    _ocr_line("Mail", x=360, y=240, width=80, height=28),
                    _ocr_line("Alliance", x=48, y=1500, width=124, height=32),
                    _ocr_line("More", x=740, y=1500, width=74, height=32),
                ),
            ),
        )

        for label, lines in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_directory:
                root = Path(temp_directory)
                screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
                screenshot = screenshot_service.capture(
                    _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                    artifact_directory="k230_probe",
                    label=label,
                )
                builder = ObservationBuilder(
                    selector_registry=_minimal_runtime_registry(),
                    selector_engine=ImageSelectorEngine(
                        template_matcher=OpenCvTemplateMatcher(),

                    ),
                    screen_classifier=ScreenClassifier(),
                    enricher=PncObservationEnricher(

                    ),
            ocr_service=_FakeOcrService(
                            lines=lines,
                        )
                    )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
            self.assertFalse(observation.has(UiElementId.PNC_BOTTOM_NAV_ALLIANCE))
            self.assertFalse(observation.has(UiElementId.PNC_HOME_BUILD_BUTTON))
