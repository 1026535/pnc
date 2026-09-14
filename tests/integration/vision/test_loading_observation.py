"""Loading observation: verifies the named internal boundary with offline fixtures."""

from __future__ import annotations

from pnc_automation.app.pnc.vision.observation_request import ObservationRequest

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pnc_automation.core.infra.storage.artifact_store import ArtifactStore
from pnc_automation.core.infra.capture.screenshot_service import ScreenshotService
from pnc_automation.app.automation.engine.action_executor import ActionExecutor
from pnc_automation.app.automation.engine.observed_action_executor import ObservedActionExecutor
from pnc_automation.app.automation.engine.runner import AutomationRunner
from pnc_automation.app.authoring.config.models import DefaultsConfig
from pnc_automation.app.authoring.scripts.registry import TaskRegistry
from pnc_automation.app.pnc.domain.action_requests import TapPointAction, WaitAction
from pnc_automation.app.pnc.domain.observation import Observation
from pnc_automation.app.pnc.domain.screen_decision import GuardVerdict
from pnc_automation.app.pnc.navigation.screen_flows import ScreenFlowPlanner
from pnc_automation.app.pnc.enums.screen_type import ScreenType
from pnc_automation.app.pnc.enums.ui_element_id import UiElementId
from pnc_automation.app.pnc.vision.observation_builder import (
    ObservationBuilder,
    ImageSelectorEngine,
)
from pnc_automation.app.pnc.vision.ocr_region_plan import compile_guard_ocr_region_plans
from pnc_automation.core.vision.ocr.ocr_service import UnavailableOcrService
from pnc_automation.app.pnc.vision.pnc_observation_enricher import PncObservationEnricher
from pnc_automation.app.pnc.vision.screen_classifier import ScreenClassifier
from pnc_automation.app.pnc.vision.selectors import SelectorRegistry, build_default_selector_registry
from pnc_automation.core.errors import SelectorResolutionError
from pnc_automation.core.infra.capture.screenshot_service import CapturedScreenshot
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

    def test_captured_configured_game_loading_is_passive_in_both_paths(self) -> None:
        """The actual title and tools chrome establish startup without progress OCR."""
        from tests.integration.vision.test_alliance_remaining_visual_contracts import (
            _BoundedOcrService, _builder, _capture, _perception,
        )
        with Image.open("tests/data/screen_recognition/loading_variants/configured_game_launch.png") as source:
            image = source.convert("RGB")
        for size in ((540, 960), (900, 1600)):
            for path in ("builder", "navigation"):
                with self.subTest(size=size, path=path):
                    ocr = _BoundedOcrService()
                    builder = _builder(ocr)
                    capture = _capture(image.resize(size, Image.Resampling.LANCZOS), session_id=f"game-loading-{path}")
                    observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                    self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
                    self.assertEqual(observation.decision.guard, GuardVerdict.BLOCKED)
                    self.assertEqual(observation.decision.layout_id, "loading_configured_game_launch")
                    self.assertFalse(observation.decision.action_eligible)
                    self.assertFalse(observation.visible_elements)
                    self.assertLessEqual(len(ocr.calls), 1)

    def test_captured_loading_requires_both_anchors_and_yields_to_foreground_update(self) -> None:
        """A lone game logo cannot prove loading or hide a current Update popup."""
        from tests.integration.vision.test_alliance_remaining_visual_contracts import (
            _BoundedOcrService, _builder, _capture, _perception,
        )
        from tests.support.pnc.capture_vision.modal_overlay import update_modal_lines, with_update_modal
        with Image.open("tests/data/screen_recognition/loading_variants/configured_game_launch.png") as source:
            image = source.convert("RGB")
        missing = image.copy()
        ImageDraw.Draw(missing).rectangle((695, 15, 898, 95), fill=(9, 18, 33))
        for path in ("builder", "navigation"):
            for case, view, lines in (
                ("missing_anchor", missing, ()),
                ("foreground_update", with_update_modal(image), update_modal_lines(image.size)),
            ):
                with self.subTest(path=path, case=case):
                    ocr = _BoundedOcrService(lines=lines)
                    builder = _builder(ocr)
                    capture = _capture(view, session_id=f"loading-negative-{path}-{case}")
                    observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                    self.assertNotEqual(observation.screen_type, ScreenType.PNC_LOADING)
                    if case == "missing_anchor":
                        self.assertEqual(observation.screen_type, ScreenType.UNKNOWN)
                        self.assertFalse(observation.visible_elements)
                    else:
                        self.assertEqual(observation.screen_type, ScreenType.PNC_POPUP)
                        self.assertEqual(set(observation.visible_elements), {UiElementId.PNC_UPDATE_CONFIRM_BUTTON})
                    self.assertLessEqual(len(ocr.calls), 1)

    def _build_with_bounded_ocr(
        self,
        builder: ObservationBuilder,
        screenshot: CapturedScreenshot,
    ) -> Observation:
        """Build one loading fixture and verify guard diagnostics stay regional."""

        ocr_context = builder.create_ocr_context(screenshot)
        observation = builder.build(screenshot, ocr_context=ocr_context)
        diagnostics = ocr_context.read_diagnostics
        allowed_regions = {plan.bounds for plan in compile_guard_ocr_region_plans(screenshot.image.size)}
        self.assertEqual(diagnostics, ())
        self.assertTrue(all(diagnostic.region is not None for diagnostic in diagnostics))
        self.assertTrue(all(diagnostic.region in allowed_regions for diagnostic in diagnostics))
        return observation

    def test_loading_reconnect_parser_preserves_legacy_text_contract(self) -> None:
        """Parse recorded reconnect wording without claiming an independently captured layout."""

        from pnc_automation.app.pnc.vision.pnc_observation_enricher import _build_loading_additions
        additions = _build_loading_additions(
            image=Image.new("RGB", (540, 960), (15, 28, 68)),
            lines=(
                _ocr_line("Connecting", x=188, y=108, width=116, height=28),
                _ocr_line("Network unstable", x=142, y=342, width=170, height=24),
                _ocr_line("Reconnect", x=195, y=668, width=112, height=30),
            ),
        )
        self.assertEqual(additions.screen_evidence[0].screen_type, ScreenType.PNC_LOADING)
        self.assertIn(UiElementId.PNC_LOADING_RECONNECT_BUTTON, additions.visible_elements)

    def test_captured_publisher_and_black_frames_are_passive_through_both_paths(self) -> None:
        """Visual startup evidence requires no speculative title or progress OCR."""

        from tests.integration.vision.test_alliance_remaining_visual_contracts import (
            _BoundedOcrService, _builder, _capture, _perception,
        )
        with Image.open("tests/data/screen_recognition/loading_publisher_splash.png") as source:
            publisher = source.convert("RGB")
        for image in (publisher, Image.new("RGB", (900, 1600))):
            for path in ("builder", "navigation"):
                with self.subTest(path=path, size=image.size):
                    ocr = _BoundedOcrService()
                    builder = _builder(ocr)
                    capture = _capture(image, session_id=f"startup-{path}-{image.size}")
                    observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                    self.assertEqual(observation.screen_type, ScreenType.PNC_LOADING)
                    self.assertFalse(observation.decision.action_eligible)
                    self.assertFalse(observation.blocking_popup)
                    self.assertFalse(observation.visible_elements)
                    if image.getextrema() == ((0, 0), (0, 0), (0, 0)):
                        self.assertEqual(ocr.calls, [])

    def test_captured_commercial_offer_is_not_loading(self) -> None:
        """The source filename said loading; reviewed pixels show a priced hero offer."""

        from tests.integration.vision.test_alliance_remaining_visual_contracts import (
            _BoundedOcrService, _builder, _capture, _perception,
        )
        with Image.open("tests/data/screen_recognition/commercial_offer_loading_negative.png") as source:
            image = source.convert("RGB")
        for path in ("builder", "navigation"):
            with self.subTest(path=path):
                builder = _builder(_BoundedOcrService())
                capture = _capture(image, session_id=f"offer-loading-negative-{path}")
                observation = builder.build(capture) if path == "builder" else _perception(builder).build(capture)
                self.assertNotEqual(observation.screen_type, ScreenType.PNC_LOADING)
                self.assertNotEqual(observation.decision.guard, GuardVerdict.CLEAR)
                self.assertTrue(set(observation.visible_elements) <= {UiElementId.PNC_POPUP_CLOSE_BUTTON})
                self.assertNotIn(UiElementId.PNC_LOADING_RECONNECT_BUTTON, observation.visible_elements)

    def test_loading_builder_output_is_passive_for_recovery_and_ineligible_for_input(self) -> None:
        """Keeps production loading guards out of popup dismissal while denying input."""

        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            screenshot_service = ScreenshotService(artifact_store=ArtifactStore(root=root / "artifacts"))
            screenshot = screenshot_service.capture(
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600)))),
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

            observation = self._build_with_bounded_ocr(builder, screenshot)

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
                _FakeScreenshotSession(_encode_png(Image.new("RGB", (900, 1600)))),
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
            loading = self._build_with_bounded_ocr(builder, screenshot)
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
