"""Navigation screen disambiguation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.domain.castles import CastleIdentity, PncAccountCastleRosterConfig
from pnc_automation.app.pnc.domain.observation import ListEntryKind
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.observation_request import ObservationRequest
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    SelectorRegistry,
    build_default_selector_registry,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line


class NavigationScreenDisambiguationTests(unittest.TestCase):
    """Proves navigation screen disambiguation."""

    def test_observation_builder_strips_alliance_tag_from_lord_info_current_castle_name(self) -> None:
        """Normalizes the Lord Info castle signal so alliance tags do not break target matching."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k287_lord_info_tagged",
                label="lord_info_tagged",
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
                            _ocr_line("Lord Info", x=184, y=20, width=208, height=48),
                            _ocr_line("Gear", x=52, y=111, width=83, height=42),
                            _ocr_line("[AAS] pine cobaye 1", x=190, y=1048, width=287, height=35),
                            _ocr_line("Talent", x=68, y=1560, width=82, height=28),
                            _ocr_line("Lord Info", x=220, y=1559, width=114, height=30),
                            _ocr_line("Boost Info", x=386, y=1561, width=124, height=27),
                            _ocr_line("Alliance Info", x=561, y=1561, width=120, height=26),
                            _ocr_line("Achievements", x=731, y=1567, width=115, height=17),
                        )
                    )
                )

            observation = builder.build(screenshot)
            target_castle = CastleIdentity(kingdom="K287", castle_name="pine cobaye 1")
            roster = PncAccountCastleRosterConfig(
                pnc_account_id="user@example.com",
                castles=(target_castle,),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_LORD_INFO)
            self.assertEqual(
                observation.require(UiElementId.PNC_LORD_INFO_NAME_LABEL).extracted_text,
                "[AAS] pine cobaye 1",
            )
            self.assertEqual(observation.current_castle_name, "pine cobaye 1")
            self.assertTrue(observation.current_castle_match(target_castle, roster=roster).matches)

    def test_home_city_follow_up_classifies_full_screen_settings_separately(self) -> None:
        """Keeps full-screen Settings identifiable during home-city follow-ups from Manage Char."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k304_more_settings_follow_up",
                label="more_settings_follow_up",
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
                            _ocr_line("Settings", x=112, y=20, width=128, height=28),
                            _ocr_line("Account", x=120, y=94, width=102, height=24),
                            _ocr_line("Manage Char.", x=304, y=94, width=134, height=24),
                            _ocr_line("Search", x=122, y=188, width=88, height=24),
                            _ocr_line("Rank", x=344, y=188, width=64, height=24),
                            _ocr_line("Blacklist", x=320, y=374, width=104, height=24),
                        )
                    )
                )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.home_city_follow_up(
                    ScreenType.PNC_CASTLE_SELECTION,
                    ScreenType.PNC_SETTINGS,
                ),
            )

            self.assertEqual(observation.screen_type, ScreenType.PNC_SETTINGS)
            self.assertFalse(observation.has(UiElementId.PNC_BACK_BUTTON_TOP_LEFT))
            self.assertTrue(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_SETTINGS))

    def test_world_map_overview_exit_follow_up_classifies_manage_char_instead_of_overview(self) -> None:
        """Keeps overview-exit follow-ups on Manage Char when that screen appears unexpectedly."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="overview_exit_manage_char",
                label="overview_exit_manage_char",
            )
            builder = ObservationBuilder(
                selector_registry=build_default_selector_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),

                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(

                ),
            ocr_service=_FakeOcrService(
                        lines=(
                            _ocr_line("Manage Char.", x=304, y=94, width=134, height=24),
                            _ocr_line("K304 Kingdom", x=214, y=194, width=127, height=18),
                            _ocr_line("K304caf8305606", x=214, y=222, width=148, height=18),
                            _ocr_line("Castle Level 4", x=214, y=250, width=125, height=18),
                            _ocr_line("K230 Kingdom", x=214, y=592, width=128, height=18),
                            _ocr_line("Lv.5 Hellhound", x=214, y=620, width=139, height=19),
                            _ocr_line("Castle Level 9", x=214, y=648, width=126, height=18),
                        )
                    )
                )

            observation = builder.build(
                screenshot,
                request=ObservationRequest.world_map_overview_exit_follow_up(),
            )
            castle_entries = observation.entries(ListEntryKind.CASTLE)

            self.assertEqual(observation.screen_type, ScreenType.PNC_CASTLE_SELECTION)
            self.assertFalse(observation.has(UiElementId.PNC_WORLD_OVERVIEW_HEADER))
            self.assertEqual(len(castle_entries), 2)
            self.assertEqual(castle_entries[0].metadata["kingdom"], "K304")
            self.assertEqual(castle_entries[1].title_text, "Lv.5 Hellhound")

    def test_observation_builder_does_not_misclassify_trial_challenge_as_more_menu(self) -> None:
        """Requires distinct More-menu support text so repeated event-page Rank buttons do not spoof the overlay."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="trial_challenge_live_like",
                label="trial_challenge_live_like",
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
                            _ocr_line("Trial Challenge", x=184, y=18, width=340, height=55),
                            _ocr_line("Exchange", x=227, y=147, width=158, height=45),
                            _ocr_line("Progress", x=477, y=149, width=148, height=42),
                            _ocr_line("Total Rank", x=695, y=151, width=170, height=33),
                            _ocr_line("Hero Trial", x=252, y=282, width=172, height=34),
                            _ocr_line("Rank", x=263, y=422, width=60, height=24),
                            _ocr_line("Curio Trial", x=253, y=507, width=178, height=34),
                            _ocr_line("Rank", x=265, y=647, width=57, height=25),
                            _ocr_line("Gear Trial", x=253, y=955, width=168, height=37),
                            _ocr_line("Trial", x=716, y=1066, width=75, height=37),
                            _ocr_line("Rune Trial", x=213, y=1178, width=214, height=37),
                            _ocr_line("Rank", x=263, y=1321, width=63, height=24),
                            _ocr_line("Sauroi Trial", x=254, y=1406, width=192, height=34),
                            _ocr_line("Rank", x=263, y=1545, width=61, height=28),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_TRIAL_CHALLENGE)
            self.assertTrue(observation.has(UiElementId.PNC_TRIAL_CHALLENGE_HEADER))
            self.assertFalse(observation.has(UiElementId.PNC_MORE_MANAGE_CHAR))
