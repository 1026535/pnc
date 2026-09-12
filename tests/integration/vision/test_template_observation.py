"""Template observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    DefaultObservationEnricher,
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import (
    ClickDefinition,
    DetectionKind,
    SelectorDefinition,
    SelectorRegistry,
    SelectorStatus,
)
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession


class TemplateObservationTests(unittest.TestCase):
    """Proves template observation."""

    def test_observation_builder_classifies_home_city_from_templates(self) -> None:
        """Builds a home-city observation from synthetic template anchors."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_path = root / "screen.png"
            world_switch_template = root / "world_switch.png"
            character_panel_template = root / "character_panel.png"
            build_button_template = root / "build_button.png"

            screen = Image.new("RGBA", (30, 20), (255, 255, 255, 255))
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)).save(world_switch_template)
            Image.new("RGBA", (4, 4), (0, 255, 0, 255)).save(character_panel_template)
            Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(build_button_template)
            screen.paste(Image.open(world_switch_template), (2, 2))
            screen.paste(Image.open(character_panel_template), (10, 2))
            screen.paste(Image.open(build_button_template), (18, 2))
            screen.save(screenshot_path)

            registry = SelectorRegistry(
                selectors=(
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_WORLD_SWITCH,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=world_switch_template,
                        click=ClickDefinition(),
                    ),
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_CHARACTER_PANEL,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=character_panel_template,
                        click=ClickDefinition(),
                    ),
                    SelectorDefinition(
                        id=UiElementId.PNC_HOME_BUILD_BUTTON,
                        screens=(ScreenType.PNC_HOME_CITY,),
                        detection_kind=DetectionKind.TEMPLATE,
                        status=SelectorStatus.SCREENSHOT_SEEDED,
                        template_path=build_button_template,
                        click=ClickDefinition(),
                    ),
                )
            )

            with screenshot_path.open("rb") as handle:
                payload = handle.read()
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            captured = screenshot_service.capture(
                _FakeScreenshotSession(payload),
                artifact_directory="k230_main_castle",
                label="synthetic",
            )
            builder = ObservationBuilder(
                selector_registry=registry,
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                    ocr_service=UnavailableOcrService(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=DefaultObservationEnricher(),
            )

            observation = builder.build(captured)

            self.assertEqual(observation.screen_type, ScreenType.PNC_HOME_CITY)
            self.assertTrue(observation.has(UiElementId.PNC_HOME_WORLD_SWITCH))
            self.assertTrue(observation.has(UiElementId.PNC_HOME_CHARACTER_PANEL))
