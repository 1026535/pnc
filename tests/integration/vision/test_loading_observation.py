"""Loading observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.config.models import DefaultsConfig
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.pnc.domain.action_requests import TapPointAction, WaitAction
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.vision.template.template_matcher import OpenCvTemplateMatcher

from tests.support.pnc.capture_vision.fake_ocr_service import _FakeOcrService
from tests.support.pnc.capture_vision.fake_screenshot_session import _FakeScreenshotSession
from tests.support.pnc.capture_vision.encode_png import _encode_png
from tests.support.pnc.capture_vision.ocr_line import _ocr_line
from tests.support.pnc.capture_vision.minimal_runtime_registry import _minimal_runtime_registry
from tests.support.automation.session import FakeSession
from tests.support.core.logging import build_logger
from tests.support.runtime.observation_service import FakeObservationService
from tests.support.pnc.observations import make_observation


class LoadingObservationTests(unittest.TestCase):
    """Proves loading observation."""

    def test_observation_builder_classifies_loading_reconnect_from_live_like_ocr(self) -> None:
        """Recognizes reconnect prompts as loading-state bootstrap screens."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (540, 960), (15, 28, 68)))),
                artifact_directory="k230_loading",
                label="loading_reconnect_live_like",
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
                            _ocr_line("Connecting", x=188, y=108, width=116, height=28),
                            _ocr_line("Network unstable", x=142, y=342, width=170, height=24),
                            _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
            self.assertTrue(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))

    def test_observation_builder_classifies_loading_splash_from_live_like_ocr(self) -> None:
        """Recognizes the branded game splash as a loading transition during castle switching or launch."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_loading_splash",
                label="loading_splash_live_like",
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
                            _ocr_line("CONQUEST", x=310, y=41, width=190, height=34),
                            _ocr_line("8%", x=430, y=1390, width=42, height=20),
                        )
                    )
                )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
            self.assertFalse(observation.has(UiElementId.PNC_LOADING_RECONNECT_BUTTON))

    def test_loading_builder_output_is_passive_for_recovery_and_ineligible_for_input(self) -> None:
        """Keeps production loading guards out of popup dismissal while denying input."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_loading_guarded",
                label="loading_guarded",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=_FakeOcrService(
                    lines=(_ocr_line("Loading", x=100, y=100, width=120, height=32),)
                ),
            )

            observation = builder.build(screenshot)

            self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
            self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
            self.assertFalse(observation.blocking_popup)
            self.assertFalse(observation.decision.action_eligible)

            session = FakeSession()
            registry = build_default_selector_registry()
            low_level_executor = ActionExecutor(
                session=session,
                selector_registry=registry,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            )
            observed_executor = ObservedActionExecutor(
                selector_registry=registry,
                action_executor=low_level_executor,
                logger=build_logger(),
                sleep=lambda _: None,
            )

            self.assertIsNone(
                observed_executor.recover_interruption_if_required(
                    observation,
                    label_prefix="loading_guarded",
                    observe=lambda *_args, **_kwargs: self.fail(
                        "loading recovery must not capture or dismiss a popup"
                    ),
                )
            )
            with self.assertRaises(SelectorResolutionError):
                low_level_executor.execute_action(
                    TapPointAction(x=10, y=10, reason="loading_guard"),
                    observation,
                )
            self.assertEqual([], session.taps)

    def test_loading_builder_output_settles_through_runner_without_input(self) -> None:
        """Passively waits for a production loading observation before accepting Home."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600), (15, 28, 68)))),
                artifact_directory="k230_loading_runner_settle",
                label="loading_runner_settle",
            )
            builder = ObservationBuilder(
                selector_registry=_minimal_runtime_registry(),
                selector_engine=ImageSelectorEngine(
                    template_matcher=OpenCvTemplateMatcher(),
                ),
                screen_classifier=ScreenClassifier(),
                enricher=PncObservationEnricher(),
                ocr_service=_FakeOcrService(
                    lines=(_ocr_line("Loading", x=100, y=100, width=120, height=32),)
                ),
            )
            loading = builder.build(screenshot)
            self.assertEqual(loading.screen_type, ScreenType.PNC_LOADING)
            self.assertEqual(loading.decision.guard, GuardVerdict.BLOCKED)

            session = FakeSession()
            registry = build_default_selector_registry()
            low_level_executor = ActionExecutor(
                session=session,
                selector_registry=registry,
                stable_click_delay_ms=0,
                post_action_observe_delay_ms=0,
                chat_stable_click_delay_ms=0,
                chat_post_action_observe_delay_ms=0,
                logger=build_logger(),
                sleep=lambda _: None,
            )
            observed_executor = ObservedActionExecutor(
                selector_registry=registry,
                action_executor=low_level_executor,
                logger=build_logger(),
                sleep=lambda _: None,
            )
            observer = FakeObservationService(observations=[make_observation(ScreenType.PNC_HOME_CITY)])
            flow_planner = ScreenFlowPlanner()
            planned_actions = []

            def plan_home_city(observation):
                """Records the canonical planner's loading action for this regression."""

                actions = flow_planner.ensure_home_city(observation)
                planned_actions.extend(actions)
                return actions

            runner = AutomationRunner(
                defaults=DefaultsConfig(stable_click_delay_ms=0, post_action_observe_delay_ms=0),
                observation_service=observer,
                action_executor=observed_executor,
                task_registry=TaskRegistry(tasks=()),
                flow_planner=flow_planner,
                logger=build_logger(),
            )

            settled = runner.execute_flow_until(
                label_prefix="loading_runner_settle",
                planner=plan_home_city,
                done=lambda observation: observation.screen_type == ScreenType.PNC_HOME_CITY,
                start_observation=loading,
                max_steps=1,
            )

            self.assertEqual(ScreenType.PNC_HOME_CITY, settled.screen_type)
            self.assertEqual(1, len(planned_actions))
            self.assertIsInstance(planned_actions[0], WaitAction)
            self.assertEqual(1000, planned_actions[0].milliseconds)
            self.assertEqual(["loading_runner_settle_step_0_post_action_1"], observer.labels)
            self.assertEqual([ObservationRequest.full_runtime_default()], observer.requests)
            self.assertEqual([], session.taps)
            self.assertEqual([], session.texts)
            self.assertEqual([], session.key_events)
            self.assertEqual([], session.swipes)
            self.assertEqual(0, session.launches)
